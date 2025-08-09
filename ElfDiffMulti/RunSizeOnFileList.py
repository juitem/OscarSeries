#!/usr/bin/env python3
import sys
import subprocess
import os

def run_size(file_path):
    """Run 'size -A' command and return output lines as list of strings"""
    try:
        result = subprocess.run(
            ["size", "-A", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip().splitlines()
    except FileNotFoundError:
        sys.stderr.write("ERROR: 'size' command not found.\n")
        sys.exit(1)

def human_readable(num):
    """Convert bytes to human readable format (B, K, M, G, T)"""
    for unit in ['B', 'K', 'M', 'G', 'T']:
        if abs(num) < 1024.0:
            return f"{num}{unit}"
        num = round(num / 1024.0, 2)
    return f"{num}P"

def is_header_line(parts):
    """Check if this line is the 'size' output header line"""
    header_set = {"text", "data", "bss", "dec", "hex", "filename"}
    return len(parts) >= 6 and all(p in header_set for p in parts[:6])

def pad_to_column(line, col):
    """Pad the line with spaces so next output starts at the given column index"""
    extra_space = col - len(line)
    if extra_space > 0:
        return line + (' ' * extra_space)
    return line

def main(list_file, dir1, dir2, output_file):
    with open(output_file, "w") as out_f:
        pass

    with open(list_file, "r") as lf:
        for relpath in lf:
            relpath = relpath.strip()
            if not relpath:
                continue

            file1 = os.path.join(dir1, relpath)
            file2 = os.path.join(dir2, relpath)

            lines1 = run_size(file1)
            lines2 = run_size(file2)

            # Save dir1 results in dict by line index and set for missing scan
            ref_data = {}
            used_in_output = set()
            for idx, line in enumerate(lines1):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit() and not is_header_line(parts):
                    ref_data[idx] = (line, parts[0], int(parts[1]))
                else:
                    ref_data[idx] = (line, parts[0] if parts else "", None)

            with open(output_file, "a") as out_f:
                maxlines = max(len(lines1), len(lines2))
                # Main comparison: go through lines2
                for idx, line in enumerate(lines2):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit() and not is_header_line(parts):
                        sym2 = parts[0]
                        val2 = int(parts[1])
                        # 1st: get corresponding line from ref_data
                        # If not present, it's a newly added or moved in 2nd
                        rec1 = ref_data.get(idx, (None, None, None))
                        sym1, val1 = rec1[1], rec1[2]
                        original_line = line.rstrip()
                        if sym1 != sym2 or val1 is None:
                            added_info = "ERROR!!!"
                        else:
                            diff = val2 - val1
                            pct = (diff / val1 * 100) if val1 != 0 else 0.0
                            hr_val1 = human_readable(val1)
                            hr_val2 = human_readable(val2)
                            hr_diff = human_readable(diff)
                            if diff == 0:
                                added_info = f"{hr_val1:>8}  {hr_val2:>8}  {hr_diff:>8}"
                            else:
                                added_info = f"{hr_val1:>8}  {hr_val2:>8}  {hr_diff:>8} ({pct:+.2f}%)"
                            used_in_output.add(idx)
                        out_f.write(f"{pad_to_column(original_line, 45)}{added_info}\n")
                    else:
                        # Header and otherwise
                        out_f.write(line.rstrip() + "\n")

                # Now, find lines only in result1 but not used
                # These are lines present only in dir1 (missing in dir2 result)
                for idx in range(len(lines1)):
                    if idx not in used_in_output:
                        # Only check actual data lines, not header
                        parts = lines1[idx].split()
                        if len(parts) >= 2 and parts[1].isdigit() and not is_header_line(parts):
                            original_line = lines1[idx].rstrip()
                            out_f.write(f"{pad_to_column(original_line, 45)}ERROR!!! (moved)\n")

                out_f.write("\n")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <list_file> <dir1> <dir2> <output_file>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
