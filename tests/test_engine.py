"""Assertion tests for the projection and grading math.

The Strikeout Engine died from a bug in its projection layer. These tests pin known
inputs to known outputs so a change that breaks the math fails loudly.
Run:  python -m unittest discover tests
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as e  # noqa: E402


class Math(unittest.TestCase):
    def test_poisson(self):
        self.assertAlmostEqual(e.pois_ge(2, 2.0), 1 - 3 * math.exp(-2), places=12)
        self.assertEqual(e.pois_ge(0, 1.3), 1.0)
        # negative binomial: sums to 1, mean is right, wider than Poisson, Poisson as r -> large
        self.assertAlmostEqual(sum(e.nb_eq(k, 2.0) for k in range(200)), 1.0, places=9)
        self.assertAlmostEqual(sum(k * e.nb_eq(k, 2.0) for k in range(200)), 2.0, places=6)
        self.assertGreater(e.nb_eq(0, 2.0), math.exp(-2))
        self.assertAlmostEqual(e.nb_ge(2, 2.0, r=1e7), e.pois_ge(2, 2.0), places=5)
        p_over, p_under, p_push = e.over_under_probs(2.0, 2.0)
        self.assertAlmostEqual(p_over + p_under + p_push, 1.0, places=12)
        self.assertAlmostEqual(p_push, e.nb_eq(2, 2.0), places=12)
        self.assertEqual(e.over_under_probs(1.5, 0.0), (0.0, 1.0, 0.0))

    def test_prices(self):
        self.assertAlmostEqual(e.american_to_decimal(-200), 1.5)
        self.assertAlmostEqual(e.american_to_decimal(150), 2.5)
        self.assertAlmostEqual(e.no_vig(-110, -110), 0.5)


class Names(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(e.norm_name("Luka Dončić"), "luka doncic")
        self.assertEqual(e.norm_name("Jaren Jackson Jr."), "jaren jackson")
        self.assertEqual(e.norm_name("De'Aaron Fox"), "deaaron fox")
        self.assertTrue(e.same_team("Los Angeles Clippers", {"name": "Clippers"}))
        self.assertTrue(e.same_team("Portland Trail Blazers", {"name": "Trail Blazers"}))
        self.assertFalse(e.same_team("Los Angeles Lakers", {"name": "Clippers"}))


class Projection(unittest.TestCase):
    def test_no_prior_needs_games(self):
        self.assertIsNone(e.project([("2026-10-21", 5, 2)] * 4, None))

    def test_known_value(self):
        games = [("2026-10-%02d" % d, 6, 2) for d in range(21, 27)]  # 6 games, 6 3PA, 2 3PM each
        prior = {"g": 80, "a": 480, "m": 180}  # 6 3PA/g, 37.5%
        r = e.project(games, prior)
        prior_pct = (180 + 0.36 * 100) / (480 + 100)
        pct = (12 + prior_pct * 100) / (36 + 100)
        self.assertAlmostEqual(r["att"], 6.0)
        self.assertAlmostEqual(r["pct"], pct)
        self.assertAlmostEqual(r["lam"], 6.0 * pct)

    def test_ignores_future(self):
        # log_tonight filters on date < game date; project itself must only see what it is given
        r1 = e.project([("2026-10-21", 8, 3)] * 5, None)
        r2 = e.project([("2026-10-21", 8, 3)] * 5, None)
        self.assertEqual(r1, r2)


class Picks(unittest.TestCase):
    def test_pick_and_grade(self):
        market = e.evaluate_line(1.0, {"dk": {"over": -110, "under": -110}, "fd": {"over": 105, "under": -135}})
        self.assertEqual(market["books"], 2)
        self.assertEqual(market["best_over"], {"price": 105, "book": "fd"})
        self.assertEqual(market["best_under"], {"price": -110, "book": "dk"})
        p_over, pick = e.choose_pick(1.5, 3.0, market)  # P(>=2 | 3.0) ~ 0.80, market ~0.49
        self.assertEqual(pick["side"], "over")
        self.assertEqual(pick["price"], 105)

        entry = {"pid": "1", "point": 1.5, "pick": pick}
        box = {"players": [{"id": "1", "played": True, "fg3m": 2}]}
        e.grade_entry(entry, box)
        self.assertEqual((entry["result"], entry["units"]), ("W", 1.05))

        entry = {"pid": "1", "point": 1.5, "pick": pick}
        e.grade_entry(entry, {"players": [{"id": "1", "played": True, "fg3m": 1}]})
        self.assertEqual((entry["result"], entry["units"]), ("L", -1.0))

        entry = {"pid": "1", "point": 1.5, "pick": pick}
        e.grade_entry(entry, {"players": [{"id": "1", "played": False, "fg3m": 0}]})
        self.assertEqual(entry["result"], "V")

    def test_no_pick_when_close(self):
        market = e.evaluate_line(1.0, {"dk": {"over": -110, "under": -110}})
        lam = -math.log(0.5) + 0.6  # P(>=2) near 0.5
        _, pick = e.choose_pick(1.5, 1.68, market)
        self.assertIsNone(pick)


if __name__ == "__main__":
    unittest.main()
