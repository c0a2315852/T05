"""CSVの読み書き。形式は README の「CSV仕様」を参照。"""
from __future__ import annotations

import csv
import os

from .model import DEPOT, Problem, skey


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.reader(f) if any(c.strip() for c in r)]


def load_problem(folder: str, mode: str = "actual") -> Problem:
    """フォルダ内の5つのCSVから問題を読み込む。mode は使う荷量('actual' か 'forecast')。"""
    p = lambda name: os.path.join(folder, name)
    forecast, actual = {}, {}
    for r in _read(p("sites.csv"))[1:]:
        forecast[r[0].strip()] = int(float(r[1]))
        actual[r[0].strip()] = int(float(r[2]))
    capacity, fixed_first = {}, {}
    for r in _read(p("vehicles.csv"))[1:]:
        v = r[0].strip()
        capacity[v] = int(float(r[1]))
        fixed_first[v] = r[2].strip() if len(r) > 2 and r[2].strip() else None
    limits = {r[0].strip(): int(float(r[1])) for r in _read(p("destinations.csv"))[1:]}
    rows = _read(p("travel_time.csv"))
    cols = [c.strip() for c in rows[0][1:]]
    tt = {}
    for r in rows[1:]:
        a = r[0].strip()
        for b, x in zip(cols, r[1:]):
            tt[a, b] = float(x)
    initial = {v: [] for v in capacity}
    for r in _read(p("initial_assignment.csv"))[1:]:
        v, s = r[0].strip(), r[1].strip()
        if v not in initial:
            raise ValueError(f"initial_assignment.csv: 未定義の車両 {v}")
        initial[v].append(s)
    prob = Problem(dict(forecast), capacity, fixed_first, limits, tt, initial, forecast, actual)
    validate(prob)
    return prob.with_loads(mode)


def validate(prob: Problem) -> None:
    nodes = [DEPOT] + list(prob.forecast) + list(prob.limits)
    for a in nodes:
        for b in nodes:
            if (a, b) not in prob.tt:
                raise ValueError(f"travel_time.csv に {a}->{b} がありません")
    seen = [s for ss in prob.initial.values() for s in ss]
    if sorted(seen, key=skey) != sorted(prob.forecast, key=skey):
        raise ValueError("initial_assignment.csv: すべての拠点をちょうど1回ずつ割り当ててください")
    for v, f in prob.fixed_first.items():
        if f is not None and f not in prob.initial[v]:
            raise ValueError(f"車両{v}の最初の拠点{f}が、初期割当で{v}に入っていません")


def write_problem(folder: str, prob: Problem) -> None:
    os.makedirs(folder, exist_ok=True)

    def w(name, rows):
        with open(os.path.join(folder, name), "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)

    w("sites.csv", [["site_id", "forecast_kg", "actual_kg"]] +
      [[s, prob.forecast[s], prob.actual[s]] for s in sorted(prob.forecast, key=skey)])
    w("vehicles.csv", [["vehicle_id", "capacity_kg", "fixed_first_site"]] +
      [[v, prob.capacity[v], prob.fixed_first.get(v) or ""] for v in prob.vehicles])
    w("destinations.csv", [["dest_id", "limit_kg"]] + [[d, prob.limits[d]] for d in prob.dests])
    nodes = [DEPOT] + sorted(prob.forecast, key=skey) + prob.dests
    w("travel_time.csv", [[""] + nodes] + [[a] + [repr(prob.tt[a, b]) for b in nodes] for a in nodes])
    w("initial_assignment.csv", [["vehicle_id", "site_id"]] +
      [[v, s] for v in prob.vehicles for s in prob.initial[v]])
