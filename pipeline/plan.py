"""Step 2: pick the stories for today's episode."""
from __future__ import annotations

import dataclasses
import logging
import re

from .claude_cli import Claude, ClaudeError, fill
from .crawl import Item

log = logging.getLogger(__name__)

PLAN_FORMAT = """{
  "stories": [
    {"index": 3, "topic": "flow", "why": "one short sentence saying why this story was chosen"},
    {"index": 17, "topic": "ai", "why": "..."}
  ]
}"""

CANDIDATE_LIMIT = 140

# Iker, 2026-09-19: no more than two stories from the same source in one day.
# Some blogs, JetBrains above all, post about their own tools every single day.
# Without this cap a short day can turn into one company's newsletter. Claude is
# told the same rule in prompt.md; this is the guard in case it does not follow.
MAX_PER_SOURCE = 2
# Iker, 2026-10-21: "I very prefer to read news about AI workflow, specific about
# IT development from business idea to deployment." So "flow" (AI workflow) was
# added as a topic, and it comes first on the page.
# Iker, 2026-10-24: "I want to add AI workflow, not because of AI workflow and we
# remove other!" So there is NO limit per topic. Workflow is added on top of the
# other news, never instead of it. Do not bring back a cap per topic.
# These shares only decide how a too-long candidate list is trimmed before Claude
# sees it. They never limit what goes on the page.
TOPIC_SHARE = {"flow": 0.3, "ai": 0.4, "web": 0.1, "ts": 0.1, "dev": 0.1}


def _candidate_block(items: list[Item]) -> str:
    lines = []
    for number, item in enumerate(items, start=1):
        lines.append(
            f"{number}. [{item.topic}] {item.title}\n"
            f"   nguồn: {item.source} | {item.link}\n"
            f"   tóm tắt: {item.summary[:400] or '(không có)'}"
        )
    return "\n".join(lines)


def shortlist(items: list[Item], limit: int = CANDIDATE_LIMIT) -> list[Item]:
    """Trim to a prompt-sized list while keeping every topic represented."""
    if len(items) <= limit:
        return items
    kept = {
        topic: [i for i in items if i.topic == topic][: max(3, round(limit * share))]
        for topic, share in TOPIC_SHARE.items()
    }
    # Trim the fullest topic first, so no topic is ever cut away entirely.
    while sum(len(bucket) for bucket in kept.values()) > limit:
        fullest = max(kept, key=lambda topic: len(kept[topic]))
        if not kept[fullest]:
            break
        kept[fullest].pop()
    return [item for topic in TOPIC_SHARE for item in kept[topic]]


# Iker, 2026-09-19: the page is only for new things a developer can use. New
# releases, new products, new packages, new models, new features. Money news,
# politics, security holes and opinion pieces are not wanted, however big the
# story is. These two word lists are only used when Claude cannot answer at all.
# Claude does the real judging; see the "plan" section of prompt.md.
NEW_THING_WORDS = (
    "release", "releases", "released", "launch", "launches", "launched",
    "introducing", "introduces", "announcing", "announces", "ships", "shipped",
    "now available", "generally available", "out now", "arrives", "adds",
    "support for", "version", "v1", "v2", "v3", "beta", "alpha", "preview",
    "open source", "open-sources", "new tool", "new model", "new library",
)
NOT_WANTED_WORDS = (
    "raises", "funding", "valuation", "million", "billion", "ipo", "acquire",
    "acquires", "acquisition", "lawsuit", "sues", "court", "senate", "congress",
    "regulator", "regulation", "bill", "governor", "election", "military",
    "vulnerability", "exploit", "breach", "hacked", "hackers", "hacking",
    "malware", "scam", "phishing", "cve-", "ransomware", "attack",
    "opinion", "why i", "podcast", "interview", "panel", "conference",
    "sponsor", "webinar", "hiring", "layoffs", "fired", "steps down",
)

# Words that mark a practical piece about building software with AI. Also only
# used when Claude cannot answer. A workflow piece rarely says "release", so
# without this list the backup picker would throw every workflow story away.
WORKFLOW_WORDS = (
    "agent", "agentic", "copilot", "claude code", "cursor", "codex", "vibe cod",
    "ai-assisted", "ai assisted", "with ai", "using ai", "llm", "prompt",
    "spec", "requirements", "code review", "testing", "test suite", "ci/cd",
    "pipeline", "deploy", "production", "workflow", "how we", "how to", "guide",
    "lessons", "case study", "in practice", "codebase",
)

_VERSION = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")


def _new_thing_score(item: Item) -> int:
    """A rough guess at "is this a new thing?", used only if Claude is down."""
    text = f" {item.title.lower()} {item.summary.lower()[:300]} "
    score = sum(2 for word in NEW_THING_WORDS if word in text)
    score -= sum(3 for word in NOT_WANTED_WORDS if word in text)
    if _VERSION.search(item.title):
        score += 3
    return score


def _workflow_score(item: Item) -> int:
    """A rough guess at "is this about building software with AI?", Claude down only."""
    text = f" {item.title.lower()} {item.summary.lower()[:300]} "
    score = sum(2 for word in WORKFLOW_WORDS if word in text)
    score -= sum(3 for word in NOT_WANTED_WORDS if word in text)
    return score


def retopic(item: Item, topic) -> Item:
    """Use the topic Claude gave, if it gave a real one. Otherwise keep ours."""
    if isinstance(topic, str) and topic.strip().lower() in TOPIC_SHARE:
        return dataclasses.replace(item, topic=topic.strip().lower())
    return item


def cap_per_source(items: list[Item], limit: int = MAX_PER_SOURCE) -> list[Item]:
    """Keep at most `limit` stories from any one source, in the order given.

    The stories arrive best first, so the ones kept are that source's best.
    """
    kept: list[Item] = []
    counts: dict[str, int] = {}
    for item in items:
        key = item.source.strip().lower()
        if counts.get(key, 0) >= limit:
            continue
        counts[key] = counts.get(key, 0) + 1
        kept.append(item)
    return kept


def by_topic_order(items: list[Item]) -> list[Item]:
    """AI workflow first, then AI, then web, ts and dev. Within a topic
    the order given is kept, so Claude's best story of each topic stays first."""
    order = list(TOPIC_SHARE)
    return sorted(items, key=lambda i: order.index(i.topic) if i.topic in order else len(order))


def _by_new_thing(items: list[Item], count: int) -> list[Item]:
    """Fallback pick. Keeps only stories that still look like a new thing.

    Returning fewer than `count`, or nothing, is correct here. Iker asked on
    2026-09-19 for a short good day rather than a full weak one.
    """
    # A workflow feed's story counts if it looks like building software with AI;
    # every other story still has to look like a new thing.
    scored = [(item, _workflow_score(item) if item.topic == "flow" else _new_thing_score(item))
              for item in items]
    good = [pair for pair in scored if pair[1] > 0]
    good.sort(key=lambda pair: pair[1], reverse=True)
    picked = cap_per_source([item for item, _ in good])[:count]
    return by_topic_order(picked)


def choose(claude: Claude, prompts: dict[str, str], items: list[Item], count: int) -> list[Item]:
    candidates = shortlist(items)
    if not candidates:
        return []
    count = min(count, len(candidates))
    prompt = fill(
        prompts["plan"],
        count=str(count),
        format=PLAN_FORMAT,
        candidates=_candidate_block(candidates),
    )
    try:
        answer = claude.ask_json(prompt, label="plan")
    except (ClaudeError, AttributeError, TypeError, ValueError) as err:
        log.warning("plan: claude failed (%s), falling back to word scoring", err)
        fallback = _by_new_thing(candidates, count)
        log.info("plan: fallback picked %d of %d stories", len(fallback), len(candidates))
        return fallback

    chosen: list[Item] = []
    for entry in answer.get("stories", []):
        try:
            number = int(entry.get("index", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if not 1 <= number <= len(candidates):
            continue
        item = candidates[number - 1]
        if item in chosen:
            continue
        # The topic a story arrives with is the topic of the feed it came from,
        # which is often wrong: a new AI model shared on Lobsters arrives as
        # "dev". The topic is shown on the page and read out loud, so Claude is
        # asked what the story is really about and that answer wins.
        chosen.append(retopic(item, entry.get("topic")))
    # A short day is a good day. Iker, 2026-09-19: "5 or 10 or even 1 is not an
    # issue. I want it must be good." So however few Claude keeps, that is the
    # day. Never top the list up with stories Claude already rejected.
    log.info("plan: claude kept %d of %d stories", len(chosen), len(candidates))
    capped = cap_per_source(chosen)
    if len(capped) < len(chosen):
        log.info("plan: %d dropped so no source has more than %d stories",
                 len(chosen) - len(capped), MAX_PER_SOURCE)
    return by_topic_order(capped[:count])
