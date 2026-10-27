# NBA Threes Engine — HANDOFF

Started 2026-10-27. A Strikeout-Engine-style tool for NBA made-threes props. It logs every threes line before tip, projects each player, flags picks that clear a locked bar, and grades them the next morning. **No real money until the forward test clears the bar below.**

## Status

- **Built and tested; not yet running.** Code, tests, page and the GitHub schedule are done. Nothing has hit the live NBA or odds feeds yet, because the workspace it was built in couldn't reach cdn.nba.com. The first real run is the real test.
- **27 Oct 2026 (Code):** setup steps 1, 2 and 4 done. Repo: https://github.com/oldstone07/nba-threes (public, same account as strikeout-engine). Pages: https://oldstone07.github.io/nba-threes/. The `daily` workflow is active, so the cron runs start on their own. Tests pass locally (8/8).
- **Next:** Tim adds the `ODDS_API_KEY` secret (step 3), then does one manual run (step 5). Until the secret exists, scheduled runs log `no ODDS_API_KEY set; skipping odds` and only fetch NBA data. If you reuse the MLB key, the live one is the one in `~/.config/mlb-scanner/odds_key`; the old app-container key is deactivated.
- **Watch:** a plain `curl` from Tim's Mac to cdn.nba.com returned 403 on 27 Oct. The engine sends its own User-Agent/Referer, so it may still work, but the first Actions log will tell. If the schedule step 403s, the feed is blocking automated requests. Decide then; don't jump straight to header spoofing.

## Setup (do these in order)

1. Put this folder at `~/Workshop/Engines/NBA Threes/` and open a Code session there.
2. Create a GitHub repo for it (same account as strikeout-engine) and push this folder.
3. Add the repo secret `ODDS_API_KEY` (Settings → Secrets and variables → Actions). Tim pastes the key there himself; it never goes in a chat or a file.
4. Turn on GitHub Pages from the main branch. The page is `index.html`.
5. Actions → daily → Run workflow (odds on). Check the log for:
   - `schedule: N regular-season games, M final` with M > 0
   - `box scores added:` a number > 0 on the first run (it backfills the season)
   - `games with lines:` > 0 and `lines logged:` > 0
   - `unmatched names:` should be short. Any name listed there needs a fix in `norm_name`.
   - `x-requests-remaining` in `data/status.json`
6. If the NBA feed refuses GitHub's servers, run `python engine.py run --odds` on the Mac with launchd instead (the same way On-Site Rates used to run).

## How it works

`engine.py` (stdlib Python, no installs):

- **NBA data:** schedule from `cdn.nba.com/static/json/staticData/scheduleLeagueV2.json`; box scores from `cdn.nba.com/static/json/liveData/boxscore/boxscore_<gameId>.json`. Each finished game is cached slim in `data/boxscores/`.
- **Odds:** The Odds API `player_threes`, region `us`, one pull per game before tip. Raw snapshots are saved in `data/odds/<date>/` — that is the price history the backtest never had.
- **Projection (v1):** attempts = half last-10 average, half season average (last season counts as 10 games of history); 3P% regressed toward 36% with a 100-attempt prior seeded from last season; made threes follow a negative binomial (size 12) instead of Poisson.
- **Pick rule (locked):** bet a side only when model probability minus the no-vig market probability is at least 5 points **and** the bet is +EV at the best available price. Over or under.
- **Log:** every line goes in `data/log.json`, picks or not, so calibration can be checked on everything. Re-runs before tip update the same row; they never duplicate it.
- **Grading:** next morning. Player didn't play → void. Flat 1 unit at the best price.
- **Schedule:** `.github/workflows/daily.yml` runs tests, then the engine, at 7 AM ET (grade only) and 5:45 PM EDT / 4:45 PM EST (odds), then commits `data/`. Weekend afternoon tips can be missed by the evening run; that is acceptable for v1.

Credits: about one per game per night (plus whatever the events list costs). A 7-game night is about 7 credits; a month is roughly 200–250. Check whether the free plan's 500 covers it after the first week.

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
| `engine.py` | The engine |
| `index.html` | Scoreboard page for GitHub Pages |
| `.github/workflows/daily.yml` | The twice-daily schedule |
| `data/prior.json` | 2025-26 per-player 3PA/3PM, from shufinskiy/nba_data shot detail |
| `data/log.json` | Every logged line and its result |
| `tests/` | Assertion tests and the season replay |
| `threes_backtest.py` | The first, simpler three-season backtest |

## Open questions

- Is the Odds API key still on a paid plan, or is the free 500-credit plan enough?
- Which books does Tim bet on in Ohio? If it's only one or two, the "best price" should be limited to those.
- Should the evening run also cover early weekend tips (a second, earlier odds pull)?
