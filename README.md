# GSE_analysis
## Aircraft type by gate

`data/flights_by_gate.csv` has one row per flight at a gate, recording the aircraft type used.

| Column | Description |
|---|---|
| `Arr/Dep` | `ARR` for an arrival, `DEP` for a departure |
| `Gate` | Gate the flight used at this station |
| `Flt_Orig_Date` | Flight origin date |
| `Origin_Stn` | Origin station code |
| `Dest_Stn` | Destination station code |
| `Aircraft_type` | Aircraft type code (same codes as `aircraft_type` in `gse_compatibility.csv`, e.g. `738`) |
| `Dept_Gate_Id` | Departure gate ID |
| `Arr_Gate_Id` | Arrival gate ID |
| `Flt_Num` | Flight number |

`Gate` must match the gate ID for the row's direction:

- `ARR` rows: `Gate` equals `Arr_Gate_Id`
- `DEP` rows: `Gate` equals `Dept_Gate_Id`

Run `python3 scripts/check_flights_by_gate.py` to check this. It lists any rows that break the rule and exits with an error if there are any.
