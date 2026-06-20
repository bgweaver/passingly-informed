#!/usr/bin/env python3
"""
Passingly Informed — a tiny daily sports digest for people who do not follow
sports but need to make polite, social noises about them.

Design rules (the whole point of the thing):
  - The DATA layer fetches real facts (ESPN free JSON). It never guesses.
  - The MODEL layer only PHRASES those facts. It is told, in blood, to never
    invent a score, team, date, or outcome. A fake result is worse than silence.
  - One generation per (city, date), cached in SQLite. Cost unit is city-days,
    not users. Indy-only means one real generation a day.

Usage:
  export GROQ_API_KEY=...                # required for phrasing
  python3 passingly_informed.py                     # today, Indianapolis
  python3 passingly_informed.py indianapolis --refresh
  python3 passingly_informed.py --no-llm            # just the raw facts, no Groq
  python3 passingly_informed.py --raw               # facts JSON + digest
  python3 passingly_informed.py --date 2026-06-19   # pin a date (testing)
  python3 passingly_informed.py --build ./site      # write index.html + digest.json
  python3 passingly_informed.py --selftest          # offline parser check

Deps: none. Pure Python standard library (urllib, sqlite3, json, zoneinfo).
That is deliberate — the GitHub Action needs no pip install, and there is
nothing to keep patched.
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error
import html
from datetime import datetime, date, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - fallback if tzdata missing
    EASTERN = None


def _load_dotenv(path=".env"):
    """Minimal .env loader, standard library only. Sets a variable only if it
    isn't already in the environment, so real env vars and GitHub Actions
    secrets always win over the file. Missing .env is fine (that's the CI case)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.lower().startswith("export "):
                    line = line[7:]
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


_load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _env(name, default):
    """Like os.environ.get, but an empty/whitespace value falls back to default.
    GitHub Actions expands an unset `${{ vars.X }}` to "" and exports X="", which
    would otherwise clobber a sensible default. This guards against that."""
    val = os.environ.get(name)
    return val.strip() if val and val.strip() else default


# Groq model. Groq deprecates models periodically (llama-3.3-70b-versatile was
# retired June 2026). gpt-oss-20b is fast, cheap, and plenty for phrasing a few
# facts. gpt-oss-120b is higher quality but noticeably slower. If the API 404s on
# the model, list current ones with:
#   curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
USER_AGENT = "PassinglyInformed/1.0 (+local tool)"
HTTP_TIMEOUT = 12

DEFAULT_DB = os.path.expanduser("~/.passingly_informed.sqlite")

# ---- Site build settings (edit these) -------------------------------------
# Tagline shown under the title for first-time visitors.
SITE_TAGLINE = "The day's sports, translated for people who don't follow sports."

# Tip jar. Put your Liberapay/Ko-fi URL here, or set the TIP_URL env var / GitHub
# repo variable. Left empty, the entire tip line is hidden.
TIP_URL = os.environ.get("TIP_URL", "")
# The sentence shown with the tip link. Wrap the clickable words in
# {link}...{/link}. Say it however you want.
TIP_TEXT = ("Not out to get rich here, but if you really want to {link}throw "
            "money at me{/link} I'll just spend it on tokens and homelab gear.")

# Link to the repo. Leave "" to hide.
SOURCE_URL = os.environ.get("SOURCE_URL", "")

# Email signup. Empty FORM_ENDPOINT => no live form (email is deferred).
# EMAIL_TEASER False => show nothing at all (no "coming soon" promise) until you
# have built and vetted the list. Flip to True when you want to start collecting.
FORM_ENDPOINT = os.environ.get("FORM_ENDPOINT", "")
EMAIL_TEASER = False

# City registry. Add cities by copying the Indianapolis block. `name` must match
# ESPN's team displayName exactly (that's how we filter the league scoreboard).
# `events` are marquee competitions surfaced regardless of a local team (e.g. the
# World Cup on US soil is a talking point everywhere). `context` are stable,
# verifiable, evergreen facts used only as fallback on dead sports days — never
# invented, just curated-true.
REGISTRY = {
    "indianapolis": {
        "label": "Indianapolis",
        "teams": [
            # Pro teams in town.
            {"path": "basketball/nba", "league": "NBA", "name": "Indiana Pacers"},
            {"path": "basketball/wnba", "league": "WNBA", "name": "Indiana Fever"},
            {"path": "football/nfl", "league": "NFL", "name": "Indianapolis Colts"},
            {"path": "soccer/usa.usl.1", "league": "USL Championship",
             "name": "Indy Eleven"},

            # Indiana / Hoosiers — basketball blue blood; football in the Big Ten.
            {"path": "football/college-football", "league": "College Football",
             "name": "Indiana Hoosiers"},
            {"path": "basketball/mens-college-basketball",
             "league": "NCAA Men's Basketball", "name": "Indiana Hoosiers"},
            {"path": "basketball/womens-college-basketball",
             "league": "NCAA Women's Basketball", "name": "Indiana Hoosiers"},
            {"path": "baseball/college-baseball", "league": "College Baseball",
             "name": "Indiana Hoosiers"},

            # Purdue / Boilermakers.
            {"path": "football/college-football", "league": "College Football",
             "name": "Purdue Boilermakers"},
            {"path": "basketball/mens-college-basketball",
             "league": "NCAA Men's Basketball", "name": "Purdue Boilermakers"},
            {"path": "basketball/womens-college-basketball",
             "league": "NCAA Women's Basketball", "name": "Purdue Boilermakers"},
            {"path": "baseball/college-baseball", "league": "College Baseball",
             "name": "Purdue Boilermakers"},

            # Notre Dame / Fighting Irish — football national brand; D1 hockey.
            {"path": "football/college-football", "league": "College Football",
             "name": "Notre Dame Fighting Irish"},
            {"path": "basketball/mens-college-basketball",
             "league": "NCAA Men's Basketball", "name": "Notre Dame Fighting Irish"},
            {"path": "basketball/womens-college-basketball",
             "league": "NCAA Women's Basketball", "name": "Notre Dame Fighting Irish"},
            {"path": "baseball/college-baseball", "league": "College Baseball",
             "name": "Notre Dame Fighting Irish"},
            {"path": "hockey/mens-college-hockey", "league": "College Hockey",
             "name": "Notre Dame Fighting Irish"},

            # Butler / Bulldogs — Big East basketball (football is FCS, which ESPN
            # covers unevenly, so basketball + baseball only).
            {"path": "basketball/mens-college-basketball",
             "league": "NCAA Men's Basketball", "name": "Butler Bulldogs"},
            {"path": "baseball/college-baseball", "league": "College Baseball",
             "name": "Butler Bulldogs"},
        ],
        "events": [
            {"path": "soccer/fifa.world", "league": "FIFA World Cup",
             "prefer": ("United States", "USA")},
        ],
        "context": [
            "Indianapolis hosts the Indianapolis 500 each May, billed as the "
            "largest single-day sporting event in the world; the IndyCar season "
            "runs through summer.",
            "The Indiana Fever (WNBA) draw national attention largely because of "
            "Caitlin Clark, who plays for them.",
            "Indiana is a basketball-mad state; Indiana University and Purdue both "
            "have storied men's programs and a long, fierce rivalry.",
            "Notre Dame football has a national following well beyond Indiana.",
            "Indianapolis regularly hosts marquee events like the NCAA Final Four "
            "and the NFL Scouting Combine.",
        ],
        # Adding another city is pure data entry: copy this block, swap the label,
        # set each team's `name` to ESPN's exact displayName, and verify in season
        # with `python3 passingly_informed.py --no-llm <city>`.
    },
}

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_scoreboard(path, day):
    """Fetch one league's scoreboard for one YYYYMMDD day. Returns events list.
    limit is high so a busy college slate isn't truncated before our team's game."""
    url = "%s/%s/scoreboard?dates=%s&limit=400" % (
        ESPN_BASE, path, day.strftime("%Y%m%d"))
    try:
        data = http_get_json(url)
        return data.get("events", []) or []
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        sys.stderr.write("  ! fetch failed %s %s: %s\n" % (path, day, e))
        return []

# ---------------------------------------------------------------------------
# Parsing  (pure functions — no network — so --selftest can exercise them)
# ---------------------------------------------------------------------------

def _parse_iso_to_eastern(iso_str):
    """ESPN gives e.g. '2026-06-19T23:00Z'. Return tz-aware datetime in ET."""
    s = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if EASTERN is not None:
        return dt.astimezone(EASTERN)
    return dt  # naive UTC fallback


def fmt_time(dt):
    s = dt.strftime("%I:%M %p")
    if s.startswith("0"):
        s = s[1:]
    return s + " ET"


def relative_day(game_d, today):
    delta = (game_d - today).days
    if delta == 0:
        return "today"
    if delta == -1:
        return "yesterday"
    if delta == 1:
        return "tomorrow"
    if 2 <= delta <= 6:
        return game_d.strftime("%A")
    if -6 <= delta <= -2:
        return "last " + game_d.strftime("%A")
    return game_d.strftime("%b ") + str(game_d.day)


def _competitors(event):
    comp = (event.get("competitions") or [{}])[0]
    return comp.get("competitors", []) or []


def _team_name(c):
    return (c.get("team") or {}).get("displayName", "")


def parse_team_games(events, team_name, league_label, today):
    """Phrasing-ready facts for one team: at most the most-recent result and the
    soonest upcoming game. Caps noise for teams that play most days (NBA), and
    lets weekly teams (college football) surface their next game cleanly."""
    results = []   # (datetime, fact)
    upcoming = []  # (datetime, fact)
    for ev in events:
        comps = _competitors(ev)
        if len(comps) != 2 or not any(_team_name(c) == team_name for c in comps):
            continue

        status = ((ev.get("status") or {}).get("type") or {})
        state = status.get("state")  # 'pre' | 'in' | 'post'
        try:
            edt = _parse_iso_to_eastern(ev.get("date", ""))
        except Exception:
            continue
        when = relative_day(edt.date(), today)

        us = next(c for c in comps if _team_name(c) == team_name)
        them = next(c for c in comps if _team_name(c) != team_name)
        opp = _team_name(them) or "their opponent"
        home = us.get("homeAway") == "home"

        if state == "post" and status.get("completed"):
            try:
                us_s = int(us.get("score", 0))
                them_s = int(them.get("score", 0))
            except (TypeError, ValueError):
                us_s = them_s = None
            won = bool(us.get("winner")) or (
                us_s is not None and them_s is not None and us_s > them_s)
            tie = (us_s is not None and them_s is not None and us_s == them_s
                   and not us.get("winner") and not them.get("winner"))
            score = None
            if us_s is not None and them_s is not None:
                hi, lo = (us_s, them_s) if us_s >= them_s else (them_s, us_s)
                score = "%d-%d" % (hi, lo)
            results.append((edt, {
                "kind": "result", "league": league_label, "team": team_name,
                "won": won, "tie": tie, "opponent": opp, "score": score,
                "when": when,
            }))
        elif state in ("pre", "in"):
            if when in ("today", "tonight") and edt.hour >= 17:
                when = "tonight"
            upcoming.append((edt, {
                "kind": "live" if state == "in" else "upcoming",
                "league": league_label, "team": team_name,
                "opponent": opp, "home": home, "when": when,
                "time": fmt_time(edt),
            }))

    out = []
    if results:
        out.append(max(results, key=lambda x: x[0])[1])   # most recent result
    if upcoming:
        out.append(min(upcoming, key=lambda x: x[0])[1])   # soonest upcoming
    return out


def parse_event_matches(events, event_label, today, prefer=()):
    """Surface marquee-competition matches (e.g. World Cup). Only keep matches
    with a hook for this reader (a `prefer` team, e.g. USA). For a non-fan, a
    random foreign group-stage result is noise -- if there's no preferred match
    but the tournament is active, emit a single 'underway' signal instead."""
    preferred = []
    any_activity = False
    for ev in events:
        comps = _competitors(ev)
        if len(comps) != 2:
            continue
        try:
            edt = _parse_iso_to_eastern(ev.get("date", ""))
        except Exception:
            continue
        any_activity = True
        status = ((ev.get("status") or {}).get("type") or {})
        state = status.get("state")
        a, b = _team_name(comps[0]), _team_name(comps[1])
        when = relative_day(edt.date(), today)

        if state == "post" and status.get("completed"):
            try:
                sa = int(comps[0].get("score", 0))
                sb = int(comps[1].get("score", 0))
                if sa == sb:
                    detail = "%s and %s drew %d-%d" % (a, b, sa, sb)
                elif sa > sb:
                    detail = "%s beat %s %d-%d" % (a, b, sa, sb)
                else:
                    detail = "%s beat %s %d-%d" % (b, a, sb, sa)
            except (TypeError, ValueError):
                detail = "%s vs %s" % (a, b)
            rec = {"kind": "event_result", "event": event_label,
                   "detail": detail, "when": when}
        else:
            rec = {"kind": "event_upcoming", "event": event_label,
                   "detail": "%s vs %s" % (a, b), "when": when,
                   "time": fmt_time(edt)}

        if any(p in a or p in b for p in prefer):
            preferred.append(rec)

    out = preferred[:2]
    if not out and any_activity:
        out = [{"kind": "event_active", "event": event_label}]
    return out

# ---------------------------------------------------------------------------
# Build the day's facts for a city
# ---------------------------------------------------------------------------

def build_facts(entry, today, offline_events=None):
    """Fetch each unique league ONCE over a short window, then parse per team.
    Many teams share a league (four colleges all play basketball), so fetching
    per unique path instead of per team avoids hammering the same endpoint.
    offline_events: optional {path: events} to bypass the network (selftest)."""
    # yesterday catches last night's result; +3 catches the upcoming weekend for
    # weekly sports like college football without flooding daily sports.
    window = [today + timedelta(days=d) for d in (-1, 0, 1, 2, 3)]

    paths = []
    for t in entry["teams"]:
        if t["path"] not in paths:
            paths.append(t["path"])
    for e in entry.get("events", []):
        if e["path"] not in paths:
            paths.append(e["path"])

    if offline_events is not None:
        events_by_path = {p: offline_events.get(p, []) for p in paths}
    else:
        events_by_path = {}
        for p in paths:
            evs = []
            for d in window:
                evs.extend(fetch_scoreboard(p, d))
            events_by_path[p] = evs

    facts = []
    for t in entry["teams"]:
        facts.extend(parse_team_games(
            events_by_path.get(t["path"], []), t["name"], t["league"], today))
    for e in entry.get("events", []):
        facts.extend(parse_event_matches(
            events_by_path.get(e["path"], []), e["league"], today,
            prefer=e.get("prefer", ())))

    # De-dupe identical facts (defensive).
    seen, deduped = set(), []
    for f in facts:
        key = json.dumps(f, sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped

# ---------------------------------------------------------------------------
# Phrasing (Groq)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You write 'Passingly Informed,' a tiny daily sports digest for a smart, "
    "busy adult who does NOT follow sports but needs to make polite small talk "
    "about them. The reader wants to sound like a normal, vaguely-aware person "
    "at the water cooler -- not a superfan, not clueless, and never someone "
    "trying too hard.\n\n"
    "You are given JSON with `live_facts` (real, already-verified results and "
    "schedules), `context` (true background you MAY weave in to place a team for "
    "someone who has no idea who they are), and the city.\n\n"
    "HARD RULES -- breaking any of these defeats the entire tool:\n"
    "- Use ONLY the given facts and context. NEVER invent or guess a score, "
    "team, player, date, time, or outcome. If it is not provided, it does not "
    "exist.\n"
    "- NEVER comment on, question, or express confusion about the data itself "
    "(no 'not sure how that score works', no 'odd result'). State things plainly "
    "and confidently, or leave them out. The reader repeats your words verbatim; "
    "any hedging makes THEM look foolish.\n"
    "- No predictions, no opinions, no tactics, no stats. The reader cannot "
    "defend any of it.\n\n"
    "HOW TO WRITE THE LINES:\n"
    "- ONE distinct topic per line. Never spend two lines on the same team or "
    "event. If a team has both a recent result and an upcoming game, that is "
    "still ONE line (e.g. 'lost to Atlanta last night, rematch today'). Fold any "
    "background -- a star player, why a team matters -- INTO that team's single "
    "line, never as its own line.\n"
    "- Every question must hand the floor to the OTHER person -- the one who "
    "actually follows sports. Good: 'Did you catch the Fever game?' / 'Are they "
    "usually better than that?' / 'Worth watching this year?' These let the fan "
    "do the talking while the reader just listens and nods.\n"
    "- NEVER ask the reader to predict, judge, or analyze ('do you think they'll "
    "turn it around?', 'what should they change?'). Those questions bounce "
    "straight back and expose the reader as having no idea.\n"
    "- Do NOT make every line a question. Across the lines as a whole, mix flat "
    "statements the reader can just say out loud ('The Fever dropped a close one "
    "to Atlanta last night') with one or two handoff questions -- but never "
    "cover the same topic twice to do it.\n"
    "- Use `context` only to enrich a line (e.g. that the Fever are Caitlin "
    "Clark's team), and only context you were actually given.\n\n"
    "THE WORLD CUP, IF PRESENT: the real talking point is that it is being "
    "hosted in the US right now -- a genuinely big deal even for people who "
    "never watch soccer. Lead with that framing; a US match is the specific "
    "hook. Never raise a foreign match that has no hook for this reader.\n\n"
    "VOICE: dry, competent, lightly warm. No exclamation points, no 'actually', "
    "no filler, no scripted-sounding bits. A real person who has just been busy, "
    "not a brochure.\n\n"
    "OUTPUT:\n"
    "- 2 to 4 short lines, each starting with '* ', each on a DIFFERENT topic. "
    "Prefer fewer strong lines over padding -- if there are only two real topics "
    "today, write two. Never repeat a topic to reach a number.\n"
    "- Then ONE final line starting 'Escape hatch: ' -- a short, graceful way to "
    "hand the floor back (e.g. \"I haven't kept up this year, what'd I miss?\"). "
    "One sentence.\n"
    "- Plain text only. No headers, no markdown bold, no preamble, no sign-off.\n"
    "- If `live_facts` are thin, say so honestly in one line and lean on "
    "context. Do not pad."
)


def phrase_with_groq(facts, city_label, date_label, context_lines):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")

    user_payload = {
        "city": city_label,
        "date": date_label,
        "live_facts": facts,
        "context": context_lines,
    }
    req_body = {
        "model": GROQ_MODEL,
        "temperature": 0.6,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, indent=2)},
        ],
    }
    # gpt-oss are reasoning models; without this they burn the whole token
    # budget "thinking" about a trivial phrasing task and return empty content.
    # This task needs no reasoning, so keep it minimal. (Param is gpt-oss only.)
    if "gpt-oss" in GROQ_MODEL:
        req_body["reasoning_effort"] = "low"
    body = json.dumps(req_body).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT * 4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Surface what Groq actually said instead of a bare status code. A 404
        # here almost always means GROQ_MODEL was deprecated -- Groq's body names
        # the model and the replacement.
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        hint = ""
        if e.code == 404 or "model" in detail.lower():
            hint = ("\nLikely a deprecated/unknown model. Set GROQ_MODEL to a "
                    "current one (e.g. openai/gpt-oss-20b). List yours:\n"
                    "  curl -H \"Authorization: Bearer $GROQ_API_KEY\" "
                    "https://api.groq.com/openai/v1/models")
        raise RuntimeError("Groq API error %s using model '%s': %s%s"
                           % (e.code, GROQ_MODEL, detail.strip(), hint))

    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    if not content:
        fr = choice.get("finish_reason")
        raise RuntimeError(
            "Groq returned an empty digest (finish_reason=%s, model=%s). If this "
            "is a reasoning model that ran out of room, lower reasoning_effort or "
            "switch to GROQ_MODEL=openai/gpt-oss-20b." % (fr, GROQ_MODEL))
    return content

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def db_connect(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS digests ("
        " city TEXT, date TEXT, facts TEXT, digest TEXT, generated_at TEXT,"
        " PRIMARY KEY (city, date))")
    return conn


def get_cached(conn, city, day):
    row = conn.execute(
        "SELECT facts, digest FROM digests WHERE city=? AND date=?",
        (city, day.isoformat())).fetchone()
    return row  # (facts_json, digest) or None


def save_cache(conn, city, day, facts, digest):
    conn.execute(
        "INSERT OR REPLACE INTO digests VALUES (?,?,?,?,?)",
        (city, day.isoformat(), json.dumps(facts), digest,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def header(city_label, day):
    title = "Passingly Informed -- %s . %s" % (
        city_label, day.strftime("%a %b ") + str(day.day))
    return title + "\n" + ("-" * len(title))


def facts_to_text(facts):
    """Readable dump of raw facts for --no-llm / --raw (no Groq involved)."""
    if not facts:
        return "(no live games found in the window)"
    lines = []
    for f in facts:
        k = f["kind"]
        if k == "result":
            r = "tied" if f.get("tie") else ("won" if f["won"] else "lost")
            vs = "with" if f.get("tie") else "vs"
            s = (" " + f["score"]) if f.get("score") else ""
            lines.append("* %s %s %s %s%s (%s)" % (
                f["team"], r, vs, f["opponent"], s, f["when"]))
        elif k in ("upcoming", "live"):
            vs = "hosts" if f.get("home") else "plays"
            tag = "LIVE now" if k == "live" else "%s %s" % (f["when"], f.get("time", ""))
            lines.append("* %s %s %s -- %s" % (f["team"], vs, f["opponent"], tag.strip()))
        elif k == "event_result":
            lines.append("* %s: %s (%s)" % (f["event"], f["detail"], f["when"]))
        elif k == "event_upcoming":
            lines.append("* %s: %s -- %s %s" % (
                f["event"], f["detail"], f["when"], f.get("time", "")))
        elif k == "event_active":
            lines.append("* %s is underway" % f["event"])
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Static site build  (digest.json + baked index.html for GitHub/Cloudflare)
# ---------------------------------------------------------------------------

def split_digest(text):
    """Parse the model's plain-text output into (lines, escape_hatch)."""
    lines, hatch = [], ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.lower().startswith("escape hatch:"):
            hatch = s.split(":", 1)[1].strip()
        elif s.startswith("* "):
            lines.append(s[2:].strip())
        elif s.startswith("*"):
            lines.append(s[1:].strip())
    return lines, hatch


def to_speech(lines, hatch, city, date_label):
    """A TTS-friendly paragraph so Home Assistant doesn't read 'asterisk' aloud."""
    body = " ".join(lines) if lines else "It's a quiet sports day, not much to report."
    out = "Here's the sports talk for %s, %s. %s" % (city, date_label, body)
    if hatch:
        out += " And if it gets away from you, your out is: %s" % hatch
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Passingly Informed — {{CITY}}</title>
<meta name="description" content="{{TAGLINE}}">
<style>
  :root{
    --base:#1e1e2e; --mantle:#181825; --crust:#11111b;
    --surface0:#313244; --surface1:#45475a;
    --text:#cdd6f4; --subtext1:#bac2de; --subtext0:#a6adc8; --overlay0:#6c7086;
    --mauve:#cba6f7; --peach:#fab387; --green:#a6e3a1;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:ui-monospace,"JetBrainsMono Nerd Font","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    background:var(--base); color:var(--text); font-family:var(--sans);
    line-height:1.6; padding:clamp(16px,5vw,48px);
    display:flex; justify-content:center;
  }
  main{width:100%; max-width:620px}
  .card{
    background:var(--mantle); border:1px solid var(--surface0);
    border-radius:14px; padding:clamp(20px,5vw,36px);
    box-shadow:0 18px 50px -20px rgba(0,0,0,.6);
    animation:rise .5s ease both;
  }
  @keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @media (prefers-reduced-motion:reduce){.card{animation:none}}
  .eyebrow{
    font-family:var(--mono); font-size:.72rem; letter-spacing:.18em;
    text-transform:uppercase; color:var(--mauve); margin:0;
  }
  h1{font-size:1.05rem; font-weight:600; margin:.55rem 0 .15rem; letter-spacing:.01em}
  .meta{font-family:var(--mono); font-size:.8rem; color:var(--subtext0); margin:0}
  .tagline{color:var(--subtext1); font-size:.95rem; margin:.9rem 0 0}
  hr{border:0; border-top:1px solid var(--surface0); margin:1.4rem 0}
  ul.digest{list-style:none; margin:0; padding:0; display:grid; gap:1rem}
  ul.digest li{
    position:relative; padding-left:1.4rem; color:var(--text); font-size:1.02rem;
  }
  ul.digest li::before{
    content:"›"; position:absolute; left:.1rem; top:-.02rem;
    color:var(--mauve); font-family:var(--mono); font-weight:700;
  }
  .out{
    margin-top:1.6rem; border:1px dashed var(--surface1); border-radius:10px;
    padding:.9rem 1rem 1rem; background:var(--crust);
  }
  .out .eyebrow{color:var(--peach)}
  .out p{margin:.4rem 0 0; font-style:italic; color:var(--subtext1)}
  .signup{margin-top:1.8rem}
  .signup .row{display:flex; gap:.5rem; margin-top:.5rem; flex-wrap:wrap}
  .signup input{
    flex:1 1 200px; min-width:0; background:var(--base); color:var(--text);
    border:1px solid var(--surface1); border-radius:8px; padding:.6rem .7rem;
    font-size:.95rem; font-family:var(--sans);
  }
  .signup input:focus-visible{outline:2px solid var(--mauve); outline-offset:1px}
  .signup button{
    background:var(--mauve); color:var(--crust); border:0; border-radius:8px;
    padding:.6rem 1rem; font-weight:600; font-size:.95rem; cursor:pointer;
  }
  .signup button:hover{filter:brightness(1.07)}
  .signup button:focus-visible{outline:2px solid var(--text); outline-offset:2px}
  .fineprint{font-size:.78rem; color:var(--overlay0); margin:.55rem 0 0}
  .soon{margin-top:1.8rem; color:var(--overlay0)}
  footer{
    margin-top:1.4rem; font-family:var(--mono); font-size:.74rem;
    color:var(--overlay0); text-align:center; line-height:1.9;
  }
  footer a{color:var(--subtext0); text-decoration:none; border-bottom:1px solid var(--surface1)}
  footer a:hover{color:var(--mauve)}
  footer .sep{opacity:.4; padding:0 .4rem}
</style>
</head>
<body>
<main>
  <div class="card">
    <p class="eyebrow">Passingly Informed</p>
    <h1>{{CITY}}</h1>
    <p class="meta">{{DATE_LABEL}}</p>
    <p class="tagline">{{TAGLINE}}</p>
    <hr>
    <ul class="digest">
{{ITEMS}}
    </ul>
{{HATCH_BLOCK}}
{{FORM_BLOCK}}
  </div>
  <footer>{{FOOTER}}</footer>
</main>
</body>
</html>
"""

HATCH_BLOCK = (
    '    <div class="out">\n'
    '      <p class="eyebrow">Your out</p>\n'
    '      <p>{{HATCH}}</p>\n'
    '    </div>'
)

FORM_BLOCK = (
    '    <form class="signup" method="POST" action="{{ENDPOINT}}">\n'
    '      <p class="eyebrow"><label for="email">Get it each morning</label></p>\n'
    '      <div class="row">\n'
    '        <input id="email" name="email" type="email" required\n'
    '               placeholder="you@example.com" autocomplete="email">\n'
    '        <button type="submit">Notify me</button>\n'
    '      </div>\n'
    '      <p class="fineprint">One email a day. Unsubscribe anytime. '
    'Your address is used for nothing else.</p>\n'
    '    </form>'
)

SOON_BLOCK = '    <p class="soon eyebrow">Email signups coming soon</p>'


def render_html(payload):
    items = "\n".join(
        "      <li>%s</li>" % html.escape(l) for l in payload["lines"]
    ) or '      <li>Quiet sports day — nothing worth faking yet.</li>'

    hatch_block = ""
    if payload.get("escape_hatch"):
        hatch_block = HATCH_BLOCK.replace("{{HATCH}}", html.escape(payload["escape_hatch"]))

    if FORM_ENDPOINT:
        form_block = FORM_BLOCK.replace("{{ENDPOINT}}", html.escape(FORM_ENDPOINT))
    elif EMAIL_TEASER:
        form_block = SOON_BLOCK
    else:
        form_block = ""

    foot = "Generated once a day by a robot. No tracking, no cookies, no analytics."
    extra = []
    if TIP_URL:
        tip = html.escape(TIP_TEXT)  # braces in {link}/{/link} survive escaping
        tip = tip.replace("{link}", '<a href="%s">' % html.escape(TIP_URL))
        tip = tip.replace("{/link}", "</a>")
        extra.append(tip)
    if SOURCE_URL:
        extra.append('<a href="%s">source</a>' % html.escape(SOURCE_URL))
    footer = foot
    if extra:
        footer += "<br>" + "<br>".join(extra)

    out = HTML_TEMPLATE
    for k, v in {
        "{{CITY}}": html.escape(payload["city"]),
        "{{DATE_LABEL}}": html.escape(payload["date_label"]),
        "{{TAGLINE}}": html.escape(SITE_TAGLINE),
        "{{ITEMS}}": items,
        "{{HATCH_BLOCK}}": hatch_block,
        "{{FORM_BLOCK}}": form_block,
        "{{FOOTER}}": footer,
    }.items():
        out = out.replace(k, v)
    return out


def build_site(out_dir, city_key, today, db_path=DEFAULT_DB, refresh=False):
    """Write digest.json + index.html into out_dir. Reuses today's cached digest
    if one exists (so re-running --build, or building after a normal run, costs no
    tokens); generates fresh on a cache miss or with refresh=True. The once-a-day
    cron lands on a miss each morning, which is the one real generation per day."""
    if city_key not in REGISTRY:
        raise SystemExit("Unknown city '%s'" % city_key)
    entry = REGISTRY[city_key]
    date_label = today.strftime("%A, %B ") + str(today.day)

    conn = db_connect(db_path)
    cached = get_cached(conn, city_key, today)
    if cached and cached[1] and not refresh:
        digest_text = cached[1]
        facts = json.loads(cached[0]) if cached[0] else []
    else:
        if not os.environ.get("GROQ_API_KEY"):
            raise SystemExit("GROQ_API_KEY required to generate a new digest")
        facts = build_facts(entry, today)
        digest_text = phrase_with_groq(
            facts, entry["label"], date_label, entry.get("context", []))
        save_cache(conn, city_key, today, facts, digest_text)

    lines, hatch = split_digest(digest_text)

    payload = {
        "city": entry["label"],
        "date": today.isoformat(),
        "date_label": date_label,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lines": lines,
        "escape_hatch": hatch,
        "display": digest_text,
        "speech": to_speech(lines, hatch, entry["label"], date_label),
    }

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "digest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_html(payload))
    return payload


# ---------------------------------------------------------------------------
# Self test (offline; proves parsing without network or Groq)
# ---------------------------------------------------------------------------

def selftest():
    today = date(2026, 6, 19)

    wnba = [{
        "date": "2026-06-19T01:00Z",  # ~9pm ET on the 18th -> "yesterday"
        "status": {"type": {"state": "post", "completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "88", "winner": True,
             "team": {"displayName": "Indiana Fever"}},
            {"homeAway": "away", "score": "81", "winner": False,
             "team": {"displayName": "Chicago Sky"}},
        ]}],
    }]
    nba = [{
        "date": "2026-06-20T23:30Z",  # tomorrow, evening
        "status": {"type": {"state": "pre"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "0",
             "team": {"displayName": "Indiana Pacers"}},
            {"homeAway": "away", "score": "0",
             "team": {"displayName": "Boston Celtics"}},
        ]}],
    }]
    wc = [{
        "date": "2026-06-19T23:00Z",  # today
        "status": {"type": {"state": "pre"}},
        "competitions": [{"competitors": [
            {"team": {"displayName": "United States"}, "score": "0"},
            {"team": {"displayName": "Mexico"}, "score": "0"},
        ]}],
    }]

    fever = parse_team_games(wnba, "Indiana Fever", "WNBA", today)
    assert fever and fever[0]["won"] is True and fever[0]["score"] == "88-81", fever
    assert fever[0]["when"] == "yesterday", fever

    pacers = parse_team_games(nba, "Indiana Pacers", "NBA", today)
    assert pacers and pacers[0]["kind"] == "upcoming", pacers
    assert pacers[0]["opponent"] == "Boston Celtics" and pacers[0]["home"] is True

    matches = parse_event_matches(wc, "FIFA World Cup", today, prefer=("United States",))
    assert matches and "United States" in matches[0]["detail"], matches
    assert matches[0]["when"] == "today", matches

    # Draw must read as a draw, never "X beat Y 1-1".
    draw_ev = [{
        "date": "2026-06-18T19:00Z",
        "status": {"type": {"state": "post", "completed": True}},
        "competitions": [{"competitors": [
            {"team": {"displayName": "Czechia"}, "score": "1"},
            {"team": {"displayName": "South Africa"}, "score": "1"},
        ]}],
    }]
    drew = parse_event_matches(draw_ev, "FIFA World Cup", today, prefer=("Czechia",))
    assert drew and "drew" in drew[0]["detail"] and "beat" not in drew[0]["detail"], drew

    # No preferred hook -> single 'underway' signal, not irrelevant filler.
    noise = parse_event_matches(draw_ev, "FIFA World Cup", today, prefer=("Brazil",))
    assert noise and noise[0]["kind"] == "event_active", noise

    assert relative_day(today, today) == "today"
    assert relative_day(today - timedelta(days=1), today) == "yesterday"
    assert relative_day(today + timedelta(days=1), today) == "tomorrow"

    entry = REGISTRY["indianapolis"]
    facts = build_facts(entry, today, offline_events={
        "basketball/wnba": wnba, "basketball/nba": nba,
        "football/nfl": [], "soccer/fifa.world": wc})
    print(header(entry["label"], today))
    print(facts_to_text(facts))
    print("\nALL SELFTEST CHECKS PASSED")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Passingly Informed daily digest")
    ap.add_argument("city", nargs="?", default="indianapolis")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, ET)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache")
    ap.add_argument("--no-llm", action="store_true", help="raw facts, skip Groq")
    ap.add_argument("--raw", action="store_true", help="also print facts JSON")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--build", metavar="DIR",
                    help="generate digest.json + index.html into DIR (for the "
                         "GitHub Action), then exit")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    if args.build:
        if EASTERN is not None:
            today = datetime.now(EASTERN).date()
        else:
            today = date.today()
        if args.date:
            today = date.fromisoformat(args.date)
        payload = build_site(args.build, args.city.lower(), today,
                              db_path=args.db, refresh=args.refresh)
        print("Wrote %s/digest.json and %s/index.html (%d lines)" % (
            args.build, args.build, len(payload["lines"])))
        return

    city = args.city.lower()
    if city not in REGISTRY:
        sys.exit("Unknown city '%s'. Known: %s" % (city, ", ".join(REGISTRY)))
    entry = REGISTRY[city]

    if args.date:
        today = date.fromisoformat(args.date)
    elif EASTERN is not None:
        today = datetime.now(EASTERN).date()
    else:
        today = date.today()

    conn = db_connect(args.db)

    # Serve cached digest unless asked to refresh or rebuild facts.
    if not args.refresh and not args.no_llm:
        cached = get_cached(conn, city, today)
        if cached and cached[1]:
            print(header(entry["label"], today))
            print(cached[1])
            if args.raw:
                print("\n--- facts ---\n" + cached[0])
            return

    facts = build_facts(entry, today)

    print(header(entry["label"], today))

    if args.no_llm:
        print(facts_to_text(facts))
        if args.raw:
            print("\n--- facts ---\n" + json.dumps(facts, indent=2))
        return

    if not os.environ.get("GROQ_API_KEY"):
        print(facts_to_text(facts))
        sys.stderr.write("\n! GROQ_API_KEY not set -- showed raw facts only.\n")
        return

    try:
        digest = phrase_with_groq(
            facts, entry["label"], today.strftime("%A, %B ") + str(today.day),
            entry.get("context", []))
    except Exception as e:
        print(facts_to_text(facts))
        sys.stderr.write("\n! phrasing failed (%s) -- showed raw facts.\n" % e)
        return

    save_cache(conn, city, today, facts, digest)
    print(digest)
    if args.raw:
        print("\n--- facts ---\n" + json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
