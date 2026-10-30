"""問題の定義、経路の組み立て(最近傍 + 2-opt + 納入先の挿入)、納入量の配分、状態の評価。"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace

DEPOT = "D"


def skey(x: str):
    """'2' < '10' となる自然順(拠点IDの並べ替えに使う)。"""
    return (0, int(x), "") if x.isdigit() else (1, 0, x)


@dataclass
class Problem:
    loads: dict      # 拠点ID -> 今回の計画で使う荷量(kg, 整数)
    capacity: dict   # 車両ID -> 積載容量(kg)
    fixed_first: dict  # 車両ID -> 最初に訪問する拠点(なければ None)
    limits: dict     # 納入先ID -> 受入上限(kg)
    tt: dict         # (出発, 到着) -> 所要時間(分)
    initial: dict    # 車両ID -> 初期の担当拠点のリスト
    forecast: dict = field(default_factory=dict)
    actual: dict = field(default_factory=dict)

    @property
    def vehicles(self):
        return sorted(self.capacity, key=skey)

    @property
    def dests(self):
        return sorted(self.limits, key=skey)

    @property
    def sites(self):
        return sorted(self.loads, key=skey)

    def with_loads(self, mode: str) -> "Problem":
        """mode='actual'(実荷量) または 'forecast'(事前予測)の荷量に切り替えた問題を返す。"""
        src = self.actual if mode == "actual" else self.forecast
        return replace(self, loads=dict(src))


@dataclass
class Route:
    seq: list      # 例: ['D','1','5','T','9','M','D']
    time: float
    excess: float  # 容量の超過量(kg)
    visits: list   # [(納入先, その納入までに積んだ量(kg))]
    total: float   # 総集荷量


def seq_stats(prob: Problem, seq: list, cap: float, cap_mode: str):
    """経路(車庫から車庫まで)の所要時間・容量超過・納入先ごとの区間荷量を計算する。"""
    time = sum(prob.tt[a, b] for a, b in zip(seq, seq[1:]))
    visits, seg, total = [], 0, 0
    for n in seq[1:-1]:
        if n in prob.limits:
            visits.append((n, seg))
            seg = 0
        else:
            seg += prob.loads[n]
            total += prob.loads[n]
    if cap_mode == "total":      # 擬似コードどおり: 総集荷量が容量以内
        excess = max(0, total - cap)
    else:                        # segment: 納入先で降ろす前提で、区間ごとの荷量が容量以内
        excess = sum(max(0, s - cap) for _, s in visits)
    excess += seg                # 最後に納入されず残った荷(通常は0)
    return time, excess, visits, total


def _tail(prob: Problem, s: str) -> float:
    return min(prob.tt[s, d] + prob.tt[d, DEPOT] for d in prob.dests)


def _path_cost(prob: Problem, order: list) -> float:
    c = prob.tt[DEPOT, order[0]] + sum(prob.tt[a, b] for a, b in zip(order, order[1:]))
    return c + _tail(prob, order[-1])


def nn_order(prob: Problem, sites: list, first):
    """近い地点を順に選んで集荷順を作る(最近傍法)。"""
    rest = sorted(sites, key=skey)
    order = []
    cur = DEPOT
    if first in rest:
        order.append(first)
        rest.remove(first)
        cur = first
    while rest:
        nxt = min(rest, key=lambda s: (prob.tt[cur, s], skey(s)))
        order.append(nxt)
        rest.remove(nxt)
        cur = nxt
    return order


def two_opt(prob: Problem, order: list, fixed_first: bool) -> list:
    """集荷順を2-opt法で改善する(最初の拠点を固定する場合は動かさない)。"""
    start = 1 if fixed_first else 0
    best = list(order)
    best_cost = _path_cost(prob, best)
    improved = True
    while improved and len(best) - start >= 2:
        improved = False
        for i in range(start, len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                c = _path_cost(prob, cand)
                if c < best_cost - 1e-9:
                    best, best_cost, improved = cand, c, True
                    break
            if improved:
                break
    return best


def plan_options(order: list, dests: list):
    """集荷順に納入先の訪問を挿入した経路をすべて作る。

    各納入先は車両あたり最大1回。最後は必ず納入先(積み残しを出さない)。
    集荷の途中で納入先に寄り、その後にまた集荷する経路も含む。
    """
    n = len(order)
    for k in range(1, len(dests) + 1):
        for perm in itertools.permutations(dests, k):
            for pos in itertools.combinations_with_replacement(range(1, n + 1), k - 1):
                seq, pi = [DEPOT], 0
                for i, s in enumerate(order, 1):
                    seq.append(s)
                    while pi < len(pos) and pos[pi] == i:
                        seq.append(perm[pi])
                        pi += 1
                seq += [perm[-1], DEPOT]
                yield seq


def allocate(prob: Problem, routes: dict, cap_mode: str):
    """各納入先での降ろす量を決める(荷物は混載・分割納品できる前提)。

    受入上限の残りを先に使い切る貪欲法。容量(segment)の制約を満たす範囲で降ろす。
    戻り値: (車両ごとの降ろす量, 納入先ごとの超過量)
    """
    remaining = dict(prob.limits)
    delivered = {d: 0 for d in prob.limits}
    amounts = {}
    order = sorted(routes, key=lambda v: (len(routes[v].visits), skey(v)))
    for v in order:
        r, cap, carry, n = routes[v], prob.capacity[v], 0, len(routes[v].visits)
        amts = []
        for i, (d, seg) in enumerate(r.visits):
            before = carry + seg
            if i == n - 1:
                u = before
            else:
                nxt = r.visits[i + 1][1]
                lo = 0 if cap_mode == "total" else max(0, before - (cap - nxt))
                u = min(max(remaining[d], lo), before)
            carry = before - u
            remaining[d] -= u
            delivered[d] += u
            amts.append((d, u))
        amounts[v] = amts
    overflow = {d: max(0, delivered[d] - prob.limits[d]) for d in prob.limits}
    return amounts, overflow


@dataclass
class Eval:
    assign: dict
    routes: dict
    total_time: float
    makespan: float
    n_viol: int
    excess_kg: float
    cap_viol: int
    amounts: dict
    overflow: dict

    def key(self):
        """擬似コードの評価順: ①制約違反数 ②総移動時間(③の変更地点数は探索側で追加)。"""
        return (self.n_viol, round(self.total_time, 6))


class Evaluator:
    """状態(車両ごとの担当拠点)を評価する。

    経路は、車両ごとに「納入先の訪問順(Tのみ / Mのみ / T→M / M→T)」ごとに、時間が短い経路と、
    最初の納入先で多く降ろせる経路を候補として持つ。全車両の候補の組み合わせは、受入上限を守れるよう
    1台ずつ切り替えて選ぶ(山登り)。
    """

    def __init__(self, prob: Problem, cap_mode: str = "total"):
        assert cap_mode in ("total", "segment")
        self.prob, self.cap_mode = prob, cap_mode
        self.cache = {}
        self.route_computations = 0

    def options(self, v: str, sites) -> list:
        key = (v, frozenset(sites))
        if key in self.cache:
            return self.cache[key]
        self.route_computations += 1
        p, cap = self.prob, self.prob.capacity[v]
        if not sites:
            opts = [Route([DEPOT, DEPOT], 0.0, 0, [], 0)]
        else:
            first = p.fixed_first.get(v)
            use_first = first in sites
            order = two_opt(p, nn_order(p, list(sites), first if use_first else None), use_first)
            groups = {}
            for seq in plan_options(order, p.dests):
                t, ex, vis, tot = seq_stats(p, seq, cap, self.cap_mode)
                perm = tuple(n for n in seq if n in p.limits)
                groups.setdefault(perm, []).append((round(ex, 6), round(t, 6), vis[0][1], Route(seq, t, ex, vis, tot)))
            opts = []
            for perm, cands in groups.items():
                # 同じ訪問順の中で「時間が短い」か「最初の納入先で降ろせる量が多い」ものを残す
                cands.sort(key=lambda c: (c[0], c[1]))
                top = -1
                for ex, t, first_seg, r in cands:
                    if first_seg > top:
                        opts.append(r)
                        top = first_seg
            opts.sort(key=lambda r: (round(r.excess, 6), round(r.time, 6)))
        self.cache[key] = opts
        return opts

    def route(self, v: str, sites) -> Route:
        return self.options(v, sites)[0]

    def finish(self, assign: dict, routes: dict) -> Eval:
        amounts, overflow = allocate(self.prob, routes, self.cap_mode)
        cap_viol = sum(1 for r in routes.values() if r.excess > 1e-9)
        n_over = sum(1 for o in overflow.values() if o > 0)
        excess = sum(r.excess for r in routes.values()) + sum(overflow.values())
        times = [r.time for r in routes.values()]
        return Eval(assign, routes, sum(times), max(times) if times else 0.0,
                    cap_viol + n_over, excess, cap_viol, amounts, overflow)

    def evaluate(self, assign: dict) -> Eval:
        opts = {v: self.options(v, assign[v]) for v in self.prob.vehicles}
        pick = {v: 0 for v in opts}
        cur = self.finish(assign, {v: opts[v][0] for v in opts})
        ck = (cur.n_viol, round(cur.excess_kg, 6), round(cur.total_time, 6))
        for _ in range(5):
            improved = False
            for v in opts:
                for j in range(len(opts[v])):
                    if j == pick[v]:
                        continue
                    routes = {u: opts[u][pick[u]] for u in opts}
                    routes[v] = opts[v][j]
                    e = self.finish(assign, routes)
                    k = (e.n_viol, round(e.excess_kg, 6), round(e.total_time, 6))
                    if k < ck:
                        cur, ck, pick[v], improved = e, k, j, True
            if not improved:
                break
        return cur

    def evaluate_candidate(self, cur: Eval, new_assign: dict, changed: list) -> Eval:
        return self.evaluate(new_assign)

    def evaluate_sequences(self, seqs: dict) -> Eval:
        """経路をそのまま与えて評価する(机上実験の経路の再現・検証用)。"""
        routes = {}
        for v, seq in seqs.items():
            t, ex, vis, tot = seq_stats(self.prob, seq, self.prob.capacity[v], self.cap_mode)
            routes[v] = Route(seq, t, ex, vis, tot)
        assign = {v: [n for n in seq if n not in self.prob.limits and n != DEPOT]
                  for v, seq in seqs.items()}
        return self.finish(assign, routes)
