"""Step 6: put the page on GitHub Pages.

Iker decided on 2026-09-16 how this must work. The page branch is rebuilt from
nothing every day and force-pushed, so it always holds exactly one commit and
only the days the page shows. That is what keeps the repository small for ever:
it can never grow, no matter how many years this runs.

Two rules protect that decision from turning into a disaster:

  * Only the page branch is ever force-pushed. The branch that holds the code is
    normal git and keeps its full history.
  * The push is refused if the branch name looks like a code branch, or if the
    folder we are about to publish has no index.html in it.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from .config import Config
from .site import build_site

log = logging.getLogger(__name__)

# Force-pushing any of these would throw away real history.
PROTECTED_BRANCHES = {"main", "master", "trunk", "develop", "dev"}

GIT_AUTHOR = ("Alpha", "tdtrinh.web@gmail.com")


class PublishError(RuntimeError):
    pass


def _git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(
        ["git", "-c", f"user.name={GIT_AUTHOR[0]}", "-c", f"user.email={GIT_AUTHOR[1]}", *args],
        cwd=cwd, capture_output=True, text=True, timeout=600,
    )
    if done.returncode != 0:
        raise PublishError(f"git {' '.join(args[:2])} failed: {done.stderr.strip()[:300]}")
    return done.stdout.strip()


def check_branch(branch: str) -> None:
    """A guard, not a formality. A typo here would force-push over the code."""
    name = (branch or "").strip()
    if not name:
        raise PublishError("no page branch is set")
    if name.lower() in PROTECTED_BRANCHES:
        raise PublishError(
            f"refusing to force-push {name!r}: that is a code branch and its history matters"
        )


def check_folder(folder: Path) -> None:
    if not (folder / "index.html").is_file():
        raise PublishError(f"refusing to publish {folder}: it has no index.html")


def publish(cfg: Config, dry_run: bool = False) -> tuple[str, list]:
    """Build the page and force-push it. Returns the page address and its days."""
    check_branch(cfg.site_branch)

    with tempfile.TemporaryDirectory(prefix="devida-site-") as tmp:
        folder = Path(tmp)
        days = build_site(cfg, folder)
        check_folder(folder)

        size_mb = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1_000_000
        log.info("site: %.1f MB in %d files", size_mb,
                 sum(1 for f in folder.rglob("*") if f.is_file()))

        if dry_run:
            keep = Path(tempfile.mkdtemp(prefix="devida-site-kept-"))
            subprocess.run(["cp", "-r", f"{folder}/.", str(keep)], check=True, timeout=300)
            log.info("dry run: nothing pushed. The page is in %s", keep)
            return f"(dry run) {keep}", days

        # A brand new repository every time. There is no old history to inherit,
        # so the branch can only ever contain this one commit.
        _git(["init", "-q", "-b", cfg.site_branch], folder)
        _git(["add", "-A"], folder)
        _git(["commit", "-q", "-m", f"DeViDa page: {days[0].isoformat()}"], folder)
        _git(["remote", "add", "origin", cfg.site_repo], folder)
        _git(["push", "--force", "origin", cfg.site_branch], folder)
        log.info("pushed %s to %s", cfg.site_branch, cfg.site_repo)

    return cfg.site_url, days
