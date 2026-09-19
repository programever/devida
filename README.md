# DeViDa

Technology news for developers, every day, in **simple English**.

Read it or listen to it here: **https://programever.github.io/devida/**

Everything is written in simple English on purpose. Short sentences, common
words, and every technical word explained the first time it appears. Iker reads
and listens in English as a second language, so simple English is the point of
this project, not a nice extra. The rules the writer follows are in `prompt.md`.

This is a small personal project. It runs on one Ubuntu box at home, once a day,
and it costs nothing to run.

---

## What one run does

1. **Reads the news.** It reads 63 news feeds from around the world. The list is
   in `feeds.txt`, one feed per line with its topic. A broken feed is skipped and
   the run carries on. Only stories from the last 24 hours are kept. Many of the
   feeds are GitHub release feeds, which only ever say "a new version is out".
   See "Where the stories come from" below.
2. **Picks the stories.** Claude keeps only the stories about **a new thing a
   developer can actually use**: a new release, a new version, a new product, a
   new package, a new model, a new feature. Everything else is dropped. See
   "Only new things" below. `STORY_COUNT` is a **maximum**, not a target, so most
   days have far fewer. No source may give more than two stories in one day. If
   Claude fails, the code falls back to a simple word score that follows the same
   rule. A story is never used twice; `out/seen.json` remembers used stories for
   45 days.
3. **Writes the content.** For each story Claude writes a plain English title and
   a longer plain English description, and keeps the address of the original
   article. The wording Claude is told to follow is in `prompt.md`, which anyone
   can edit without touching code. Each story also keeps the date it was
   published, shown under its title **on the page only**. The voice never reads
   a story's date out loud — Iker asked for that on 2026-09-16, because hearing
   a date before every story gets in the way of listening. A feed that gives no
   date simply shows no date line.
4. **Makes the sound.** All the stories are read out by edge-tts, Microsoft's
   free voice, and joined into one mp3 file for the day. The voice reads a
   little slower than normal, which is much easier to follow in a second
   language. If Microsoft fails, the day is still published, just without sound.
5. **Builds the page.** One plain HTML file holding the last 7 days.
6. **Publishes.** See "How publishing works" below.

## Topics, and the 24 hour rule

| Topic | Place | What it is |
|---|---|---|
| AI | **Main focus** | About half the day when there is enough good AI news. |
| Web | Second | Browsers, HTML, CSS, JavaScript. |
| TypeScript | Second | TypeScript, Node, Deno, Bun, and the tools around them. |
| Dev tools | The rest | Databases, cloud, build tools, editors, languages, and how real teams build software. |

**Every topic looks back exactly 24 hours.** Anything older is ignored. Iker
asked for this on 2026-09-16: only what really happened since yesterday.

Elm and mobile development were dropped on the same day.

### Know the cost of the 24 hour rule before you change anything

The official web and TypeScript blogs post only a few times a year. Measured on
2026-09-16, with a 24 hour window:

| Source | Topic | Newest post that day |
|---|---|---|
| web.dev | Web | 110 days old |
| MDN | Web | 93 days old |
| developer.chrome.com | Web | 86 days old |
| totaltypescript.com | TypeScript | 510 days old |
| Microsoft TypeScript blog | TypeScript | 69 days old |

In the same 24 hours AI gave 31 stories, web gave 0 and TypeScript gave 1.

So **most days will be AI and dev tools**. That is expected, not a bug. Iker was
shown these numbers and chose it, because he would rather see a short honest page
than read a story he already saw last week. The quiet official blogs are still in
the list so that a real release is caught on the day it happens.

Do not quietly widen the windows to make the page look fuller.

## Only new things

Iker on 2026-09-19: *"I dont like news about security, or politic, or something
like that, I want new tech, new product, new package."* And: *"5 or 10 or even 1
is not an issue. I want it must be good."*

So the page keeps only stories about a new thing somebody can use, and drops
everything else, however big the story is. The full keep and drop lists are in
the `## plan` section of `prompt.md`, where Iker can edit them without touching
code.

**Dropped, always:** money and funding news, politics and government, security
holes and hacks, opinion pieces and essays, podcasts and interviews, conference
adverts, company gossip, benchmark arguments between projects, and an old link
that somebody shared today.

Measured on 2026-09-19: of 57 stories from the feeds in 24 hours, the old rules
took 15 and the new rules took 6. Only 4 of the 34 AI stories that day were about
a new thing at all. The AI feeds, TechCrunch and The Verge above all, mostly
write about the AI *business*: who raised money, who said what, which law is
coming. That is why so much is dropped.

**A short day is the goal, not a fault.** One good story is a good day. Do not
add a rule that tops the list back up to a number.

**No source may give more than two stories in one day.** Some blogs, the
JetBrains blog above all, post about their own tools every day. Without this cap
a short day turns into one company's newsletter. `pipeline/plan.py` enforces it
in code (`cap_per_source`), and `prompt.md` asks Claude for it too.

If a day has nothing good at all, the run stops with a clear message and the page
keeps yesterday. That is correct, not a crash.

## Where the stories come from

The feed list was rebuilt on 2026-09-19, after Iker said the page should only
carry new things.

**What was added: 29 feeds that only announce new things.** Most are GitHub
release feeds (`.../releases.atom`) for tools people really use: React, Next.js,
Svelte, Vue, Tailwind, TypeScript, Deno, Bun, Biome, Rust, Go, VS Code, Neovim,
Zed, the GitHub command line tool, uv, ruff, Redis, Grafana, Polars, Docker
Compose, Ollama, vLLM and Hugging Face transformers. Plus the Rust blog, the Go
blog, the PostgreSQL news page, the Google AI blog, the Gemini blog and the
Mistral blog.

**A GitHub release feed also carries every test build**: `v3.6.0-rc.9`,
`v16.4.0-canary.36`, `nightly: ...`, `collab-staging: ...`. A busy project can
post ten of those in a day and bury the real release. `pipeline/crawl.py` drops
them (`_is_prerelease`). The filter runs **only on GitHub release feeds**,
because a company blog post may honestly be called "Gemini 3.8 preview" and that
is real news. Every pattern has its own check in `selftest.py`.

**What was removed: The Verge AI feed.** On 2026-09-19 it gave 5 stories and not
one was about a new thing: a governor, Hollywood, a flood warning, an essay.

**What was deliberately not added**, all checked on 2026-09-19:

| Feed | Why not |
|---|---|
| llama.cpp releases | Ten builds a day, named `b11046`. Pure noise. |
| NVIDIA deep learning | Nothing in 30 days. |
| helix editor | Nothing in over a year. |
| sqlite releases | Only internal branch tags, not real releases. |
| astro releases | One package of a big repo at a time, ten a month. |
| ghostty releases | Only a nightly build. |
| langchain releases | Ten small patch versions a month. |

Anthropic, Meta AI and Mistral have no working news feed at their own address;
`mistral.ai/rss.xml` does work and is used. Do not re-add a dead one without
checking it first.

**TechCrunch and Ars Technica were kept on purpose**, even though most of what
they write is AI business news that gets dropped. They are the only sources that
cover a big company's product launch, and on 2026-09-19 they gave 2 of the day's
best stories. The filter throws their noise away at no cost.

**The topic shown on the page comes from Claude, not from the feed.** A story
arrives labelled with the topic of the feed it came from, which is often wrong: a
new AI model shared on Lobsters arrives as `dev`. The topic is printed on the
page and read out loud, so Claude is asked what the story is really about and
that answer wins (`retopic` in `pipeline/plan.py`).

Result on 2026-09-19, same day, same hour: the old feeds and old rules gave 15
stories with politics, hacking and opinion in them. The new feeds and new rules
gave 10, every one about a new release, product, package or model.

## How publishing works, and why

This repository has two branches, and they are treated very differently.

**`main` holds the code.** It is only text files, so it stays small.
**`main` is always exactly one commit, and force-pushing it is allowed.** Iker
gave standing permission on 2026-09-16 and confirmed it again the same day:
"We should just always have 1 commit. It is ok." Keep it that way. Do not ask
before doing it; just run `selftest.py` first, and never squash away work that
has not been pushed anywhere else. The daily run never touches `main` — squashing
is done by hand, on purpose.

**`gh-pages` holds the web page and the sound files.** Every run builds this
branch again from nothing, as a brand new repository with a single commit, and
force-pushes it. So that branch always holds exactly one commit and only the 7
days the page shows.

The reason is size. Git normally remembers every version of every file for ever.
One mp3 a day would be about 1 GB after a year, even though the page only ever
shows a week. Rebuilding the branch from nothing means it can never grow. Iker
chose this on 2026-09-16.

Two guards in `pipeline/publish.py` protect that decision. The push is refused if
the branch name looks like a code branch (`main`, `master`, `develop`, ...), and
refused if the folder being published has no `index.html` in it. Both guards have
their own checks in `selftest.py`. So the daily run can never touch `main`.

**Old days are never deleted from this box.** They only stop being published.
`out/days/` keeps every day for ever.

## Commands

Run these in `~/devida`.

| Command | What it does |
|---|---|
| `python3 selftest.py` | 184 quick checks. No internet, no keys, no voice. |
| `./setup.sh` | Installs what the code needs. Safe to run again. |
| `./run.sh --skip-voice` | Reads the news and writes the content. No sound, no publishing. |
| `./run.sh --dry-run` | Builds everything including sound, publishes nothing. |
| `./run.sh` | The real daily run. Builds and publishes. |
| `./run.sh --publish-only` | Rebuilds the page from days already on this box. |
| add `--force` | Build the day again from scratch. |
| add `--date 2026-09-15` | Work on another day. |
| add `--stories 5` | Use fewer stories, for a quick test. |

## Settings

Everything has a safe default, so no settings file is needed. To change
something, put it in `~/alpha/.env` on the box.

| Setting | Default | What it is |
|---|---|---|
| `STORY_COUNT` | 15 | The **most** stories one day may have. It is a ceiling, not a target. A real day is usually 5 to 8, because most stories are dropped. |
| `SUMMARY_WORDS` | 130 | Roughly how long each description is. Simple English needs more words. **Iker read a full day at this setting on 2026-09-16 and said to leave it. Do not shorten it.** |
| `PAGE_DAYS` | 7 | How many days the page shows. |
| `TTS_VOICE` | `en-US-AriaNeural` | Which Microsoft voice reads the news. |
| `TTS_RATE` | `-10%` | Speed of the voice. Negative is slower. |
| `CLAUDE_MODEL` | `claude-opus-5` | Which Claude writes the content. |
| `SITE_BRANCH` | `gh-pages` | The branch the page is pushed to. |

## The daily job

The timer runs at 03:00 Vietnam time, and again at 04:00 if the first run failed.
The second run reuses the content the first run already wrote, so it is cheap.

```
mkdir -p ~/.config/systemd/user
cp ~/devida/devida.service ~/devida/devida.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now devida.timer
systemctl --user list-timers devida.timer
```

Every run writes `out/last-run.txt`. It is always exactly one line: `OK ...` or
`FAIL ...`. The full log of a day is in `out/days/<date>/run.log`.

## Things that already cost time

1. **The box clock is UTC**, 7 hours behind Vietnam. The timer file names the
   Vietnam time zone itself. Do not change it to UTC hours.
2. **The `claude` command is not found when the timer starts the run**, because
   the timer does not load the normal login settings. `run.sh` fixes this by
   adding `~/.local/bin` to the path. Do not remove that line.
3. **edge-tts can break without warning.** Microsoft does not promise this
   service to anyone. On 2026-09-16 version 7.0.2 started getting HTTP 403 and
   the fix was to install a newer version. If the sound stops working, try
   upgrading edge-tts first.
4. **A Python error is long, and only its last line says anything useful.** The
   voice code keeps the last line on purpose. Do not "fix" it back to the first.
5. **The sound file carries a stamp of the exact words it says.** Before the page
   publishes a sound it checks that stamp against the text it is about to print.
   If they disagree the sound is left off. This exists because on 2026-09-16 a
   page went out showing 15 stories and playing a leftover recording of 3.
6. **`main` is always one commit, and force-pushing it is allowed.** Iker gave
   standing permission on 2026-09-16 and confirmed it. Keep it that way. Because
   there is no history to fall back on, run `selftest.py` before every push, and
   never squash away work that exists nowhere else.
7. **A full day is about 22 minutes of sound, and that is on purpose.** Claude
   writes roughly 170 words a story, more than the 130 asked for, because the
   prompt says longer is better for simple English. Iker read and heard a full
   day at this setting on 2026-09-16 and said "Leave it. I like the current
   english". Do not shorten the descriptions, cut the story count, or speed the
   voice up to make the recording shorter. If it ever needs changing, Iker will
   say so.
8. **GitHub Pages takes a minute or two to rebuild after a push.** Checking the
   live address straight away can show the old page and look like a bug. To see
   what was really pushed, read the branch itself:
   `raw.githubusercontent.com/programever/devida/gh-pages/index.html`.
