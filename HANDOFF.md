# NBA Threes Engine — HANDOFF

Started 2026-10-27. A Strikeout-Engine-style page for NBA made-threes props. Tim pulls lines by hand before tip (official = Odds API, free = SharpAPI DK/FD); it projects each player, flags picks that clear a locked bar, and grades them once ESPN has the box score. **No real money until the forward test clears the bar below.**

## Status

- **27 Oct 2026: switched to a browser page with Pull buttons, like the Strikeout Engine.** Tim wants to pull by hand each night, so `index.html` is now the whole engine. The GitHub schedule (`daily.yml`) is **disabled** (`disabled_manually`) and never ran. `engine.py` stays as the reference implementation and the source of the tests.
- Repo: https://github.com/oldstone07/nba-threes (public). Page: https://oldstone07.github.io/nba-threes/
- **Verified 27 Oct, local server:** the self-test passes; ESPN sync loaded 52 box scores from opening night (20 Oct); a free pull on real SharpAPI lines logged 41 lines across 4 games with 0 unmatched names; 5 of those lines were re-run through `engine.py` and matched exactly (lam, p_over, no-vig, pick). The official pull was tested with a mock Odds API response only: parsing, re-pull updates the same row, unmatched names get reported, credits are read, grading is right.
- **Not yet verified:** a real official pull with Tim's Odds API key. On the first one, check that `odds credits left` appears in the header. It reads the `x-requests-remaining` header; if the Odds API doesn't expose it to browsers, the page just won't show it.
- **27 Oct, model v2** (after Tim's first real official pull worked: 18 lines on BKN @ BOS, credits read fine). Two rule changes:
  - **Tim's books only:** DraftKings, FanDuel, BetMGM, Caesars (`williamhill_us`, paid Odds API plans only) and theScore (`espnbet`). The request uses `bookmakers=` (5 books = 1 region = 1 credit). bet365 isn't on the Odds API for the US. The first pull had priced picks at Bovada (offshore) and BetRivers.
  - **One pick per player per game:** the biggest edge counts; the others keep `pick_dropped` and `pick = null`.
  - The forward test counts v2 only. v1 rows stay in the log but are hidden from the game board.
- **Next (was):** Tim opens the page, adds both keys under Settings (Odds API = official; SharpAPI = free. The SharpAPI key is the one in `Engines/Promo EV/key.txt`), then pulls.

## Using it

1. Open the page. It syncs ESPN by itself on load: schedule, box scores for finished games, grading.
2. **⬡ Pull / Re-pull** (per game) or **⬡ Pull all (official):** Odds API `player_threes`, about 1 credit per game. This is the bet of record, and the only source the forward test counts.
3. **◇ Free / Free pull all:** SharpAPI, DraftKings + FanDuel main lines, free (12 requests/min; one request covers the whole slate). Saved in a separate list and scored separately under "Free-line picks"; never mixed into the forward test.
4. Re-pulling before tip updates the same row (`pulls` count, `last_logged`). The first pull's prices and pick are kept in `first`, so early vs late pulls can be compared later.
5. Games lock at tip.
6. **Download backup** now and then. Everything lives in this browser's IndexedDB (`nba-threes`) on the oldstone07.github.io origin, and clearing site data wipes it. Restore takes a backup file.

## How it works

`index.html` (no build, no installs), ported line for line from `engine.py` v1:

- **NBA data:** ESPN `site.api.espn.com` scoreboard (one call per day from `SEASON_START`; finished days are cached) and `summary?event=` box scores (cached slim). cdn.nba.com is blocked for browsers (CORS) and returned 403 to a plain curl, so ESPN replaced it. Players are matched by normalised name (`normName`), not ID.
- **Prior:** `data/prior.json` (2025-26 per-player 3PA/3PM), re-keyed by normalised name on load.
- **Projection (v1):** attempts = half last-10 average, half season average (last season counts as 10 games of history); 3P% regressed toward 36% with a 100-attempt prior seeded from last season; made threes follow a negative binomial (size 12) instead of Poisson.
- **Pick rule (locked, v2):** bet a side only when model probability minus the no-vig market probability is at least 5 points **and** the bet is +EV at the best available price among Tim's books (`BOOKS`). Over or under. At most one pick per player per game (biggest edge). `engine.py` is still v1 (all US books, no per-player limit).
- **Log:** every line, picks or not, so calibration can be checked on everything. Every book's prices are kept on the row (`prices`).
- **Grading:** automatic once ESPN has the box score. Player didn't play → void. Flat 1 unit at the best price.
- **Self-test:** the assertions from `tests/test_engine.py` run on every page load. If any fails, a red banner shows and the pull buttons are disabled.

Credits: about one per game per pull (the events list is free). A 7-game night is about 7 credits; re-pulls cost again.

## The bar (locked before any results)

Real money only after **150 graded picks** with **ROI of +5% or better**, and ROI positive in **both halves** of those 150 taken in date order. The page tracks this.

If the rule or the model changes, bump `MODEL_VERSION` in `engine.py`. Results from different versions are never mixed when judging the bar.

## Testing done

- `tests/test_engine.py`: assertion tests on the probability math, prices, name matching, projection (known input → known output) and grading. Run `python -m unittest discover tests`. They run before every scheduled engine run, so a broken projection stops the run instead of logging bad picks. This is the lesson from the Strikeout Engine's projection bug.
- `tests/replay_season.py`: replays the live model over a past season. The first replay showed the Poisson version ran 3–5 points too confident (worse early in the season). The negative-binomial size was fit on 2024-25 only, then checked on 2025-26:

| Model says over 1.5 | 2025-26 lines | Actual hit |
| --- | --- | --- |
| 50–60% (avg 54.8%) | 2,855 | 54.2% |
| 60–65% (avg 62.4%) | 1,081 | 62.3% |
| 65–70% (avg 67.3%) | 973 | 66.2% |
| 70–75% (avg 72.4%) | 921 | 73.1% |
| 75–80% (avg 77.1%) | 734 | 72.3% |
| 80%+ (avg 83.7%) | 564 | 85.5% |

Early season is still a little overconfident: in the first 10 games, the 50–60% bucket hit 49%. Watch the calibration table on the page through November.

- A full dry run (mock schedule, box scores and Odds API response in their documented shapes) logged lines, matched names, flagged a pick, updated without duplicating, and graded a win and a void correctly.

## Research behind it

- **Overs are the shaded side.** Across 428,529 graded NBA props at the closing line, blind overs returned -8.8% and blind unders -4.0% ([SickFade](https://sickfade.com/overs-vs-unders)). The engine looks at both sides.
- **Calibration isn't edge.** The model matches outcomes, but so do the books. Any edge lives in the gap to the price, which only the logged prices can show.
- **stats.nba.com blocks cloud servers**; cdn.nba.com live endpoints are reported open. If that turns out wrong from GitHub, run on the Mac.
- **Kalshi isn't an option in Ohio** (cease-and-desist; a federal judge declined to block enforcement in March 2026).
- **Price backtest (optional, later):** The Odds API has prop history back to May 2023 at 10 credits × markets × regions per event snapshot. Three seasons of `player_threes` ≈ 37,000 credits, so one month of the 100K plan ($59). Worth doing if the forward test looks promising, to get a bigger sample fast.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The engine: pull buttons, projection, log, grading, self-test (GitHub Pages) |
| `engine.py` | Original Python engine; reference implementation, and what `tests/` run against |
| `.github/workflows/daily.yml` | The old twice-daily schedule. Disabled on GitHub; re-enable in the Actions tab to go back to automatic |
| `data/prior.json` | 2025-26 per-player 3PA/3PM, from shufinskiy/nba_data shot detail |
| `data/log.json` | Unused since the browser switch (the log lives in the browser; use Download backup) |
| `tests/` | Assertion tests and the season replay |
| `threes_backtest.py` | The first, simpler three-season backtest |

## Open questions

- Is the Odds API key still on a paid plan, or is the free 500-credit plan enough?
- Which books does Tim bet on in Ohio? If it's only one or two, the "best price" should be limited to those.
- Pull timing: early vs close to tip. Every row keeps its first-pull prices, so the log can answer this after a few weeks.

## Session log

- **31 Oct 2026, data read** (backup 2026-10-31): 136 graded, 74-62, +3.96u, +2.9% ROI after a +9.9u night on 30 Oct. Wins: 74 actual vs 69.7 market-expected (SD 5.7) vs 82.6 model-expected, so results sit between market and model, closer to the market. Brier over 314 lines is now tied (model 0.2443 vs market 0.2437, z 0.13). The cuts are all inside noise: unders 46-32 (+6.8%) vs overs 28-30; edges of 12%+ went 11-14 (-18%); line 2.5 +27% vs line 1.5 -13%. With ~18 cuts, one or two will look real by chance, so don't promote any of them to a rule. Watch unders and the big-edge losses.
- **30 Oct 2026, data read from Tim's backup** (`~/Downloads/nba-threes-backup-2026-10-30.json`): 87 graded official v2 picks, 42-45, -5.96u, ROI -6.8% (luck SD about ±9u, so the ROI itself is noise). The telling number: the model expected 52.8 wins, the market's no-vig odds expected 44.0, and 42 happened, about 2.4 SD under the model and right on the market. Brier over 200 lines: model 0.2436 vs market 0.2399 (market slightly better, z 0.7). The pick rate is about 45% of lines, because the model disagrees with the market by 6 points on average. Caesars never appears (free Odds API plan). 470 credits left before the 1 Nov reset. Early read agrees with the July scout: a projection model doesn't beat the market. Not conclusive yet.
- **30 Oct 2026:** Tim is pulling nightly. Early results swing hard (expected: about ±5 units of luck on a 20-pick night, ±13 units over 150 picks). A Promo-EV-style luck band (the range the record should fall in from luck alone) was offered as an idea, not built; Tim hasn't asked for it. Next: keep pulling; download a backup weekly; the Odds API credits reset 1 Nov.
- **28 Oct 2026:** Tim reports the first full night (27 Oct) logged with official pulls. Plan: forward only, one Pull all a night. Historical odds need a paid Odds API plan, so no backtest on the free 500 (resets 1 Nov). Tim tracks CLV in Pikkit, so the page won't add it. Open item: 150 picks is noise-level (±8 ROI pts), so it's a checkpoint; a real verdict needs ~1,000–1,600 picks. Tim hasn't decided whether to show that on the page.
- **27 Oct 2026:** repo created and pushed, Pages on. Tim chose manual pulls, so the engine was ported into `index.html` with official + free pulls (per game and all), ESPN data, in-page self-test, IndexedDB storage and backup/restore. GitHub schedule disabled.
