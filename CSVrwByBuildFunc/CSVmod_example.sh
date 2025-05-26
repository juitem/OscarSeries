#!/bin/bash

# Assume the wrapper functions above are already sourced or defined in this script

csv_file="example_modpkg.csv"
build_func="build_nginx"

# 1. Delete a row by BuildFunc and capture result
result=$(delete_row_by_buildfunc "$csv_file" "$build_func" 2>&1)
echo "Delete result:"
echo "$result"

# 2. Try to get the deleted row (should show error)
result=$(get_row_by_buildfunc "$csv_file" "$build_func" 2>&1)
echo "Get deleted row result:"
echo "$result"

# 3. Update a row and capture result
result=$(update_fields_by_buildfunc "$csv_file" "build_bash" Option2="minimal" NewField="testvalue" 2>&1)
echo "Update result:"
echo "$result"

# 4. Get a specific field value and capture result
result=$(get_field_by_buildfunc "$csv_file" "build_bash" "NewField" 2>&1)
echo "Get field result:"
echo "$result"
