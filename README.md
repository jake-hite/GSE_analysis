# GSE_analysis
## GSE inventory tables

The inventory is split into three CSV files in `data/`, linked by `model_name`.

### `gse_models.csv`: one row per equipment model

| Column | Description |
|---|---|
| `model_name` | Manufacturer model name (unique; the key the other tables reference) |
| `gse_type` | Equipment category (e.g. tug, belt loader, GPU) |
| `short_name` | Short name or abbreviation for the equipment |

### `gse_assets.csv`: one row per physical unit

| Column | Description |
|---|---|
| `asset_number` | Unique asset number for the unit |
| `model_name` | Model of the unit; must match a row in `gse_models.csv` |

### `gse_compatibility.csv`: one row per model–aircraft pair

| Column | Description |
|---|---|
| `model_name` | Equipment model; must match a row in `gse_models.csv` |
| `aircraft_type` | One aircraft type the model can service |

The asset count for a model is the number of rows for that model in `gse_assets.csv`, so it isn't stored separately.

## Aircraft type by gate

`data/flights_by_gate.csv` has one row per flight at a gate, recording the aircraft type used.

It is built from `data/raw/Hite_Pull_10.7.csv` by `python3 scripts/build_flights_by_gate.py`: SEA arrivals and departures from 2026-01-01 to 2026-08-31. 52 rows without a usable gate are left out:

- 27 with a blank or `NULL` gate (including flight 354 on 2026-03-13 and flight 2889 on 2026-07-28)
- 23 with the gate set to `NONE`
- 2 with the gate set to `OPS`

Flights with a blank aircraft type have `NULL` as their `Aircraft_type`.

The earlier export, `data/raw/Hite_Pull_2_Sept_17.csv`, has the same flights without times, plus flight 81 from CDG on 2026-08-23, which the newer export does not include.

In the raw export, the `Ib_*` time columns describe the flight that brought the aircraft into the row's origin airport, and `schd_dprt_gts` is the row's own scheduled departure in GMT. So only `DEP` rows, whose origin is SEA, have SEA times; on `ARR` rows the time columns are `NULL`. The export's `Time`, second `schd_dprt_gts`, `Schd_Op_Ct`, `DOT_D0_Ct` and unnamed last column are not used.

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
| `sea_sched_dep_local` | `DEP` only: scheduled departure from SEA |
| `inbound_gate` | `DEP` only: SEA gate the aircraft arrived at before this departure |
| `inbound_sched_arr_local` | `DEP` only: scheduled arrival at SEA of the inbound aircraft |
| `inbound_actual_arr_local` | `DEP` only: actual arrival at SEA of the inbound aircraft |
| `towed` | `DEP` only: `Y` if `inbound_gate` differs from `Gate`, so the aircraft was moved between gates; `N` if not; `NULL` if the inbound gate is unknown |

Times are Seattle local time (PST/PDT) as `YYYY-MM-DD HH:MM`.

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

## Capability match

`python3 scripts/build_capability_match.py` compares the tow tractor fleet with departure demand and writes three tables. Only departures are counted, since each one needs a pushback. Departures with a `NULL` aircraft type are left out of the capability checks.

- `data/tractor_capability_by_family.csv`: one row per tractor model, with its unit count and a `1` for each aircraft family it can tow every type of.
- `data/family_daily_demand.csv`: for each aircraft family, average and peak-day departures against the number of tractors able to tow it.
- `data/gate_capability_match.csv`: one row per gate, with its departures, widebody (767, A330, A350) departures, the hardest family to cover there (the one the fewest tractors can tow), and the tractor models that can tow every aircraft type seen at that gate.

These are daily figures. They show which tractors each gate depends on, but not whether enough tractors are free at the same time; that needs departure times.

## Peak demand

`python3 scripts/build_peak_demand.py` measures how many tractors are busy at the same time. Each departure is a pushback job at its scheduled time, and each towed departure also has a tow job. The assumptions are set at the top of the script:

- a pushback keeps a tractor busy for 20 minutes (30 for widebodies), and a tow for 45 minutes
- a tow starts 60 minutes before departure, or when the aircraft arrived if that was later
- no tractors are out of service (`SPARE_UNITS`)

Travel time between gates is not modelled, and times are scheduled, not actual. Departures with a `NULL` aircraft type are left out.

- `data/hourly_departures.csv`: average and peak-day departures for each hour of the day, by aircraft family
- `data/peak_demand_by_class.csv`: for groups of aircraft families, the most jobs in progress at once against the tractors able to do them, with median and 95th-percentile daily peaks
- `data/peak_demand_by_concourse.csv`: the same peaks for each concourse, i.e. what each would need with its own tractors
- `data/shortage_periods.csv`: every 5-minute step when no assignment of tractors to the jobs in progress works

## Hybrid staging

`python3 scripts/build_hybrid_staging.py` models one tractor staged at each gate in `STAGED_GATES` (set at the top of the script) with every other tractor in a shared pool. Gates joined with `+` (e.g. `A12+A12A`) share one staged tractor. It uses the same jobs and assumptions as the peak demand analysis. Each staged gate gets a model that can tow as many of its aircraft as possible, picked so the pool is left short as rarely as possible. A staged tractor takes each job at its gate if it is free and can tow the aircraft; everything else goes to the pool.

- `data/hybrid_staged_gates.csv`: for each staged gate, the model staged there, how many of the gate's jobs it handles, why the rest go to the pool, and how busy it is over the 05:00–24:00 day
- `data/hybrid_pool_demand.csv`: peak pool jobs for each group of aircraft families against the pool's tractors
- `data/hybrid_pool_shortages.csv`: every 5-minute step when the pool cannot cover its jobs
