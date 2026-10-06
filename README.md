# GSE_analysis
## GSE inventory table

`data/gse_inventory.csv` lists ground support equipment by model.

| Column | Description |
|---|---|
| `gse_type` | Equipment category (e.g. tug, belt loader, GPU) |
| `model_name` | Manufacturer model name |
| `asset_numbers` | Asset numbers for units of this model, separated by `;` |
| `asset_count` | Number of units; should match the number of entries in `asset_numbers` |
| `compatible_planes` | Aircraft types this model can service, separated by `;` |

Fields that hold several values use `;` so they don't clash with the CSV's commas.
