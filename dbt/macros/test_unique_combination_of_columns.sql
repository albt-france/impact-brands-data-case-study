{#
  Generic test (written here to avoid a package dependency):
  fails with the duplicated key combinations of a model.
#}
{% test unique_combination_of_columns(model, columns) %}
select
    {{ columns | join(', ') }},
    count(*) as row_count
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
