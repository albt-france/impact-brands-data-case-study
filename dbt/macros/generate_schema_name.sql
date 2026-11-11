{#
  Use the folder schema as-is (staging, intermediate, marts, seeds, audit)
  instead of dbt's default "<target_schema>_<custom_schema>".
  On BigQuery each one becomes a dataset; on DuckDB a schema in the same file.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
