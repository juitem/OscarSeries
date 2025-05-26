# 1. BuildFunc로 해당 row 전체 출력 (헤더 포함)
# usage: get_row_by_buildfunc <csv_file> <BuildFunc>
get_row_by_buildfunc() {
  python3 csv_helper.py get "$1" "$2"
}

# 2. BuildFunc로 임의의 필드 값만 출력
# usage: get_field_by_buildfunc <csv_file> <BuildFunc> <FieldName>
get_field_by_buildfunc() {
  python3 csv_helper.py getfield "$1" "$2" "$3"
}

# 3. BuildFunc로 여러 필드 값 수정 (FieldName="Value" 형태, 여러 개 가능)
# usage: update_fields_by_buildfunc <csv_file> <BuildFunc> Field1="Value1" [Field2="Value2" ...]
update_fields_by_buildfunc() {
  local csv_file="$1"
  local build_func="$2"
  shift 2
  python3 csv_helper.py update "$csv_file" "$build_func" "$@"
}
