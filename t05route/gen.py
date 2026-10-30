"""疑似データの生成(乱数の種を固定して再現できる)。"""
from __future__ import annotations

import math
import random

from .data import write_problem
from .model import DEPOT, Problem, skey


def generate(out: str, n_sites: int = 20, n_vehicles: int = 3, seed: int = 0,
             noise: float = 0.2, fill: float = 0.8, margin: float = 0.05) -> Problem:
    """拠点・荷量・予測誤差を乱数で作り、CSVに書き出す。

    noise: 予測の誤差の幅(実荷量 = 予測 x (1+誤差)、誤差は ±noise の一様乱数)
    fill : 総荷量 / 総容量 の目安
    margin: 受入上限の余裕(総荷量に対する割合)
    """
    rng = random.Random(seed)
    sites = [str(i) for i in range(1, n_sites + 1)]
    dests = ["T", "M"]
    pos = {DEPOT: (rng.uniform(0, 100), rng.uniform(0, 100))}
    for n in sites + dests:
        pos[n] = (rng.uniform(0, 100), rng.uniform(0, 100))
    tt = {(a, b): 0.0 if a == b else round(math.dist(pos[a], pos[b]) * 0.5, 1)
          for a in pos for b in pos}
    vids = [chr(ord("A") + i) for i in range(n_vehicles)]
    caps = {v: [2000, 1000][i % 2] for i, v in enumerate(vids)}
    base = {s: rng.uniform(30, 600) for s in sites}
    scale = fill * sum(caps.values()) / sum(base.values())
    actual, forecast = {}, {}
    for s in sites:
        a = max(1, int(round(base[s] * scale)))
        actual[s] = a
        forecast[s] = max(1, int(round(a * (1 + rng.uniform(-noise, noise)))))
    total = sum(actual.values())
    limits = {"T": math.ceil(total * 0.54 * (1 + margin)), "M": math.ceil(total * 0.46 * (1 + margin))}
    slack, initial = dict(caps), {v: [] for v in vids}
    for s in sorted(sites, key=lambda x: -forecast[x]):
        v = max(vids, key=lambda x: (slack[x], x))
        initial[v].append(s)
        slack[v] -= forecast[s]
    for v in vids:
        initial[v].sort(key=skey)
    prob = Problem(dict(actual), caps, {v: None for v in vids}, limits, tt, initial, forecast, actual)
    write_problem(out, prob)
    return prob
