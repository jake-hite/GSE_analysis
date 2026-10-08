"""Model a hybrid: one tractor staged at each gate in STAGED_GATES, a shared pool for the rest.

Jobs (pushbacks and tows) come from build_peak_demand.jobs_for, with the same assumptions.
A tow counts against its departure gate.

Each staged gate gets a tractor model that can tow the most of that gate's departures.
Among models that tie, the choice is the one that leaves the pool shortest the least often:
a greedy pick first, then one model at a time is swapped while that reduces pool shortages. The staged
tractor takes each job at its gate in time order if it is free and can tow that aircraft;
otherwise the job goes to the pool. The pool is every tractor not staged, and serves all
other gates as well as the staged gates' overflow. As in build_peak_demand, the pool is
short at a time step when some group of aircraft families has more jobs in progress than
pool tractors able to tow at least one of them. Travel time is not modelled.

Writes to data/:
- hybrid_staged_gates.csv: for each staged gate, the tractor staged there and how much of the
  gate's work it covers
- hybrid_pool_demand.csv: peak pool jobs for each family group against pool tractors
- hybrid_pool_shortages.csv: every time step where the pool cannot cover its jobs
"""
import collections
import itertools
from datetime import datetime, timedelta

from build_peak_demand import (BIN, CLASSES, FAMILIES, floor_bin, jobs_for, parse, read,
                               write)

STAGED_GATES = ["B7B", "B5A", "B5", "B3", "B1", "A1", "A2", "A3", "A4", "A5", "A6",
                "A11", "A12A", "A12B", "A13", "A14"]
OPERATING_MINUTES = 19 * 60  # 05:00 to midnight, for staged tractor utilisation


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

    # Candidate models per gate: those that can tow the most of its jobs.
    def coverage(gate, model):
        return sum(fam in can_tow[model] for _, _, fam in jobs[gate])

    candidates = {}
    for gate in STAGED_GATES:
        best = max(coverage(gate, m) for m in units)
        candidates[gate] = [m for m in units if coverage(gate, m) == best]

    # Greedy start: most constrained gates first, least capable model first.
    remaining = dict(units)
    staged = {}
    for gate in sorted(STAGED_GATES, key=lambda g: len(candidates[g])):
        options = [m for m in candidates[gate] if remaining[m] > 0] or \
                  [m for m in units if remaining[m] > 0]
        staged[gate] = min(options, key=lambda m: len(can_tow[m]))
        remaining[staged[gate]] -= 1

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
        for gate in STAGED_GATES:
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
    write("hybrid_staged_gates.csv",
          ["Gate", "staged_model", "jobs", "jobs_per_day", "jobs_by_staged_tractor",
           "share_by_staged_tractor", "to_pool_aircraft_too_big", "to_pool_tractor_busy",
           "staged_tractor_busy_share"], sorted(gate_rows, key=lambda r: STAGED_GATES.index(r[0])))

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
