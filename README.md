# Passingly Informed

A tiny daily sports digest for people who don't follow sports but need to make polite small talk about them.

Every morning it writes a few plain-English lines about what's happening in local and national sports — phrased so you can repeat them at the water cooler and sound like a normal, vaguely-aware person. Not a superfan. Not clueless. Just someone who's been busy but caught the gist.

It exists because following sports is a whole social currency that some of us never picked up, and "did you catch the game?" is a question that comes up whether you care or not. This is a cheat sheet for that conversation.

---

## What it actually does

Once a day it pulls **real** sports data, hands it to a small language model that's only allowed to *phrase* it (never invent), and publishes a short digest. A typical day reads like:

> - The United States beat Australia 2-0 in the World Cup yesterday.
> - The Fever are 9-6, third in the East, and Caitlin Clark's a big part of it — about 21 a game — heading to Atlanta for a 1:00 game.
> - **Your out:** "Did you catch the Fever game?"

Each digest has two parts: a few talking points, and an "out" — a single graceful question you can ask to hand the conversation back to the person who actually follows sports, so you look curious instead of lost.

---

## The one rule that makes it trustworthy

**The model phrases facts. It never makes them up.**

The data layer fetches real scores, schedules, standings, and player stats. The language model's only job is to turn those into natural sentences. If a fact wasn't fetched, it can't appear — because a confidently-stated wrong score is worse than saying nothing. Someone repeating a hallucinated result to a real fan is the one failure this whole thing is built to avoid.

So when it says "Caitlin Clark averages about 21 a game," that 21 came from a live stat feed and got rounded to how a person would actually say it — not from the model guessing.

---

## What it knows

For Indianapolis (the only city it covers right now), it tracks:

- **Pro teams** — Pacers, Fever, Colts, and Indy Eleven (soccer).
- **College** — Indiana, Purdue, Notre Dame, and Butler, across football, basketball, and baseball, plus Notre Dame hockey.
- **National championships** — the NBA Finals, Super Bowl, World Series, and Stanley Cup surface even when no local team is involved, because everyone talks about those.
- **The World Cup** — currently being hosted in the US, which is a talking point even for people who never watch soccer.
- **Trends** — a team's record and standing ("third in the East"), and local star players' stats ("Caitlin Clark is one of the top scorers in the league").

It leans local first. A national stat about a player nobody here follows gets dropped in favor of the Fever and their stars.

It only speaks up about what's actually in season — a team idle in its offseason won't show a stale line.

---

## How it's built (the short version)

- **Data:** free public sports JSON feeds (scores, standings, leaderboards).
- **Phrasing:** a small, fast language model, given the facts and strict instructions to phrase-not-invent.
- **Publishing:** generated once each morning by an automated job and served as a plain static web page. One generation a day, shared by everyone who visits — which is what keeps it essentially free to run.
- **Privacy:** no tracking, no cookies, no analytics, no accounts. It's a page that shows you the day's digest and nothing else.

It runs entirely on free hosting, off any home network, with a cost that rounds to nothing.

---

## Ask Nabu (Home Assistant)

Alongside the web page, it publishes a machine-readable `digest.json` with a speech-ready version of the day's digest. That lets a Home Assistant voice assistant read it aloud — ask "what's the sports news?" and it speaks the day's talking points through whatever satellite heard you.

(The wiring for this — and everything about running or deploying your own — lives in **SETUP.md**.)

---

## Status

Live and running for Indianapolis. The architecture is built to add more cities later — it's mostly data entry — but the digest is deliberately one-city, one-generation-a-day while it proves itself.

It's a personal project, free to use, with a tip link in the footer for anyone feeling generous. The money goes to API tokens and homelab gear, not to getting rich.
