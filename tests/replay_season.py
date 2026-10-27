"""Replay the live model (engine.project) over a past season, using the season before as the prior.

Example:
  python tests/replay_season.py shotdetail_2025.csv prior_2024.json
Prints hit rate by model-probability bucket for Over 1.5. No prices, so this checks calibration only.
"""
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
import engine as e  # noqa: E402


def main(shots, prior_path):
    prior = json.load(open(prior_path))
    g = defaultdict(lambda: [0, 0, ""])
    with open(shots) as f:
        for r in csv.DictReader(f):
            if not r["GAME_ID"].startswith("2"):
                continue
            x = g[(r["PLAYER_ID"], r["GAME_ID"])]
            x[2] = r["GAME_DATE"]
            if r["SHOT_TYPE"].startswith("3PT"):
                x[0] += 1
                x[1] += int(r["SHOT_MADE_FLAG"])
    hist = defaultdict(list)
    for (pid, _), (a, m, d) in g.items():
        hist[pid].append((d, a, m))
    rows = []
    for pid, gl in hist.items():
        gl.sort()
        for i, (d, a, m) in enumerate(gl):
            proj = e.project(gl[:i], prior.get(pid))
            if proj:
                rows.append((e.nb_ge(2, proj["lam"]), m >= 2, i))
    print(f"{len(rows):,} projected player-games")
    for label, sel_fn in (("all games", lambda r: True), ("first 10 games", lambda r: r[2] < 10)):
        print(f"-- {label} --")
        for lo, up in ((0.5, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 1.01)):
            sel = [r for r in rows if sel_fn(r) and lo <= r[0] < up]
            if len(sel) >= 50:
                h = sum(r[1] for r in sel) / len(sel)
                mid = sum(r[0] for r in sel) / len(sel)
                print(f"  model {lo:.2f}-{min(up, 1):.2f}  avg {mid:.3f}  n={len(sel):>5}  hit {h:.3f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
