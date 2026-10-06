# GSE_analysis
## Aircraft type by gate

`data/flights_by_gate.csv` has one row per flight at a gate, recording the aircraft type used.

| Column | Description |
|---|---|
| `Arr/Dep` | Whether the row is an arrival or a departure |
| `Gate` | Gate the flight used |
| `Flt_Orig_Date` | Flight origin date |
| `Origin_Stn` | Origin station code |
| `Dest_Stn` | Destination station code |
| `Aircraft_type` | Aircraft type code (same codes as `aircraft_type` in `gse_compatibility.csv`, e.g. `738`) |
| `Dept_Gate_Id` | Departure gate ID |
| `Arr_Gate_Id` | Arrival gate ID |
| `Flt_Num` | Flight number |
