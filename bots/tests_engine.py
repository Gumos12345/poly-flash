#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy jednostkowe silnika (bez sieci): drabinka, fill, opłata, przewaga, model, PnL, serializacja.
Uruchomienie: python3 -m unittest -q tests_engine.py  (albo python3 tests_engine.py)"""
import math
import os
import tempfile
import unittest

import poly_dryrun_engine as E


class TestLadder(unittest.TestCase):
    def test_zamowiona_drabinka_50pct(self):
        lad = dict(E.DEFAULT_LADDER)
        self.assertAlmostEqual(E.ladder_stake(lad, 50.0)[0], 1.25, places=6)
        self.assertAlmostEqual(E.ladder_stake(lad, 75.0)[0], 1.875, places=6)
        self.assertAlmostEqual(E.ladder_stake(lad, 112.5)[0], 2.8125, places=6)

    def test_reset_nie_rosnie_ponizej_progu(self):
        lad = dict(E.DEFAULT_LADDER)
        self.assertAlmostEqual(E.ladder_stake(lad, 74.9)[0], 1.25, places=6)   # jeszcze nie 75
        self.assertAlmostEqual(E.ladder_stake(lad, 76.0)[0], 1.875, places=6)

    def test_up_nie_spada(self):
        lad = dict(E.DEFAULT_LADDER, down=False)
        st_up, _ = E.ladder_stake(lad, 40.0, peak_level=2)   # kapitał spadł, poziom zapamiętany
        self.assertAlmostEqual(st_up, 2.8125, places=6)

    def test_ud_spada(self):
        lad = dict(E.DEFAULT_LADDER, down=True)
        self.assertAlmostEqual(E.ladder_stake(lad, 40.0)[0], 1.25, places=6)

    def test_proc_kapitalu(self):
        lad = dict(E.DEFAULT_LADDER, kind="prop", pct=0.025)
        self.assertAlmostEqual(E.ladder_stake(lad, 100.0)[0], 2.5, places=6)

    def test_krok_2pct(self):
        lad = dict(E.DEFAULT_LADDER, step_bank=0.02, step_stake=0.02)
        # 50 -> po 1 kroku (+2%) stawka 1.25*1.02
        self.assertAlmostEqual(E.ladder_stake(lad, 51.0)[0], 1.25 * 1.02, places=6)

    def test_limit_max_stake(self):
        lad = dict(E.DEFAULT_LADDER, max_stake=3.0)
        self.assertLessEqual(E.ladder_stake(lad, 100000.0)[0], 3.0)


class TestFill(unittest.TestCase):
    def test_walk_fill_jeden_poziom(self):
        sh, spent, avg = E.walk_fill([(0.5, 100.0)], 1.25)
        self.assertAlmostEqual(spent, 1.25, places=9)
        self.assertAlmostEqual(sh, 2.5, places=9)
        self.assertAlmostEqual(avg, 0.5, places=9)

    def test_walk_fill_poziomami(self):
        sh, spent, avg = E.walk_fill([(0.5, 1.0), (0.6, 10.0)], 1.25)
        self.assertAlmostEqual(spent, 1.25, places=9)      # 0.5 + 0.75
        self.assertAlmostEqual(sh, 1.0 + 0.75 / 0.6, places=9)
        self.assertAlmostEqual(avg, 1.25 / sh, places=9)
        self.assertGreater(avg, 0.5)                        # poślizg w górę

    def test_walk_fill_brak_plynnosci(self):
        sh, spent, _ = E.walk_fill([(0.5, 0.4)], 1.25)      # książka za cienka
        self.assertAlmostEqual(spent, 0.2, places=9)
        self.assertLess(spent, 1.25)

    def test_walk_sell_poziomami(self):
        got, avg = E.walk_sell([(0.7, 1.0), (0.6, 5.0)], 2.0)
        self.assertAlmostEqual(got, 0.7 + 0.6, places=9)
        self.assertAlmostEqual(avg, 0.65, places=9)


class TestFeeEdge(unittest.TestCase):
    def test_fee_szczyt_przy_pol(self):
        self.assertAlmostEqual(E.fee_ps(0.5), 0.07 * 0.25, places=9)   # 0.0175
        self.assertLess(E.fee_ps(0.9), E.fee_ps(0.5))

    def test_edge_netto_ujemny_gdy_cena_rownа_p(self):
        self.assertLess(E.net_edge(0.5, 0.5), 0.0)
        self.assertAlmostEqual(E.net_edge(0.60, 0.50), 0.10 - E.fee_ps(0.5), places=9)


class TestModel(unittest.TestCase):
    def _ctx(self, d, rem, sig=1e-4, tf="5m", mid=None):
        c = E.Ctx.__new__(E.Ctx)
        c.tf, c.rem, c.d = tf, rem, d
        c.sig = c.sig_s = c.sig_l = sig
        c.mid = {"Up": mid} if mid is not None else {"Up": None}
        return c

    def test_symetria(self):
        p, _ = E.model_probs(self._ctx(0.0, 150), "v1")
        self.assertAlmostEqual(p, 0.5, places=6)

    def test_monotonicznosc(self):
        p1, _ = E.model_probs(self._ctx(0.001, 150), "v1")
        p2, _ = E.model_probs(self._ctx(0.003, 150), "v1")
        self.assertGreater(p2, p1)
        self.assertLess(p2, 0.995)

    def test_shrink_ogranicza_pewnosc(self):
        c = self._ctx(0.05, 150, sig=5e-5)
        p_norm, _ = E.model_probs(c, "v1")
        self.assertLessEqual(p_norm, 0.5 + 0.5 * E.SHRINK + 1e-12)

    def test_t5_mniej_pewny_niz_normalny(self):
        c = self._ctx(0.001, 150, sig=1e-4)
        p1, _ = E.model_probs(c, "v1")
        p2, _ = E.model_probs(c, "v2")
        self.assertLess(p2, p1)

    def test_v3_miesza_z_rynkiem(self):
        c = self._ctx(0.0, 150, mid=0.80)
        p, _ = E.model_probs(c, "v3", w_mkt=0.5)
        self.assertAlmostEqual(p, 0.5 * 0.5 + 0.5 * 0.80, places=6)


class TestBook(unittest.TestCase):
    def test_pnl_wygrana_i_przegrana(self):
        v = dict(id=1, name="T", tfs=("5m",))
        b = E.VBook(v, 50.0)
        pos = dict(key="k", slug="s", asset="BTC", tf="5m", side="Up", end=0, start=0,
                   entry=0.5, shares=2.5, cost=1.30, stake=1.25, p=0.6, edge=0.1,
                   t_open=0.0, status="open", tp=None, sl=None, rem_at_open=200)
        b.positions["k"] = pos
        eng = E.Engine([v], "tmp_test", start_bank=50.0)
        eng.books[1].positions["k"] = dict(pos)
        bb = eng.books[1]
        eng._close(bb, dict(pos), 2.5 - 1.30, "WIN", 1.0, 10.0)
        self.assertAlmostEqual(bb.realized, 1.20, places=6)
        self.assertAlmostEqual(bb.equity(), 51.20, places=6)
        st, lvl = bb.stake_now()
        self.assertAlmostEqual(st, 1.25, places=6)      # 51.2 < 75 -> jeszcze poziom 0

    def test_drabinka_po_wzroscie(self):
        v = dict(id=1, name="T", tfs=("5m",))
        eng = E.Engine([v], "tmp_test2", start_bank=50.0)
        bb = eng.books[1]
        bb.realized = 25.5                                # kapitał 75.5 -> poziom 1
        st, lvl = bb.stake_now()
        self.assertEqual(lvl, 1)
        self.assertAlmostEqual(st, 1.875, places=6)

    def test_serializacja(self):
        v = dict(id=1, name="T", tfs=("5m",))
        b = E.VBook(v, 50.0)
        b.realized = 3.5
        b.closed = [{"pnl": 3.5, "entry": 0.5, "edge": 0.1, "tf": "5m", "asset": "BTC",
                     "exit": "WIN", "cost": 1.3, "hold": 10.0}]
        b2 = E.VBook(v, 50.0)
        b2.load(b.dump())
        self.assertAlmostEqual(b2.realized, 3.5, places=6)
        self.assertEqual(len(b2.closed), 1)
        s = b2.stats()
        self.assertEqual(s["n"], 1)
        self.assertEqual(s["wins"], 1)
        self.assertAlmostEqual(s["wr"], 100.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
