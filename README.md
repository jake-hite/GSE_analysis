# GSE_analysis
## Aircraft type by gate

`data/flights_by_gate.csv` has one row per flight at a gate, recording the aircraft type used.

The data comes from `data/raw/Hite_Pull_2_Sept_17.csv`: SEA arrivals and departures from 2026-01-01 to 2026-08-31. 52 rows without a usable gate were left out:

- 25 with a blank `Gate`
- 23 with `Gate` set to `NONE`
- 2 with `Gate` set to `OPS`
- 2 arrivals with `Gate` set to `0` and a blank `Arr_Gate_Id` (flight 354 on 2026-03-13 and flight 2889 on 2026-07-28)

233 flights had a blank aircraft type; their `Aircraft_type` is `NULL`.

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
| `short_ac_type` | Aircraft family, grouped from `Aircraft_type` (see below) |

`short_ac_type` groups aircraft type codes as follows. Rows whose `Aircraft_type` is `NULL` also get `NULL`.

| `short_ac_type` | `Aircraft_type` codes |
|---|---|
| ERJ | EA4, EMW, ES4, ES5 |
| A220 | 221, 223 |
| A321 Neo | 319, 320, 321, 3N1, 3NE, 3NP |
| 737 | 738, 739, 73J, 73R |
| 757 | 75D, 75G, 75H, 75S, 75Y |
| 767 | 764, 76K, 76L |
| A330 | 332, 333, 339 |
| A350 | 359, 35H, 35J, 35M |

`Gate` must match the gate ID for the row's direction:

- `ARR` rows: `Gate` equals `Arr_Gate_Id`
- `DEP` rows: `Gate` equals `Dept_Gate_Id`

Run `python3 scripts/check_flights_by_gate.py` to check this. It lists any rows that break the rule and exits with an error if there are any.

## Arrival and departure summary

`data/arr_dep_summary.csv` counts flights in `flights_by_gate.csv` for each gate, split into arrivals and departures, with one column per `short_ac_type` family.

| Column | Description |
|---|---|
| `Gate` | Gate |
| `Arr/Dep` | `ARR` or `DEP` |
| `ERJ` … `A350` | Number of flights of that aircraft family |
| `NULL` | Number of flights with an unknown aircraft type |
| `Total` | All flights for that gate and direction |

Every gate has both an `ARR` and a `DEP` row, with zeros where there were no flights. Rebuild it after changing `flights_by_gate.csv` with `python3 scripts/build_arr_dep_summary.py`.
