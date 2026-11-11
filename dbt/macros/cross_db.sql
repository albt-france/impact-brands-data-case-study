{#
  Small cross-database helpers. dbt picks the right version for the active adapter:
  `default__` runs on DuckDB (local), `bigquery__` runs on BigQuery.
  Everything else in the project uses dbt's built-in cross-db macros
  (dbt.date_trunc, dbt.dateadd, dbt.datediff, dbt.safe_cast, dbt.type_*).

  Convention: every timestamp in staging and later is UTC.
  DuckDB stores it as a plain TIMESTAMP (UTC), BigQuery as TIMESTAMP (always UTC).
#}

{# Local wall-clock timestamp (no zone) + IANA zone name -> UTC timestamp #}
{% macro local_to_utc(column, tz_column) %}
  {{ return(adapter.dispatch('local_to_utc', 'impact_brands')(column, tz_column)) }}
{% endmacro %}

{% macro default__local_to_utc(column, tz_column) %}
  timezone('UTC', timezone({{ tz_column }}, cast({{ column }} as timestamp)))
{% endmacro %}

{% macro bigquery__local_to_utc(column, tz_column) %}
  timestamp(cast({{ column }} as datetime), {{ tz_column }})
{% endmacro %}


{# UTC timestamp -> calendar date in a given zone (the "reporting day") #}
{% macro utc_to_local_date(column, tz=None) %}
  {%- set tz = tz or "'" ~ var('reporting_timezone') ~ "'" -%}
  {{ return(adapter.dispatch('utc_to_local_date', 'impact_brands')(column, tz)) }}
{% endmacro %}

{% macro default__utc_to_local_date(column, tz) %}
  cast(timezone({{ tz }}, timezone('UTC', {{ column }})) as date)
{% endmacro %}

{% macro bigquery__utc_to_local_date(column, tz) %}
  date({{ column }}, {{ tz }})
{% endmacro %}


{# Unix epoch seconds (payment provider style) -> UTC timestamp #}
{% macro epoch_to_utc(column) %}
  {{ return(adapter.dispatch('epoch_to_utc', 'impact_brands')(column)) }}
{% endmacro %}

{% macro default__epoch_to_utc(column) %}
  make_timestamp(cast({{ column }} as bigint) * 1000000)
{% endmacro %}

{% macro bigquery__epoch_to_utc(column) %}
  timestamp_seconds(cast({{ column }} as int64))
{% endmacro %}


{# Lower-case text and replace every run of non-alphanumeric characters with one space.
   'PHR_BloodSugar-US v3' -> 'phr bloodsugar us v3' #}
{% macro normalize_text(column) %}
  {{ return(adapter.dispatch('normalize_text', 'impact_brands')(column)) }}
{% endmacro %}

{% macro default__normalize_text(column) %}
  trim(regexp_replace(lower({{ column }}), '[^a-z0-9]+', ' ', 'g'))
{% endmacro %}

{% macro bigquery__normalize_text(column) %}
  trim(regexp_replace(lower({{ column }}), r'[^a-z0-9]+', ' '))
{% endmacro %}


{# Same as normalize_text but removes the spaces too: 'Blood-Sugar' -> 'bloodsugar' #}
{% macro squash_text(column) %}
  replace({{ normalize_text(column) }}, ' ', '')
{% endmacro %}


{# Source location: Parquet files locally, loaded raw tables on BigQuery #}
{% macro raw_schema() %}
  {{ return('raw' if target.type == 'bigquery' else 'main') }}
{% endmacro %}
