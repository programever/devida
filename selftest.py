#!/usr/bin/env python3
"""Quick checks for the DeViDa code. No internet, no keys, no claude, no voice.

Run this before every commit. Iker's rule, 2026-09-16: every fix gets a check.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

fails = 0


def check(name: str, ok: bool, note: str = "") -> None:
    global fails
    if not ok:
        fails += 1
    print(f"{'PASS' if ok else 'FAIL'} {name}{('  ' + note) if note else ''}")


def _fake_command(rate: str = "-10%") -> list[str]:
    """The exact command line speak_part would run, without running it."""
    import subprocess as _sp

    seen: list[list[str]] = []
    real = _sp.run
    _sp.run = lambda cmd, **kw: (seen.append(cmd), real(["true"], **kw))[1]
    try:
        from pipeline import voice as _v
        try:
            _v._speak_once("hi", "en-US-AriaNeural", rate, Path(tempfile.mkdtemp()) / "x.mp3")
        except Exception:
            pass
    finally:
        _sp.run = real
    return seen[0] if seen else []


def raises(kind, fn, *args) -> bool:
    """True when calling fn(*args) fails in the way we want it to."""
    try:
        fn(*args)
        return False
    except kind:
        return True


# Keep the real ~/alpha/.env out of the checks, so results never depend on it.
os.environ["DEVIDA_ENV"] = "/nonexistent-on-purpose"

from pipeline import claude_cli, config, content, crawl, plan, publish, site, voice  # noqa: E402
from pipeline import main  # noqa: E402

cfg = config.load_config()

# ---------------------------------------------------------------- settings ---
check("the page is at full size, about 15 stories", cfg.story_count == 15,
      str(cfg.story_count))
check("the page keeps 7 days", cfg.page_days == 7, str(cfg.page_days))
check("the voice is an English voice, not a Vietnamese one",
      cfg.tts_voice.startswith("en-"), cfg.tts_voice)
check("the voice reads a little slower than normal, for a second-language ear",
      cfg.tts_rate.startswith("-"), cfg.tts_rate)
check("descriptions are long enough for simple English", cfg.summary_words >= 120,
      str(cfg.summary_words))
check("the writing model is pinned, not left to chance", cfg.claude_model == "claude-opus-5",
      cfg.claude_model)
check("the page branch is not a code branch", cfg.site_branch == "gh-pages", cfg.site_branch)
check("the repo it pushes to is the new public one",
      cfg.site_repo == "git@github.com:programever/devida.git", cfg.site_repo)
check("the page address matches the repo",
      cfg.site_url == "https://programever.github.io/devida/", cfg.site_url)
check("a bad number in the settings falls back instead of crashing",
      (os.environ.__setitem__("STORY_COUNT", "not-a-number"),
       config.load_config().story_count)[1] == 15)
os.environ.pop("STORY_COUNT", None)

check("dates are written out in full, so the voice reads them like a person",
      config.long_date(dt.date(2026, 9, 16)) == "Wednesday, 16 September 2026",
      config.long_date(dt.date(2026, 9, 16)))
check("each day gets its own folder",
      config.day_dir(dt.date(2026, 9, 16)).name == "2026-09-16")

# ------------------------------------------------------------------- feeds ---
feeds = crawl.read_feeds()
check("the feed list loads", len(feeds) >= 25, f"{len(feeds)} feeds")
check("every feed has a topic we know",
      all(f.topic in crawl.TOPICS for f in feeds))
check("every feed is a real web address",
      all(f.url.startswith("http") for f in feeds))
check("no feed is listed twice", len({f.url for f in feeds}) == len(feeds))
# Iker asked on 2026-09-16 for a hard 24 hour rule: nothing older is ever shown.
check("every topic looks back exactly 24 hours",
      all(crawl.window_hours(dt.date(2026, 9, 16), topic) == 24 for topic in crawl.TOPICS))
check("Monday is not treated differently any more",
      all(crawl.window_hours(dt.date(2026, 9, 14), topic) == 24 for topic in crawl.TOPICS))
check("Elm and mobile are gone",
      "elm" not in crawl.TOPICS and "mobile" not in crawl.TOPICS, str(crawl.TOPICS))
check("the four topics are ai, web, ts and dev",
      set(crawl.TOPICS) == {"ai", "web", "ts", "dev"}, str(crawl.TOPICS))
check("AI is weighted as the main focus", plan.TOPIC_SHARE["ai"] >= 0.5,
      str(plan.TOPIC_SHARE["ai"]))
check("web and TypeScript are weighted above dev tools",
      plan.TOPIC_SHARE["web"] == plan.TOPIC_SHARE["ts"] >= 0.15)
check("the weights add up to one", abs(sum(plan.TOPIC_SHARE.values()) - 1.0) < 1e-9,
      str(sum(plan.TOPIC_SHARE.values())))
check("every weighted topic is a real topic",
      set(plan.TOPIC_SHARE) == set(crawl.TOPICS))
check("no feed is left on a topic we dropped",
      all(f.topic in crawl.TOPICS for f in crawl.read_feeds()))
_feeds = crawl.read_feeds()
_hosts = [f.url for f in _feeds]
check("the release feeds are in the list",
      sum(1 for u in _hosts if u.endswith("releases.atom")) >= 20,
      str(sum(1 for u in _hosts if u.endswith("releases.atom"))))
check("the Verge AI feed was removed",
      not any("theverge.com" in u for u in _hosts))
check("every topic still has at least one release or blog feed",
      {f.topic for f in _feeds} == set(crawl.TOPICS))
check("the candidate list is big enough for the longer feed list",
      plan.CANDIDATE_LIMIT >= len(_feeds) * 2, str(plan.CANDIDATE_LIMIT))

check("the new dev topic really has sources",
      sum(1 for f in crawl.read_feeds() if f.topic == "dev") >= 8,
      str(sum(1 for f in crawl.read_feeds() if f.topic == "dev")))
check("html tags are stripped out of a feed title",
      crawl._clean("<b>Hello</b>  <i>world</i>") == "Hello world")
check("the same link is always the same story id",
      crawl._uid("https://a.com/x", "T") == crawl._uid("https://a.com/X", "other"))
check("two near-identical titles collapse to one key",
      crawl._title_key("OpenAI Ships GPT-9!") == crawl._title_key("openai ships gpt9"))
# Iker, 2026-09-19: GitHub release feeds were added so the page gets real new
# versions. They also carry every test build, which is not news.
_gh = crawl.Feed("dev", "https://github.com/vuejs/core/releases.atom")
_blog = crawl.Feed("ai", "https://blog.google/products/gemini/rss/")
check("a GitHub release feed is recognised", crawl._is_github_releases(_gh))
check("a company blog is not a GitHub release feed", not crawl._is_github_releases(_blog))
for _bad in ("v3.6.0-rc.9", "v16.4.0-canary.36", "nightly: install deps",
             "Nvim development (prerelease) build", "v0.30.0rc2",
             'Ghostty Tip ("Nightly")', "collab-staging: drop rustls"):
    check(f"a test build is dropped: {_bad[:38]}", crawl._is_prerelease(_bad))
for _good in ("Ktor 3.6.0 Is Now Available!", "v0.34.3", "TypeScript 7.0.2",
              "Rust 1.98.1", "svelte@5.57.1", "GitHub CLI 2.101.0", "1.138.0",
              "Bun v1.4.2", "0.12.17"):
    check(f"a real release is kept: {_good[:38]}", not crawl._is_prerelease(_good))
check("a company blog post named preview is never filtered",
      not crawl._is_github_releases(_blog))

check("a Hacker News item about models counts as AI",
      crawl._looks_like_ai("A new LLM beats the rest", ""))
check("a Hacker News item about gardening does not",
      not crawl._looks_like_ai("My tomato greenhouse", "soil and water"))
# The AI word filter used to key off the host, so a Hacker News feed added under
# any other topic would silently have been filtered for AI words too.
check("the Hacker News AI filter is tied to the topic, not the web address",
      'feed.topic == "ai"' in Path("pipeline/crawl.py").read_text(encoding="utf-8"))

# ----------------------------------------------------------------- picking ---
def _item(n: int, topic: str, title: str = "", summary: str = "tóm tắt") -> crawl.Item:
    return crawl.Item(uid=f"u{n}", topic=topic, title=title or f"Tin {n}",
                      link=f"https://e.com/{n}", source="Nguồn", summary=summary,
                      published=dt.datetime(2026, 9, 16, tzinfo=dt.timezone.utc))


many = [_item(n, t) for t in crawl.TOPICS for n in range(40)]
short = plan.shortlist(many, limit=90)
check("a huge candidate list is trimmed to fit the prompt", len(short) <= 90, str(len(short)))
check("trimming never deletes a whole topic",
      {i.topic for i in short} == set(crawl.TOPICS))
check("a short list is left alone", plan.shortlist(many[:10], limit=90) == many[:10])

# Iker, 2026-09-19: only new things. New releases, products, packages, models.
# No money news, no politics, no security holes, no opinion pieces.
_release = _item(1, "dev", "Ktor 3.6.0 Is Now Available")
_launch = _item(2, "ai", "Meta launches Muse for Mac")
_money = _item(3, "ai", "A startup raises $100M in new funding round")
_politics = _item(4, "ai", "Governor pushes a new AI bill through the senate")
_security = _item(5, "dev", "Four Linux kernel bugs let a user become root, CVE-2026-1")
_opinion = _item(6, "dev", "Why I think passkeys are the wrong idea")

check("a version number counts as a new thing", plan._new_thing_score(_release) > 0)
check("a launch counts as a new thing", plan._new_thing_score(_launch) > 0)
check("funding news is not a new thing", plan._new_thing_score(_money) <= 0)
check("politics is not a new thing", plan._new_thing_score(_politics) <= 0)
check("a security hole is not a new thing", plan._new_thing_score(_security) <= 0)
check("an opinion piece is not a new thing", plan._new_thing_score(_opinion) <= 0)

_mixed = [_release, _launch, _money, _politics, _security, _opinion]
_picked = plan._by_new_thing(_mixed, 15)
check("the backup picker keeps only the new things", len(_picked) == 2, str(len(_picked)))
check("the backup picker drops money, politics, security and opinion",
      all(i in (_release, _launch) for i in _picked))
check("a short good day is allowed, the list is never topped up",
      len(plan._by_new_thing([_money, _politics], 15)) == 0)
check("the backup picker never returns more than asked",
      len(plan._by_new_thing(_mixed, 1)) == 1)

# Iker, 2026-09-19: one company must not fill the page. JetBrains posts daily.
def _from(source: str, n: int) -> crawl.Item:
    item = _item(n, "dev", f"Tool {n} 1.0 released")
    return dataclasses.replace(item, source=source)


_lots = [_from("The JetBrains Blog", n) for n in range(4)] + [_from("Lobsters", 9)]
_capped = plan.cap_per_source(_lots)
check("no source gives more than two stories in one day", len(_capped) == 3, str(len(_capped)))
check("the cap keeps that source's best two, in order",
      [i.uid for i in _capped] == ["u0", "u1", "u9"], str([i.uid for i in _capped]))
check("a source with one story is untouched",
      len(plan.cap_per_source([_from("Lobsters", 1)])) == 1)
check("the cap ignores upper and lower case",
      len(plan.cap_per_source([_from("Lobsters", 1), _from("lobsters", 2),
                               _from("LOBSTERS", 3)])) == 2)
check("the backup picker also obeys the cap",
      len(plan._by_new_thing(_lots, 15)) == 3,
      str(len(plan._by_new_thing(_lots, 15))))

# ----------------------------------------------------------------- prompts ---
prompts = claude_cli.load_prompts()
check("both prompts are in prompt.md", set(prompts) == {"plan", "story"}, str(sorted(prompts)))
check("the plan prompt is in English", "Take **up to" in prompts["plan"])
check("the plan prompt names the four topics",
      "(ai / web / ts / dev)" in prompts["plan"])
check("the plan prompt asks only for new things",
      "a new thing a developer can actually" in prompts["plan"])
check("the plan prompt says a short day is fine",
      "with one story is a good day" in prompts["plan"])
check("the plan prompt drops money news", "funding rounds" in prompts["plan"])
check("the plan prompt drops politics", "politics and government" in prompts["plan"])
check("the plan prompt drops security holes", "security holes" in prompts["plan"])
check("the plan prompt drops opinion pieces", "opinion pieces" in prompts["plan"])
check("the plan prompt drops old news shared today",
      "not really new" in prompts["plan"])
check("the plan prompt caps one source at two stories",
      "more than two stories from the same source" in prompts["plan"])
check("the plan prompt asks for the real topic",
      "its real topic" in prompts["plan"])
check("the plan answer shape has a topic field", '"topic": "ai"' in plan.PLAN_FORMAT)

# The topic shown on the page must be what the story is about, not the feed.
_bonsai = _item(1, "dev", "Bonsai 2 27B, a smaller model")
check("claude's topic wins over the feed's topic",
      plan.retopic(_bonsai, "ai").topic == "ai")
check("a missing topic keeps the feed's topic",
      plan.retopic(_bonsai, None).topic == "dev")
check("a made-up topic keeps the feed's topic",
      plan.retopic(_bonsai, "science").topic == "dev")
check("a topic in capitals still works", plan.retopic(_bonsai, " AI ").topic == "ai")
check("the plan prompt says not to fill the list",
      "Do not fill\nthe list" in prompts["plan"])
check("the story prompt bans the repeated Watch for ending",
      'Never begin the last sentence with' in prompts["story"])
check("the story prompt bans the For a developer this matters phrase",
      "For a developer, this matters because" in prompts["story"])
check("the plan prompt mentions no dropped topic",
      "elm" not in prompts["plan"].lower() and "mobile" not in prompts["plan"].lower())
check("the story prompt demands simple English",
      "very simple English" in prompts["story"])
check("the story prompt says to explain technical words",
      "explain it in plain" in prompts["story"])
check("the story prompt tells the writer not to read links out loud",
      "Never read out a link" in prompts["story"])
filled = claude_cli.fill(prompts["story"], words="70", format="{}", topic="AI", title="T",
                         source="S", link="L", summary="Y", article="A")
check("a filled prompt has no placeholder left", "{{" not in filled)
check("a half-filled prompt is caught here, not sent to claude",
      raises(claude_cli.ClaudeError, claude_cli.fill, prompts["story"]))
check("json comes back even when claude wraps it in a code fence",
      claude_cli.extract_json('```json\n{"a": 1}\n```') == {"a": 1})
check("json comes back even with chatter around it",
      claude_cli.extract_json('Đây nhé: {"a": 2} xong.') == {"a": 2})
check("a reply with no json is an error, not a crash",
      raises(ValueError, claude_cli.extract_json, "xin chào"))

# ----------------------------------------------------------------- content ---
story = content.Story(uid="u1", topic="ai", title="A new model was released",
                      description="A lab released a new model today. It is faster than the old one.",
                      link="https://e.com/1", source="Example News", original_title="Original",
                      published="2026-09-15T22:00:00+00:00")
day = content.Day(day=dt.date(2026, 9, 16), stories=[story] * 3, built_at="2026-09-16 03:12")
check("a topic gets a short readable label", story.topic_label == "AI", story.topic_label)
check("every topic has a label", set(content.TOPIC_LABELS) == set(crawl.TOPICS),
      str(sorted(content.TOPIC_LABELS)))
check("a day saved and loaded again is the same day",
      content.day_from_dict(content.day_to_dict(day)).stories[0] == story)
parts = content.spoken_parts(day)
check("the voice gets one piece per story plus hello and goodbye",
      len(parts) == 5, f"{len(parts)} pieces for 3 stories")
check("the hello says the date and how many stories",
      "16 September 2026" in parts[0] and "3 stories" in parts[0])
check("the goodbye and hello are English, with no Vietnamese left",
      not any(ch in "ăâđêôơưàáảãạ" for ch in (parts[0] + parts[-1]).lower()))
check("each story piece is numbered for the listener",
      parts[1].startswith("Story number 1."))
check("no link is ever read out loud", not any("https://" in p for p in parts))
check("the goodbye is last", "Thank you for listening" in parts[-1])
one = content.Day(day=dt.date(2026, 9, 16), stories=[story], built_at="x")
one_parts = content.spoken_parts(one)
check("one story is announced as one story, not '1 stories'",
      "there is 1 story." in one_parts[0], one_parts[0][-30:])
check("a single story is not called 'story number 1'",
      one_parts[1].startswith("Here is the story."))
check("more workers than 4 are refused, they only time out",
      content.safe_workers(config.load_config().__class__(**{**cfg.__dict__, "claude_workers": 40})) == 4)

# ------------------------------------------------------------------- voice ---
check("the edge-tts error says the real reason, not the traceback top",
      "403" in voice._edge_reason(
          "Traceback (most recent call last):\n  File x\n"
          "aiohttp.client_exceptions.WSServerHandshakeError: 403, message='Invalid response'\n")
      and "Traceback" not in voice._edge_reason(
          "Traceback (most recent call last):\n  File x\n"
          "aiohttp.client_exceptions.WSServerHandshakeError: 403, message='Invalid response'\n"))
check("an empty edge-tts error does not crash", voice._edge_reason("") == "no error message")
check("silence is the right length", len(voice.silence(1.0)) == voice.PCM_RATE * voice.PCM_WIDTH)
_vdir = Path(tempfile.mkdtemp())
Path(_vdir, "empty.mp3").write_bytes(b"")
check("an empty file from edge-tts is refused, not used as audio",
      raises(voice.VoiceError, voice._speak_once, "xin chào", "v", "+0%", Path(_vdir, "empty.mp3")))
check("nothing to say is an error, not an empty file",
      raises(voice.VoiceError, voice.speak_day, [], _vdir, "v", "+0%", 0.5))

# On 2026-09-16 the voice failed halfway through a 15 story day. The run said
# "no audio" and published the text, but the page builder found a leftover sound
# file from an earlier 3 story test and published that instead. The page then
# showed 15 stories and played only 3. These checks stop that ever happening.
_adir = Path(tempfile.mkdtemp())
_parts = content.spoken_parts(day)
check("a sound file is stamped with the exact words it says",
      voice.fingerprint(_parts) == voice.fingerprint(list(_parts)))
check("different words give a different stamp",
      voice.fingerprint(_parts) != voice.fingerprint(_parts[:2]))
check("one changed word changes the stamp",
      voice.fingerprint(["a", "b"]) != voice.fingerprint(["a", "b "]))
check("joining the pieces differently cannot fake the same stamp",
      voice.fingerprint(["a", "b"]) != voice.fingerprint(["a\n@@\nb"]))
check("with no stamp at all, the sound is not trusted",
      not voice.audio_matches(_adir, _parts))
voice.stamp_file(_adir).write_text(voice.fingerprint(_parts), encoding="utf-8")
check("a sound file that matches the words is trusted",
      voice.audio_matches(_adir, _parts))
check("a sound file from a shorter day is refused",
      not voice.audio_matches(_adir, _parts[:2]))
Path(_adir, "audio.mp3").write_bytes(b"not really audio")
voice.drop_audio(_adir)
check("throwing away the sound removes both the file and its stamp",
      not Path(_adir, "audio.mp3").exists() and not voice.stamp_file(_adir).exists())
check("throwing away a sound that is not there does not crash",
      voice.drop_audio(_adir) is None)
# A slower rate looks like "-10%". Passed as a separate word, edge-tts reads the
# minus sign as the start of another option and refuses the whole command. That
# killed a run on 2026-09-16, and the retries then waited 150 seconds for an
# error that could never fix itself.
check("the speed is passed as one word, so a minus sign is not read as an option",
      any(a.startswith("--rate=") for a in _fake_command()), str(_fake_command()))
check("a normal speed adds no speed option at all",
      not any("--rate" in a for a in _fake_command(rate="+0%")))
check("a mistake in our own command is not retried",
      issubclass(voice.BadCommand, voice.VoiceError)
      and voice._is_bad_command("edge-tts: error: argument --rate: expected one argument"))
check("a real Microsoft problem is still retried",
      not voice._is_bad_command("aiohttp.client_exceptions.WSServerHandshakeError: 403"))
check("an empty error is not mistaken for a bad command", not voice._is_bad_command(""))
check("the voice waits longer after each failed try",
      list(voice.RETRY_WAITS) == sorted(voice.RETRY_WAITS)
      and voice.RETRY_WAITS[0] >= 5 and voice.TRIES >= 5,
      f"{voice.TRIES} tries, waits {voice.RETRY_WAITS}")

# Iker asked on 2026-09-16 for each story's own publish date to sit under its
# title on the page, and to be kept out of the voice.
check("a story's publish date is read in Vietnam time, not world time",
      config.published_on("2026-09-16T18:30:00+00:00") == "17 September 2026",
      config.published_on("2026-09-16T18:30:00+00:00"))
check("a publish time with no timezone is treated as world time",
      config.published_on("2026-09-15T09:00:00") == "15 September 2026")
check("a missing publish date gives nothing, not an error",
      config.published_on("") == "")
check("a broken publish date gives nothing, not an error",
      config.published_on("not a date") == "" and config.published_on("2026-13-45") == "")
check("the story date reads simply, with no weekday",
      story.published_label == "16 September 2026", story.published_label)
check("a story with no date at all still works",
      content.Story(uid="u", topic="ai", title="T", description="D", link="L",
                    source="S", original_title="O").published_label == "")

# -------------------------------------------------------------------- site ---
page = site.render([(day, None)], cfg.site_url)
check("the page footer counts one day as a day, not days",
      "last 1 day." in site.render([(one, None)], cfg.site_url))
check("the page is real html", page.startswith("<!doctype html>") and page.endswith("</html>\n"))
check("the page says it is English", 'lang="en"' in page)
check("the page asks search engines to stay away", 'name="robots"' in page)
check("the page works on a phone", 'name="viewport"' in page)
check("a day with no audio says so instead of showing a broken player",
      "no recording today" in page.lower() and "<audio" not in page)
page_with_audio = site.render([(day, Path("/tmp/x.mp3"))], cfg.site_url)
check("a day with audio gets a player pointing at that day's file",
      'src="audio/2026-09-16.mp3"' in page_with_audio)
check("the date sits under the title, before the description",
      page.index("class=\"when\"") > page.index("<h3>")
      and page.index("class=\"when\"") < page.index(story.description[:20]))
check("the date really is printed on the page", "16 September 2026" in page)
check("a story with no date shows no empty date line",
      "class=\"when\"" not in site.render(
          [(content.Day(day=dt.date(2026, 9, 16), built_at="x", stories=[
              content.Story(uid="u", topic="ai", title="T", description="D",
                            link="https://e.com", source="S", original_title="O")]), None)],
          cfg.site_url))
# The voice must not read dates out. Hearing a date before every story is noise,
# and the sound file's stamp depends on these exact words, so a date creeping in
# would also silently invalidate every cached recording.
_spoken = content.spoken_parts(day)
check("the voice never speaks a story's publish date",
      not any(story.published_label in p for p in _spoken[1:-1]),
      f"looking for {story.published_label!r} in the story parts")
check("the voice still says the day's own date in its hello",
      "16 September 2026" in content.spoken_parts(day)[0])
check("adding the date did not change what the voice says",
      content.spoken_parts(day) == content.spoken_parts(
          content.day_from_dict(content.day_to_dict(day))))
check("the page links out in English",
      "read the original" in page)
check("nothing Vietnamese is left anywhere on the page",
      not any(ch in page.lower() for ch in "ăâđêôơư"))
check("the story link is on the page",
      'href="https://e.com/1"' in page and 'rel="noopener noreferrer"' in page)
danger = content.Story(uid="u", topic="ai", title='<script>alert(1)</script>',
                       description='a & b <b>c</b>', link="https://e.com/?a=1&b=2",
                       source="S", original_title="O")
bad_day = content.Day(day=dt.date(2026, 9, 16), stories=[danger], built_at="x")
unsafe = site.render([(bad_day, None)], cfg.site_url)
check("a story title can never inject html into the page",
      "<script>" not in unsafe and "&lt;script&gt;" in unsafe)
check("an ampersand in a link is escaped properly", "a=1&amp;b=2" in unsafe)
check("robots.txt tells everyone to stay out", "Disallow: /" in site.ROBOTS_TXT)

# ----------------------------------------------------------------- publish ---
# These guards are the most important checks in this file. A mistake here would
# force-push over the branch that holds the code and destroy its history.
for protected in ("main", "master", "Main", "DEVELOP", "trunk"):
    check(f"force-pushing {protected!r} is refused",
          raises(publish.PublishError, publish.check_branch, protected))
check("an empty branch name is refused", raises(publish.PublishError, publish.check_branch, ""))
check("a blank branch name is refused", raises(publish.PublishError, publish.check_branch, "   "))
check("the real page branch is allowed",
      publish.check_branch("gh-pages") is None)
_empty = Path(tempfile.mkdtemp())
check("publishing a folder with no index.html is refused",
      raises(publish.PublishError, publish.check_folder, _empty))
Path(_empty, "index.html").write_text("<html></html>", encoding="utf-8")
check("a folder with a real page is allowed", publish.check_folder(_empty) is None)
check("main is in the protected list", "main" in publish.PROTECTED_BRANCHES)

# -------------------------------------------------------------------- days ---
_out = Path(tempfile.mkdtemp())
_real_days_dir = config.DAYS_DIR
try:
    config.DAYS_DIR = _out
    for d in ("2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13",
              "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"):
        folder = _out / d
        folder.mkdir()
        (folder / "content.json").write_text("{}", encoding="utf-8")
    (_out / "not-a-date").mkdir()
    (_out / "not-a-date" / "content.json").write_text("{}", encoding="utf-8")
    (_out / "2026-09-09").mkdir()   # no content.json, must be ignored
    got = config.published_days(7)
    check("the page shows the newest 7 days and no more", len(got) == 7, str(len(got)))
    check("the newest day is first", got[0] == dt.date(2026, 9, 17), str(got[0]))
    check("an older day is left off the page, not deleted",
          dt.date(2026, 9, 10) not in got and (_out / "2026-09-10").is_dir())
    check("a folder that is not a date is ignored", dt.date(2026, 9, 9) not in got)
finally:
    config.DAYS_DIR = _real_days_dir

# -------------------------------------------------------------------- main ---
_last = Path(tempfile.mkdtemp()) / "last-run.txt"
_real_last = main.LAST_RUN
try:
    main.LAST_RUN = _last
    main.write_last_run("2026-09-16 03:20 FAIL VoiceError: edge-tts failed: Traceback\n"
                        "  File x\n    boom\n")
    written = _last.read_text(encoding="utf-8")
    check("a failed run still writes only one line",
          written.count("\n") == 1 and written.endswith("\n"), f"{written.count(chr(10))} newline(s)")
    main.write_last_run("x" * 5000)
    check("a huge error does not make a huge file",
          len(_last.read_text(encoding="utf-8")) <= main.LAST_RUN_MAX_CHARS + 1)
finally:
    main.LAST_RUN = _real_last

check("a plain run publishes", main.parse_args([]).dry_run is False)
check("--dry-run publishes nothing", main.parse_args(["--dry-run"]).dry_run is True)
check("--skip-voice is understood", main.parse_args(["--skip-voice"]).skip_voice is True)
check("--publish-only is understood", main.parse_args(["--publish-only"]).publish_only is True)
check("--stories changes how many stories",
      main.tune(cfg, main.parse_args(["--stories", "4"])).story_count == 4)
check("without --stories the setting is untouched",
      main.tune(cfg, main.parse_args([])).story_count == 15)
check("a date can be given by hand",
      main.resolve_day("2026-09-15") == dt.date(2026, 9, 15))
check("no date means today in Vietnam", main.resolve_day("") == config.now_vn().date())

print()
print("FAILED:", fails if fails else "none")
sys.exit(1 if fails else 0)
