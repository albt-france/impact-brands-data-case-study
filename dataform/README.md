# Dataform version (2 models)

The warehouse is built with dbt. These two models show the same logic written for **Dataform**
(BigQuery's native transformation tool), to compare the two side by side.

| File | dbt equivalent |
|---|---|
| `definitions/stg_shop__orders.sqlx` | `dbt/models/staging/stg_shop__orders.sql` |
| `definitions/int_campaigns_mapped.sqlx` | `dbt/models/intermediate/int_campaigns_mapped.sql` |

## dbt ↔ Dataform

| Concept | dbt | Dataform |
|---|---|---|
| Model file | `.sql` + `.yml` | `.sqlx` (config block + SQL) |
| Reference another model | `{{ ref('model') }}` | `${ref("model")}` |
| Raw table | `{{ source('shop', 'raw_shop_orders') }}` | `${ref("raw", "raw_shop_orders")}` or a `declaration` |
| Materialization | `{{ config(materialized='table') }}` | `config { type: "table" }` |
| Incremental | `materialized='incremental'` + `is_incremental()` | `type: "incremental"` + `when(incremental(), ...)` |
| Tests | `data_tests: [unique, not_null]`, singular tests in `tests/` | `assertions: { uniqueKey, nonNull, rowConditions }`, assertion files |
| Variables | `var('fix_version')` in `dbt_project.yml` | `dataform.projectConfig.vars.fixVersion` in `workflow_settings.yaml` |
| Seeds (CSV) | `seeds/*.csv` + `dbt seed` | load the CSV as a table, then `declaration` |
| Docs & lineage | `dbt docs generate` | Compiled graph in the Dataform UI |
| Cross-database macros | `dbt.dateadd`, adapter dispatch | Not needed: BigQuery only |

Not run in this repository (Dataform needs a Google Cloud project); kept as a syntax and design comparison.
