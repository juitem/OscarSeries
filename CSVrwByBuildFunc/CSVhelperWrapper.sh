# -----------------------------------------------------------------------------
# get_row_by_buildfunc
# Description: Print the header and the row where BuildFunc matches.
# Usage: get_row_by_buildfunc <csv_file> <BuildFunc>
# -----------------------------------------------------------------------------
get_row_by_buildfunc() {
  python3 csv_helper.py get "$1" "$2"
}

# -----------------------------------------------------------------------------
# get_field_by_buildfunc
# Description: Print the value of a specific field in the row where BuildFunc matches.
# Usage: get_field_by_buildfunc <csv_file> <BuildFunc> <FieldName>
# -----------------------------------------------------------------------------
get_field_by_buildfunc() {
  python3 csv_helper.py getfield "$1" "$2" "$3"
}

# -----------------------------------------------------------------------------
# update_fields_by_buildfunc
# Description: Update one or more fields in the row where BuildFunc matches.
#              If a field does not exist, it will be added as a new column.
#              If BuildFunc does not exist, a new row will be inserted.
# Usage: update_fields_by_buildfunc <csv_file> <BuildFunc> Field1="Value1" [Field2="Value2" ...]
# -----------------------------------------------------------------------------
update_fields_by_buildfunc() {
  local csv_file="$1"
  local build_func="$2"
  shift 2
  python3 csv_helper.py update "$csv_file" "$build_func" "$@"
}

# -----------------------------------------------------------------------------
# delete_row_by_buildfunc
# Description: Delete the row where BuildFunc matches the given value.
# Usage: delete_row_by_buildfunc <csv_file> <BuildFunc>
# -----------------------------------------------------------------------------
delete_row_by_buildfunc() {
  python3 csv_helper.py delete "$1" "$2"
}
