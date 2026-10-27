"""Quick 3PM backtest: projected made threes vs actual, by model-probability bucket.

Model (deliberately simple, only uses games before the one being predicted):
  attempts  = 0.5 * last-10-game 3PA avg + 0.5 * season-to-date 3PA avg
  3P%       = season-to-date makes/attempts regressed toward 36% with a 100-attempt prior
  made 3s   ~ Poisson(attempts * 3P%)
Players need 10+ prior games that season. Regular season only.
"""
import csv, math, sys
from collections import defaultdict

LEAGUE_PCT, PRIOR_ATT, MIN_GAMES = 0.36, 100, 10


def load(path):
    games = defaultdict(lambda: [0, 0, ""])  # (player, game) -> [3PA, 3PM, date]
    names = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if not row["GAME_ID"].startswith("2"):  # regular season ids look like 22300018
                continue
            key = (row["PLAYER_ID"], row["GAME_ID"])
            g = games[key]
            g[2] = row["GAME_DATE"]
            names[row["PLAYER_ID"]] = row["PLAYER_NAME"]
            if row["SHOT_TYPE"].startswith("3PT"):
                g[0] += 1
                g[1] += int(row["SHOT_MADE_FLAG"])
    by_player = defaultdict(list)
    for (pid, gid), (a, m, d) in games.items():
        by_player[pid].append((d, gid, a, m))
    for v in by_player.values():
        v.sort()
    return by_player


def pois_ge(k, lam):
    return 1 - sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k))


def run(path, label):
    rows = []
    for pid, gl in load(path).items():
        tot_a = tot_m = 0
        for i, (d, gid, a, m) in enumerate(gl):
            if i >= MIN_GAMES:
                last10 = sum(x[2] for x in gl[i - 10:i]) / 10
                season = tot_a / i
                att = 0.5 * last10 + 0.5 * season
                pct = (tot_m + LEAGUE_PCT * PRIOR_ATT) / (tot_a + PRIOR_ATT)
                lam = att * pct
                rows.append((pois_ge(2, lam), m >= 2, pois_ge(3, lam), m >= 3))
            tot_a += a
            tot_m += m
    print(f"\n=== {label}: {len(rows):,} player-games ===")
    for line, pi, hi in (("1.5", 0, 1), ("2.5", 2, 3)):
        print(f"-- Over {line} --")
        print(f"{'model prob':>12} {'n':>7} {'hit%':>7} {'break-even price':>18}")
        for lo, up in ((0.5, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 1.01)):
            sel = [r for r in rows if lo <= r[pi] < up]
            if len(sel) < 50:
                continue
            h = sum(r[hi] for r in sel) / len(sel)
            be = -100 * h / (1 - h) if h > 0.5 else 100 * (1 - h) / h
            print(f"{lo:.2f}-{min(up,1):.2f} {len(sel):>7} {h*100:>6.1f}% {be:>17.0f}")
        sel = [r for r in rows if r[pi] >= 0.70]
        if sel:
            h = sum(r[hi] for r in sel) / len(sel)
            print(f"  >=0.70 all: n={len(sel)} hit={h*100:.1f}% break-even={-100*h/(1-h):.0f}")


if __name__ == "__main__":
    for p, lab in zip(sys.argv[1::2], sys.argv[2::2]):
        run(p, lab)
