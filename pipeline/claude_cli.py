"""Headless `claude -p` calls: the planner and the writer both go through here."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

from .config import PROMPT_FILE

log = logging.getLogger(__name__)


class ClaudeError(RuntimeError):
    pass


def load_prompts(path: Path = PROMPT_FILE) -> dict[str, str]:
    sections: dict[str, str] = {}
    name: str | None = None
    buffer: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(\S+)\s*$", line)
        if heading:
            if name:
                sections[name] = "\n".join(buffer).strip()
            name = heading.group(1).strip().lower()
            buffer = []
        elif name:
            buffer.append(line)
    if name:
        sections[name] = "\n".join(buffer).strip()
    return sections


def fill(template: str, **values: str) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key.upper() + "}}", str(value))
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise ClaudeError(f"prompt still has unfilled placeholders: {sorted(set(left))}")
    return text


class Claude:
    def __init__(self, binary: str, model: str = "", timeout: int = 420, retries: int = 2):
        self.binary = binary
        self.model = model
        self.timeout = timeout
        self.retries = retries
        # A neutral cwd keeps the repo's CLAUDE.md (Alpha's rules) out of the prompt.
        self._workdir = Path(tempfile.mkdtemp(prefix="devida-claude-"))

    def _command(self) -> list[str]:
        """Pin the model: an unattended job must not follow the CLI's default."""
        command = [self.binary, "-p", "--output-format", "text"]
        return command + ["--model", self.model] if self.model else command

    def ask(self, prompt: str, label: str = "claude") -> str:
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            started = time.monotonic()
            try:
                done = subprocess.run(
                    self._command(),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=self._workdir,
                )
            except subprocess.TimeoutExpired as err:
                last = err
                log.warning("%s: timed out after %ss (try %d)", label, self.timeout, attempt)
                continue
            took = time.monotonic() - started
            if done.returncode != 0:
                last = ClaudeError(f"exit {done.returncode}: {done.stderr.strip()[:400]}")
                log.warning("%s: %s (try %d)", label, last, attempt)
                continue
            answer = done.stdout.strip()
            if not answer:
                last = ClaudeError("empty answer")
                log.warning("%s: empty answer (try %d)", label, attempt)
                continue
            log.info("%s: %d chars in %.0fs", label, len(answer), took)
            return answer
        raise ClaudeError(f"{label} failed after {self.retries} tries: {last}")

    def ask_json(self, prompt: str, label: str = "claude"):
        for attempt in range(1, self.retries + 1):
            answer = self.ask(prompt, label=f"{label} json#{attempt}")
            try:
                return extract_json(answer)
            except ValueError as err:
                log.warning("%s: answer was not JSON (%s)", label, err)
        raise ClaudeError(f"{label}: no valid JSON after {self.retries} tries")


def extract_json(text: str):
    body = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", body, re.S)
    if fenced:
        body = fenced.group(1).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = body.find(opener), body.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(body[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in answer: {body[:200]!r}")
