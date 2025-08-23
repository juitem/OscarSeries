#!/bin/bash

# Assume the above wrapper functions are sourced or defined above this line

# 1. Create a sample CSV file
cat > example_modpkg.csv <<EOF
ModName,PkgName,BuildFunc,SrcRoot,GitUrl,Branch,Option1,Option2
coreutils,coreutils,build_coreutils,/src/coreutils,https://git.example.com/coreutils.git,main,enable_nls,static
bash,bash,build_bash,/src/bash,https://git.example.com/bash.git,master,debug,shared
EOF

source CSVhelperWrapper.sh

csv_file="mydata2.csv"

echo "===== 1. Update (insert if not exist) ====="
field1="Option2=\"minimal\""
field2="NewField=\"test\""
result=$(update_fields_by_buildfunc "$csv_file" "build_nginx2" "$field1" "$field2" 2>&1)
echo "Update result:"
echo "$result"

echo
echo "===== 2. Get the inserted row ====="
result=$(get_row_by_buildfunc "$csv_file" "build_nginx2" 2>&1)
echo "$result"

echo
echo "===== 3. Update an existing row ====="
field3="Option2=\"minimal\""
field4="Option1=\"testvalue\""
result=$(update_fields_by_buildfunc "$csv_file" "build_bash" "$field3" "$field4" 2>&1)
echo "Update result:"
echo "$result"

echo
echo "===== 4. Get the updated row ====="
result=$(get_row_by_buildfunc "$csv_file" "build_bash" 2>&1)
echo "$result"

echo
echo "===== 5. Get a specific field value ====="
result=$(get_field_by_buildfunc "$csv_file" "build_bash" "Option2" 2>&1)
echo "Option2 of build_bash: $result"

echo
echo "===== 6. Delete a row ====="
result=$(delete_row_by_buildfunc "$csv_file" "build_nginx2" 2>&1)
echo "Delete result:"
echo "$result"

echo
echo "===== 7. Try to get the deleted row ====="
result=$(get_row_by_buildfunc "$csv_file" "build_nginx2" 2>&1)
echo "$result"
