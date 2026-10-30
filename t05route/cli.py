"""コマンドライン。使い方は README を参照。"""
from __future__ import annotations

import argparse

from .data import load_problem
from .gen import generate
from .model import Eval, Problem
from .replan import replan
from .search import local_search


def describe(prob: Problem, ev: Eval) -> str:
    lines = []
    for v in prob.vehicles:
        r = ev.routes[v]
        amt = {i: u for i, (_, u) in enumerate(ev.amounts.get(v, []))}
        parts, vi = [], 0
        load, cap = 0, prob.capacity[v]
        for n in r.seq:
            if n in prob.limits:
                u = amt[vi]
                vi += 1
                load -= u
                parts.append(f"{n}(降ろす{u}kg→残{load}kg)")
            elif n == "D":
                parts.append("車庫")
            else:
                load += prob.loads[n]
                parts.append(f"{n}(+{prob.loads[n]}kg→{load}kg)")
        lines.append(f"車両{v} 容量{cap}kg  {r.time:.2f}分  " + " → ".join(parts))
    lines.append(f"総移動時間 {ev.total_time:.2f}分 / 完了時間(最長の車両) {ev.makespan:.2f}分")
    lines.append(f"制約違反数 {ev.n_viol}(容量超過の車両 {ev.cap_viol}、受入上限の超過 "
                 f"{sum(1 for o in ev.overflow.values() if o > 0)}) / 不足・超過の合計 {ev.excess_kg:.0f}kg")
    for d in prob.dests:
        got = sum(u for v in ev.amounts for dd, u in ev.amounts[v] if dd == d)
        lines.append(f"納入先{d}: 受入 {got}kg / 上限 {prob.limits[d]}kg")
    return "\n".join(lines)


def stats_line(name, r):
    s = r.stats
    return (f"{name}: 反復{s.iterations}回 / 評価した候補 {s.candidates_evaluated}"
            f"(索引なしなら{s.candidates_total}) / 経路の再計算 {s.route_computations}回 / "
            f"索引の更新 {s.index_updates}回 / {s.seconds:.3f}秒")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="t05route")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("solve", "compare", "replan"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="CSVのフォルダ")
        p.add_argument("--capacity-mode", choices=["total", "segment"], default="total")
        p.add_argument("--load", choices=["actual", "forecast"], default="actual")
        p.add_argument("--max-iter", type=int, default=1000)
        if name == "solve":
            p.add_argument("--algo", choices=["baseline", "index"], default="index")
    g = sub.add_parser("generate")
    g.add_argument("--out", required=True)
    g.add_argument("--sites", type=int, default=20)
    g.add_argument("--vehicles", type=int, default=3)
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--noise", type=float, default=0.2)
    g.add_argument("--fill", type=float, default=0.8)
    a = ap.parse_args(argv)

    if a.cmd == "generate":
        generate(a.out, a.sites, a.vehicles, a.seed, a.noise, a.fill)
        print(f"{a.out} にCSVを作りました(拠点{a.sites}、車両{a.vehicles}、種{a.seed})")
        return
    prob = load_problem(a.data, a.load)
    if a.cmd == "solve":
        r = local_search(prob, prob.initial, a.capacity_mode, a.algo == "index", a.max_iter)
        print(describe(prob, r.ev))
        print(stats_line(a.algo, r))
    elif a.cmd == "compare":
        b = local_search(prob, prob.initial, a.capacity_mode, False, a.max_iter)
        i = local_search(prob, prob.initial, a.capacity_mode, True, a.max_iter)
        print(describe(prob, i.ev))
        print(stats_line("素朴(索引なし)", b))
        print(stats_line("荷量索引あり  ", i))
        same = b.ev.assign.keys() == i.ev.assign.keys() and all(
            sorted(b.ev.assign[v]) == sorted(i.ev.assign[v]) for v in b.ev.assign)
        print("2つの結果は" + ("一致" if same else "不一致") +
              f"(総移動時間 {b.ev.total_time:.2f} / {i.ev.total_time:.2f}分)")
    else:
        pf, pa = prob.with_loads("forecast"), prob.with_loads("actual")
        plan, before, again, chg = replan(pf, pa, a.capacity_mode, True)
        print("【事前予測での計画】"); print(describe(pf, plan.ev))
        print("\n【その計画を実荷量で走らせた場合】"); print(describe(pa, before))
        print("\n【実荷量で再計画した結果】"); print(describe(pa, again.ev))
        print("\n指示の変更: " + " / ".join(f"{k} {v}" for k, v in chg.items()))
