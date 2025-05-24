#!/bin/bash

# Usage: ./script.sh <SRC1_DIR> <SRC2_DIR> <OUTPUT_DIR>
# Example: ./script.sh ./dir1 ./dir2 ./output

SRC1="$1"
SRC2="$2"
OUTPUT="$3"

if [ -z "$SRC1" ] || [ -z "$SRC2" ] || [ -z "$OUTPUT" ]; then
  echo "Usage: $0 <SRC1 directory> <SRC2 directory> <OUTPUT directory>"
  exit 1
fi

# Get the directory where the script is located using dirname and realpath
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
TMP_DIR="$SCRIPT_DIR/tmp"

# Create temporary directory (always absolute path)
mkdir -p "$TMP_DIR"

# Ensure all directories exist and get their absolute paths
mkdir -p "$SRC1" "$SRC2" "$OUTPUT"
SRC1_ABS=$(cd "$SRC1" && pwd)
SRC2_ABS=$(cd "$SRC2" && pwd)
OUTPUT_ABS=$(cd "$OUTPUT" && pwd)

# 1. Get relative file list from SRC1 and SRC2 (exclude .log, .txt, /rootfs/proc, /rootfs/tmp, all .git)
find "$SRC1_ABS" \( -type f -o -type l \) \
  ! -name '*.log' \
  ! -name '*.txt' \
  ! -path "$SRC1_ABS/rootfs/proc/*" \
  ! -path "$SRC1_ABS/rootfs/tmp/*" \
  ! -path '*/.git/*' \
  | sed "s|^$SRC1_ABS/||" | sort > "$TMP_DIR/src1_list.txt"

find "$SRC2_ABS" \( -type f -o -type l \) \
  ! -name '*.log' \
  ! -name '*.txt' \
  ! -path "$SRC2_ABS/rootfs/proc/*" \
  ! -path "$SRC2_ABS/rootfs/tmp/*" \
  ! -path '*/.git/*' \
  | sed "s|^$SRC2_ABS/||" | sort > "$TMP_DIR/src2_list.txt"

# 2. Find added files (in SRC1 but not in SRC2)
comm -23 "$TMP_DIR/src1_list.txt" "$TMP_DIR/src2_list.txt" > "$TMP_DIR/added_files.txt"

# 3. Copy added files from SRC1 to OUTPUT (preserve structure and symlinks)
cd "$SRC1_ABS" || exit 1
while IFS= read -r file; do
  [ -e "$file" ] || continue
  mkdir -p "$OUTPUT_ABS/$(dirname "$file")"
  cp -a "$file" "$OUTPUT_ABS/$file"
done < "$TMP_DIR/added_files.txt"

# 4. Print results
echo "==== Added files ===="
cat "$TMP_DIR/added_files.txt"
echo
echo "Added files have been copied to $OUTPUT_ABS."

# 5. Clean up temporary files
rm -f "$TMP_DIR/src1_list.txt" "$TMP_DIR/src2_list.txt" "$TMP_DIR/added_files.txt"
