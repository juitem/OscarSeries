**Run Command:** `./ElfMulti3_Refactor.py ../../OscarSeries/ElfDiffMulti/9 ../../OscarSeries/ElfDiffMulti/10/ --output-dir=sample --mode=all --common-files --top-n-files-mode=custom --readable --top-n-files=10 --top-n-groups=all`

# Analysis Report - Mode: sysv

| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | FILE&VM<br>Mapping |
|-------|----------|----------|----------|----------|-------------------|
|  |  | 0x5 | 0x0 | SHT_NULL | ✔(1) |
| INTERP | .interp | 0x5 | 0x2 | SHT_PROGBITS | ✔(1) |
| NOTE.GNU.BUILD-ID | .note.gnu.build-id | 0x5 | 0x2 | SHT_NOTE | ✔(1) |
| NOTE.ABI-TAG | .note.ABI-tag | 0x5 | 0x2 | SHT_NOTE | ✔(1) |
| GNU.HASH | .gnu.hash | 0x5 | 0x2 | SHT_GNU_HASH | ✔(1) |
| DYNSYM | .dynsym | 0x5 | 0x2 | SHT_DYNSYM | ✔(1) |
| DYNSTR | .dynstr | 0x5 | 0x2 | SHT_STRTAB | ✔(1) |
| GNU.VERSION | .gnu.version | 0x5 | 0x2 | SHT_GNU_VERSYM | ✔(1) |
| GNU.VERSION_R | .gnu.version_r | 0x5 | 0x2 | SHT_GNU_VERNEED | ✔(1) |
| RELA.DYN | .rela.dyn | 0x5 | 0x2 | SHT_RELA | ✔(1) |
| RELA.PLT | .rela.plt | 0x5 | 0x42 | SHT_RELA | ✔(1) |
| INIT | .init | 0x5 | 0x6 | SHT_PROGBITS | ✔(1) |
| PLT | .plt | 0x5 | 0x6 | SHT_PROGBITS | ✔(1) |
| TEXT | .text | 0x5 | 0x6 | SHT_PROGBITS | ✔(1) |
| FINI | .fini | 0x5 | 0x6 | SHT_PROGBITS | ✔(1) |
| RODATA | .rodata | 0x5 | 0x2 | SHT_PROGBITS | ✔(1) |
| EH_FRAME_HDR | .eh_frame_hdr | 0x5 | 0x2 | SHT_PROGBITS | ✔(1) |
| EH_FRAME | .eh_frame | 0x5 | 0x2 | SHT_PROGBITS | ✔(1) |
| INIT_ARRAY | .init_array | 0x6 | 0x3 | SHT_INIT_ARRAY | ✔(1) |
| FINI_ARRAY | .fini_array | 0x6 | 0x3 | SHT_FINI_ARRAY | ✔(1) |
| DATA.REL.RO | .data.rel.ro | 0x6 | 0x3 | SHT_PROGBITS | ✔(1) |
| DYNAMIC | .dynamic | 0x6 | 0x3 | SHT_DYNAMIC | ✔(1) |
| GOT | .got | 0x6 | 0x3 | SHT_PROGBITS | ✔(1) |
| DATA | .data | 0x6 | 0x3 | SHT_PROGBITS | ✔(1) |
| BSS | .bss | - | 0x3 | SHT_NOBITS | ✖(1) |
| GNU_DEBUGLINK | .gnu_debuglink | - | 0x0 | SHT_PROGBITS | ✖(1) |
| SHSTRTAB | .shstrtab | - | 0x0 | SHT_STRTAB | ✖(1) |
| GNU_DEBUGALTLINK | .gnu_debugaltlink | - | 0x0 | SHT_PROGBITS | ✖(1) |

### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)
### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0xFF00000=OS_MASK (legacy range, SHF_MASKOS), 0x80000000=OS_MASK (OS-specific high bit, SHF_MASKOS), 0xF0000000=PROC_MASK (Processor-specific, SHF_MASKPROC)

| Group | Old Total | New Total | Delta | Delta% |
|-------|-----------|-----------|-------|--------|
| OTHERS | 0B | 0B | 0B | - |
| DATA | +33.0KB | +33.5KB | +536B | 1.59% |
| EXCLUDE | 0B | 0B | 0B | - |
| BSS | +44.1KB | +48.7KB | +4.6KB | 10.44% |
| TEXT | +1.0MB | +1.0MB | -21.0KB | -2.00% |
|  | 0B | 0B | 0B | - |
| GOT | +8.4KB | +8.2KB | -200B | -2.31% |
| DYNSTR | +42.1KB | +41.9KB | -207B | -0.48% |
| RODATA | +125.6KB | +124.2KB | -1.4KB | -1.13% |
| GNU_DEBUGLINK | +104B | +104B | 0B | 0.00% |
| RELA.DYN | +76.5KB | +76.9KB | +456B | 0.58% |
| GNU.VERSION | +5.3KB | +5.3KB | -42B | -0.77% |
| FINI | +40B | +40B | 0B | 0.00% |
| GNU.HASH | +19.2KB | +19.2KB | +36B | 0.18% |
| DYNAMIC | +1.1KB | +1.0KB | -32B | -2.94% |
| EH_FRAME | +158.7KB | +155.0KB | -3.7KB | -2.33% |
| EH_FRAME_HDR | +19.4KB | +19.4KB | -8B | -0.04% |
| FINI_ARRAY | +16B | +16B | 0B | 0.00% |
| PLT | +5.8KB | +5.3KB | -480B | -8.06% |
| NOTE.GNU.BUILD-ID | +72B | +72B | 0B | 0.00% |
| GNU.VERSION_R | +352B | +352B | 0B | 0.00% |
| INTERP | +54B | +54B | 0B | 0.00% |
| NOTE.ABI-TAG | +64B | +64B | 0B | 0.00% |
| DATA.REL.RO | +14.2KB | +13.2KB | -968B | -6.67% |
| DYNSYM | +64.1KB | +63.7KB | -504B | -0.77% |
| SHSTRTAB | +506B | +524B | +18B | 3.56% |
| INIT_ARRAY | +16B | +16B | 0B | 0.00% |
| RELA.PLT | +8.6KB | +7.9KB | -720B | -8.15% |
| INIT | +48B | +48B | 0B | 0.00% |
| GNU_DEBUGALTLINK | 0B | +74B | +74B | - |
