"""事前予測と実荷量が違うときの再計画と、ドライバーへの指示変更の数え方。"""
from __future__ import annotations

from .model import DEPOT, Eval, Problem
from .search import local_search


def next_stops(routes: dict) -> dict:
    """拠点 -> (担当車両, 次に向かう地点)。車両の最初の行き先は ('first', 車両) として記録。"""
    m = {}
    for v, r in routes.items():
        for a, b in zip(r.seq, r.seq[1:]):
            m[v, a] = b
    return m


def instruction_changes(old: Eval, new: Eval) -> dict:
    """前の計画と比べて、ドライバーに伝え直す指示がいくつ変わったか。"""
    veh_old = {s: v for v, ss in old.assign.items() for s in ss}
    veh_new = {s: v for v, ss in new.assign.items() for s in ss}
    reassigned = sum(1 for s in veh_new if veh_old.get(s) != veh_new[s])
    o, n = next_stops(old.routes), next_stops(new.routes)
    # 各車両の各地点(車庫を含む)について、次の行き先が変わった数
    keys = set(o) | set(n)
    changed = sum(1 for k in keys if o.get(k) != n.get(k))
    return {"担当が変わった拠点数": reassigned, "次の行き先が変わった地点数": changed}


def replan(prob_forecast: Problem, prob_actual: Problem, cap_mode: str = "total",
           use_index: bool = True):
    """予測荷量で計画 -> 実荷量で評価 -> 実荷量で再計画(予測の計画を出発点にする)。"""
    plan = local_search(prob_forecast, prob_forecast.initial, cap_mode, use_index)
    from .model import Evaluator
    ev_a = Evaluator(prob_actual, cap_mode)
    before = ev_a.evaluate(plan.ev.assign)          # 予測の計画を、そのまま実荷量で走らせた場合
    again = local_search(prob_actual, plan.ev.assign, cap_mode, use_index)
    return plan, before, again, instruction_changes(plan.ev, again.ev)
