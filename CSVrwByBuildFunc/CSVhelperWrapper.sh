# get_row_by_buildfunc: Print the header and the row where BuildFunc matches.
get_row_by_buildfunc() {
  python3 csv_helper.py get "$1" "$2"
}

# get_field_by_buildfunc: Print the value of a specific field in the row where BuildFunc matches.
get_field_by_buildfunc() {
  local csv_file="$1"
  local build_func="$2"
  shift 2
  python3 csv_helper.py getfield "$csv_file" "$build_func" "$@"
}

# update_fields_by_buildfunc: Update or insert fields for a BuildFunc.
# Usage: update_fields_by_buildfunc <csv_file> <BuildFunc> Field1="Value1" [Field2="Value2" ...]
update_fields_by_buildfunc() {
  local csv_file="$1"
  local build_func="$2"
  shift 2
  python3 csv_helper.py update "$csv_file" "$build_func" "$@"
}

# delete_row_by_buildfunc: Delete the row where BuildFunc matches.
delete_row_by_buildfunc() {
  python3 csv_helper.py delete "$1" "$2"
}
