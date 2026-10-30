"""探索の性質の確認: 索引あり/なしで同じ結果になること、制約を守ること。"""
import os
import tempfile
import unittest

from t05route.data import load_problem
from t05route.gen import generate
from t05route.search import local_search

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "sample9")


def groups(assign):
    return {v: sorted(ss) for v, ss in assign.items()}


class TestSearch(unittest.TestCase):
    def check_valid(self, prob, ev):
        sites = sorted(s for ss in ev.assign.values() for s in ss)
        self.assertEqual(sites, sorted(prob.sites))            # 全拠点をちょうど1回ずつ
        for v, f in prob.fixed_first.items():
            if f:
                self.assertEqual(ev.routes[v].seq[1], f)       # 最初の拠点が固定されている
        for r in ev.routes.values():
            self.assertEqual(sorted(set(r.seq) & set(prob.dests)), sorted(n for n in r.seq if n in prob.dests))

    def test_sample9(self):
        prob = load_problem(DATA)
        b = local_search(prob, prob.initial, "total", False)
        i = local_search(prob, prob.initial, "total", True)
        self.check_valid(prob, b.ev)
        self.assertEqual(groups(b.ev.assign), groups(i.ev.assign))
        self.assertAlmostEqual(b.ev.total_time, i.ev.total_time, places=6)
        self.assertLessEqual(b.ev.total_time, 303.34)          # 初期割当より悪くならない

    def test_generated_same_result_and_fewer_candidates(self):
        for seed in range(5):
            with tempfile.TemporaryDirectory() as d:
                generate(d, n_sites=20, n_vehicles=3, seed=seed)
                prob = load_problem(d)
                b = local_search(prob, prob.initial, "total", False)
                i = local_search(prob, prob.initial, "total", True)
                self.check_valid(prob, i.ev)
                self.assertEqual(groups(b.ev.assign), groups(i.ev.assign), f"seed={seed}")
                self.assertAlmostEqual(b.ev.total_time, i.ev.total_time, places=6)
                self.assertLessEqual(i.stats.candidates_evaluated, b.stats.candidates_evaluated)

    def test_generate_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            generate(d1, 10, 2, seed=3)
            generate(d2, 10, 2, seed=3)
            for name in os.listdir(d1):
                with open(os.path.join(d1, name)) as f1, open(os.path.join(d2, name)) as f2:
                    self.assertEqual(f1.read(), f2.read())


if __name__ == "__main__":
    unittest.main()
