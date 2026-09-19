"""Step 4: Vietnamese speech with edge-tts, joined into one mp3 for the day.

edge-tts is Microsoft's free voice. It has no daily limit and needs no key, which
is why Iker chose it on 2026-09-16. Microsoft does not promise it to us, so it
can break without warning; when it does, the log must say why in one clear line.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

PCM_RATE = 24000
PCM_WIDTH = 2
TRIES = 5
# Microsoft answers "no audio received" when it is busy. Trying again three
# seconds later just gets the same answer, which is how a whole day lost its
# sound on 2026-09-16. Each try now waits longer than the last.
RETRY_WAITS = (5, 15, 40, 90)


class VoiceError(RuntimeError):
    pass


def _edge_binary() -> str:
    """run.sh execs .venv/bin/python directly, so .venv/bin is not on PATH."""
    beside_python = Path(sys.executable).parent / "edge-tts"
    return str(beside_python) if beside_python.exists() else "edge-tts"


def _edge_reason(stderr: str) -> str:
    """The real reason is the last line. edge-tts prints a long Python traceback,
    and the first 300 characters of it are all boilerplate. On 2026-09-16 that is
    why a log never showed that Microsoft had answered 403."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    return lines[-1][:300] if lines else "no error message"


class BadCommand(VoiceError):
    """Our own command line is wrong. Trying again would fail the same way."""


def _speak_once(text: str, voice: str, rate: str, target: Path) -> None:
    command = [_edge_binary(), "--voice", voice, "--text", text,
               "--write-media", str(target)]
    if rate and rate != "+0%":
        # Written as one word with "=". A slower rate looks like "-10%", and a
        # value that starts with a minus sign is read as another option if it is
        # passed separately. That cost a whole run on 2026-09-16.
        command.append(f"--rate={rate}")
    done = subprocess.run(command, capture_output=True, text=True, timeout=300)
    # edge-tts creates the file before it talks to Microsoft, so a failed call
    # leaves an empty file behind. An empty file is not audio.
    if done.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        reason = _edge_reason(done.stderr)
        if _is_bad_command(done.stderr):
            raise BadCommand(f"edge-tts refused our command: {reason}")
        raise VoiceError(f"edge-tts failed: {reason}")


def _is_bad_command(stderr: str) -> bool:
    """A mistake in the command we sent, not a problem at Microsoft.

    Waiting and asking again cannot fix this, so it must fail at once instead of
    burning two and a half minutes on four hopeless retries.
    """
    text = (stderr or "").lower()
    return "error: argument" in text or "error: unrecognized arguments" in text


def speak_part(text: str, voice: str, rate: str, target: Path) -> None:
    """One piece of the bulletin. Microsoft drops a connection now and then, so
    a failure is tried again, waiting longer each time, before it is called a
    real failure."""
    last: VoiceError | None = None
    for attempt in range(1, TRIES + 1):
        try:
            _speak_once(text, voice, rate, target)
            return
        except BadCommand:
            raise
        except (VoiceError, subprocess.TimeoutExpired) as err:
            last = err if isinstance(err, VoiceError) else VoiceError(f"edge-tts timed out: {err}")
            log.warning("voice: try %d of %d failed (%s)", attempt, TRIES, last)
            if attempt < TRIES:
                wait = RETRY_WAITS[min(attempt - 1, len(RETRY_WAITS) - 1)]
                log.info("voice: waiting %ds before trying again", wait)
                time.sleep(wait)
    raise last or VoiceError("edge-tts failed for an unknown reason")


def fingerprint(parts: list[str]) -> str:
    """Names exactly what a sound file says.

    The page must never play a sound that does not match the words next to it.
    On 2026-09-16 the voice failed halfway through a 15 story day, and the page
    published a leftover sound file from an earlier 3 story test. The stamp
    below is saved beside the mp3 and checked again before publishing, so a
    sound file that belongs to different words is simply left off the page.
    """
    # Each piece is written with its length in front of it. Simply gluing the
    # pieces together with a separator would let a piece that contains the
    # separator pretend to be two pieces, and two different days could then get
    # the same stamp. Writing the length first makes that impossible.
    digest = hashlib.sha1()
    digest.update(f"{len(parts)}\x00".encode("utf-8"))
    for part in parts:
        raw = part.encode("utf-8")
        digest.update(f"{len(raw)}\x00".encode("utf-8"))
        digest.update(raw)
    return digest.hexdigest()


def stamp_file(workdir: Path) -> Path:
    return workdir / "audio.sha1"


def audio_matches(workdir: Path, parts: list[str]) -> bool:
    saved = stamp_file(workdir)
    if not saved.is_file():
        return False
    return saved.read_text(encoding="utf-8").strip() == fingerprint(parts)


def _to_pcm(source: Path) -> bytes:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-"],
        capture_output=True, timeout=300,
    )
    if done.returncode != 0:
        raise VoiceError(f"ffmpeg decode failed: {done.stderr.decode()[:300]}")
    return done.stdout


def silence(seconds: float) -> bytes:
    return b"\x00" * (int(PCM_RATE * seconds) * PCM_WIDTH)


def speak_day(parts: list[str], workdir: Path, voice: str, rate: str,
              pause_seconds: float) -> Path:
    """One mp3 for the whole day. Finished pieces are cached, so a retry resumes
    where it stopped instead of speaking everything again."""
    if not parts:
        raise VoiceError("nothing to speak")
    cache = workdir / "tts"
    cache.mkdir(parents=True, exist_ok=True)

    raw = workdir / "day.pcm"
    reused = 0
    with raw.open("wb") as sink:
        for number, text in enumerate(parts, start=1):
            digest = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:10]
            piece_mp3 = cache / f"{number:03d}-{digest}.mp3"
            if piece_mp3.is_file() and piece_mp3.stat().st_size > 0:
                reused += 1
            else:
                speak_part(text, voice, rate, piece_mp3)
                log.info("voice %d/%d: %d bytes", number, len(parts), piece_mp3.stat().st_size)
            sink.write(_to_pcm(piece_mp3))
            if number < len(parts):
                sink.write(silence(pause_seconds))
    if reused:
        log.info("voice: reused %d pieces from an earlier run", reused)

    mp3 = workdir / "audio.mp3"
    encode_mp3(raw, mp3)
    raw.unlink(missing_ok=True)
    stamp_file(workdir).write_text(fingerprint(parts), encoding="utf-8")
    return mp3


def drop_audio(workdir: Path) -> None:
    """Throw away a sound file that no longer matches the words of the day."""
    (workdir / "audio.mp3").unlink(missing_ok=True)
    stamp_file(workdir).unlink(missing_ok=True)


def encode_mp3(pcm: Path, mp3: Path) -> None:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", str(pcm),
         "-codec:a", "libmp3lame", "-b:a", "64k", "-ac", "1", str(mp3)],
        capture_output=True, timeout=900,
    )
    if done.returncode != 0:
        raise VoiceError(f"ffmpeg encode failed: {done.stderr.decode()[:400]}")


def duration_seconds(mp3: Path) -> int:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)],
        capture_output=True, text=True, timeout=120,
    )
    try:
        return int(float(done.stdout.strip()))
    except ValueError:
        return 0
