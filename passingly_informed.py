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
import re
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
# MLB's own free stats API -- the one feed that covers the minors (Triple-A,
# sportId 11), which ESPN doesn't. Used only for teams flagged source="milb".
STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"
# HockeyTech / LeagueStat powers the ECHL (and most minor hockey). The scorebar
# feed needs the league's public client key (shipped in their own web app).
# Used only for teams flagged source="echl".
HOCKEYTECH_FEED = "https://lscluster.hockeytech.com/feed/index.php"
ECHL_KEY = os.environ.get("ECHL_KEY", "2c2b89ea7345cae8")
USER_AGENT = "PassinglyInformed/1.0 (+local tool)"
HTTP_TIMEOUT = 12

DEFAULT_DB = os.path.expanduser("~/.passingly_informed.sqlite")

# Where past digests are kept so the site can flip back a few days. This is
# committed to the repo (the only thing that persists between Action runs); the
# build copies the recent ones into the published site. ARCHIVE_DAYS includes
# today, so 8 == today plus a week back.
ARCHIVE_DIR = "data/digests"
ARCHIVE_DAYS = 8

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
            {"path": "basketball/nba", "league": "NBA", "name": "Indiana Pacers",
             "players": ["Tyrese Haliburton", "Pascal Siakam"]},
            {"path": "basketball/wnba", "league": "WNBA", "name": "Indiana Fever",
             "players": ["Caitlin Clark", "Aliyah Boston"]},
            {"path": "football/nfl", "league": "NFL", "name": "Indianapolis Colts"},
            {"path": "soccer/usa.usl.1", "league": "USL Championship",
             "name": "Indy Eleven"},

            # Indianapolis Indians (Triple-A baseball) via statsapi, not ESPN.
            # team_id below is from statsapi's Triple-A team list -- VERIFY it:
            #   curl -s "https://statsapi.mlb.com/api/v1/teams?sportId=11" \
            #     | python3 -c "import sys,json;[print(t['id'],t['name']) for t \
            #       in json.load(sys.stdin)['teams'] if 'Indianapolis' in t['name']]"
            {"source": "milb", "team_id": 484, "league": "Triple-A",
             "name": "Indianapolis Indians"},

            # Indy Fuel (ECHL hockey) via HockeyTech's scorebar feed. `match` is
            # how they appear in that feed (city "Indy"); season is Oct-mid-June.
            {"source": "echl", "match": "Indy", "league": "ECHL",
             "name": "Indy Fuel"},

            # Out-of-market: some Indiana fans follow the Blackhawks, but hockey is
            # a smaller deal here, so they ride the ticker and only headline when
            # something notable is happening (a playoff run, a big result).
            {"path": "hockey/nhl", "league": "NHL", "name": "Chicago Blackhawks",
             "out_of_market": True},

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
            "Indiana has no NHL team; some local fans follow the Chicago "
            "Blackhawks, though hockey is a smaller deal in the state.",
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


# Standings live on /apis/v2/ (NOT /apis/site/v2/, which returns a stub).
STANDINGS_BASE = "https://site.api.espn.com/apis/v2/sports"


def fetch_standings(path):
    """Fetch a league's standings table. Returns the raw dict, or {} on failure."""
    url = "%s/%s/standings" % (STANDINGS_BASE, path)
    try:
        return http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        sys.stderr.write("  ! standings fetch failed %s: %s\n" % (path, e))
        return {}


# Player stat leaderboards (e.g. scoring) live on the common/v3 host.
LEADERS_BASE = "https://site.web.api.espn.com/apis/common/v3/sports"


def fetch_leaders(path, sort, limit=50):
    """Fetch a league's per-athlete stat leaderboard, already sorted. Returns the
    raw dict or {} on failure."""
    url = "%s/%s/statistics/byathlete?sort=%s&limit=%d" % (
        LEADERS_BASE, path, sort.replace(":", "%3A"), limit)
    try:
        return http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        sys.stderr.write("  ! leaders fetch failed %s: %s\n" % (path, e))
        return {}

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


def _overall_record(c):
    """Pull a team's overall season win-loss (e.g. '12-4') from a scoreboard
    competitor. ESPN embeds it here, so no extra fetch is needed. Returns the
    summary string, or None if not present."""
    recs = c.get("records") or []
    for r in recs:
        if r.get("name") in ("overall", "total") or r.get("type") in ("total", "overall"):
            if r.get("summary"):
                return r["summary"]
    if recs and recs[0].get("summary"):
        return recs[0]["summary"]
    return None


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
        record = _overall_record(us)

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
                "record": record, "when": when,
            }))
        elif state in ("pre", "in"):
            if when in ("today", "tonight") and edt.hour >= 17:
                when = "tonight"
            upcoming.append((edt, {
                "kind": "live" if state == "in" else "upcoming",
                "league": league_label, "team": team_name,
                "opponent": opp, "home": home, "record": record,
                "when": when, "time": fmt_time(edt),
            }))

    out = []
    if results:
        out.append(max(results, key=lambda x: x[0])[1])   # most recent result
    if upcoming:
        out.append(min(upcoming, key=lambda x: x[0])[1])   # soonest upcoming
    return out


def fetch_milb_schedule(team_id, start, end):
    """One Triple-A team's schedule from statsapi over [start, end] (date objs).
    Returns the flat list of game dicts, or [] on any failure -- never invents.
    This is the only non-ESPN feed; it's the one that covers the minors."""
    url = "%s/schedule?sportId=11&teamId=%s&startDate=%s&endDate=%s" % (
        STATSAPI_BASE, team_id, start.isoformat(), end.isoformat())
    try:
        data = http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        sys.stderr.write("  ! milb fetch failed %s: %s\n" % (team_id, e))
        return []
    games = []
    for d in (data.get("dates") or []):
        games.extend(d.get("games") or [])
    return games


def parse_milb_team(games, team_id, team_name, league_label, today):
    """Turn statsapi games into the SAME fact shape as parse_team_games: the
    most-recent result and soonest upcoming for our team. leagueRecord gives us a
    free W-L record, same as ESPN's."""
    tid = str(team_id)
    results, upcoming = [], []
    for g in games:
        teams = g.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        hid = str((home.get("team") or {}).get("id"))
        aid = str((away.get("team") or {}).get("id"))
        if tid == hid:
            us, them, is_home = home, away, True
        elif tid == aid:
            us, them, is_home = away, home, False
        else:
            continue
        opp = (them.get("team") or {}).get("name") or "?"
        try:
            edt = _parse_iso_to_eastern(g.get("gameDate", ""))
        except Exception:
            continue
        when = relative_day(edt.date(), today)
        st = g.get("status") or {}
        abstract = (st.get("abstractGameState") or "").lower()
        detailed = (st.get("detailedState") or "").lower()
        rec = us.get("leagueRecord") or {}
        record = ("%s-%s" % (rec["wins"], rec["losses"])
                  if rec.get("wins") is not None and rec.get("losses") is not None else None)

        if abstract == "final" or "final" in detailed or "completed" in detailed:
            us_s, them_s = us.get("score"), them.get("score")
            score = None
            if isinstance(us_s, int) and isinstance(them_s, int):
                hi, lo = (us_s, them_s) if us_s >= them_s else (them_s, us_s)
                score = "%d-%d" % (hi, lo)
            results.append((edt, {
                "kind": "result", "league": league_label, "team": team_name,
                "won": bool(us.get("isWinner")), "tie": bool(g.get("isTie")),
                "opponent": opp, "score": score, "record": record, "when": when,
            }))
        elif abstract in ("preview", "live") or "progress" in detailed or detailed in (
                "scheduled", "pre-game", "warmup", "delayed start"):
            live = abstract == "live" or "progress" in detailed
            if when in ("today", "tonight") and edt.hour >= 17:
                when = "tonight"
            upcoming.append((edt, {
                "kind": "live" if live else "upcoming", "league": league_label,
                "team": team_name, "opponent": opp, "home": is_home,
                "record": record, "when": when, "time": fmt_time(edt),
            }))

    out = []
    if results:
        out.append(max(results, key=lambda x: x[0])[1])
    if upcoming:
        out.append(min(upcoming, key=lambda x: x[0])[1])
    return out


def fetch_echl_scorebar(days_back=3, days_ahead=4):
    """ECHL games over a short window from HockeyTech's league-wide scorebar feed
    (one request covers every team). Returns the games list, or [] on any
    failure -- never invents. Empty in the offseason is normal and fine."""
    url = ("%s?feed=modulekit&view=scorebar&client_code=echl&key=%s"
           "&numberofdaysback=%d&numberofdaysahead=%d&fmt=json&lang=en") % (
        HOCKEYTECH_FEED, ECHL_KEY, days_back, days_ahead)
    try:
        data = http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        sys.stderr.write("  ! echl fetch failed: %s\n" % e)
        return []
    return (data.get("SiteKit") or {}).get("Scorebar") or []


def _echl_side(g, prefix):
    """Pull one side's (Home/Visitor) name, goals, and W-L-OTL record."""
    name = g.get(prefix + "LongName") or "%s %s" % (
        g.get(prefix + "City", ""), g.get(prefix + "Nickname", ""))
    try:
        goals = int(g.get(prefix + "Goals"))
    except (TypeError, ValueError):
        goals = None
    w = g.get(prefix + "Wins")
    rl = g.get(prefix + "RegulationLosses")
    otl = g.get(prefix + "OTLosses")
    sol = g.get(prefix + "ShootoutLosses")
    record = None
    try:
        record = "%d-%d-%d" % (int(w), int(rl), int(otl) + int(sol))
    except (TypeError, ValueError):
        pass
    return name.strip(), goals, record


def parse_echl_team(games, match, team_name, league_label, today):
    """From the league-wide scorebar, keep games involving our team (matched on
    `match`, e.g. 'Indy') and emit the same fact shape as the ESPN teams: the
    most-recent result and soonest upcoming."""
    m = match.lower()
    results, upcoming = [], []
    for g in games:
        home_is_us = (m in (g.get("HomeCity", "") + g.get("HomeLongName", "")).lower())
        away_is_us = (m in (g.get("VisitorCity", "") + g.get("VisitorLongName", "")).lower())
        if not (home_is_us or away_is_us):
            continue
        us_pre, them_pre = ("Home", "Visitor") if home_is_us else ("Visitor", "Home")
        _, us_goals, record = _echl_side(g, us_pre)
        opp, them_goals, _ = _echl_side(g, them_pre)
        try:
            edt = _parse_iso_to_eastern(g.get("GameDateISO8601", ""))
        except Exception:
            continue
        when = relative_day(edt.date(), today)
        status = (g.get("GameStatusStringLong") or g.get("GameStatusString") or "").lower()
        gstatus = str(g.get("GameStatus") or "")

        if "final" in status or gstatus == "4":
            score = None
            if isinstance(us_goals, int) and isinstance(them_goals, int):
                hi, lo = (us_goals, them_goals) if us_goals >= them_goals else (them_goals, us_goals)
                score = "%d-%d" % (hi, lo)
            won = (us_goals is not None and them_goals is not None and us_goals > them_goals)
            results.append((edt, {
                "kind": "result", "league": league_label, "team": team_name,
                "won": won, "tie": False, "opponent": opp, "score": score,
                "record": record, "when": when,
            }))
        else:
            live = gstatus in ("2", "3") or "progress" in status
            if when in ("today", "tonight") and edt.hour >= 17:
                when = "tonight"
            upcoming.append((edt, {
                "kind": "live" if live else "upcoming", "league": league_label,
                "team": team_name, "opponent": opp, "home": home_is_us,
                "record": record, "when": when, "time": fmt_time(edt),
            }))

    out = []
    if results:
        out.append(max(results, key=lambda x: x[0])[1])
    if upcoming:
        out.append(min(upcoming, key=lambda x: x[0])[1])
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


def _event_round(ev):
    """If this is a postseason/championship game, return a round label (e.g.
    'NBA Finals'); else None. ESPN marks postseason with season type 3 and often
    a notes headline naming the round."""
    season_type = (ev.get("season") or {}).get("type")
    comp = (ev.get("competitions") or [{}])[0]
    notes = comp.get("notes") or []
    headline = ((notes[0].get("headline") if notes else "") or "").strip()
    if headline:
        return headline
    if season_type == 3:
        return "playoffs"
    return None


def parse_national_event(events, league_label, today):
    """Surface a major league's POSTSEASON games (the Finals, Super Bowl, World
    Series, Stanley Cup) regardless of any local team. Regular-season games are
    ignored, so this only speaks up when it's a moment everyone's talking about."""
    results, upcoming = [], []
    for ev in events:
        rnd = _event_round(ev)
        if not rnd:
            continue
        comps = _competitors(ev)
        if len(comps) != 2:
            continue
        try:
            edt = _parse_iso_to_eastern(ev.get("date", ""))
        except Exception:
            continue
        when = relative_day(edt.date(), today)
        a, b = _team_name(comps[0]), _team_name(comps[1])
        status = ((ev.get("status") or {}).get("type") or {})
        state = status.get("state")
        # Avoid "NBA NBA Finals" if the headline already names the league.
        round_label = rnd if league_label.lower() in rnd.lower() else \
            "%s %s" % (league_label, rnd)

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
            results.append((edt, {"kind": "marquee", "league": league_label,
                                  "round": round_label, "detail": detail,
                                  "when": when}))
        elif state in ("pre", "in"):
            upcoming.append((edt, {"kind": "marquee", "league": league_label,
                                   "round": round_label,
                                   "detail": "%s vs %s" % (a, b),
                                   "when": when, "time": fmt_time(edt)}))

    out = []
    if results:
        out.append(max(results, key=lambda x: x[0])[1])   # most recent
    if upcoming:
        out.append(min(upcoming, key=lambda x: x[0])[1])   # soonest
    return out


def _ordinal(n):
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', etc."""
    if n is None:
        return None
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


def _stat_value(stats, name):
    for s in stats:
        if s.get("name") == name:
            return s.get("value", s.get("displayValue"))
    return None


def parse_standings(data, season_year):
    """Build {team_displayName: {seed, conference, record}} from a standings
    table. Guards on season year so a stale offseason table (last season's final
    standings) is ignored. Verified against ESPN's WNBA standings shape:
    children[] (conferences) -> standings.entries[] -> stats[] keyed by name."""
    out = {}
    children = data.get("children")
    # Some leagues expose a single flat table instead of conference children.
    groups = children if children else [data]
    for child in groups:
        standings = child.get("standings") or {}
        season = standings.get("season")
        # Reject only clearly-stale tables. Leagues that span two calendar years
        # (NBA, NHL, NFL) may label a season by its start year, so allow +/-1.
        # The real freshness guard is that standings only attach to teams with a
        # game in the current window.
        if season_year is not None and season is not None \
                and abs(season - season_year) > 1:
            continue
        conf = child.get("name") or child.get("abbreviation") or ""
        for e in (standings.get("entries") or []):
            name = (e.get("team") or {}).get("displayName")
            if not name:
                continue
            stats = e.get("stats") or []
            wins = _stat_value(stats, "wins")
            losses = _stat_value(stats, "losses")
            seed = _stat_value(stats, "playoffSeed")
            rec = None
            if wins is not None and losses is not None:
                rec = "%d-%d" % (int(wins), int(losses))
            out[name] = {
                "seed": int(seed) if seed is not None else None,
                "conference": conf if children else None,
                "record": rec,
            }
    return out


def _athlete_stat(athlete_entry, top_index_by_cat, stat_name):
    """Read one stat value (display string) for one athlete from a byathlete
    entry. Handles both layouts: a per-athlete category that carries its own
    `names`, or one whose `values`/`displayValues` align to the top-level
    category column order. Returns a display string or None."""
    cats = athlete_entry.get("categories") or athlete_entry.get("statistics") or []
    for c in cats:
        names = c.get("names")
        dv = c.get("displayValues") or []
        vv = c.get("values") or []
        if names and stat_name in names:
            i = names.index(stat_name)
            if i < len(dv):
                return str(dv[i])
            if i < len(vv):
                return str(vv[i])
        cat_name = c.get("name")
        if cat_name in top_index_by_cat:
            i = top_index_by_cat[cat_name]
            if i < len(dv):
                return str(dv[i])
            if i < len(vv):
                return str(vv[i])
    return None


def parse_leaders(data, stat_name, tracked_names):
    """From a sorted byathlete leaderboard, return the league leader plus any
    tracked local players (by display name), each with rank, value, and team.
    Athletes arrive already sorted by the API, so list position is the rank."""
    athletes = data.get("athletes") or []

    # Map each top-level category name -> the column index of stat_name in it.
    top_index_by_cat = {}
    for c in (data.get("categories") or []):
        names = c.get("names") or []
        if stat_name in names:
            top_index_by_cat[c.get("name")] = names.index(stat_name)

    tracked_set = set(tracked_names or [])
    league_leader, tracked = None, []
    for i, entry in enumerate(athletes):
        ath = entry.get("athlete") or {}
        name = ath.get("displayName")
        team = ath.get("teamName")
        if not name:
            continue
        val = _athlete_stat(entry, top_index_by_cat, stat_name)
        if val is None:
            continue
        rank = i + 1  # API already sorted descending
        if league_leader is None:
            league_leader = {"player": name, "team": team, "value": val, "rank": rank}
        if name in tracked_set:
            tracked.append({"player": name, "team": team, "value": val, "rank": rank})
    return {"league_leader": league_leader, "tracked": tracked}

# ---------------------------------------------------------------------------
# Build the day's facts for a city
# ---------------------------------------------------------------------------

# Leagues where a standings table is meaningful and the shape is verified. (Pro
# only for now; college "rank in a 350-team field" isn't a clean talking point.)
STANDINGS_LEAGUES = {
    "basketball/nba", "basketball/wnba", "football/nfl",
    "baseball/mlb", "hockey/nhl",
}

# Leagues where we surface a player stat leader (scoring). Each: the byathlete
# sort key, the stat field to read, a league label, and human wording. Only
# fetched when the league is in season (a game in the window).
LEADER_LEAGUES = {
    "basketball/wnba": {"sort": "offensive.avgPoints:desc", "stat": "avgPoints",
                        "league": "WNBA", "label": "scoring", "unit": "a game"},
    "basketball/nba": {"sort": "offensive.avgPoints:desc", "stat": "avgPoints",
                       "league": "NBA", "label": "scoring", "unit": "a game"},
}

# National marquee events: surfaced for EVERY city, no local team required, but
# ONLY their postseason games (Super Bowl, NBA Finals, World Series, Stanley Cup).
# Regular-season games in these leagues are ignored here -- the team registry
# already handles "did my local team play." nba/nfl paths overlap the Indy
# registry, so they're fetched once and parsed twice (team filter + postseason).
NATIONAL_EVENTS = [
    {"path": "basketball/nba", "league": "NBA"},
    {"path": "football/nfl", "league": "NFL"},
    {"path": "baseball/mlb", "league": "MLB"},
    {"path": "hockey/nhl", "league": "NHL"},
]


def build_facts(entry, today, offline_events=None, offline_standings=None,
                offline_leaders=None, offline_milb=None, offline_echl=None):
    """Fetch each unique league ONCE over a short window, then parse per team.
    Many teams share a league (four colleges all play basketball), so fetching
    per unique path instead of per team avoids hammering the same endpoint.
    Non-ESPN teams (source="milb"/"echl") use their own feeds, kept fully
    isolated from the ESPN path. offline_* : optional dicts to bypass network."""
    # yesterday catches last night's result; +3 catches the upcoming weekend for
    # weekly sports like college football without flooding daily sports.
    window = [today + timedelta(days=d) for d in (-1, 0, 1, 2, 3)]

    espn_teams = [t for t in entry["teams"] if not t.get("source")]
    milb_teams = [t for t in entry["teams"] if t.get("source") == "milb"]
    echl_teams = [t for t in entry["teams"] if t.get("source") == "echl"]

    paths = []
    for t in espn_teams:
        if t["path"] not in paths:
            paths.append(t["path"])
    for e in entry.get("events", []):
        if e["path"] not in paths:
            paths.append(e["path"])
    for e in NATIONAL_EVENTS:
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

    # Standings (position + record) for the pro leagues this city has teams in.
    # Fetched once per league; the season-year guard drops stale offseason tables.
    standings_leagues = [p for p in paths if p in STANDINGS_LEAGUES]
    standing_by_team = {}
    for p in standings_leagues:
        if offline_standings is not None:
            data = offline_standings.get(p, {})
        elif offline_events is None:
            data = fetch_standings(p)
        else:
            data = {}  # offline events mode without standings -> skip network
        standing_by_team.update(parse_standings(data, today.year))

    facts = []
    for t in espn_teams:
        tf = parse_team_games(
            events_by_path.get(t["path"], []), t["name"], t["league"], today)
        if t.get("out_of_market"):
            for f in tf:
                f["out_of_market"] = True
        facts.extend(tf)
    for e in entry.get("events", []):
        facts.extend(parse_event_matches(
            events_by_path.get(e["path"], []), e["league"], today,
            prefer=e.get("prefer", ())))
    for e in NATIONAL_EVENTS:
        facts.extend(parse_national_event(
            events_by_path.get(e["path"], []), e["league"], today))

    # MiLB teams (e.g. the Indianapolis Indians) via statsapi -- fully isolated
    # from the ESPN path above; any fetch failure just yields no facts.
    for t in milb_teams:
        if offline_milb is not None:
            games = offline_milb.get(t["team_id"], [])
        elif offline_events is None:
            games = fetch_milb_schedule(t["team_id"], window[0], window[-1])
        else:
            games = []
        facts.extend(parse_milb_team(
            games, t["team_id"], t["name"], t["league"], today))

    # ECHL teams (e.g. the Indy Fuel) via HockeyTech's league-wide scorebar --
    # fetched once and filtered per team; same isolation/graceful rules.
    if echl_teams:
        if offline_echl is not None:
            scorebar = offline_echl
        elif offline_events is None:
            scorebar = fetch_echl_scorebar()
        else:
            scorebar = []
        for t in echl_teams:
            facts.extend(parse_echl_team(
                scorebar, t["match"], t["name"], t["league"], today))

    # Player stat leaders. Only for leagues that (a) we configured and (b) are in
    # season -- gated on a game in the window, which avoids stale offseason stats.
    tracked_by_path = {}
    for t in espn_teams:
        if t.get("players") and t["path"] in LEADER_LEAGUES:
            tracked_by_path.setdefault(t["path"], []).extend(t["players"])
    for p, cfg in LEADER_LEAGUES.items():
        if p not in paths or not events_by_path.get(p):
            continue  # not relevant here, or out of season
        if offline_leaders is not None:
            data = offline_leaders.get(p, {})
        elif offline_events is None:
            data = fetch_leaders(p, cfg["sort"])
        else:
            data = {}
        res = parse_leaders(data, cfg["stat"], tracked_by_path.get(p, []))
        ll = res.get("league_leader")
        tracked = res.get("tracked", [])
        local_is_leader = bool(ll and any(t["player"] == ll["player"] for t in tracked))
        # Local stars (excluding the one who IS the league leader -- reported below).
        local_facts = [
            {"kind": "leader", "scope": "local", "league": cfg["league"],
             "stat": cfg["label"], "unit": cfg["unit"], **t}
            for t in tracked if not (ll and t["player"] == ll["player"])
        ]
        # The generic league leader earns a HEADLINE line only when it has a
        # local hook (the leader plays for our team) or there's no local star to
        # talk about. Otherwise it's trivia nobody here follows for a headline --
        # but it's good ticker fuel, so keep it tagged ticker_only.
        if ll:
            lead_fact = {"kind": "leader", "scope": "league",
                         "league": cfg["league"], "stat": cfg["label"],
                         "unit": cfg["unit"], **ll}
            if not (local_is_leader or not local_facts):
                lead_fact["ticker_only"] = True
            facts.append(lead_fact)
        facts.extend(local_facts)

    # Enrich team facts with standings: seed, conference, and (preferring the
    # standings table's record over a possibly-older scoreboard record).
    for f in facts:
        if f.get("kind") in ("result", "upcoming", "live"):
            st = standing_by_team.get(f.get("team"))
            if st:
                if st.get("seed") is not None:
                    f["seed"] = st["seed"]
                if st.get("conference"):
                    f["conference"] = st["conference"]
                if st.get("record"):
                    f["record"] = st["record"]

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
    "- Each team gets ONE short bullet built from the 1-2 most conversation-worthy "
    "facts about them -- NOT every fact you were given. People mention a team's "
    "most interesting thing or two, not its full line score. Good: 'The Fever "
    "lost to the Dream last night and host the Mercury tomorrow.' or 'The Fever "
    "are 9-7, third in the East.' BAD: cramming result AND record AND standing "
    "AND next game AND a stat into one breath, or stringing facts together with "
    "semicolons. If you have lots of facts about one team, PICK the best and let "
    "the rest go -- the ticker carries the full slate. Keep it to one bullet, at "
    "most two short sentences, no semicolon run-ons.\n"
    "- NAMES: keep an opponent's FULL name (city + nickname) whenever shortening "
    "it would point at the wrong, more-famous team. Minor-league nicknames "
    "constantly collide with the majors, so write 'Iowa Cubs' (never 'the Cubs' "
    "-- that means Chicago) and 'Toledo Mud Hens', not a bare nickname. Only "
    "shorten when it's unmistakable -- a clearly local team like 'the Fever' or "
    "'the Colts' is fine.\n"
    "- The talking-point lines are STATEMENTS, not questions. There is exactly "
    "ONE question in the whole digest and it is the 'Escape hatch' line. Do NOT "
    "write a separate question bullet -- it just duplicates the escape hatch.\n"
    "- (For the escape hatch and any question) hand the floor to the OTHER "
    "person, the one who follows sports ('what'd you make of the US game?'). "
    "NEVER ask the reader to predict, judge, or analyze ('who'll win?', 'do you "
    "think they'll turn it around?') -- those bounce back and expose them.\n"
    "- Use `context` only to enrich a line (e.g. that the Fever are Caitlin "
    "Clark's team), and only context you were actually given.\n"
    "- Some facts include a `record` (a team's season win-loss, e.g. '12-4') and "
    "may include `seed` (playoff position) and `conference`. These are real "
    "trends you may state plainly ('the Fever are 12-4, first in the East') or "
    "build the escape hatch around. State only what's given -- do NOT "
    "characterize it ('best in the league', 'on a tear') unless that's "
    "provided.\n"
    "- A `leader` fact is a real player stat: their rank and number in something "
    "like scoring. A LOCAL star (scope 'local', e.g. Caitlin Clark) is an "
    "excellent hook. Lead with the plain point and let the number support it, "
    "the way a person actually talks: 'Caitlin Clark's been the bright spot for "
    "the Fever -- scoring around 21 a game' -- NOT 'Caitlin Clark is 4th in WNBA "
    "scoring at 20.79'. ROUND numbers to how people say them out loud (20.79 -> "
    "'about 21'); never inflate or invent, but a recited decimal is the wrong "
    "register. Work in the rank only if it stays natural ('one of the top "
    "scorers', 'fourth in the league').\n\n"
    "LEAD WITH THE BIGGEST STORY. Not every fact is equal. A `marquee` fact -- a "
    "national championship or its games (NBA Finals, Super Bowl, World Series, "
    "Stanley Cup) -- is what the whole country is talking about, so it usually "
    "deserves the TOP line even though no local team is involved; people in every "
    "city discuss the Finals. Rank roughly: a title just decided or underway > a "
    "big event hosted here (World Cup) > a local team's notable result or game > "
    "a routine local game.\n"
    "- A fact marked `out_of_market` is a team some locals follow but that isn't "
    "truly local (e.g. the Blackhawks for Indianapolis). Lowest headline "
    "priority: feature it ONLY if it's genuinely notable (a playoff run, a big "
    "result) AND nothing bigger is happening. Otherwise leave it out of the "
    "talking points -- it still shows up in the day's ticker.\n\n"
    "BIG EVENTS:\n"
    "- World Cup: the talking point is that it's being hosted in the US right "
    "now -- a big deal even for people who never watch soccer. Lead with that "
    "framing; a US match is the specific hook. Skip foreign matches with no "
    "hook.\n"
    "- A `marquee` championship result (a team just won the title) is a strong "
    "opener: state who won plainly, then hand off ('wild they finally won one -- "
    "you been following it?').\n\n"
    "VOICE: dry, competent, lightly warm. No exclamation points, no 'actually', "
    "no filler, no scripted-sounding bits. A real person who has just been busy, "
    "not a brochure.\n"
    "- TALK, DON'T RECITE. The reader says these lines out loud, so they must "
    "sound spoken, not read off a stat sheet. Lead with the human point; let "
    "numbers support it. Round stats the way people say them ('about 21 a game', "
    "never '20.79'). Say standings naturally ('third in the East'), not 'third "
    "seed'. A couple of related numbers said naturally is fine ('9-6, third in "
    "the East'); just don't stack stats like a box score. If a line sounds like "
    "a stat sheet, rewrite it as something a person would say.\n\n"
    "OUTPUT:\n"
    "- Aim for 3 to 4 short lines when the day has that much real material -- it "
    "usually does. Each starts with '* ' and covers a DIFFERENT topic. After the "
    "biggest stories, USE the other real local topics you were given rather than "
    "leaving them for the ticker: a local team that actually played -- Indy "
    "Eleven, the Indianapolis Indians, the Indy Fuel, a college team -- is worth "
    "its own line. Only drop to 2 on a genuinely quiet day with little real "
    "material. Never pad, invent, or repeat a topic just to reach a number.\n"
    "- Then ONE final line starting 'Escape hatch: '. This is the reader's way "
    "OUT of the conversation -- a line that lets them tap out gracefully without "
    "needing to know anything, by handing it fully to the other person and "
    "stepping back. It is NOT a curiosity question that keeps them on the hook. "
    "The test: after the reader says it, they can stop talking and the fan "
    "carries on. Rotate (using variety_seed) between these REAL exit moves so it "
    "never feels samey:\n"
    "    1. Defer to them: 'you follow this way closer than I do.'\n"
    "    2. Honest punt: 'I mostly just catch the highlights, honestly.'\n"
    "    3. Hand off and bow out: 'tell me how it shakes out.'\n"
    "    4. Lob it and let them run: 'sounds like the Fever are the ones to "
    "watch -- you been keeping up with them?' (a question is fine ONLY if it "
    "clearly puts THEM in the talker's seat and lets the reader coast).\n"
    "  Prefer a statement over a question when in doubt -- a statement closes "
    "the reader's turn; a question can reopen it back onto them. Tie it to a "
    "real angle from the day when there is one, but the move itself is the exit, "
    "not a quiz. NEVER ask the reader to predict, analyze, or judge, and never "
    "invent a stat or storyline. Vary the shape day to day; do not reuse 'did "
    "you catch X' / 'what'd you make of X' every time.\n"
    "- VARIETY: a `variety_seed` integer is provided. Use it to vary your "
    "opening, your sentence shapes, and which fact leads, so someone checking "
    "daily doesn't get the same template every time. Never mention the seed.\n"
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
        "variety_seed": sum(ord(c) for c in date_label) % 97,
        # ticker_only facts (e.g. a non-local league leader) feed the page ticker,
        # not the headline talking points -- keep them out of the model's view.
        "live_facts": [f for f in facts if not f.get("ticker_only")],
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


def _trend_suffix(f):
    """Combine record and standings position into a readable trend string."""
    bits = []
    if f.get("record"):
        bits.append(f["record"])
    if f.get("seed") is not None:
        pos = _ordinal(f["seed"])
        conf = f.get("conference")
        bits.append("%s in the %s" % (pos, conf) if conf else "%s seed" % pos)
    return ", ".join(bits)


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
            sfx = _trend_suffix(f)
            sfx = (" -- " + sfx) if sfx else ""
            lines.append("* %s %s %s %s%s (%s)%s" % (
                f["team"], r, vs, f["opponent"], s, f["when"], sfx))
        elif k in ("upcoming", "live"):
            vs = "hosts" if f.get("home") else "plays"
            tag = "LIVE now" if k == "live" else "%s %s" % (f["when"], f.get("time", ""))
            sfx = _trend_suffix(f)
            sfx = (" [%s]" % sfx) if sfx else ""
            lines.append("* %s%s %s %s -- %s" % (
                f["team"], sfx, vs, f["opponent"], tag.strip()))
        elif k == "event_result":
            lines.append("* %s: %s (%s)" % (f["event"], f["detail"], f["when"]))
        elif k == "event_upcoming":
            lines.append("* %s: %s -- %s %s" % (
                f["event"], f["detail"], f["when"], f.get("time", "")))
        elif k == "event_active":
            lines.append("* %s is underway" % f["event"])
        elif k == "marquee":
            if f.get("time"):
                lines.append("* %s: %s -- %s %s" % (
                    f["round"], f["detail"], f["when"], f["time"]))
            else:
                lines.append("* %s: %s (%s)" % (f["round"], f["detail"], f["when"]))
        elif k == "leader":
            if f.get("scope") == "league":
                lines.append("* %s leads the %s in %s at %s %s" % (
                    f["player"], f["league"], f["stat"], f["value"], f["unit"]))
            else:
                tm = (" (%s)" % f["team"]) if f.get("team") else ""
                lines.append("* %s%s is %s in the %s in %s at %s %s" % (
                    f["player"], tm, _ordinal(f["rank"]), f["league"],
                    f["stat"], f["value"], f["unit"]))
    return "\n".join(lines)


def build_ticker(facts, today):
    """Terse, broadcast-style ticker strings built straight from real facts (no
    model, so nothing here can be invented). This is the B-side: the full slate
    of scores, standings, and leaders -- including ones that never made the
    headline talking points (like a non-local league scoring leader)."""
    items, seen = [], set()

    def push(s):
        s = " ".join(s.split()).strip(" -·")
        if s and s.lower() not in seen:
            seen.add(s.lower())
            items.append(s)

    push(today.strftime("%a %b ").upper() + str(today.day))  # e.g. "SAT JUN 20"

    for f in facts:
        k = f.get("kind")
        lg = (f.get("league") or f.get("event") or "").upper()
        if k == "result":
            verb = "drew with" if f.get("tie") else ("beat" if f.get("won") else "lost to")
            push("%s · %s %s %s %s" % (lg, f.get("team", ""), verb,
                                       f.get("opponent", "?"), f.get("score", "")))
        elif k in ("upcoming", "live"):
            prep = "vs" if f.get("home") else "at"
            tag = "LIVE" if k == "live" else lg
            push("%s · %s %s %s %s %s" % (tag, f.get("team", ""), prep,
                                          f.get("opponent", "?"),
                                          f.get("when", ""), f.get("time", "")))
        elif k == "event_result":
            push("%s · %s" % (lg, f.get("detail", "")))
        elif k == "event_upcoming":
            push("%s · %s %s" % (lg, f.get("detail", ""), f.get("when", "")))
        elif k == "event_active":
            push("%s · underway" % lg)
        elif k == "marquee":
            push("%s · %s %s" % ((f.get("round") or lg).upper(),
                                 f.get("detail", ""), f.get("when", "")))
        elif k == "leader":
            stat = (f.get("stat") or "").upper()
            if f.get("scope") == "league":
                push("%s %s · %s %s" % (lg, stat, f.get("player", ""), f.get("value", "")))
            else:
                push("%s %s · %s %s, %s" % (lg, stat, f.get("player", ""),
                                            _ordinal(f.get("rank") or 0), f.get("value", "")))
    return items


# ---------------------------------------------------------------------------
# Static site build  (digest.json + baked index.html for GitHub/Cloudflare)
# ---------------------------------------------------------------------------

def split_digest(text):
    """Parse the model's plain-text output into (lines, escape_hatch). Tolerant
    of the model occasionally putting a '* ' bullet in front of the escape-hatch
    line: we strip a leading bullet before checking, so the 'out' is always
    pulled out rather than leaking in as a talking point."""
    lines, hatch = [], ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        body = re.sub(r"^[\*\-\u2022]+\s*", "", s)  # drop a leading bullet, if any
        if body.lower().startswith("escape hatch:"):
            hatch = body.split(":", 1)[1].strip()
        elif s[:1] in "*\u2022":
            lines.append(body)
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
    --bg:#0b0f17; --panel:#141b27; --panel2:#1b2433; --line:#2a3547;
    --text:#e9eef6; --dim:#8995a8; --faint:#5c6678;
    --amber:#ffb84d; --green:#3ddc84; --red:#ff5d6c;
    --cond:"Arial Narrow","Roboto Condensed",Oswald,"Helvetica Neue",Impact,sans-serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg); color:var(--text); font-family:var(--sans); line-height:1.55;
    padding:clamp(12px,4vw,40px); display:flex; justify-content:center;
    background-image:radial-gradient(1200px 380px at 50% -8%, #18324a55, transparent);}
  main{width:100%; max-width:660px}

  .board{background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--line); border-radius:6px; box-shadow:0 28px 70px -28px #000; overflow:hidden}
  .head{display:flex; align-items:center; gap:1rem; padding:clamp(16px,4vw,24px); padding-bottom:.7rem}
  .mascot{flex:0 0 auto; width:72px; height:72px}
  .head .titles{min-width:0; flex:1}
  .kicker{font-family:var(--mono); font-size:.66rem; letter-spacing:.34em; text-transform:uppercase; color:var(--amber); margin:0}
  .city{font-family:var(--cond); font-weight:700; text-transform:uppercase; letter-spacing:.02em;
    font-size:clamp(2.1rem,9vw,3.1rem); line-height:.9; margin:.18rem 0 0; font-stretch:condensed}
  .clock{font-family:var(--mono); font-size:.72rem; color:var(--green); margin-left:auto; align-self:flex-start; white-space:nowrap}

  .ticker{display:flex; gap:0; border-top:1px solid var(--line); border-bottom:1px solid var(--line);
    background:#0e1521; overflow:hidden; white-space:nowrap}
  .ticker .run{display:inline-flex; gap:2.4rem; padding:.4rem 0; font-family:var(--mono); font-size:.7rem;
    color:var(--dim); animation:slide 46s linear infinite}
  .ticker .run span b{color:var(--amber); font-weight:600}
  @keyframes slide{from{transform:translateX(0)}to{transform:translateX(-50%)}}
  @media (prefers-reduced-motion:reduce){.ticker .run{animation:none; padding-left:1rem}}

  .carousel{position:relative; padding:clamp(14px,4vw,22px)}
  .viewport{overflow:hidden}
  .track{display:flex; transition:transform .26s ease}
  @media (prefers-reduced-motion:reduce){.track{transition:none}}
  .card{flex:0 0 100%; width:100%}
  .cmeta{display:flex; align-items:center; gap:.7rem; font-family:var(--mono); font-size:.74rem; color:var(--dim); margin:0 0 1.1rem}
  .badge{font-family:var(--cond); font-weight:700; letter-spacing:.12em; text-transform:uppercase;
    color:#0b0f17; background:var(--amber); padding:.1rem .5rem; border-radius:3px; font-size:.8rem}
  .rows{display:grid; gap:.7rem}
  .row{background:#0e1521; border:1px solid var(--line); border-left:3px solid var(--amber);
    border-radius:4px; padding:.7rem .8rem}
  .row:nth-child(2n){border-left-color:var(--green)}
  .row p{margin:0; font-size:1.02rem}
  .out{margin-top:1.1rem; border:1px dashed var(--faint); border-radius:5px; padding:.7rem .9rem .85rem; background:#0e1521}
  .out .ol{font-family:var(--mono); font-size:.64rem; letter-spacing:.22em; text-transform:uppercase; color:var(--red)}
  .out p{margin:.3rem 0 0; font-style:italic; color:var(--dim)}

  .cdots{display:flex; gap:.55rem; justify-content:center; margin:0 0 1.1rem}
  .cdot{width:9px; height:9px; padding:0; border:0; border-radius:50%; background:#26303f; cursor:pointer}
  .cdot.on{background:var(--amber); box-shadow:0 0 8px var(--amber)}
  .cbtn{position:absolute; top:46%; width:36px; height:36px; border-radius:50%; border:1px solid var(--line);
    background:var(--panel); color:var(--text); cursor:pointer; font-size:1.1rem; z-index:2}
  .cbtn:hover{color:var(--amber); border-color:var(--amber)} .cbtn:disabled{opacity:.25; cursor:default}
  .cprev{left:-6px} .cnext{right:-6px}
  @media (max-width:580px){.cbtn{display:none}}

  .signup{margin:0 clamp(14px,4vw,22px) clamp(16px,4vw,22px)}
  .signup .eyebrow{font-family:var(--mono); font-size:.66rem; letter-spacing:.18em; text-transform:uppercase; color:var(--amber); margin:0}
  .signup .row{display:flex; gap:.5rem; margin-top:.5rem; flex-wrap:wrap; background:none; border:0; padding:0}
  .signup input{flex:1 1 200px; min-width:0; background:#0e1521; color:var(--text);
    border:1px solid var(--line); border-radius:4px; padding:.6rem .7rem; font-size:.95rem; font-family:var(--sans)}
  .signup input:focus-visible{outline:2px solid var(--amber); outline-offset:1px}
  .signup button{background:var(--amber); color:#0b0f17; border:0; border-radius:4px;
    padding:.6rem 1rem; font-weight:700; font-size:.95rem; cursor:pointer}
  .signup button:hover{filter:brightness(1.07)}
  .fineprint{font-size:.78rem; color:var(--faint); margin:.55rem 0 0}
  .soon{font-family:var(--mono); font-size:.66rem; letter-spacing:.18em; text-transform:uppercase; color:var(--faint)}

  footer{margin:1.3rem 4px 0; color:var(--faint); font-family:var(--mono); font-size:.7rem; text-align:center; line-height:1.9}
  footer a{color:var(--dim); text-decoration:none; border-bottom:1px solid var(--line)}
  footer a:hover{color:var(--amber)}
  footer .sep{opacity:.4; padding:0 .4rem}
</style>
</head>
<body>
<main>
  <div class="board">
    <div class="head">
      <svg class="mascot" viewBox="0 0 100 100" aria-label="robot mascot with basketball">
        <line x1="50" y1="14" x2="50" y2="6" stroke="#8995a8" stroke-width="2.4"/>
        <circle cx="50" cy="5" r="3" fill="#ffb84d"/>
        <rect x="30" y="14" width="40" height="30" rx="8" fill="#cfd8e6"/>
        <rect x="35" y="22" width="30" height="14" rx="5" fill="#0e1521"/>
        <circle cx="44" cy="29" r="3.1" fill="#ffb84d"/><circle cx="56" cy="29" r="3.1" fill="#3ddc84"/>
        <rect x="33" y="46" width="34" height="30" rx="7" fill="#aeb9cc"/>
        <rect x="40" y="52" width="20" height="13" rx="3" fill="#0e1521"/>
        <line x1="46" y1="58" x2="54" y2="58" stroke="#3ddc84" stroke-width="2"/>
        <rect x="22" y="50" width="9" height="20" rx="4" fill="#8995a8" transform="rotate(18 26 60)"/>
        <circle cx="76" cy="70" r="15" fill="#ff8a3d"/>
        <path d="M61 70h30 M76 55v30 M64 60q12 10 24 0 M64 80q12 -10 24 0" stroke="#0b0f17" stroke-width="1.6" fill="none"/>
        <rect x="66" y="60" width="9" height="9" rx="3" fill="#aeb9cc" transform="rotate(-20 70 64)"/>
      </svg>
      <div class="titles">
        <p class="kicker">Passingly Informed</p>
        <h1 class="city">{{CITY}}</h1>
      </div>
      <div class="clock">{{TODAY_STAMP}}</div>
    </div>

{{TICKER}}

    <div class="carousel">
      <button class="cbtn cprev" id="cprev" type="button" aria-label="Newer day">&lsaquo;</button>
      <div class="viewport"><div class="track" id="track">
{{CARDS}}
      </div></div>
      <button class="cbtn cnext" id="cnext" type="button" aria-label="Older day">&rsaquo;</button>
    </div>
    <div class="cdots" id="cdots"></div>
{{FORM_BLOCK}}
  </div>
  <footer>{{FOOTER}}</footer>
</main>
<script>{{CAROUSEL_JS}}</script>
</body>
</html>
"""

HATCH_BLOCK = (
    '        <div class="out">\n'
    '          <span class="ol">Your out</span>\n'
    '          <p>{{HATCH}}</p>\n'
    '        </div>'
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

SOON_BLOCK = ('    <p class="signup soon">Email signups coming soon</p>')


CAROUSEL_JS = (
    "(function(){"
    "var track=document.getElementById('track');if(!track)return;"
    "var n=track.children.length,i=0;"
    "var dots=document.getElementById('cdots');"
    "var prev=document.getElementById('cprev'),next=document.getElementById('cnext');"
    "function render(){"
    "track.style.transform='translateX(-'+(i*100)+'%)';"
    "if(dots){var d=dots.children;for(var k=0;k<d.length;k++)d[k].className='cdot'+(k===i?' on':'');}"
    "if(prev)prev.disabled=(i<=0);if(next)next.disabled=(i>=n-1);}"
    "function go(x){i=x<0?0:(x>n-1?n-1:x);render();}"
    "if(n<2){if(prev)prev.style.display='none';if(next)next.style.display='none';"
    "if(dots)dots.style.display='none';return;}"
    "for(var k=0;k<n;k++){(function(idx){var b=document.createElement('button');"
    "b.className='cdot';b.type='button';b.setAttribute('aria-label','Day '+(idx+1));"
    "b.onclick=function(){go(idx);};dots.appendChild(b);})(k);}"
    "if(prev)prev.onclick=function(){go(i-1);};"
    "if(next)next.onclick=function(){go(i+1);};"
    "var x0=null;"
    "track.addEventListener('touchstart',function(e){x0=e.touches[0].clientX;},{passive:true});"
    "track.addEventListener('touchend',function(e){if(x0==null)return;"
    "var dx=e.changedTouches[0].clientX-x0;if(Math.abs(dx)>40)go(dx<0?i+1:i-1);x0=null;},{passive:true});"
    "document.addEventListener('keydown',function(e){"
    "if(e.key==='ArrowLeft')go(i-1);else if(e.key==='ArrowRight')go(i+1);});"
    "render();})();"
)


def _short_date(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%b ") + str(d.day)


def render_day_card(payload, is_today):
    """One day's digest as a scoreboard-style card: each talking point a row,
    plus the 'out'."""
    lines = payload.get("lines", [])
    if lines:
        rows = "\n".join(
            '          <div class="row"><p>%s</p></div>' % html.escape(l)
            for l in lines)
    else:
        rows = '          <div class="row"><p>Quiet sports day — nothing worth faking yet.</p></div>'

    hatch_block = ""
    if payload.get("escape_hatch"):
        hatch_block = "\n" + HATCH_BLOCK.replace(
            "{{HATCH}}", html.escape(payload["escape_hatch"]))

    badge = '<span class="badge">Today</span>' if is_today else ""
    meta = badge + html.escape(payload.get("date_label", ""))

    return (
        '      <article class="card day">\n'
        '        <p class="cmeta">%s</p>\n'
        '        <div class="rows">\n%s\n        </div>%s\n'
        '      </article>'
    ) % (meta, rows, hatch_block)


def render_ticker(items):
    """The scrolling bottom-line, built from real ticker facts. Bolds the tag
    before the divider ('WNBA · ...'). Returns '' if there's nothing to scroll."""
    if not items:
        return ""
    spans = []
    for it in items:
        if " \u00b7 " in it:
            tag, rest = it.split(" \u00b7 ", 1)
            spans.append("<span><b>%s</b> &middot; %s</span>" % (
                html.escape(tag), html.escape(rest)))
        else:
            spans.append("<span><b>%s</b></span>" % html.escape(it))
    run = "".join(spans)
    # Duplicated so the marquee can loop seamlessly (CSS scrolls one full copy).
    return '    <div class="ticker"><div class="run">%s%s</div></div>' % (run, run)


def render_html(today_payload, earlier_payloads=None):
    """Build the single scoreboard page: masthead, ticker (real facts), and
    today's card first, then earlier days as cards to swipe/flip through."""
    earlier_payloads = earlier_payloads or []
    cards = [render_day_card(today_payload, True)]
    cards += [render_day_card(p, False) for p in earlier_payloads]

    try:
        d = date.fromisoformat(today_payload["date"])
        today_stamp = (d.strftime("%a %b ") + str(d.day)).upper()
    except (KeyError, ValueError):
        today_stamp = ""

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
        "{{CITY}}": html.escape(today_payload["city"]),
        "{{TAGLINE}}": html.escape(SITE_TAGLINE),
        "{{TODAY_STAMP}}": html.escape(today_stamp),
        "{{TICKER}}": render_ticker(today_payload.get("ticker") or []),
        "{{CARDS}}": "\n".join(cards),
        "{{FORM_BLOCK}}": form_block,
        "{{FOOTER}}": footer,
        "{{CAROUSEL_JS}}": CAROUSEL_JS,
    }.items():
        out = out.replace(k, v)
    return out


def _load_archive(archive_dir, today):
    """Write today's payload (caller does that first), then load up to
    ARCHIVE_DAYS most recent stored payloads, newest first."""
    import glob
    files = sorted(glob.glob(os.path.join(archive_dir, "*.json")))  # ISO sorts by date
    # Keep only valid YYYY-MM-DD.json names.
    keep = [f for f in files if re.match(r"\d{4}-\d{2}-\d{2}\.json$", os.path.basename(f))]
    # Prune older than ARCHIVE_DAYS so the repo doesn't grow forever.
    for old in keep[:-ARCHIVE_DAYS]:
        try:
            os.remove(old)
        except OSError:
            pass
    recent = keep[-ARCHIVE_DAYS:]
    payloads = []
    for f in reversed(recent):  # newest first
        try:
            with open(f, encoding="utf-8") as fh:
                payloads.append(json.load(fh))
        except (OSError, ValueError):
            pass
    return payloads


def build_site(out_dir, city_key, today, db_path=DEFAULT_DB, refresh=False,
               archive_dir=ARCHIVE_DIR):
    """Write digest.json + a single index.html into out_dir. index.html holds
    today's digest plus the last few days as cards the visitor can flip through.
    Reuses today's cached digest if one exists (so re-running costs no tokens);
    generates fresh on a cache miss or refresh=True."""
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
        "ticker": build_ticker(facts, today),
        "display": digest_text,
        "speech": to_speech(lines, hatch, entry["label"], date_label),
    }

    # Persist today into the archive (overwrites if regenerated), then load recent.
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, "%s.json" % today.isoformat()),
              "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    recent = _load_archive(archive_dir, today)

    os.makedirs(out_dir, exist_ok=True)
    # digest.json is always TODAY (this is what Home Assistant reads).
    with open(os.path.join(out_dir, "digest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # One page: today's card first, then earlier days as flip-through cards.
    earlier = [p for p in recent if p.get("date") != today.isoformat()]
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_html(payload, earlier_payloads=earlier))
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
    ap.add_argument("--archive-dir", default=ARCHIVE_DIR,
                    help="where past digests are stored for the flip-back archive")
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
                             db_path=args.db, refresh=args.refresh,
                             archive_dir=args.archive_dir)
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
