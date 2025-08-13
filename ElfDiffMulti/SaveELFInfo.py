import os
import sys
import csv
from elftools.elf.elffile import ELFFile

# ELF constants
SHT_NOBITS = 8
SHF_ALLOC = 0x2
SHF_WRITE = 0x1
SHF_EXECINSTR = 0x4

def is_target_file(file_path):
    """
    Decide if the file should be processed.
    - Exclude symlinks
    - Currently only process ELF files
    """
    if os.path.islink(file_path):
        return False
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)
            return magic == b'\x7fELF'
    except:
        return False

def get_segment_flags_and_mapping(elf, section):
    """Return PT_FLAGS for the segment mapping this section and mapping pass status."""
    pt_flags_val = "-"
    mapping_pass = False

    sec_off  = section['sh_offset']
    sec_endf = sec_off + section['sh_size']
    sec_addr = section['sh_addr']
    sec_enda = sec_addr + section['sh_size']

    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        seg_off  = seg['p_offset']
        seg_endf = seg_off + seg['p_filesz']
        seg_addr = seg['p_vaddr']
        seg_enda = seg_addr + seg['p_memsz']

        if (sec_off >= seg_off and sec_endf <= seg_endf and
            sec_addr >= seg_addr and sec_enda <= seg_enda):
            pt_flags_val = seg['p_flags']
            mapping_pass = True
            break
    return pt_flags_val, mapping_pass

def extract_section_info(file_path, base_dir):
    """Extract detailed section info from an ELF file."""
    results = []
    try:
        with open(file_path, 'rb') as f:
            elf = ELFFile(f)
            file_size = os.path.getsize(file_path)
            rel_path = os.path.relpath(file_path, base_dir)

            for sec in elf.iter_sections():
                pt_flags, mapping_pass = get_segment_flags_and_mapping(elf, sec)
                results.append({
                    "file": rel_path,
                    "file_size": file_size,
                    "section_name": sec.name,
                    "section_size": sec['sh_size'],
                    "pt_flags": pt_flags,
                    "sh_flags": int(sec['sh_flags']),
                    "sh_type": int(sec['sh_type']) if isinstance(sec['sh_type'], int) else str(sec['sh_type']),
                    "mapping_pass": mapping_pass
                })
    except Exception:
        pass
    return results

def scan_directory(directory):
    """Walk directory tree and extract info from target files."""
    all_results = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if not is_target_file(file_path):
                continue
            res = extract_section_info(file_path, directory)
            if res:
                all_results.extend(res)
    return all_results

def save_to_csv(results, csv_path):
    """Save extracted ELF section info to CSV."""
    fieldnames = ["file", "file_size", "section_name", "section_size", "pt_flags", "sh_flags", "sh_type", "mapping_pass"]
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"[INFO] Saved {len(results)} rows to {csv_path}")

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <directory> <output.csv>")
        sys.exit(1)

    directory = sys.argv[1]
    output_csv = sys.argv[2]

    if not os.path.isdir(directory):
        print(f"[ERROR] {directory} is not a directory")
        sys.exit(1)

    results = scan_directory(directory)
    save_to_csv(results, output_csv)

if __name__ == "__main__":
    main()
