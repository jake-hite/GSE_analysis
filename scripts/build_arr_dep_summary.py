"""Build data/arr_dep_summary.csv: flights per gate and direction, by aircraft family."""
import collections
import csv
import re
import sys

FAMILIES = ["ERJ", "A220", "A321 Neo", "737", "757", "767", "A330", "A350", "NULL"]


def gate_sort_key(gate):
    # Sort by terminal letter, then gate number, so A2 comes before A10.
    return gate[0], int(re.match(r"\D(\d+)", gate).group(1)), gate


def main(src="data/flights_by_gate.csv", dst="data/arr_dep_summary.csv"):
    counts = collections.defaultdict(collections.Counter)
    with open(src, newline="") as f:
        for row in csv.DictReader(f):
            counts[(row["Gate"], row["Arr/Dep"])][row["short_ac_type"]] += 1
    unknown = {fam for c in counts.values() for fam in c} - set(FAMILIES)
    if unknown:
        sys.exit(f"Unknown short_ac_type values: {sorted(unknown)}")

    gates = sorted({gate for gate, _ in counts}, key=gate_sort_key)
    with open(dst, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["Gate", "Arr/Dep", *FAMILIES, "Total"])
        for gate in gates:
            for direction in ("ARR", "DEP"):
                c = counts[(gate, direction)]
                writer.writerow([gate, direction, *(c[fam] for fam in FAMILIES), sum(c.values())])
    print(f"Wrote {len(gates) * 2} rows to {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
