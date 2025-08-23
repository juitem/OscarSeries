VERBOSE = False

def logv(msg: str) -> None:
    if VERBOSE:
        print(msg)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ELF directory scanner (per-section) → CSV + minimal per-dir summaries.

What it does
------------
- Takes either:
  (A) one directory => write one CSV, or
  (B) two directories => write two CSVs (old.csv, new.csv).
- Scans recursively for ELF files.
- For each ELF file, emits ONE CSV ROW PER SECTION.
- Classifies each section as VA / VA+PA / FileOnly / Unknown by mapping to PT_LOAD.
- Emits one extra META row per file: section_name=FILESIZE, section_size=<file bytes>.
- After writing CSV(s), prints a minimal summary per directory:
    * Unique section names count
    * Accumulated size per section name (descending)

Requirements
------------
    pip install pyelftools

CSV columns (exact order)
-------------------------
  base_rel_dir,
  filename,
  section_name,
  section_type,
  section_type_human,
  section_size,
  section_addr_hex,
  section_offset,
  section_align,
  section_flags_hex,
  section_flags_perms,
  is_nobits,
  in_load_segment,
  load_segment_index,
  load_segment_rwx,
  va_range_in_segment,
  file_range_in_segment,
  addr_space,
  has_paddr,
  paddr_range_in_segment
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError


# ---------------------------
# Helpers
# ---------------------------

ELF_MAGIC = b"\x7fELF"

def is_elf(path: Path) -> bool:
    try:
        with path.open('rb') as f:
            return f.read(4) == ELF_MAGIC
    except Exception:
        return False


# Mach-O detector for macOS binaries
def is_macho(path: Path) -> bool:
    """Detect common Mach-O magics so we can tell the user why no rows were recorded on macOS."""
    try:
        with path.open('rb') as f:
            m = f.read(4)
        # Little/Big + 32/64 magics
        return m in {
            b"\xcf\xfa\xed\xfe",  # MH_MAGIC_64 (LE)
            b"\xfe\xed\xfa\xcf",  # MH_CIGAM_64 (BE)
            b"\xfe\xed\xfa\xce",  # MH_CIGAM (BE 32)
            b"\xce\xfa\xed\xfe",  # MH_MAGIC (LE 32)
        }
    except Exception:
        return False


def posix_rel_dir(scan_root: Path, file_path: Path) -> str:
    try:
        rel = file_path.parent.resolve().relative_to(scan_root.resolve())
        s = str(rel).replace("\\", "/")
        return s if s != "" else "."
    except Exception:
        return "."


# ---------------------------
# Decoders
# ---------------------------

_SHT_HUMAN = {
    0:  "NULL",
    1:  "PROGBITS",
    2:  "SYMTAB",
    3:  "STRTAB",
    4:  "RELA",
    5:  "HASH",
    6:  "DYNAMIC",
    7:  "NOTE",
    8:  "NOBITS",
    9:  "REL",
    10: "SHLIB",
    11: "DYNSYM",
    14: "INIT_ARRAY",
    15: "FINI_ARRAY",
    16: "PREINIT_ARRAY",
    17: "GROUP",
    18: "SYMTAB_SHNDX",
    19: "NUM",
}
def section_type_human(sh_type) -> str:
    """Return a human-friendly section type.
    Accepts either an int (numeric SHT_*) or a str like 'SHT_PROGBITS'.
    """
    # If it's already a string like 'SHT_PROGBITS', strip the prefix for readability
    if isinstance(sh_type, str):
        return sh_type[4:] if sh_type.startswith('SHT_') else sh_type
    # If it's an int, map via table
    try:
        return _SHT_HUMAN.get(int(sh_type), f"TYPE_{sh_type}")
    except Exception:
        return str(sh_type)


def decode_section_flags_perms(flags: int) -> str:
    """
    Keep only execution/data-relevant bits:
      W (WRITE), A (ALLOC), X (EXEC), T (TLS)
    Helpful extras:
      M (MERGE), S (STRINGS), G (GROUP), C (COMPRESSED*), E (EXCLUDE*)
    (* values are toolchain-dependent; we use common masks)
    """
    pairs = []
    if flags & (1 << 0):   # SHF_WRITE
        pairs.append("W")
    if flags & (1 << 1):   # SHF_ALLOC
        pairs.append("A")
    if flags & (1 << 2):   # SHF_EXECINSTR
        pairs.append("X")
    if flags & (1 << 10):  # SHF_TLS
        pairs.append("T")
    if flags & (1 << 4):   # SHF_MERGE
        pairs.append("M")
    if flags & (1 << 5):   # SHF_STRINGS
        pairs.append("S")
    if flags & (1 << 9):   # SHF_GROUP
        pairs.append("G")
    if flags & 0x800:      # SHF_COMPRESSED (commonly 0x800)
        pairs.append("C")
    if flags & 0x80000000: # SHF_EXCLUDE (GNU)
        pairs.append("E")
    return "|".join(pairs) if pairs else ""


def _parse_sh_flags(val) -> int:
    """Return SHF_* bitmask from either int or string like 'SHF_ALLOC|SHF_EXECINSTR'."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        bits = 0
        mapping = {
            'SHF_WRITE': 0x1,
            'SHF_ALLOC': 0x2,
            'SHF_EXECINSTR': 0x4,
            'SHF_MERGE': 0x10,
            'SHF_STRINGS': 0x20,
            'SHF_INFO_LINK': 0x40,
            'SHF_LINK_ORDER': 0x80,
            'SHF_OS_NONCONFORMING': 0x100,
            'SHF_GROUP': 0x200,
            'SHF_TLS': 0x400,
            'SHF_COMPRESSED': 0x800,
            'SHF_EXCLUDE': 0x80000000,
        }
        for token in val.split('|'):
            token = token.strip()
            if token in mapping:
                bits |= mapping[token]
            else:
                # Try hex literal like '0x20'
                try:
                    if token.startswith('0x'):
                        bits |= int(token, 16)
                except Exception:
                    pass
        return bits
    return 0

def _parse_p_flags(val) -> int:
    """Return PF_* bitmask from either int or string like 'PF_R|PF_X'."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        bits = 0
        mapping = {
            'PF_X': 0x1,
            'PF_W': 0x2,
            'PF_R': 0x4,
        }
        for token in val.split('|'):
            token = token.strip()
            if token in mapping:
                bits |= mapping[token]
            else:
                try:
                    if token.startswith('0x'):
                        bits |= int(token, 16)
                except Exception:
                    pass
        return bits
    return 0


def decode_pflags_rwx(pflags: int) -> str:
    # PF_X=1, PF_W=2, PF_R=4
    out = []
    if pflags & 4:
        out.append("R")
    if pflags & 2:
        out.append("W")
    if pflags & 1:
        out.append("X")
    return "|".join(out)


def _range_intersection(a0: int, a1: int, b0: int, b1: int) -> Optional[Tuple[int, int]]:
    s = max(a0, b0)
    e = min(a1, b1)
    if s < e:
        return (s, e)
    return None


# ---------------------------
# CSV schema
# ---------------------------

CSV_FIELDS: List[str] = [
    "base_rel_dir",
    "filename",
    "section_name",
    "section_type",
    "section_type_human",
    "section_size",
    "section_addr_hex",
    "section_offset",
    "section_align",
    "section_flags_hex",
    "section_flags_perms",
    "is_nobits",
    "in_load_segment",
    "load_segment_index",
    "load_segment_rwx",
    "va_range_in_segment",
    "file_range_in_segment",
    "addr_space",
    "has_paddr",
    "paddr_range_in_segment",
]


# ---------------------------
# Core: per-ELF → per-section rows
# ---------------------------

def iter_elf_section_rows(elf_path: Path, scan_root: Path) -> Iterator[Dict[str, str]]:
    base_rel = posix_rel_dir(scan_root, elf_path)
    fname = elf_path.name
    fsize = int(elf_path.stat().st_size)

    try:
        with elf_path.open("rb") as fp:
            ef = ELFFile(fp)

            # Emit a META row carrying the file size as a pseudo-section
            yield {
                "base_rel_dir": base_rel,
                "filename": fname,
                "section_name": "FILESIZE",
                "section_type": "META",
                "section_type_human": "META",
                "section_size": str(fsize),
                "section_addr_hex": "0x0",
                "section_offset": "0",
                "section_align": "0",
                "section_flags_hex": "0x0",
                "section_flags_perms": "",
                "is_nobits": "false",
                "in_load_segment": "false",
                "load_segment_index": "-1",
                "load_segment_rwx": "",
                "va_range_in_segment": "",
                "file_range_in_segment": "",
                "addr_space": "FileOnly",
                "has_paddr": "false",
                "paddr_range_in_segment": "",
            }

            # Collect PT_LOAD segments
            load_segments = []
            for idx, seg in enumerate(ef.iter_segments()):
                if seg.header['p_type'] != 'PT_LOAD':
                    continue
                p_vaddr_raw = seg.header['p_vaddr']
                p_memsz_raw = seg.header['p_memsz']
                p_offset_raw = seg.header['p_offset']
                p_filesz_raw = seg.header['p_filesz']
                p_flags_raw = seg.header['p_flags']
                p_paddr_raw = seg.header.get('p_paddr', 0)

                p_vaddr  = int(p_vaddr_raw)
                p_memsz  = int(p_memsz_raw)
                p_offset = int(p_offset_raw)
                p_filesz = int(p_filesz_raw)
                p_flags  = _parse_p_flags(p_flags_raw)
                p_paddr  = int(p_paddr_raw)

                load_segments.append({
                    "index": idx,
                    "v0": p_vaddr,
                    "v1": p_vaddr + p_memsz,
                    "f0": p_offset,
                    "f1": p_offset + p_filesz,
                    "p0": p_paddr,
                    "p1": p_paddr + p_memsz,
                    "rwx": decode_pflags_rwx(p_flags),
                    "has_paddr": (p_paddr != 0 and p_memsz != 0),
                })

            # Sections
            for sec in ef.iter_sections():
                try:
                    sh = sec.header
                    sh_type_raw  = sh['sh_type']  # may be int (e.g., 1) or str (e.g., 'SHT_PROGBITS')
                    sh_flags     = _parse_sh_flags(sh['sh_flags'])
                    sh_addr      = int(sh['sh_addr'])
                    sh_offset    = int(sh['sh_offset'])
                    sh_size      = int(sh['sh_size'])
                    sh_addralign = int(sh.get('sh_addralign', 0))
                    idx = sec.index if hasattr(sec, "index") else -1
                    name = sec.name
                    if not name:
                        name = f"null{idx}"

                    # NOBITS detection works for both int and string representations
                    is_nobits = (
                        (isinstance(sh_type_raw, int) and sh_type_raw == 8) or
                        (isinstance(sh_type_raw, str) and sh_type_raw == 'SHT_NOBITS')
                    )

                    # Human-friendly type strings
                    section_type_str = str(sh_type_raw)
                    section_type_h   = section_type_human(sh_type_raw)

                    perms = decode_section_flags_perms(sh_flags)
                    flags_hex = f"0x{sh_flags:x}"

                    # Half-open ranges ([a, b))
                    s_va0, s_va1 = sh_addr, sh_addr + (sh_size if sh_size > 0 else 1)
                    if is_nobits:
                        s_f0, s_f1 = 0, 0
                    else:
                        s_f0, s_f1 = sh_offset, sh_offset + (sh_size if sh_size > 0 else 1)

                    in_load = False
                    chosen_ld_idx = -1
                    ld_rwx = ""
                    va_inter_str = ""
                    f_inter_str = ""
                    has_paddr = False
                    paddr_inter_str = ""
                    addr_space = "Unknown"

                    # First PT_LOAD overlapping VA wins
                    for ld in load_segments:
                        va_inter = _range_intersection(s_va0, s_va1, ld["v0"], ld["v1"])
                        if va_inter is None:
                            continue

                        in_load = True
                        chosen_ld_idx = ld["index"]
                        ld_rwx = ld["rwx"]
                        va_inter_str = f"0x{va_inter[0]:x}-0x{va_inter[1]:x}"

                        if not is_nobits:
                            f_inter = _range_intersection(s_f0, s_f1, ld["f0"], ld["f1"])
                            if f_inter:
                                f_inter_str = f"{f_inter[0]}-{f_inter[1]}"

                        if ld["has_paddr"]:
                            has_paddr = True
                            p_inter = _range_intersection(s_va0, s_va1, ld["p0"], ld["p1"])
                            if p_inter:
                                paddr_inter_str = f"0x{p_inter[0]:x}-0x{p_inter[1]:x}"

                        addr_space = "VA"
                        if paddr_inter_str:
                            addr_space = "VA+PA"
                        break

                    if not in_load:
                        if is_nobits:
                            addr_space = "VA"
                        else:
                            addr_space = "FileOnly"

                    yield {
                        "base_rel_dir": base_rel,
                        "filename": fname,
                        "section_name": name,
                        "section_type": section_type_str,
                        "section_type_human": section_type_h,
                        "section_size": str(sh_size),
                        "section_addr_hex": f"0x{sh_addr:x}",
                        "section_offset": str(sh_offset),
                        "section_align": str(sh_addralign),
                        "section_flags_hex": flags_hex,
                        "section_flags_perms": perms,
                        "is_nobits": "true" if is_nobits else "false",
                        "in_load_segment": "true" if in_load else "false",
                        "load_segment_index": str(chosen_ld_idx),
                        "load_segment_rwx": ld_rwx,
                        "va_range_in_segment": va_inter_str,
                        "file_range_in_segment": f_inter_str,
                        "addr_space": addr_space,
                        "has_paddr": "true" if has_paddr else "false",
                        "paddr_range_in_segment": paddr_inter_str,
                    }
                except Exception as se:
                    print(f"[WARN] Skipping section in {elf_path}: {type(se).__name__}: {se}", file=sys.stderr)
                    continue
    except ELFError:
        return
    except Exception as e:
        print(f"[WARN] Failed to parse {elf_path}: {type(e).__name__}: {e}", file=sys.stderr)
        return


# ---------------------------
# Scan & write CSV + minimal summary
# ---------------------------

def scan_dir_to_csv(scan_root: Path, out_csv: Path) -> None:
    rows: List[Dict[str, str]] = []
    total_files = 0
    regular_files = 0
    elf_candidates = 0
    macho_candidates = 0
    elves_parsed = 0

    for p in scan_root.rglob("*"):
        total_files += 1
        if not p.is_file():
            continue
        regular_files += 1
        if is_elf(p):
            elf_candidates += 1
            per_file_rows = 0
            for row in iter_elf_section_rows(p, scan_root):
                rows.append(row)
                per_file_rows += 1
            if per_file_rows > 0:
                elves_parsed += 1
            logv(f"[ELF] {p} -> {per_file_rows} rows")
        else:
            if is_macho(p):
                macho_candidates += 1
                logv(f"[Mach-O] {p} (not ELF)")
            else:
                logv(f"[skip] {p}")

    logv(
        f"Scanned: total={total_files}, regular={regular_files}, ELF_magic={elf_candidates}, Mach-O_magic={macho_candidates}, files_with_rows={elves_parsed}, total_rows={len(rows)}"
    )
    if elf_candidates == 0 and macho_candidates > 0:
        print("[INFO] No ELF files found but Mach-O binaries were detected. On macOS, system binaries are Mach-O, not ELF.")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"[OK] Wrote {len(rows)} rows to {out_csv}")
    print(f"[OK] Rows came from {len({r['filename'] for r in rows})} unique files")

    # Minimal per-dir summary: unique section names + accumulated size per name
    _print_minimal_summary(out_csv)


def _print_minimal_summary(csv_path: Path) -> None:
    import collections
    section_sizes = collections.Counter()
    section_names = set()

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row.get("section_name", "")
            section_names.add(name)
            try:
                sz = int(row.get("section_size", "0"))
            except Exception:
                sz = 0
            section_sizes[name] += sz

    print(f"== Minimal Section Summary for {csv_path} ==")
    print(f"Unique section names: {len(section_names)}")
    for sec_name, total in section_sizes.most_common(None):
        print(f"  {sec_name:<20} : {total} bytes")


# ---------------------------
# CLI
# ---------------------------

def main():
    p = argparse.ArgumentParser(
        description="Scan ELF directories into CSV (per-section). Prints minimal per-dir summaries."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Single directory
    scan = sub.add_parser("scan", help="Scan ONE directory and write ONE CSV.")
    scan.add_argument("--dir", required=True, type=Path, help="Directory to scan recursively.")
    scan.add_argument("--out", required=True, type=Path, help="Output CSV path.")
    scan.add_argument("--verbose", action="store_true", help="Verbose logging (diagnose why rows may be missing)")

    # Two directories at once
    scan2 = sub.add_parser("scan-two", help="Scan TWO directories and write TWO CSVs.")
    scan2.add_argument("--old-dir", required=True, type=Path, help="Old directory (recursively scanned).")
    scan2.add_argument("--new-dir", required=True, type=Path, help="New directory (recursively scanned).")
    scan2.add_argument("--old-csv", type=Path, default=Path("old.csv"), help="Output CSV for old_dir (default: old.csv).")
    scan2.add_argument("--new-csv", type=Path, default=Path("new.csv"), help="Output CSV for new_dir (default: new.csv).")
    scan2.add_argument("--verbose", action="store_true", help="Verbose logging (diagnose why rows may be missing)")

    args = p.parse_args()
    global VERBOSE
    VERBOSE = getattr(args, "verbose", False)

    if args.cmd == "scan":
        scan_dir_to_csv(args.dir, args.out)
    elif args.cmd == "scan-two":
        scan_dir_to_csv(args.old_dir, args.old_csv)
        scan_dir_to_csv(args.new_dir, args.new_csv)
    else:
        p.print_help()


if __name__ == "__main__":
    main()