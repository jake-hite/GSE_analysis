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
