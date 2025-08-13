**Run Command:** `./ElfMulti3_Refactor.py ../../OscarSeries/ElfDiffMulti/9 ../../OscarSeries/ElfDiffMulti/10/ --output-dir=sample --mode=all --common-files --top-n-files-mode=custom --readable --top-n-files=10 --top-n-groups=all`

# Analysis Report - Mode: berkeley

| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | FILE&VM<br>Mapping |
|-------|----------|----------|----------|----------|-------------------|
| TEXT | , .dynstr, .dynsym, .eh_frame, .eh_frame_hdr, .fini, .gnu.hash, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init, .interp, .note.ABI-tag, .note.gnu.build-id, .plt, .rela.dyn, .rela.plt, .rodata, .shstrtab, .text | 0x5 | 0x0; 0x2; 0x42; 0x6 | SHT_DYNSYM; SHT_GNU_HASH; SHT_GNU_VERNEED; SHT_GNU_VERSYM; SHT_NOTE; SHT_NULL; SHT_PROGBITS; SHT_RELA; SHT_STRTAB | ✔(18); ✖(3) |
| DATA | .data, .data.rel.ro, .dynamic, .fini_array, .got, .init_array | 0x6 | 0x3 | SHT_DYNAMIC; SHT_FINI_ARRAY; SHT_INIT_ARRAY; SHT_PROGBITS | ✔(6) |
| BSS | .bss | - | 0x3 | SHT_NOBITS | ✖(1) |

### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)
### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0xFF00000=OS_MASK (legacy range, SHF_MASKOS), 0x80000000=OS_MASK (OS-specific high bit, SHF_MASKOS), 0xF0000000=PROC_MASK (Processor-specific, SHF_MASKPROC)

| Group | Old Total | New Total | Delta | Delta% |
|-------|-----------|-----------|-------|--------|
| OTHERS | 0B | 0B | 0B | - |
| DATA | +56.7KB | +56.1KB | -664B | -1.14% |
| EXCLUDE | 0B | 0B | 0B | - |
| BSS | +44.1KB | +48.7KB | +4.6KB | 10.44% |
| TEXT | +1.5MB | +1.5MB | -27.5KB | -1.74% |
