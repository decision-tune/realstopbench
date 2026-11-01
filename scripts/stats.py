"""Cluster-aware statistics used by scripts/synthetic_scores.py (copied from the maintainers' replay package; only this docstring changed).

Stdlib only. DESIGN.md section 10: resample whole clusters (family for T1), 2,000 resamples,
fixed seed, percentile 95% interval of the ratio sum(num) / sum(den).
"""
from __future__ import annotations

import itertools
import random
from collections import OrderedDict

SEED = 20261030
N_BOOT = 2000


def _exact_bounds(events: int, n: int, alpha: float):
    """Exact Clopper-Pearson two-sided bounds for the all-or-nothing cases (closed form).

    n is the number of CLUSTERS, not items: treating each cluster as one trial is conservative when items
    inside a cluster are correlated. Ceiling: for a mid-range rate in a single cluster there is no closed form
    here (it needs a beta quantile); that case returns None and is flagged degenerate.
    """
    if n <= 0:
        return None
    if events == 0:
        return (0.0, 1 - (alpha / 2) ** (1 / n))
    if events == n:
        return ((alpha / 2) ** (1 / n), 1.0)
    return None


def cluster_rate(units, n_boot: int = N_BOOT, seed: int = SEED, alpha: float = 0.05, scale: float = 1.0) -> dict:
    """units: iterable of (cluster_id, num, den) per row. Returns the pooled rate and a cluster bootstrap interval.

    value None = undefined (no denominator anywhere), never zero. When every resample gives the same rate
    (0 events, all events, or one cluster) the percentile interval would be a fake [x, x]: lo/hi are None,
    `degenerate` names the reason, and `exact` carries a Clopper-Pearson bound over clusters where one exists.
    """
    agg: "OrderedDict[str, list[float]]" = OrderedDict()
    for cid, num, den in units:
        a = agg.setdefault(str(cid), [0.0, 0.0])
        a[0] += num
        a[1] += den
    clusters = [(k, n, d) for k, (n, d) in sorted(agg.items()) if d > 0]
    num = sum(n for _, n, _ in clusters)
    den = sum(d for _, _, d in clusters)
    out = {"num": num, "den": den, "value": None, "lo": None, "hi": None, "n_clusters": len(clusters),
           "n_boot": n_boot, "seed": seed, "degenerate": None, "exact": None}
    if den == 0:
        out["degenerate"] = "undefined: no denominator"
        return out
    out["value"] = num / den * scale
    if len(clusters) < 2:
        out["degenerate"] = "one cluster"
    elif num == 0:
        out["degenerate"] = "zero events"
        ex = _exact_bounds(0, len(clusters), alpha)
    elif num == den:
        out["degenerate"] = "all events"
        ex = _exact_bounds(len(clusters), len(clusters), alpha)
    if out["degenerate"]:
        if out["degenerate"] in ("zero events", "all events"):
            out["exact"] = (ex[0] * scale, ex[1] * scale)
        return out
    rng = random.Random(seed)
    k = len(clusters)
    stats = []
    for _ in range(n_boot):
        sn = sd = 0.0
        for _ in range(k):
            _, n, d = clusters[rng.randrange(k)]
            sn += n
            sd += d
        stats.append(sn / sd * scale)  # sd > 0: every kept cluster has d > 0
    stats.sort()
    lo_i = int((alpha / 2) * n_boot)
    hi_i = min(n_boot - 1, int((1 - alpha / 2) * n_boot) - 1)
    out["lo"], out["hi"] = stats[lo_i], stats[hi_i]
    return out


def fmt_interval(r: dict, digits: int = 3) -> str:
    """Compact text for tables: 'value [lo, hi]', or the degenerate reason with its exact bound."""
    if r["value"] is None:
        return "undef"
    f = "%." + str(digits) + "f"
    if r["degenerate"]:
        ex = "" if r["exact"] is None else (" exact [" + f + ", " + f + "]") % r["exact"]
        return (f % r["value"]) + " (" + r["degenerate"] + ex + ")"
    return (f + " [" + f + ", " + f + "]") % (r["value"], r["lo"], r["hi"])


def sign_flip_p(diffs, n_mc: int = 20000, seed: int = SEED) -> float:
    """Two-sided paired sign-flip test on per-cluster differences (ImpasseBench Appendix A).

    Exact enumeration up to 16 clusters; Monte Carlo with n_mc flips beyond (p includes the observed statistic,
    so it is never 0). Zero differences carry no sign information and are kept (they add nothing to the sum).
    """
    d = [float(x) for x in diffs]
    obs = abs(sum(d))
    if not d:
        return 1.0
    eps = 1e-12
    if len(d) <= 16:
        hits = total = 0
        for signs in itertools.product((1, -1), repeat=len(d)):
            total += 1
            hits += abs(sum(s * x for s, x in zip(signs, d))) >= obs - eps
        return hits / total
    rng = random.Random(seed)
    hits = 1
    for _ in range(n_mc):
        hits += abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - eps
    return hits / (n_mc + 1)


def holm(pvals: dict) -> dict:
    """Holm step-down adjusted p values for one comparison family {name: p}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[name] = running
    return out
