"""Match tow tractor capability to departure demand, by aircraft family and by gate.

Reads the tractor tables (gse_models, gse_assets, gse_compatibility) and
flights_by_gate.csv, and writes three tables to data/:

- tractor_capability_by_family.csv: which tractor models can tow each aircraft family
- family_daily_demand.csv: departures per day for each family against the tractors able to tow it
- gate_capability_match.csv: for each gate, the hardest aircraft family to cover and the
  tractors that can cover it

Only departures are counted, since they need a pushback. Flights whose aircraft type
is NULL are left out of capability checks because their type is unknown.
"""
import collections
import csv
import re

DATA = "data/"
FAMILIES = ["ERJ", "A220", "A321 Neo", "737", "757", "767", "A330", "A350"]


def read(name):
    with open(DATA + name, newline="") as f:
        return list(csv.DictReader(f))


def write(name, header, rows):
    with open(DATA + name, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {DATA}{name}")


def gate_sort_key(gate):
    return gate[0], int(re.match(r"\D(\d+)", gate).group(1)), gate


def main():
    models = read("gse_models.csv")
    units = collections.Counter(r["model_name"] for r in read("gse_assets.csv"))
    tows = collections.defaultdict(set)
    for r in read("gse_compatibility.csv"):
        tows[r["model_name"]].add(r["aircraft_type"])

    deps = [r for r in read("flights_by_gate.csv") if r["Arr/Dep"] == "DEP"]
    known = [r for r in deps if r["Aircraft_type"] != "NULL"]
    days = sorted({r["Flt_Orig_Date"] for r in deps})

    # Aircraft type codes seen in the flights, grouped by family.
    family_types = collections.defaultdict(set)
    for r in known:
        family_types[r["short_ac_type"]].add(r["Aircraft_type"])
    missing = {r["Aircraft_type"] for r in known} - set().union(*tows.values())
    if missing:
        raise SystemExit(f"No tractor is listed as compatible with: {sorted(missing)}")

    def can_tow(model, types):
        return types <= tows[model]

    capable = {
        fam: [m["model_name"] for m in models if can_tow(m["model_name"], family_types[fam])]
        for fam in FAMILIES
    }
    capable_units = {fam: sum(units[m] for m in capable[fam]) for fam in FAMILIES}

    # 1. Capability matrix.
    write(
        "tractor_capability_by_family.csv",
        ["model_name", "short_name", "units", *FAMILIES],
        [
            [m["model_name"], m["short_name"], units[m["model_name"]],
             *(int(m["model_name"] in capable[fam]) for fam in FAMILIES)]
            for m in models
        ],
    )

    # 2. Daily demand per family against capable tractors.
    per_day = collections.defaultdict(collections.Counter)
    for r in known:
        per_day[r["short_ac_type"]][r["Flt_Orig_Date"]] += 1
    rows = []
    for fam in FAMILIES:
        total = sum(per_day[fam].values())
        peak_date, peak = max(per_day[fam].items(), key=lambda kv: kv[1]) if total else ("", 0)
        n = capable_units[fam]
        rows.append([
            fam, total, round(total / len(days), 1), peak, peak_date, n,
            round(total / len(days) / n, 1), round(peak / n, 1),
        ])
    write(
        "family_daily_demand.csv",
        ["short_ac_type", "departures", "avg_per_day", "peak_day_departures", "peak_date",
         "capable_units", "avg_per_capable_unit_per_day", "peak_per_capable_unit_per_day"],
        rows,
    )

    # 3. Per gate: hardest family to cover, and whether one model can cover every type.
    scarcity = sorted(FAMILIES, key=lambda fam: capable_units[fam])  # hardest first
    by_gate = collections.defaultdict(list)
    for r in deps:
        by_gate[r["Gate"]].append(r)
    rows = []
    for gate in sorted(by_gate, key=gate_sort_key):
        flights = by_gate[gate]
        fams = {r["short_ac_type"] for r in flights} - {"NULL"}
        types = {r["Aircraft_type"] for r in flights} - {"NULL"}
        hardest = next((fam for fam in scarcity if fam in fams), "")
        all_round = [m["model_name"] for m in models if can_tow(m["model_name"], types)] if types else []
        widebody = sum(r["short_ac_type"] in ("767", "A330", "A350") for r in flights)
        rows.append([
            gate, gate[0], len(flights), round(len(flights) / len(days), 1), widebody,
            hardest, capable_units.get(hardest, ""),
            sum(units[m] for m in all_round),
            "; ".join(all_round),
        ])
    write(
        "gate_capability_match.csv",
        ["Gate", "concourse", "departures", "avg_departures_per_day", "widebody_departures",
         "hardest_family", "units_for_hardest_family", "units_covering_all_types",
         "models_covering_all_types"],
        rows,
    )


if __name__ == "__main__":
    main()
