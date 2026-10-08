"""Measure peak tow tractor demand at SEA from scheduled departures and tows.

Each departure in flights_by_gate.csv is a pushback job at its scheduled departure time.
Each departure flagged towed=Y also has a tow job, from the gate the aircraft arrived at to
its departure gate. The export has no tow times, so a tow is assumed to start TOW_LEAD
minutes before departure, but not before the aircraft arrived.

A job keeps its tractor busy for a fixed time (JOB_MINUTES), counted in BIN-minute steps.
At each step the jobs in progress are checked against the fleet: for every group of aircraft
families, the jobs for those families must not outnumber the tractors able to tow at least one
of them. When that holds for every group, each job can be given a capable tractor; when it
fails, the fleet is short at that moment. Departures whose aircraft type is NULL are left out.

Writes to data/:
- hourly_departures.csv: average and peak-day departures per hour of day, by family
- peak_demand_by_class.csv: peak simultaneous jobs for each family group against capable tractors
- shortage_periods.csv: every time step where the fleet cannot cover the jobs in progress
- peak_demand_by_concourse.csv: the same peaks for each concourse (first letter of the gate),
  i.e. what each concourse would need if it kept its own tractors
"""
import collections
import csv
import itertools
from datetime import datetime, timedelta

DATA = "data/"
FAMILIES = ["ERJ", "A220", "A321 Neo", "737", "757", "767", "A330", "A350"]
WIDEBODY = {"767", "A330", "A350"}

# Assumptions: change these and rerun to test sensitivity.
BIN = 5  # minutes per time step
JOB_MINUTES = {"pushback": 20, "pushback_widebody": 30, "tow": 45}
TOW_LEAD = 60  # minutes before departure that a tow starts
SPARE_UNITS = 0  # tractors assumed out of service at any time, taken from the least capable

# Family groups reported in peak_demand_by_class.csv.
CLASSES = {
    "All jobs": set(FAMILIES),
    "ERJ": {"ERJ"},
    "Narrowbody (A220, A321 Neo, 737)": {"A220", "A321 Neo", "737"},
    "757 and widebody": {"757", "767", "A330", "A350"},
    "Widebody (767, A330, A350)": WIDEBODY,
    "A330 and A350": {"A330", "A350"},
    "A350": {"A350"},
}


def read(name):
    with open(DATA + name, newline="") as f:
        return list(csv.DictReader(f))


def write(name, header, rows):
    with open(DATA + name, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {DATA}{name}")


def parse(value):
    return None if value == "NULL" else datetime.strptime(value, "%Y-%m-%d %H:%M")


def floor_bin(dt):
    return dt.replace(minute=dt.minute - dt.minute % BIN)


def jobs_for(r):
    """The (start, minutes) tractor jobs for one departure: its pushback, plus a tow if towed."""
    fam, dep = r["short_ac_type"], parse(r["sea_sched_dep_local"])
    jobs = [(dep, JOB_MINUTES["pushback_widebody" if fam in WIDEBODY else "pushback"])]
    if r["towed"] == "Y":
        arrived = parse(r["inbound_actual_arr_local"]) or parse(r["inbound_sched_arr_local"])
        start = dep - timedelta(minutes=TOW_LEAD)
        if arrived and arrived > start:
            start = min(arrived, dep - timedelta(minutes=JOB_MINUTES["tow"]))
        jobs.append((start, JOB_MINUTES["tow"]))
    return jobs


def main():
    fleet = read("tractor_capability_by_family.csv")
    units = {r["model_name"]: int(r["units"]) for r in fleet}
    can_tow = {r["model_name"]: {f for f in FAMILIES if r[f] == "1"} for r in fleet}

    deps = [r for r in read("flights_by_gate.csv")
            if r["Arr/Dep"] == "DEP" and r["short_ac_type"] in FAMILIES]
    days = sorted({r["Flt_Orig_Date"] for r in deps})

    # 1. Departures per hour of day.
    per_day_hour = collections.Counter()
    for r in deps:
        per_day_hour[(r["Flt_Orig_Date"], parse(r["sea_sched_dep_local"]).hour, r["short_ac_type"])] += 1
    rows = []
    for hour in range(24):
        row = [hour]
        for fam in FAMILIES + ["All"]:
            fams = FAMILIES if fam == "All" else [fam]
            counts = [sum(per_day_hour[(d, hour, f)] for f in fams) for d in days]
            row += [round(sum(counts) / len(days), 1), max(counts)]
        rows.append(row)
    write("hourly_departures.csv",
          ["hour"] + [f"{f} {s}" for f in FAMILIES + ["All"] for s in ("avg", "peak")], rows)

    # 2. Jobs and the time steps they occupy.
    busy = collections.defaultdict(collections.Counter)  # time step -> family -> jobs in progress
    busy_by_concourse = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in deps:
        fam = r["short_ac_type"]
        for start, minutes in jobs_for(r):
            t = floor_bin(start)
            while t < start + timedelta(minutes=minutes):
                busy[t][fam] += 1
                busy_by_concourse[r["Gate"][0]][t][fam] += 1
                t += timedelta(minutes=BIN)

    # Spare units come out of the least capable models first.
    available = dict(units)
    spare = SPARE_UNITS
    for m in sorted(units, key=lambda m: len(can_tow[m])):
        take = min(spare, available[m])
        available[m] -= take
        spare -= take

    def capacity(families):
        return sum(available[m] for m in available if can_tow[m] & families)

    groups = [set(c) for n in range(1, len(FAMILIES) + 1) for c in itertools.combinations(FAMILIES, n)]
    group_capacity = [(g, capacity(g)) for g in groups]

    def peaks(steps, fams):
        """Peak simultaneous jobs, when it happened, and the median and 95th percentile daily peak."""
        per_day_peak = collections.defaultdict(int)
        peak, peak_at = 0, None
        for t, c in steps.items():
            n = sum(c[f] for f in fams)
            per_day_peak[t.date()] = max(per_day_peak[t.date()], n)
            if n > peak:
                peak, peak_at = n, t
        daily = sorted(per_day_peak.get(datetime.strptime(d, "%Y-%m-%d").date(), 0) for d in days)
        at = peak_at.strftime("%Y-%m-%d %H:%M") if peak_at else ""
        return peak, at, daily[len(daily) // 2], daily[int(0.95 * (len(daily) - 1))]

    # 3. Peak simultaneous jobs per class, for the whole airport and per concourse.
    rows = []
    for name, fams in CLASSES.items():
        peak, at, median, p95 = peaks(busy, fams)
        cap = capacity(fams)
        steps_over = sum(1 for c in busy.values() if sum(c[f] for f in fams) > cap)
        rows.append([name, cap, peak, at, median, p95, steps_over * BIN])
    write("peak_demand_by_concourse.csv",
          ["concourse", "class", "peak_jobs", "peak_at", "median_daily_peak", "p95_daily_peak"],
          [[con, name, *peaks(busy_by_concourse[con], fams)]
           for con in sorted(busy_by_concourse) for name, fams in CLASSES.items()])
    write("peak_demand_by_class.csv",
          ["class", "capable_tractors", "peak_jobs", "peak_at", "median_daily_peak",
           "p95_daily_peak", "minutes_over_capacity"], rows)

    # 4. Moments when no assignment of tractors to jobs works.
    rows = []
    for t in sorted(busy):
        c = busy[t]
        worst = None
        for g, cap in group_capacity:
            need = sum(c[f] for f in g)
            if need > cap and (worst is None or need - cap > worst[1] - worst[2]):
                worst = (g, need, cap)
        if worst:
            g, need, cap = worst
            rows.append([t.strftime("%Y-%m-%d %H:%M"), ", ".join(f for f in FAMILIES if f in g),
                         need, cap, sum(c.values())])
    write("shortage_periods.csv",
          ["time", "families", "jobs", "capable_tractors", "all_jobs_in_progress"], rows)


if __name__ == "__main__":
    main()
