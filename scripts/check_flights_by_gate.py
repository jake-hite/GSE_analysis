"""Check that Gate matches the gate ID for each flight's direction.

ARR rows must have Gate == Arr_Gate_Id; DEP rows must have Gate == Dept_Gate_Id.
"""
import csv
import sys

GATE_ID_COLUMN = {"ARR": "Arr_Gate_Id", "DEP": "Dept_Gate_Id"}


def main(path="data/flights_by_gate.csv"):
    problems = []
    with open(path, newline="") as f:
        # Line 1 is the header, so data rows start at line 2.
        for line, row in enumerate(csv.DictReader(f), start=2):
            direction = row["Arr/Dep"].strip().upper()
            column = GATE_ID_COLUMN.get(direction)
            if column is None:
                problems.append(f"line {line}: Arr/Dep is {row['Arr/Dep']!r}, expected ARR or DEP")
            elif row["Gate"].strip() != row[column].strip():
                problems.append(
                    f"line {line}: {direction} flight {row['Flt_Num']} has Gate "
                    f"{row['Gate']!r} but {column} {row[column]!r}"
                )
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s) found in {path}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
