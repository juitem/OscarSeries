## 1. Overview

`elfinfo.py` is a tool that recursively scans ELF binaries within a directory and records section-level metadata into a CSV file. Additionally, it prints a simple summary (number of sections / cumulative size per section) to the console for each directory (or old/new directory pair).

Core features:
- Single directory scan → generates one CSV file
- Dual directory scan → generates two CSV files, `old.csv` and `new.csv`
- One row per section per ELF file (plus a meta row per file showing total file size)
- Computes memory/file layout characteristics of sections (VA, VA+PA, FileOnly, etc.) and PT_LOAD segment mappings
- macOS environment detection (displays message if Mach-O binaries found instead of ELF)

---

## 2. Goals and Non-goals

### Goals
- Recursively select only ELF files and collect section metadata into CSV
- Provide key information such as section type, flags, address, and offset
- Provide a stable schema for use by higher-level comparison tools (e.g., `compareCSV.py`)

### Non-goals
- No binary modification, relocation, or linking operations
- No parsing of deep debug formats like DWARF (only section-level metadata collected)
- No ELF-like parsing of Mach-O or PE executables (only detection of Mach-O presence)

---

## 3. High-level Architecture

```
+-------------------+
| CLI (argparse)    |
|  - scan           |
|  - scan-two       |
+---------+---------+
          |
          v
+-------------------+    +---------------------+
| scan_dir_to_csv   | -> | iter_elf_section... | -> rows[] (dict per section)
|  - walk dir       |    |  - open ELF         |    * +1 META row per file ("FILESIZE")
|  - is_elf check   |    |  - iterate sections |
+---------+---------+    |  - map PT_LOAD      |
          |              +---------------------+
          v
+-------------------+         +-----------------------+
| CSV writer        | <------ | rows[], CSV_FIELDS    |
+---------+---------+         +-----------------------+
          |
          v
+-------------------+
| minimal summary   | (console)
+-------------------+
```

---

## 4. Data Model (CSV Schema)

CSV columns (fixed order and schema):

1. `base_rel_dir`: Relative directory from scan root (POSIX style, root is ".")
2. `filename`: Filename including extension
3. `section_name`: Section name (null if empty, indexed), meta row for file size is "FILESIZE"
4. `section_type`: Raw section type value (integer or 'SHT_*' string)
5. `section_type_human`: Human-readable section type (PROGBITS, NOBITS, etc.)
6. `section_size`: Section size in bytes; for FILESIZE meta row, total file size
7. `section_addr_hex`: Section VA start address (hex string)
8. `section_offset`: File offset in bytes
9. `section_align`: Section alignment in bytes
10. `section_flags_hex`: Section flags (hex)
11. `section_flags_perms`: Summary of flags as W|A|X|T|M|S|G|C|E (empty if none)
12. `is_nobits`: true/false indicating if SHT_NOBITS
13. `in_load_segment`: true/false if VA overlaps a PT_LOAD segment
14. `load_segment_index`: Index of mapped PT_LOAD segment (-1 if none)
15. `load_segment_rwx`: PT_LOAD permission summary (R|W|X)
16. `va_range_in_segment`: Intersection VA range [a,b) as "0x...-0x...", empty if none
17. `file_range_in_segment`: File offset range (start-end), empty if NOBITS or mismatch
18. `addr_space`: VA / VA+PA / FileOnly / Unknown
19. `has_paddr`: true/false if LOAD segment has physical address
20. `paddr_range_in_segment`: Physical address intersection range (hex), empty if none

The META row (`section_name=FILESIZE`) is not a section but provides one row per file with total file size for grouping.

---

## 5. Key Components and Responsibilities

### 5.1 Helpers
- `is_elf(path: Path) -> bool`  
  Checks if the first 4 bytes of the file header are 0x7f 'E' 'L' 'F'.
- `is_macho(path: Path) -> bool`  
  Detects common Mach-O magic numbers to provide a warning message on macOS.
- `posix_rel_dir(scan_root, file_path) -> str`  
  Returns the relative directory from root, converting Windows `\` to `/`.
- `section_type_human(sh_type)`  
  Converts integer/string SHT types to a standardized human-readable form.
- `_parse_sh_flags(val) / _parse_p_flags(val)`  
  Parses string combinations ("SHF_ALLOC|...") or integers into common bitmasks.
- `decode_section_flags_perms(flags: int) -> str / decode_pflags_rwx(pflags: int) -> str`  
  Converts flags/permissions into summary strings.
- `_range_intersection(a0,a1,b0,b1)`  
  Calculates intersection of half-open intervals; returns None if no overlap.

### 5.2 Core: `iter_elf_section_rows(elf_path, scan_root)`
- Opens ELF file and collects PT_LOAD segments.
- Generates one meta row with `section_name=FILESIZE` for total file size.
- Iterates all sections and records:
  - Type, flags, alignment, offset, size
  - SHT_NOBITS status and file offset handling
  - VA intersection with PT_LOAD segments (first matching segment selected)
  - `load_segment_index`, `load_segment_rwx`, `va_range_in_segment`
  - `file_range_in_segment` (none for NOBITS)
  - If physical address present, calculates `paddr_range_in_segment` and sets `addr_space=VA+PA`
  - If no intersection, assigns `addr_space` as VA or FileOnly accordingly

### 5.3 Orchestration: `scan_dir_to_csv(scan_root, out_csv)`
- Recursively walks directory
- Processes only ELF files via `iter_elf_section_rows`
- Writes CSV with fixed header `CSV_FIELDS`, UTF-8 encoding, proper newline handling
- Prints simple summary on console:
  - Number of unique section names
  - Cumulative size per section (descending order)

### 5.4 CLI (main)
- `scan`: options `--dir`, `--out`, `--verbose`
- `scan-two`: options `--old-dir`, `--new-dir`, `--old-csv`, `--new-csv`, `--verbose`
- Enables verbose logging if `--verbose` is specified

---

## 6. Error Handling and Logging

- On ELF parsing failure: prints warning and skips file
- On section processing exception: prints warning and skips section
- If only Mach-O binaries detected: prints informative message clarifying no ELF found
- Detailed logs (`logv`) shown only if `VERBOSE=True`

---

## 7. Performance Considerations

- Single-threaded file-level processing (simple and reliable)
- I/O may become bottleneck for large directories
- Future enhancements: multiprocessing/threading, worker pools, producer/consumer patterns
- CSV written with buffered streams (`csv.DictWriter`) to save memory

---

## 8. Determinism and Ordering

- Directory traversal depends on file system order (`Path.rglob("*")`)
- Output rows are not guaranteed sorted (higher-level tools should sort/aggregate)
- Re-running on same input/environment generally produces identical output

---

## 9. Extensibility Points (Future Work)

- Add more segment/section attributes to fields
- Filtering by section name patterns or permissions
- Performance improvements: parallel processing, caching
- Additional output formats: Parquet, JSONL, etc.
- Separate collectors for Mach-O / PE formats (currently only detection)

---

## 10. Testing Strategy

- Unit tests:
  - `is_elf` / `is_macho` magic detection
  - Flag parsers (`_parse_sh_flags`, `_parse_p_flags`)
  - Intersection calculation (`_range_intersection`)
  - `section_type_human` mappings
- Integration tests:
  - Generate CSV from small ELF samples and verify schema/values
  - Cases with NOBITS / PT_LOAD mapping
  - macOS environment with mixed Mach-O detection message
- Regression tests:
  - Check fixed CSV field order and header
  - Verify presence of FILESIZE meta rows

---

## 11. CLI Usage Examples

```bash
# Single directory scan → out.csv
python3 elfinfo.py scan --dir ./build/release --out ./out.csv

# Dual directory scan → old.csv, new.csv
python3 elfinfo.py scan-two \
  --old-dir ./build/prev \
  --new-dir ./build/curr \
  --old-csv ./old.csv \
  --new-csv ./new.csv

# Verbose logging
python3 elfinfo.py scan --dir ./bin --out ./sections.csv --verbose
```

---

## 12. Known Limitations

- Does not parse binaries other than ELF (Mach-O only detected)
- Only partial decoding of special toolchain flags/segments
- Some fields may remain empty if sections/segments are malformed

---

## 13. Rationale (Design Choices)

- Fixed CSV schema: ensures stable integration with higher-level comparison/aggregation tools
- META row (file size): provides aggregation/comparison without separate section
- Single PT_LOAD mapping per section: uses first intersecting segment for simplicity and performance
- Minimal logging by default; verbose mode enabled with `--verbose` for troubleshooting

---

## 14. File and Module Layout

- `elfinfo.py`: single script, functions well separated for easy library use
- External dependency: `pyelftools` (install via `pip install pyelftools`)

---

## 15. Backward Compatibility

- CSV field order and names are fixed to maintain compatibility with tools like `compareCSV.py`
- New fields added only at the end, with validation to avoid pipeline conflicts

---

## 16. Appendix — Field Semantics Cheatsheet

- `addr_space` values:
  - `VA`: VA range exists, no physical address or NOBITS
  - `VA+PA`: LOAD segment has physical address and overlapping range
  - `FileOnly`: File offset exists without LOAD mapping
  - `Unknown`: Invalid or unidentifiable
- Flag summaries:
  - Section flags: W (write), A (alloc), X (execute), T (TLS), M (merge), S (string), G (group), C (compress), E (exclude)
  - Segment flags: R (read), W (write), X (execute)

---
