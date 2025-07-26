#!/bin/bash

# Usage: ./script.sh <SRC_DIR> <TARGET_DIR>
# Example: ./script.sh ./myrepo ../backup

SRC="$1"
TARGET="$2"

if [ -z "$SRC" ] || [ -z "$TARGET" ]; then
  echo "Usage: $0 <SRC directory> <TARGET directory>"
  exit 1
fi

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP_DIR="$SCRIPT_DIR/tmp"

# Create temporary directory
mkdir -p "$TMP_DIR"

ADDED="$TMP_DIR/added_files.txt"
DELETED="$TMP_DIR/deleted_files.txt"
MODIFIED="$TMP_DIR/modified_files.txt"

# Convert SRC and TARGET to absolute paths
SRC_ABS=$(cd "$SRC" && pwd)
TARGET_ABS=$(cd "$TARGET" 2>/dev/null || mkdir -p "$TARGET" && cd "$TARGET" && pwd)

if [ ! -d "$SRC_ABS/.git" ]; then
  echo "SRC directory is not a git repository: $SRC_ABS"
  # Remove temporary files
  rm -f "$ADDED" "$DELETED" "$MODIFIED"
  exit 1
fi

cd "$SRC_ABS" || exit 1

# 1. Extract lists of added, deleted, and modified files (excluding .log files and proc folder)
git ls-files --others --exclude-standard \
  | grep -v '\.log$' | grep -v '^proc/' > "$ADDED"

git ls-files --deleted \
  | grep -v '\.log$' | grep -v '^proc/' > "$DELETED"

git ls-files -m \
  | grep -v '\.log$' | grep -v '^proc/' > "$MODIFIED"

# 2. Copy added/modified files to TARGET (preserve directory structure and symlinks)
cat "$ADDED" "$MODIFIED" | sort | uniq | while read file; do
  [ -e "$file" ] || continue  # Only if the file actually exists
  mkdir -p "$TARGET_ABS/$(dirname "$file")"
  cp -a "$file" "$TARGET_ABS/$file"
done

# 3. Print results
echo "==== Added files ===="
cat "$ADDED"
echo
echo "==== Deleted files ===="
cat "$DELETED"
echo
echo "==== Modified files ===="
cat "$MODIFIED"
echo
echo "Added/modified files have been copied to $TARGET_ABS."

# 4. Clean up temporary files
rm -f "$ADDED" "$DELETED" "$MODIFIED"
# (Optionally, you can also clean up TMP_DIR if needed)
