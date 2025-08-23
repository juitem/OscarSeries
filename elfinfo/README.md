# How to Use — ELF Size Diff Reports (accurate to compareCSV.py)

This tool compares two ELF section CSV snapshots (produced by your data‑gathering step, e.g., elfinfo.py) and generates:

- (optional) a wide per‑file diff CSV
- Top‑N Groups / Top‑N Files (CSV + Markdown)
- a full Groups Report (Markdown) with attribute summaries

It supports grouping via JSON configs (Berkeley/GNU/SysV/Custom, or your own).

## 1) Prerequisites

- Python 3.8+
- Two CSV snapshots with at least these columns:  
  `relative_path` or `base_rel_dir`, `filename`, `section_name`, `section_size`  
  (Optional columns for richer attribution: `section_type`, `section_flags_perms`, `is_nobits`, `in_load_segment`, `load_segment_rwx`, `addr_space`)

---

## 2) Quick Start

### Example CSV snapshots

```bash
$ ls 9.csv 10.csv
```

### Run with a grouping config

```bash
$ python3 compareCSV.py \
    --old-csv ./9.csv \
    --new-csv ./10.csv \
    --config-file ./config_berkeley.json
```

Outputs (by default):

- Output directory: `9_vs_10/`
- `9_vs_10_top-n-groups_common.csv`  (Top‑N groups; by default it includes ALL groups)
- `9_vs_10_top-n-files_common.csv`   (Top‑N files per group; by default includes ALL files with non‑zero diffs)
- `9_vs_10_top-n-groups_common.md`   (Markdown summary)
- `9_vs_10_groups-report_common.md`  (Full groups report with attributes)
- `9_vs_10_topfiles_used_common.txt` (Flattened list of files used in Top‑N)

“common” means files present in both snapshots. See `--target-files` for other modes.

---

## 3) CLI Options (from parse_args())

### Required

- `--old-csv PATH` : old snapshot CSV
- `--new-csv PATH` : new snapshot CSV

### Selection

- `--target-files (all|common|added+removed)`  
  Which files to include. Default: `common`
- `--all-files (deprecated)` : equivalent to `--target-files=all` when provided

### Grouping

- `--config-file PATH` : JSON config overriding/adding groups and rules

### Outputs

- `--out-dir DIR` : output directory (default: `<old>_vs_<new>`)
- `--output-prefix STR` : file prefix (default: `<old>_vs_<new>`)
- `--whole-filedata-csv PATH` : path for the wide per‑file diff CSV
- `--gen-whole-filedata-csv (true|false)` : whether to generate the above file (default: false)
- `--files-csv PATH (deprecated)` : old alias of `--whole-filedata-csv`

### Top‑N controls

- `--top-n-groups INT` : keep Top‑N groups (by chosen metric); 0 means no truncation
- `--top-n-files INT`  : per Top group, keep Top‑N files; 0 means no truncation
- `--top-n INT (deprecated)` : sets both of the above unless they are explicitly set
- `--topn-groups-csv PATH` : where to write Top‑N groups CSV  
  (default is auto‑constructed inside `--out-dir`)
- `--topn-files-csv PATH`  : where to write Top‑N files CSV  
  (default is auto‑constructed inside `--out-dir`)

### Sorting

- `--files-sort-by GROUP` : how to sort rows in the per‑file wide CSV  
  (default: `FILESIZE`)
- `--files-sort-metric (absdiff|diff|old|new|diff%)` : metric for the above (default: `absdiff`)
- `--group-sort-by (metric|name)` : Top‑N groups ordering (default: `metric`)
- `--group-sort-metric (absdiff|diff|old|new|diff%)` : metric for Top‑N grouping (default: `absdiff`)


---

## 4) Grouping configs (how they’re interpreted)

- Default group name (when no rule matches):  
  remove the leading `.` from `section_name` and UPPERCASE the rest.  
  e.g., `.text` → `TEXT`, `.rodata.str1.1` → `RODATA.STR1.1`.

- groups mapping in JSON (optional):  
  A dictionary of `GROUP` → `[patterns]`. The first matching group (by fnmatch) wins and returns immediately.  
  Example:

```json
{
  "groups": {
    "FILESIZE": ["FILESIZE"],
    "TEXT": [".text"], 
    "RODATA": [".rodata*"]
  }
}
```

- rules array in JSON (optional):  
  List of `{ "if": {...}, "group": "NAME" }`.  
  The first matching rule wins. Each condition inside `"if"` is AND‑combined.  
  All string fields are matched with fnmatch (wildcards allowed).  
  Valid keys include:  
  - `section_name`  
  - `section_type`  
  - `section_flags_perms`  (note: the code strips `|`; wildcards like `AX*`, `WA*` work)  
  - `is_nobits`  
  - `in_load_segment`  
  - `load_segment_rwx` (the code strips `|`)  
  - `addr_space`  

If no groups match and no rules match, the default group (derived from name) is used.

---

## 5) Typical Workflows & Examples

### A) Berkeley semantics (code vs rodata split)

```bash
python3 compareCSV.py \
  --old-csv ./9.csv \
  --new-csv ./10.csv \
  --config-file ./config_berkeley.json
```

Generates Top‑N (all by default) and the full Groups Report.

### B) GNU semantics (rodata folded into TEXT)

```bash
python3 compareCSV.py \
  --old-csv ./9.csv \
  --new-csv ./10.csv \
  --config-file ./config_gnu.json
```

### C) SysV‑like exhaustive view

```bash
python3 compareCSV.py \
  --old-csv ./9.csv \
  --new-csv ./10.csv \
  --config-file ./config_sysv.json
```

If your `config_sysv.json` is set to no rules and minimal groups, the program falls back to section name → group and lists each ALLOC section separately.

### D) Custom 6‑bucket analysis

```bash
python3 compareCSV.py \
  --old-csv ./9.csv \
  --new-csv ./10.csv \
  --config-file ./config_custom.json \
  --top-n-groups 12
```

### E) Generate the wide per‑file diff CSV

```bash
python3 compareCSV.py \
  --old-csv ./9.csv \
  --new-csv ./10.csv \
  --config-file ./config_berkeley.json \
  --gen-whole-filedata-csv true \
  --whole-filedata-csv ./9_vs_10_files_common.csv
```

---

## 6) What gets written

- Top‑N CSV/MD are written by default to auto‑computed paths under `<out_dir>`  
  (even if you didn’t pass `--top-n-*`; “0” means “no truncation”, so all groups/files with diffs are included).
- Groups Report (Markdown):  
  `<out_dir>/<prefix>_groups-report_<target>.md`  
  Includes attribute aggregates with counts:  
  `section_type`, `section_flags_perms`, `is_nobits`, `in_load_segment`, `load_segment_rwx`, `addr_space`
- Top files list for downstream tools:  
  `<out_dir>/<prefix>_topfiles_used_<target>.txt`
- Wide per‑file diff CSV only if `--gen-whole-filedata-csv true` (path from `--whole-filedata-csv` or default)

---

## 7) Sorting & metrics

- Per‑file wide CSV rows are sorted by `|<files-sort-by>_diff|` using the metric from `--files-sort-metric` (default `absdiff`).
- Top‑N groups ordering:  
  - `--group-sort-by=metric` (default) uses one of: `absdiff`, `diff`, `old`, `new`, `diff%`  
  - `--group-sort-by=name` sorts alphabetically by group name

Diff% rules:

- `(new - old) / old * 100`
- If `old == 0 && new == 0` → `0.0`
- If `old == 0 && new > 0` → `+100.0` (finite cap used instead of inf)

---

## 8) Targets: which files are compared

- `--target-files=common` (default) : intersection only
- `--target-files=all` : common + added + removed
- `--target-files=added+removed` : symmetric difference only
- `--all-files` (deprecated) : treated as all when present

“Added/Removed” rows show 0 on the missing side.

---

## 9) Common pitfalls

- Empty path error:  
  If `--gen-whole-filedata-csv true` but `--whole-filedata-csv ""` (or config sets it empty), Python will try `open("")`.  
  → Provide a filename or keep `--gen-whole-filedata-csv=false` (default is false).
- Wrong config filename:  
  `config_berkely.json` vs `config_berkeley.json` (typo). Make sure the path matches the file you edited.
- OTHERS is empty:  
  With Berkeley/GNU configs, ALLOC sections are mostly absorbed by TEXT/DATA/BSS; OTHERS being zero is expected.

---

## 10) Custom rules — quick examples

### Name‑based (wildcards)

```json
{
  "groups": { "INIT_FINI": ["INIT_FINI"] },
  "rules": [
    { "if": { "section_name": [".init*", ".fini*"] }, "group": "INIT_FINI" }
  ]
}
```

### Flag‑based (wildcards)

```json
{
  "groups": { "READ_EXEC": ["READ_EXEC"] },
  "rules": [
    { "if": { "section_flags_perms": ["RX*"] }, "group": "READ_EXEC" }
  ]
}
```

### Type‑based

```json
{
  "groups": { "RELOC": ["RELOC"] },
  "rules": [
    { "if": { "section_type": ["SHT_RELA", "SHT_REL"] }, "group": "RELOC" }
  ]
}
```

Under the hood, `fnmatch` is used for all string fields, so `AX*`, `.rodata*`, etc. are supported.  
If no group or rule matches, the fallback is `uppercase(section_name without leading .)`.

---

If you want, I can also scan one of your real CSVs and suggest a minimal custom config tailored to the actual sections/flags in your build (no guesses, just from the data).