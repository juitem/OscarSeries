import os
import csv
import re
import sys
import subprocess
from collections import defaultdict

def get_elf_section_sizes(filepath):
    """Return (.text, .data, .bss) sizes for ELF files, or (0,0,0) otherwise."""
    try:
        output = subprocess.check_output(
            ['size', filepath],
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        lines = output.strip().split('\n')
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        pass
    return 0, 0, 0

def clean_filename(filename):
    """Remove digits, dots, and hyphens from the filename (including extension)."""
    return re.sub(r'[\d.\-]', '', filename)

def generate_uniq_id(entries):
    """Replace all duplicated UniqIDs with the original directory+filename."""
    uniqid_counts = defaultdict(int)
    duplicated_ids = set()
    for entry in entries:
        dirpath, filename = entry[0], entry[1]
        cleaned = clean_filename(filename)
        entry.append(dirpath + cleaned)
        uniqid_counts[entry[-1]] += 1
    duplicated_ids = {uid for uid, cnt in uniqid_counts.items() if cnt > 1}
    for entry in entries:
        if entry[-1] in duplicated_ids:
            entry[-1] = entry[0] + entry[1]

def list_files_info(directory):
    entries = []
    for root, _, files in os.walk(directory):
        dirpath = root.replace("\\", "/")
        if not dirpath.endswith("/"):
            dirpath += "/"
        for file in files:
            filepath = os.path.join(root, file)
            # Skip symbolic links
            if os.path.islink(filepath):
                continue
            try:
                filesize = os.path.getsize(filepath)
                text, data, bss = get_elf_section_sizes(filepath)
                entries.append([dirpath, file, filesize, text, data, bss])
            except Exception:
                entries.append([dirpath, file, 0, 0, 0, 0])
    generate_uniq_id(entries)
    return entries

def save_to_csv(file_list):
    with open('FileList.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['directory', 'filename', 'filesize', '.textsize', '.datasize', '.bsssize', 'UniqID'])
        writer.writerows(file_list)

def main(directory):
    save_to_csv(list_files_info(directory))
    return 'CSV file created successfully.'

if __name__ == "__main__":
    script_name = os.path.basename(sys.argv[0])
    if len(sys.argv) > 1:
        print(main(sys.argv[1]))
    else:
        print(f"Usage: python3 {script_name} <directory_path>")
        print(f"Example: python3 {script_name} /home/user/documents")
