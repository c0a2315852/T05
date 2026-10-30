"""割当の局所探索(擬似コードの手順2)と、荷量索引による候補の絞り込み。

候補は2種類:
  R(s, b): 拠点sの担当車両を b に変更する
  S(s, t): 拠点sと拠点tの担当車両を交換する
評価は ①制約違反数 ②総移動時間 ③変更地点数 の順(小さいほど良い)。
"""
from __future__ import annotations

import bisect
import time
from dataclasses import dataclass

from .model import Evaluator, Eval, Problem, skey


@dataclass
class Stats:
    iterations: int = 0
    candidates_total: int = 0      # 索引を使わない場合に評価する候補の総数(のべ)
    candidates_evaluated: int = 0  # 実際に評価した候補の数(のべ)
    index_iterations: int = 0      # 索引で絞り込んだ反復の回数
    index_updates: int = 0         # 索引の更新(再構築)回数
    route_computations: int = 0    # 経路の再計算回数(キャッシュにない場合)
    seconds: float = 0.0


@dataclass
class Result:
    ev: Eval
    stats: Stats


class LoadIndex:
    """荷量索引: 車両ごとに、担当拠点を荷量の小さい順に並べた一覧。

    入れ替え後も積載上限を守れる候補を、二分探索で範囲検索して見つける。
    変更のあった車両の分だけ更新する。
    """

    def __init__(self, prob: Problem, assign: dict):
        self.prob = prob
        self.items, self.weights = {}, {}
        for v in prob.vehicles:
            self.rebuild(v, assign[v])

    def rebuild(self, v, sites):
        it = sorted((self.prob.loads[s], skey(s), s) for s in sites)
        self.items[v] = it
        self.weights[v] = [x[0] for x in it]

    def candidates(self, assign: dict, fixed: set):
        prob = self.prob
        slack = {v: prob.capacity[v] - sum(prob.loads[s] for s in assign[v]) for v in prob.vehicles}
        out = set()
        for a in prob.vehicles:
            for b in prob.vehicles:
                if a == b:
                    continue
                # 移動: 拠点の荷量 <= 移動先の残り容量
                hi = bisect.bisect_right(self.weights[a], slack[b])
                for _, _, s in self.items[a][:hi]:
                    if s not in fixed:
                        out.add(("R", s, b))
                # 交換: 荷量 w_t が [w_s - slack_b, w_s + slack_a] に入る組だけ
                for w, _, s in self.items[a]:
                    if s in fixed:
                        continue
                    lo = bisect.bisect_left(self.weights[b], w - slack[b])
                    hi = bisect.bisect_right(self.weights[b], w + slack[a])
                    for _, _, t in self.items[b][lo:hi]:
                        if t not in fixed:
                            x, y = (s, t) if skey(s) < skey(t) else (t, s)
                            out.add(("S", x, y))
        return sorted(out, key=_canon)


def _canon(c):
    return (0 if c[0] == "R" else 1, skey(c[1]), skey(c[2]))


def all_candidates(prob: Problem, vehof: dict, fixed: set):
    """索引を使わない: すべての移動と交換を列挙する(比較用の素朴な方式)。"""
    sites = [s for s in prob.sites if s not in fixed]
    for s in sites:
        for b in prob.vehicles:
            if b != vehof[s]:
                yield ("R", s, b)
    for i, s in enumerate(sites):
        for t in sites[i + 1:]:
            if vehof[s] != vehof[t]:
                yield ("S", s, t)


def space_size(prob: Problem, vehof: dict, fixed: set) -> int:
    movable = [s for s in prob.sites if s not in fixed]
    m = len(movable)
    per = {}
    for s in movable:
        per[vehof[s]] = per.get(vehof[s], 0) + 1
    return m * (len(prob.vehicles) - 1) + (m * m - sum(x * x for x in per.values())) // 2


def apply(c, assign: dict, vehof: dict):
    new = {v: list(ss) for v, ss in assign.items()}
    if c[0] == "R":
        _, s, b = c
        a = vehof[s]
        new[a].remove(s)
        new[b].append(s)
        return new, [a, b], 1
    _, s, t = c
    a, b = vehof[s], vehof[t]
    new[a].remove(s)
    new[b].remove(t)
    new[a].append(t)
    new[b].append(s)
    return new, [a, b], 2


def local_search(prob: Problem, init: dict, cap_mode: str = "total",
                 use_index: bool = False, max_iter: int = 1000) -> Result:
    t0 = time.perf_counter()
    ev = Evaluator(prob, cap_mode)
    st = Stats()
    fixed = {f for f in prob.fixed_first.values() if f}
    cur = ev.evaluate({v: list(init[v]) for v in prob.vehicles})
    index = LoadIndex(prob, cur.assign) if use_index else None
    for _ in range(max_iter):
        st.iterations += 1
        vehof = {s: v for v, ss in cur.assign.items() for s in ss}
        st.candidates_total += space_size(prob, vehof, fixed)
        # 絞り込みが安全なのは「現状に違反がない」とき(違反のある候補は必ず現状より悪い)
        if index and cap_mode == "total" and cur.n_viol == 0:
            cands = index.candidates(cur.assign, fixed)
            st.index_iterations += 1
        else:
            cands = all_candidates(prob, vehof, fixed)
        best = None
        for c in cands:
            new, changed, nchg = apply(c, cur.assign, vehof)
            e = ev.evaluate_candidate(cur, new, changed)
            st.candidates_evaluated += 1
            k = (e.n_viol, round(e.total_time, 6), nchg)
            if best is None or k < best[0]:
                best = (k, e, changed)
        if best is not None and best[0][:2] < cur.key():
            cur = best[1]
            if index:
                for v in best[2]:
                    index.rebuild(v, cur.assign[v])
                    st.index_updates += 1
        else:
            break
    st.route_computations = ev.route_computations
    st.seconds = time.perf_counter() - t0
    return Result(cur, st)
