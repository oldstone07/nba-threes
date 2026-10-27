#!/usr/bin/env python3
"""NBA Threes Engine — forward-test logger for made-threes player props.

Stdlib only. One command does everything:

    python engine.py run            # update box scores, grade finished games
    python engine.py run --odds     # ...and pull tonight's threes lines, project, log picks

What it does on each run:
  1. Reads the NBA schedule and caches a slim box score for every finished game.
  2. Grades every logged line whose game is final (W / L / P / Void).
  3. With --odds and an ODDS_API_KEY: pulls `player_threes` for games not yet
     tipped, projects each player, logs every line, flags picks that clear the bar.

Everything lands in data/ so the page (index.html) and GitHub can read it.
Rules are locked here, before results exist. Change MODEL_VERSION if you touch them.
"""
import datetime as dt
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- locked rules
MODEL_VERSION = "v1"
EDGE_BAR = 0.05          # model prob minus no-vig book prob, on the side we'd bet
LEAGUE_PCT = 0.36        # 3P% everyone regresses toward
PRIOR_ATT = 100          # 3P% regression strength, in attempts
PRIOR_GAMES = 10         # weight of last season's 3PA/game, in games
MIN_GAMES_NO_PRIOR = 5   # players with no last-season data need this many games
LAST_N = 10              # recent-form window
DISPERSION = 12          # negative-binomial size; fit on 2024-25, checked on 2025-26

# ---------------------------------------------------------------- paths / urls
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
BOX_DIR = os.path.join(DATA, "boxscores")
ODDS_DIR = os.path.join(DATA, "odds")
LOG_PATH = os.path.join(DATA, "log.json")
TODAY_PATH = os.path.join(DATA, "today.json")
PRIOR_PATH = os.path.join(DATA, "prior.json")
STATUS_PATH = os.path.join(DATA, "status.json")

SCHED_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
BOX_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
ODDS_BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"

ET = dt.timezone(dt.timedelta(hours=-5))  # used only for "what day is it" labels


# ======================================================================= math
def pois_ge(k, lam):
    """P(X >= k) for X ~ Poisson(lam)."""
    if k <= 0:
        return 1.0
    term, total = math.exp(-lam), 0.0
    for i in range(k):
        if i:
            term *= lam / i
        total += term
    return max(0.0, 1.0 - total)


def pois_eq(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)


def nb_eq(k, mu, r=None):
    """P(X == k) for a negative binomial with mean mu and size r (wider than Poisson)."""
    r = DISPERSION if r is None else r
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mu)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1 - p))


def nb_ge(k, mu, r=None):
    return max(0.0, 1.0 - sum(nb_eq(i, mu, r) for i in range(max(k, 0))))


def over_under_probs(point, lam):
    """(p_over, p_under, p_push) for a line like 1.5 or 2.0, using the negative binomial."""
    if float(point).is_integer():
        k = int(point)
        p_push = nb_eq(k, lam)
        p_over = nb_ge(k + 1, lam)
        return p_over, 1 - p_over - p_push, p_push
    p_over = nb_ge(math.floor(point) + 1, lam)
    return p_over, 1 - p_over, 0.0


def american_to_decimal(price):
    return 1 + (price / 100 if price > 0 else 100 / abs(price))


def implied(price):
    return 1 / american_to_decimal(price)


def no_vig(over_price, under_price):
    io, iu = implied(over_price), implied(under_price)
    return io / (io + iu)


# ======================================================================= names
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", " ", s.replace("'", "").replace(".", ""))
    parts = [p for p in s.split() if p not in SUFFIXES]
    return " ".join(parts)


def same_team(odds_team, sched_team):
    """Odds API uses 'Los Angeles Clippers'; NBA uses city 'LA' + name 'Clippers'."""
    return norm_name(odds_team).endswith(norm_name(sched_team["name"]))


# ======================================================================= io
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def http_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh) nba-threes-engine",
        "Accept": "application/json",
        "Referer": "https://www.nba.com/",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404, 422):
                raise
            err = e
        except Exception as e:  # network blips
            err = e
        time.sleep(2 * (attempt + 1))
    raise err


# ======================================================================= schedule + box scores
def parse_schedule(raw):
    games = []
    for day in raw["leagueSchedule"]["gameDates"]:
        for g in day["games"]:
            if not g["gameId"].startswith("002"):  # regular season only (NBA Cup games are 002 too)
                continue
            games.append({
                "gameId": g["gameId"],
                "status": int(g["gameStatus"]),  # 1 scheduled, 2 live, 3 final
                "tipUTC": g.get("gameDateTimeUTC") or g.get("gameDateUTC"),
                "date": (g.get("gameDateEst") or "")[:10],
                "home": {"tri": g["homeTeam"]["teamTricode"], "name": g["homeTeam"]["teamName"],
                         "city": g["homeTeam"]["teamCity"]},
                "away": {"tri": g["awayTeam"]["teamTricode"], "name": g["awayTeam"]["teamName"],
                         "city": g["awayTeam"]["teamCity"]},
            })
    return games


def parse_minutes(s):
    """'PT32M10.00S' -> 32.17"""
    m = re.match(r"PT(\d+)M([\d.]+)S", s or "")
    return round(int(m.group(1)) + float(m.group(2)) / 60, 2) if m else 0.0


def slim_box(raw, date):
    g = raw["game"]
    players = []
    for side in ("homeTeam", "awayTeam"):
        team = g[side]
        for p in team.get("players", []):
            st = p.get("statistics", {})
            mins = parse_minutes(st.get("minutes"))
            players.append({
                "id": str(p["personId"]),
                "name": p.get("name") or f"{p.get('firstName','')} {p.get('familyName','')}".strip(),
                "team": team["teamTricode"],
                "played": p.get("played") == "1" and mins > 0,
                "min": mins,
                "fg3a": int(st.get("threePointersAttempted", 0)),
                "fg3m": int(st.get("threePointersMade", 0)),
            })
    return {"gameId": g["gameId"], "date": date, "players": players}


def update_boxscores(games):
    os.makedirs(BOX_DIR, exist_ok=True)
    added = 0
    for g in games:
        path = os.path.join(BOX_DIR, g["gameId"] + ".json")
        if g["status"] != 3 or os.path.exists(path):
            continue
        try:
            raw, _ = http_json(BOX_URL.format(g["gameId"]))
        except Exception as e:
            print(f"  box score {g['gameId']} not ready: {e}")
            continue
        save_json(path, slim_box(raw, g["date"]))
        added += 1
    return added


def load_history():
    """{player_id: [(date, fg3a, fg3m), ...] played games only, oldest first}, plus name index."""
    hist, names = {}, {}
    if not os.path.isdir(BOX_DIR):
        return hist, names
    for fn in sorted(os.listdir(BOX_DIR)):
        box = load_json(os.path.join(BOX_DIR, fn), None)
        if not box:
            continue
        for p in box["players"]:
            names[norm_name(p["name"])] = (p["id"], p["team"], p["name"])
            if p["played"]:
                hist.setdefault(p["id"], []).append((box["date"], p["fg3a"], p["fg3m"]))
    for v in hist.values():
        v.sort()
    return hist, names


# ======================================================================= model
def project(games, prior):
    """Expected made threes (distribution mean) from this season's played games before tonight.

    games: [(date, fg3a, fg3m)] played games before the game being projected.
    prior: {"g","a","m"} last-season totals for this player, or None.
    Returns None when there isn't enough to go on.
    """
    n = len(games)
    if prior is None and n < MIN_GAMES_NO_PRIOR:
        return None
    sum_a = sum(g[1] for g in games)
    sum_m = sum(g[2] for g in games)
    if prior and prior["g"] > 0:
        prior_apg, k = prior["a"] / prior["g"], PRIOR_GAMES
        prior_pct = (prior["m"] + LEAGUE_PCT * PRIOR_ATT) / (prior["a"] + PRIOR_ATT)
    else:
        prior_apg, k, prior_pct = 0.0, 0, LEAGUE_PCT
    season_apg = (prior_apg * k + sum_a) / (k + n)
    if n >= 5:
        recent = games[-LAST_N:]
        recent_apg = sum(g[1] for g in recent) / len(recent)
    else:
        recent_apg = season_apg
    att = 0.5 * recent_apg + 0.5 * season_apg
    pct = (sum_m + prior_pct * PRIOR_ATT) / (sum_a + PRIOR_ATT)
    return {"lam": att * pct, "att": att, "pct": pct, "n": n}


# ======================================================================= odds
def fetch_odds(api_key, games_today, today):
    """Pull player_threes for each not-yet-tipped game. Returns (rows, status)."""
    status = {}
    events, hdr = http_json(f"{ODDS_BASE}/events", {"apiKey": api_key})
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    snap_dir = os.path.join(ODDS_DIR, today)
    for ev in events:
        tip = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        if tip <= now:
            continue
        match = next((g for g in games_today
                      if same_team(ev["home_team"], g["home"]) and same_team(ev["away_team"], g["away"])), None)
        if not match:
            continue
        data, hdr = http_json(f"{ODDS_BASE}/events/{ev['id']}/odds", {
            "apiKey": api_key, "regions": "us", "markets": "player_threes", "oddsFormat": "american"})
        status = {"credits_used": hdr.get("x-requests-used") or hdr.get("X-Requests-Used"),
                  "credits_remaining": hdr.get("x-requests-remaining") or hdr.get("X-Requests-Remaining")}
        save_json(os.path.join(snap_dir, f"{match['gameId']}.json"),
                  {"pulled_at": now.isoformat(timespec="seconds"), "event": data})
        out.append((match, data))
    return out, status


def collect_lines(event_odds):
    """{(player_name, point): {book: {"over": price, "under": price}}}"""
    lines = {}
    for bm in event_odds.get("bookmakers", []):
        for mk in bm.get("markets", []):
            if mk["key"] != "player_threes":
                continue
            for o in mk["outcomes"]:
                side = o["name"].lower()
                if side not in ("over", "under") or o.get("point") is None:
                    continue
                key = (o["description"], float(o["point"]))
                lines.setdefault(key, {}).setdefault(bm["key"], {})[side] = o["price"]
    return lines


def evaluate_line(lam, book_prices):
    """Model vs market for one player line. Returns dict or None if no two-sided book."""
    pairs = {b: p for b, p in book_prices.items() if "over" in p and "under" in p}
    if not pairs:
        return None
    nv_over = sum(no_vig(p["over"], p["under"]) for p in pairs.values()) / len(pairs)
    best_under = max(((p["under"], b) for b, p in book_prices.items() if "under" in p),
                     key=lambda x: american_to_decimal(x[0]))
    best_over = max(((p["over"], b) for b, p in book_prices.items() if "over" in p),
                    key=lambda x: american_to_decimal(x[0]))
    return {"nv_over": nv_over, "books": len(pairs),
            "best_over": {"price": best_over[0], "book": best_over[1]},
            "best_under": {"price": best_under[0], "book": best_under[1]}}


def choose_pick(point, lam, market):
    p_over, p_under, p_push = over_under_probs(point, lam)
    nv_over = market["nv_over"]
    # compare on a no-push basis so integer lines are fair to both sides
    live = 1 - p_push
    m_over = p_over / live if live > 0 else 0.5
    best = None
    for side, m_prob, nv, price in (("over", m_over, nv_over, market["best_over"]["price"]),
                                     ("under", 1 - m_over, 1 - nv_over, market["best_under"]["price"])):
        edge = m_prob - nv
        ev = m_prob * american_to_decimal(price) - 1
        if edge >= EDGE_BAR and ev > 0 and (best is None or edge > best["edge"]):
            best = {"side": side, "edge": round(edge, 4), "ev": round(ev, 4), "price": price}
    return p_over, best


# ======================================================================= logging + grading
def line_id(date, game_id, pid, point):
    return f"{date}|{game_id}|{pid}|{point:g}"


def log_tonight(pulled, hist, names, prior, today):
    log = load_json(LOG_PATH, [])
    by_id = {e["id"]: e for e in log}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    unmatched, rows = [], []
    for game, event in pulled:
        for (pname, point), books in collect_lines(event).items():
            hit = names.get(norm_name(pname))
            pid = hit[0] if hit else None
            if pid is None:
                pr_hit = next((k for k, v in prior.items() if norm_name(v["name"]) == norm_name(pname)), None)
                pid = pr_hit
            if pid is None:
                unmatched.append(pname)
                continue
            past = [g for g in hist.get(pid, []) if g[0] < game["date"]]
            proj = project(past, prior.get(pid))
            market = evaluate_line(proj["lam"] if proj else 0, books)
            if not proj or not market:
                continue
            p_over, pick = choose_pick(point, proj["lam"], market)
            lid = line_id(game["date"], game["gameId"], pid, point)
            entry = by_id.get(lid, {"id": lid, "first_logged": now})
            entry.update({
                "date": game["date"], "gameId": game["gameId"], "tipUTC": game["tipUTC"],
                "matchup": f"{game['away']['tri']} @ {game['home']['tri']}",
                "player": hit[2] if hit else prior[pid]["name"], "pid": pid,
                "team": hit[1] if hit else prior[pid].get("team", ""),
                "point": point, "lam": round(proj["lam"], 3), "att": round(proj["att"], 2),
                "pct": round(proj["pct"], 3), "games": proj["n"],
                "p_over": round(p_over, 4), "nv_over": round(market["nv_over"], 4),
                "books": market["books"], "best_over": market["best_over"],
                "best_under": market["best_under"], "pick": pick,
                "model": MODEL_VERSION, "last_logged": now,
            })
            by_id[lid] = entry
            rows.append(entry)
    log = sorted(by_id.values(), key=lambda e: (e["date"], e["gameId"], e["player"], e["point"]))
    save_json(LOG_PATH, log)
    return rows, sorted(set(unmatched))


def grade_entry(entry, box):
    p = next((x for x in box["players"] if x["id"] == entry["pid"]), None)
    if p is None or not p["played"]:
        entry.update({"actual": None, "result": "V", "units": 0.0})
        return
    entry["actual"] = p["fg3m"]
    pick = entry.get("pick")
    if not pick:
        entry["result"] = None
        return
    if p["fg3m"] == entry["point"]:
        res = "P"
    elif (p["fg3m"] > entry["point"]) == (pick["side"] == "over"):
        res = "W"
    else:
        res = "L"
    entry["result"] = res
    entry["units"] = {"W": round(american_to_decimal(pick["price"]) - 1, 4), "L": -1.0, "P": 0.0}[res]


def grade_all():
    log = load_json(LOG_PATH, [])
    graded = 0
    for e in log:
        if "actual" in e:
            continue
        box = load_json(os.path.join(BOX_DIR, e["gameId"] + ".json"), None)
        if box:
            grade_entry(e, box)
            graded += 1
    if graded:
        save_json(LOG_PATH, log)
    return graded


# ======================================================================= main
def main(argv):
    if len(argv) < 2 or argv[1] != "run":
        print(__doc__)
        return 2
    want_odds = "--odds" in argv
    today = dt.datetime.now(ET).date().isoformat()
    status = load_json(STATUS_PATH, {})

    raw, _ = http_json(SCHED_URL)
    games = parse_schedule(raw)
    print(f"schedule: {len(games)} regular-season games, "
          f"{sum(g['status'] == 3 for g in games)} final")
    print(f"box scores added: {update_boxscores(games)}")
    print(f"lines graded: {grade_all()}")

    if want_odds:
        key = os.environ.get("ODDS_API_KEY")
        if not key:
            print("no ODDS_API_KEY set; skipping odds")
        else:
            prior = load_json(PRIOR_PATH, {})
            hist, names = load_history()
            tonight = [g for g in games if g["date"] == today and g["status"] == 1]
            pulled, st = fetch_odds(key, tonight, today)
            status.update(st)
            rows, unmatched = log_tonight(pulled, hist, names, prior, today)
            picks = [r for r in rows if r["pick"]]
            print(f"games with lines: {len(pulled)}; lines logged: {len(rows)}; picks: {len(picks)}")
            if unmatched:
                print(f"unmatched names: {', '.join(unmatched)}")
            save_json(TODAY_PATH, {"date": today, "games": len(pulled), "lines": len(rows),
                                   "picks": len(picks), "unmatched": unmatched})

    status["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    status["model"] = MODEL_VERSION
    status["edge_bar"] = EDGE_BAR
    save_json(STATUS_PATH, status)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
