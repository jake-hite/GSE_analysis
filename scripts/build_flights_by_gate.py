"""Build data/flights_by_gate.csv from the raw flight export data/raw/Hite_Pull_10.7.csv.

Cleaning rules (agreed with the data owner):
- Gate is Ob_Arr_Gt_Id for ARR rows and Ob_Dprt_Gt_Id for DEP rows. Gates listed together
  in GATE_GROUPS are treated as one gate, named like "A4/A4A"; Dept_Gate_Id and Arr_Gate_Id
  keep the original gate IDs.
- Rows whose Gate is blank, NULL, NONE or OPS are dropped.
- A blank or NULL aircraft type becomes NULL.
- short_ac_type groups aircraft type codes into families.

In this export the Ib_* columns describe the flight that brought the aircraft into the
row's origin airport, and schd_dprt_gts is the row's own scheduled departure in GMT.
So only DEP rows (origin SEA) carry SEA times:
- sea_sched_dep_local: scheduled departure from SEA (from schd_dprt_gts)
- inbound_gate: SEA gate the aircraft arrived at (Ib_Arr_Gt_Id)
- inbound_sched_arr_local: scheduled arrival at SEA (Ib_Schd_Arr_LTs, Seattle time)
- inbound_actual_arr_local: actual arrival at SEA (ib_actl_arr_gts, GMT)
- towed: Y if the aircraft arrived at a different gate than it departed from (gates in
  the same group count as the same gate)
All times are Seattle local (PST/PDT) as YYYY-MM-DD HH:MM. ARR rows have NULL there.
"""
import csv
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SRC = "data/raw/Hite_Pull_10.7.csv"
DST = "data/flights_by_gate.csv"
SEA = ZoneInfo("America/Los_Angeles")

# Gates treated as one gate. Each group's members are reported under the group name.
GATE_GROUPS = ["A4/A4A", "A8/A8A", "A10/A10A", "A11/A11A", "A13/A13A", "B7/B7A/B7B",
               "S1/S1B", "S3/S3A", "S4/S4A", "S6/S6A", "S7/S7A", "S8/S8A", "S9/S9A/S9B",
               "S10/S10A"]
MERGED_GATE = {gate: group for group in GATE_GROUPS for gate in group.split("/")}


def merged(gate):
    """The gate name used in the table: the group name for a grouped gate, else the gate."""
    return MERGED_GATE.get(gate, gate)

FAMILIES = {
    "ERJ": "EA4 EMW ES4 ES5", "A220": "221 223", "A321 Neo": "319 320 321 3N1 3NE 3NP",
    "737": "738 739 73J 73R", "757": "75D 75G 75H 75S 75Y", "767": "764 76K 76L",
    "A330": "332 333 339", "A350": "359 35H 35J 35M",
}
SHORT_AC_TYPE = {code: fam for fam, codes in FAMILIES.items() for code in codes.split()}
SHORT_AC_TYPE["NULL"] = "NULL"

COLUMNS = [
    "Arr/Dep", "Gate", "Flt_Orig_Date", "Origin_Stn", "Dest_Stn", "Aircraft_type",
    "Dept_Gate_Id", "Arr_Gate_Id", "Flt_Num", "short_ac_type",
    "sea_sched_dep_local", "inbound_gate", "inbound_sched_arr_local",
    "inbound_actual_arr_local", "towed",
]


def clean(value):
    value = value.strip()
    return "" if value == "NULL" else value


def parse_time(value):
    value = clean(value)
    return datetime.strptime(value, "%I:%M:%S %p").time() if value else None


def fmt(dt):
    return dt.astimezone(SEA).strftime("%Y-%m-%d %H:%M") if dt else "NULL"


def on_local_date(t, local_date):
    """The moment with UTC time of day t whose Seattle date is local_date."""
    for offset in (-1, 0, 1):
        dt = datetime.combine(local_date + timedelta(days=offset), t, timezone.utc)
        if dt.astimezone(SEA).date() == local_date:
            return dt
    raise ValueError(f"No UTC time {t} falls on {local_date} in Seattle")


def last_before(t, tz, limit):
    """The latest moment with time of day t (in tz) at or before limit."""
    local = limit.astimezone(tz)
    dt = datetime.combine(local.date(), t, tz)
    return dt if dt <= limit else dt - timedelta(days=1)


def nearest(t, tz, target):
    """The moment with time of day t (in tz) closest to target."""
    local = target.astimezone(tz)
    options = [datetime.combine(local.date() + timedelta(days=o), t, tz) for o in (-1, 0, 1)]
    return min(options, key=lambda dt: abs(dt - target))


def main(src=SRC, dst=DST):
    with open(src, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    # Two columns are named schd_dprt_gts; index() finds the first, which is the one to use.
    col = {name: header.index(name) for name in header if name}

    dropped, out = {}, []
    for r in rows:
        v = lambda name: r[col[name]].strip()
        direction = v("ARR/DEP")
        dep_gate, arr_gate = clean(v("Ob_Dprt_Gt_Id")), clean(v("Ob_Arr_Gt_Id"))
        gate = merged(arr_gate if direction == "ARR" else dep_gate)
        if gate in ("", "NONE", "OPS"):
            reason = gate or "blank or NULL Gate"
            dropped[reason] = dropped.get(reason, 0) + 1
            continue

        flt_date = datetime.strptime(v("Flt_Orig_Dt"), "%m/%d/%Y").date()
        ac_type = clean(v("Actl_Ac_Typ_Cd")) or "NULL"
        sched_dep = inbound_sched = inbound_actual = None
        inbound_gate, towed = "NULL", "NULL"
        if direction == "DEP":
            dep_gt = parse_time(v("schd_dprt_gts"))
            if dep_gt:
                sched_dep = on_local_date(dep_gt, flt_date)
                arr_lt, arr_gt = parse_time(v("Ib_Schd_Arr_LTs")), parse_time(v("ib_actl_arr_gts"))
                if arr_lt:
                    inbound_sched = last_before(arr_lt, SEA, sched_dep)
                if arr_gt:
                    inbound_actual = nearest(arr_gt, timezone.utc, inbound_sched or sched_dep)
            inbound_gate = merged(clean(v("Ib_Arr_Gt_Id"))) or "NULL"
            if inbound_gate != "NULL":
                towed = "Y" if inbound_gate != gate else "N"

        out.append({
            "Arr/Dep": direction, "Gate": gate, "Flt_Orig_Date": flt_date.isoformat(),
            "Origin_Stn": v("Schd_Orig_Stn_Cd"), "Dest_Stn": v("Schd_Dest_Stn_Cd"),
            "Aircraft_type": ac_type, "Dept_Gate_Id": dep_gate or "NULL",
            "Arr_Gate_Id": arr_gate or "NULL", "Flt_Num": v("Flt_Nb"),
            "short_ac_type": SHORT_AC_TYPE[ac_type],
            "sea_sched_dep_local": fmt(sched_dep), "inbound_gate": inbound_gate,
            "inbound_sched_arr_local": fmt(inbound_sched),
            "inbound_actual_arr_local": fmt(inbound_actual), "towed": towed,
        })

    with open(dst, "w", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    print(f"Read {len(rows)} rows, dropped {sum(dropped.values())} {dropped}, wrote {len(out)} to {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
