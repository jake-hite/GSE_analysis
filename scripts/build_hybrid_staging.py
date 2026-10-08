"""Model a hybrid: a tractor staged at each gate, except the pool gates, which a shared pool serves.

The pool gates are set by POOL_CONCOURSES and POOL_GATES. Gates joined with "+" in
SHARED_TRACTORS (e.g. "A12+A12A+A12B") share a single staged tractor.

Jobs (pushbacks and tows) come from build_peak_demand.jobs_for, with the same assumptions.
A tow counts against its departure gate.

Staged gates get tractor models so that, within the fleet, staged tractors can tow as many
jobs as possible in total. Among models that tie at a gate, the choice is the one that leaves
the pool short least often: one model at a time is swapped while that reduces pool shortages.
The staged tractor takes each job at its gate in time order if it is free and can tow that aircraft;
otherwise the job goes to the pool. The pool is every tractor not staged, and serves all
other gates as well as the staged gates' overflow. As in build_peak_demand, the pool is
short at a time step when some group of aircraft families has more jobs in progress than
pool tractors able to tow at least one of them. Travel time is not modelled.

Writes to data/:
- hybrid_gates.csv: every gate, staged or pool, with its total departures; for staged gates, the tractor staged there and
  how much of the gate's work it covers; for all gates, departures by aircraft family
  (% of the gate's departures)
- hybrid_pool_demand.csv: peak pool jobs for each family group against pool tractors
- hybrid_pool_shortages.csv: every time step where the pool cannot cover its jobs
"""
import collections
import itertools
import re
from datetime import datetime, timedelta

from build_peak_demand import (BIN, CLASSES, FAMILIES, floor_bin, jobs_for, parse, read,
                               write)

# Gates served only by the pool: every gate in POOL_CONCOURSES, plus POOL_GATES.
# Every other gate with departures gets its own staged tractor, except that the gates in
# each SHARED_TRACTORS entry share one.
POOL_CONCOURSES = ["S"]
POOL_GATES = ["A8/A8A", "A9", "A10/A10A", "A20", "A21", "B14"]
SHARED_TRACTORS = ["A12+A12A+A12B"]
OPERATING_MINUTES = 19 * 60  # 05:00 to midnight, for staged tractor utilisation


def gate_sort_key(gate):
    return gate[0], int(re.match(r"\D(\d+)", gate).group(1)), gate


def best_assignment(gates, units, value):
    """Assign one model to each gate, at most units[m] gates per model, maximising total value.

    Solved as a min-cost flow (source -> gate -> model -> sink) by successive shortest paths.
    """
    models = list(units)
    n = len(gates) + len(models) + 2
    source, sink = n - 2, n - 1
    graph = [[] for _ in range(n)]  # edges: [to, capacity, cost, index of reverse edge]

    def add(a, b, cap, cost):
        graph[a].append([b, cap, cost, len(graph[b])])
        graph[b].append([a, 0, -cost, len(graph[a]) - 1])

    for i, g in enumerate(gates):
        add(source, i, 1, 0)
        for j, m in enumerate(models):
            add(i, len(gates) + j, 1, -value(g, m))
    for j, m in enumerate(models):
        add(len(gates) + j, sink, units[m], 0)

    for _ in gates:
        dist = [float("inf")] * n
        dist[source], prev = 0, [None] * n
        for _ in range(n):  # Bellman-Ford: costs can be negative
            changed = False
            for a in range(n):
                if dist[a] == float("inf"):
                    continue
                for k, (b, cap, cost, _) in enumerate(graph[a]):
                    if cap and dist[a] + cost < dist[b]:
                        dist[b], prev[b], changed = dist[a] + cost, (a, k), True
            if not changed:
                break
        if dist[sink] == float("inf"):
            raise SystemExit("Not enough tractors to stage every gate")
        b = sink
        while b != source:
            a, k = prev[b]
            graph[a][k][1] -= 1
            graph[b][graph[a][k][3]][1] += 1
            b = a

    return {g: models[e[0] - len(gates)] for i, g in enumerate(gates)
            for e in graph[i] if len(gates) <= e[0] < len(gates) + len(models) and e[1] == 0}


def simulate(staged, jobs, can_tow):
    """Run the staged tractors. Returns per-gate rows and the pool's jobs per time step."""
    pool_busy = collections.defaultdict(collections.Counter)

    def to_pool(start, end, fam):
        t = floor_bin(start)
        while t < end:
            pool_busy[t][fam] += 1
            t += timedelta(minutes=BIN)

    days = len({start.date() for gate_jobs in jobs.values() for start, _, _ in gate_jobs})
    rows = []
    for gate, model in staged.items():
        free_at = None
        taken = cannot_tow = clashed = busy_minutes = 0
        for start, end, fam in sorted(jobs[gate]):
            if fam not in can_tow[model]:
                cannot_tow += 1
                to_pool(start, end, fam)
            elif free_at and start < free_at:
                clashed += 1
                to_pool(start, end, fam)
            else:
                taken += 1
                busy_minutes += (end - start).seconds // 60
                free_at = end
        total = len(jobs[gate])
        rows.append([gate, model, total, round(total / days, 1), taken,
                     f"{taken / total:.0%}" if total else "", cannot_tow, clashed,
                     f"{busy_minutes / (days * OPERATING_MINUTES):.1%}"])
    for gate, gate_jobs in jobs.items():
        if gate not in staged:
            for start, end, fam in gate_jobs:
                to_pool(start, end, fam)
    return rows, pool_busy


def main():
    fleet = read("tractor_capability_by_family.csv")
    units = {r["model_name"]: int(r["units"]) for r in fleet}
    can_tow = {r["model_name"]: {f for f in FAMILIES if r[f] == "1"} for r in fleet}

    deps = [r for r in read("flights_by_gate.csv")
            if r["Arr/Dep"] == "DEP" and r["short_ac_type"] in FAMILIES]
    days = sorted({r["Flt_Orig_Date"] for r in deps})
    jobs = collections.defaultdict(list)  # gate -> [(start, end, family)]
    for r in deps:
        for start, minutes in jobs_for(r):
            jobs[r["Gate"]].append((start, start + timedelta(minutes=minutes), r["short_ac_type"]))
    # Gates joined with "+" share one staged tractor.
    for entry in SHARED_TRACTORS:
        jobs[entry] = [job for gate in entry.split("+") for job in jobs.pop(gate, [])]
    pool_gates = [g for g in jobs if g[0] in POOL_CONCOURSES or g in POOL_GATES]
    staged_entries = sorted((g for g in jobs if g not in pool_gates), key=gate_sort_key)
    if len(staged_entries) > sum(units.values()):
        raise SystemExit(f"{len(staged_entries)} staged gates but only {sum(units.values())} tractors")

    def coverage(gate, model):
        return sum(fam in can_tow[model] for _, _, fam in jobs[gate])

    # Give each staged gate a model so that staged tractors can tow as many jobs as possible
    # in total, within the units of each model. Ties go to less capable models.
    cover = {(g, m): coverage(g, m) for g in staged_entries for m in units}
    staged = best_assignment(staged_entries, units, lambda g, m: cover[g, m] * 100 - len(can_tow[m]))
    remaining = dict(units)
    for model in staged.values():
        remaining[model] -= 1
    # Models that would cover exactly as many jobs at each gate, for the swap search below.
    candidates = {g: [m for m in units if cover[g, m] == cover[g, staged[g]]] for g in staged_entries}

    pool_busy = simulate(staged, jobs, can_tow)[1]
    groups = [set(c) for n in range(1, len(FAMILIES) + 1) for c in itertools.combinations(FAMILIES, n)]
    # Distinct job mixes seen in the pool, with how many time steps had each.
    mixes = collections.Counter(tuple(c[f] for f in FAMILIES) for c in pool_busy.values())
    group_index = [[i for i, f in enumerate(FAMILIES) if f in g] for g in groups]

    def short_steps(pool_units):
        caps = [sum(n for m, n in pool_units.items() if can_tow[m] & g) for g in groups]
        return sum(count for mix, count in mixes.items()
                   if any(sum(mix[i] for i in idx) > cap for idx, cap in zip(group_index, caps)))

    # Swap one gate's model at a time (same coverage, so pool jobs do not change)
    # while that lowers the number of short time steps.
    best = short_steps(remaining)
    improved = True
    while improved:
        improved = False
        for gate in staged_entries:
            for model in candidates[gate]:
                if model == staged[gate] or remaining[model] == 0:
                    continue
                trial = dict(remaining)
                trial[staged[gate]] += 1
                trial[model] -= 1
                score = short_steps(trial)
                if score < best:
                    best, remaining, staged[gate], improved = score, trial, model, True

    # Run each staged tractor; everything it cannot take goes to the pool.
    gate_rows, pool_busy = simulate(staged, jobs, can_tow)

    # Aircraft mix: each gate's departures by family, as a share of its departures.
    # NULL (unknown type) departures are counted here so the shares add up to 100%.
    mix = collections.defaultdict(collections.Counter)
    for r in read("flights_by_gate.csv"):
        if r["Arr/Dep"] == "DEP":
            mix[r["Gate"]][r["short_ac_type"]] += 1
    mix_families = FAMILIES + ["NULL"]
    mix_header = [f"% {fam}" for fam in mix_families]

    def mix_cells(entry):
        counts = sum((mix[g] for g in entry.split("+")), collections.Counter())
        total = sum(counts.values())
        return ["" if not counts[fam] else "<1%" if counts[fam] / total < 0.005
                else f"{counts[fam] / total:.0%}" for fam in mix_families]

    # One table for every gate: staged gates first, then pool gates.
    staged_cells = {row[0]: row[1:] for row in gate_rows}
    rows = []
    for assignment, gates in (("Staged", staged_entries), ("Pool", sorted(pool_gates, key=gate_sort_key))):
        for g in gates:
            if assignment == "Staged":
                model, total, per_day, *rest = staged_cells[g]
            else:
                model, total, per_day = "", len(jobs[g]), round(len(jobs[g]) / len(days), 1)
                rest = [""] * 5
            departures = sum(sum(mix[gate].values()) for gate in g.split("+"))
            rows.append([g, assignment, model, departures, total, per_day, *rest, *mix_cells(g)])
    write("hybrid_gates.csv",
          ["Gate", "assignment", "staged_model", "departures", "jobs", "jobs_per_day",
           "jobs_by_staged_tractor",
           "share_by_staged_tractor", "to_pool_aircraft_too_big", "to_pool_tractor_busy",
           "staged_tractor_busy_share", *mix_header], rows)

    def capacity(families):
        return sum(remaining[m] for m in remaining if can_tow[m] & families)

    rows = []
    for name, fams in CLASSES.items():
        per_day_peak = collections.defaultdict(int)
        peak, peak_at = 0, None
        for t, c in pool_busy.items():
            n = sum(c[f] for f in fams)
            per_day_peak[t.date()] = max(per_day_peak[t.date()], n)
            if n > peak:
                peak, peak_at = n, t
        daily = sorted(per_day_peak.get(datetime.strptime(d, "%Y-%m-%d").date(), 0) for d in days)
        cap = capacity(fams)
        over = sum(1 for c in pool_busy.values() if sum(c[f] for f in fams) > cap)
        rows.append([name, cap, peak, peak_at.strftime("%Y-%m-%d %H:%M") if peak_at else "",
                     daily[len(daily) // 2], daily[int(0.95 * (len(daily) - 1))], over * BIN])
    write("hybrid_pool_demand.csv",
          ["class", "pool_tractors", "peak_jobs", "peak_at", "median_daily_peak",
           "p95_daily_peak", "minutes_over_capacity"], rows)

    group_capacity = [(g, capacity(g)) for g in groups]
    rows = []
    for t in sorted(pool_busy):
        c = pool_busy[t]
        worst = None
        for g, cap in group_capacity:
            need = sum(c[f] for f in g)
            if need > cap and (worst is None or need - cap > worst[1] - worst[2]):
                worst = (g, need, cap)
        if worst:
            g, need, cap = worst
            rows.append([t.strftime("%Y-%m-%d %H:%M"), ", ".join(f for f in FAMILIES if f in g),
                         need, cap, sum(c.values())])
    write("hybrid_pool_shortages.csv",
          ["time", "families", "jobs", "pool_tractors", "all_pool_jobs_in_progress"], rows)


if __name__ == "__main__":
    main()
