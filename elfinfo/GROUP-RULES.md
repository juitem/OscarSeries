# ELF Size Report Configurations

This tool provides several grouping rules (config JSON) to classify ELF sections and compare size differences.  
It supports four representative modes.

---

## 1. Berkeley Mode (`config_berkeley.json`)

- Mimics BSD style `size --format=berkeley`.
- Grouping rules:
  - **TEXT**: `AX*` / `RX*` (executable code)
  - **DATA**: `WA* & !NOBITS` (writable data), `A*` (read‑only rodata included)
  - **BSS**: `WA* & NOBITS`
  - **OTHERS**: remaining ALLOC sections
  - **IGNORE**: non‑ALLOC (debug, note, etc.)
- Note: `.rodata` is aggregated into DATA.

---

## 2. GNU Mode (`config_gnu.json`)

- Mimics GNU style `size --format=gnu`.
- Grouping rules:
  - **TEXT**: `AX*` / `RX*` + `A*` (rodata also included in TEXT)
  - **DATA**: `WA* & !NOBITS`
  - **BSS**: `WA* & NOBITS`
  - **OTHERS**: remaining ALLOC sections
  - **IGNORE**: non‑ALLOC
- Note: `.rodata` is aggregated into TEXT, making the code size look larger.

---

## 3. SysV Mode (`config_sysv.json`)

- Mimics SysV style `size --format=sysv`.
- Characteristics:
  - **All ALLOC sections are listed individually** (`.text`, `.rodata`, `.data`, `.bss`, `.plt`, `.got`, …)
  - Shows a `Total` at the end
  - Non‑ALLOC sections are ignored
- In this implementation, **no rules are applied**; the section name itself becomes the group name.
- Most detailed view, but produces many rows.

---

## 4. Custom Mode (`config_custom.json`)

- Provides an analytical 6‑category grouping for deeper analysis.
- Grouping rules:
  - **TEXT**: executable (`AX*`, `RX*`)
  - **RODATA**: read‑only ALLOC (`A* & !NOBITS`)
  - **DATA**: writable with data (`WA* & !NOBITS`)
  - **BSS**: writable with no bits (`WA* & NOBITS`)
  - **DYNAMIC**: dynamic symbol/relocation/version related (`SHT_DYNAMIC`, `SHT_RELA`, `SHT_DYNSYM`, `SHT_GNU_HASH`, …)
  - **OTHERS**: remaining ALLOC sections
  - **IGNORE**: non‑ALLOC
- Useful when you want to separate TEXT vs RODATA or track changes in dynamic sections.

---

## Comparison Summary

| Mode     | TEXT              | DATA                   | BSS   | RODATA handling | Output style   |
|----------|------------------|-----------------------|-------|-----------------|----------------|
| Berkeley | `.text`          | `.data` + `.rodata`   | `.bss`| Aggregated into DATA | Short summary (3‑4 rows) |
| GNU      | `.text` + `.rodata` | `.data`             | `.bss`| Aggregated into TEXT | Short summary (3‑4 rows) |
| SysV     | each section     | each section          | each section | separate row   | Many rows      |
| Custom   | 6 categories     | 6 categories          | 6 categories | RODATA separated | Analysis‑oriented |

---