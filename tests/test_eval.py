"""机上実験の経路を、このプログラムの評価で再現できるかを確認する。"""
import os
import unittest

from t05route.data import load_problem
from t05route.model import Evaluator

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "sample9")


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.prob = load_problem(DATA, "actual")

    def test_collect_then_deliver_303(self):
        """以前の案(集荷後に納品): A 170分 + B 133.33分 = 303.33分"""
        ev = Evaluator(self.prob, "total").evaluate_sequences({
            "A": ["D", "1", "5", "2", "4", "9", "T", "M", "D"],
            "B": ["D", "3", "7", "8", "6", "M", "D"]})
        self.assertAlmostEqual(ev.routes["A"].time, 170.0, places=6)
        self.assertAlmostEqual(ev.routes["B"].time, 400 / 3, places=6)
        self.assertEqual(ev.n_viol, 0)

    def test_interleaved_255(self):
        """途中納品を許した案: A 165分 + B 90分 = 255分(厳密探索で最短と確認済み)"""
        ev = Evaluator(self.prob, "segment").evaluate_sequences({
            "A": ["D", "1", "5", "6", "2", "4", "T", "9", "M", "D"],
            "B": ["D", "3", "7", "8", "M", "D"]})
        self.assertAlmostEqual(ev.total_time, 255.0, places=6)
        self.assertEqual(ev.n_viol, 0)
        got = {d: sum(u for v in ev.amounts for dd, u in ev.amounts[v] if dd == d) for d in "TM"}
        self.assertEqual(got, {"T": 1471, "M": 1262})

    def test_255_violates_total_mode(self):
        """擬似コードどおり(総集荷量 <= 容量)だと、Aの総集荷量2433kgは容量超過になる"""
        ev = Evaluator(self.prob, "total").evaluate_sequences({
            "A": ["D", "1", "5", "6", "2", "4", "T", "9", "M", "D"],
            "B": ["D", "3", "7", "8", "M", "D"]})
        self.assertEqual(ev.cap_viol, 1)
        self.assertEqual(ev.excess_kg, 433)


if __name__ == "__main__":
    unittest.main()
