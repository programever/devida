"""One DeViDa run: read the news, write the content, speak it, publish the page."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from . import publish as publish_step
from .claude_cli import Claude, load_prompts
from .config import OUT_DIR, Config, day_dir, load_config, now_vn
from .content import Day, build_day, day_to_dict, spoken_parts
from .crawl import crawl
from .plan import choose
from .site import load_day
from .state import load_seen, save_seen
from .voice import VoiceError, drop_audio, duration_seconds, speak_day

log = logging.getLogger("devida")

LAST_RUN = OUT_DIR / "last-run.txt"
LAST_RUN_MAX_CHARS = 500


def setup_logging(logfile: Path) -> None:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(logfile, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def write_last_run(line: str) -> None:
    """Always exactly one line. A Python error can be many lines long, and the
    morning check reads this file expecting one line."""
    one_line = " ".join(line.split())[:LAST_RUN_MAX_CHARS]
    LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(one_line + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="devida", description="Build and publish one DeViDa day.")
    p.add_argument("--date", default="", help="the day, YYYY-MM-DD (default: today in VN time)")
    p.add_argument("--dry-run", action="store_true", help="build everything, publish nothing")
    p.add_argument("--force", action="store_true", help="build again even if today is done")
    p.add_argument("--skip-voice", action="store_true", help="content only, make no audio")
    p.add_argument("--stories", type=int, default=0, help="how many stories (default: from config)")
    p.add_argument("--publish-only", action="store_true",
                   help="do not build anything, just publish the days already on this box")
    return p.parse_args(argv)


def resolve_day(raw: str) -> date:
    return date.fromisoformat(raw) if raw else now_vn().date()


def tune(cfg: Config, args: argparse.Namespace) -> Config:
    import dataclasses

    return dataclasses.replace(cfg, story_count=args.stories) if args.stories else cfg


def save_day(entry: Day) -> None:
    folder = day_dir(entry.day)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content.json").write_text(
        json.dumps(day_to_dict(entry), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def build_content(cfg: Config, day: date, seen: dict[str, str]) -> Day:
    items = crawl(day, seen, cfg.http_timeout)
    if not items:
        raise RuntimeError("no fresh stories from any feed")
    claude = Claude(cfg.claude_bin, cfg.claude_model, timeout=cfg.claude_timeout)
    prompts = load_prompts()
    chosen = choose(claude, prompts, items, cfg.story_count)
    if not chosen:
        raise RuntimeError(
            "nothing today passed the rules in prompt.md: no new release, "
            "product or package in the last 24 hours"
        )
    return build_day(claude, prompts, cfg, day, chosen)


def run(args: argparse.Namespace) -> str:
    day = resolve_day(args.date)
    folder = day_dir(day)
    folder.mkdir(parents=True, exist_ok=True)
    setup_logging(folder / "run.log")
    cfg = tune(load_config(), args)

    if args.publish_only:
        log.info("publish only: building the page from the days already on this box")
        url, days = publish_step.publish(cfg, dry_run=args.dry_run)
        return f"OK (publish only) {url} {len(days)} days"

    log.info("DeViDa run for %s  dry_run=%s skip_voice=%s", day, args.dry_run, args.skip_voice)
    seen = load_seen()

    entry = None if args.force else load_day(day)
    if entry:
        log.info("reusing the content built earlier today (%d stories)", len(entry.stories))
    else:
        entry = build_content(cfg, day, seen)
        save_day(entry)
    log.info("content ready: %d stories", len(entry.stories))

    if args.skip_voice:
        return f"OK (content only, no audio) {len(entry.stories)} stories {folder/'content.json'}"

    # The audio is nice to have, not essential. Iker can always read the page, so
    # a broken Microsoft voice must not stop the day being published.
    try:
        mp3 = speak_day(spoken_parts(entry), folder, cfg.tts_voice, cfg.tts_rate,
                        cfg.tts_pause_seconds)
        seconds = duration_seconds(mp3)
        log.info("audio: %d min %02d s, %.1f MB", seconds // 60, seconds % 60,
                 mp3.stat().st_size / 1_000_000)
    except VoiceError as err:
        # Throw away any older sound file for this day. It belongs to different
        # words, and a page that reads one thing and says another is worse than
        # a page with no sound at all.
        drop_audio(folder)
        log.error("no audio today: %s", err)
        log.error("the page will still be published, with the text but no sound")
        seconds = 0

    if args.dry_run:
        url, days = publish_step.publish(cfg, dry_run=True)
        return (f"OK (dry run) {len(entry.stories)} stories "
                f"{seconds // 60}m{seconds % 60:02d}s page in {url}")

    url, days = publish_step.publish(cfg, dry_run=False)
    save_seen({**seen, **{s.uid: day.isoformat() for s in entry.stories}}, day)
    audio_note = f"{seconds // 60}m{seconds % 60:02d}s" if seconds else "NO AUDIO"
    return f"OK {url} {len(entry.stories)} stories {audio_note} {len(days)} days on the page"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        summary = run(args)
    except Exception as err:
        log.error("run failed: %s", err)
        log.debug(traceback.format_exc())
        write_last_run(f"{stamp} FAIL {type(err).__name__}: {err}")
        return 1
    write_last_run(f"{stamp} {summary}")
    log.info("done: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
