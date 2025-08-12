# Analysis Report - Mode: sysv

| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | MappingPass |
|-------|----------|----------|----------|----------|-------------|
|  |  | 0x5 | 0x0 | SHT_NULL | ✔ |
| INTERP | .interp | 0x5 | 0x2 | SHT_PROGBITS | ✔ |
| NOTE.GNU.BUILD-ID | .note.gnu.build-id | 0x5 | 0x2 | SHT_NOTE | ✔ |
| NOTE.ABI-TAG | .note.ABI-tag | 0x5 | 0x2 | SHT_NOTE | ✔ |
| GNU.HASH | .gnu.hash | 0x5 | 0x2 | SHT_GNU_HASH | ✔ |
| DYNSYM | .dynsym | 0x5 | 0x2 | SHT_DYNSYM | ✔ |
| DYNSTR | .dynstr | 0x5 | 0x2 | SHT_STRTAB | ✔ |
| GNU.VERSION | .gnu.version | 0x5 | 0x2 | SHT_GNU_VERSYM | ✔ |
| GNU.VERSION_R | .gnu.version_r | 0x5 | 0x2 | SHT_GNU_VERNEED | ✔ |
| RELA.DYN | .rela.dyn | 0x5 | 0x2 | SHT_RELA | ✔ |
| RELA.PLT | .rela.plt | 0x5 | 0x42 | SHT_RELA | ✔ |
| INIT | .init | 0x5 | 0x6 | SHT_PROGBITS | ✔ |
| PLT | .plt | 0x5 | 0x6 | SHT_PROGBITS | ✔ |
| TEXT | .text | 0x5 | 0x6 | SHT_PROGBITS | ✔ |
| FINI | .fini | 0x5 | 0x6 | SHT_PROGBITS | ✔ |
| RODATA | .rodata | 0x5 | 0x2 | SHT_PROGBITS | ✔ |
| EH_FRAME_HDR | .eh_frame_hdr | 0x5 | 0x2 | SHT_PROGBITS | ✔ |
| EH_FRAME | .eh_frame | 0x5 | 0x2 | SHT_PROGBITS | ✔ |
| INIT_ARRAY | .init_array | 0x6 | 0x3 | SHT_INIT_ARRAY | ✔ |
| FINI_ARRAY | .fini_array | 0x6 | 0x3 | SHT_FINI_ARRAY | ✔ |
| DATA.REL.RO | .data.rel.ro | 0x6 | 0x3 | SHT_PROGBITS | ✔ |
| DYNAMIC | .dynamic | 0x6 | 0x3 | SHT_DYNAMIC | ✔ |
| GOT | .got | 0x6 | 0x3 | SHT_PROGBITS | ✔ |
| DATA | .data | 0x6 | 0x3 | SHT_PROGBITS | ✔ |
| BSS | .bss | 0x6 | 0x3 | SHT_NOBITS | ✔ |
| GNU_DEBUGLINK | .gnu_debuglink | 0x5 | 0x0 | SHT_PROGBITS | ✔ |
| SHSTRTAB | .shstrtab | 0x5 | 0x0 | SHT_STRTAB | ✔ |
| GNU_DEBUGALTLINK | .gnu_debugaltlink | 0x5 | 0x0 | SHT_PROGBITS | ✔ |

| Group | Old Total | New Total | Delta | Delta% |
|-------|-----------|-----------|-------|--------|
|  | 0.0B | 0.0B | 0.0B | - |
| GNU_DEBUGLINK | 104.0B | 104.0B | 0.0B | 0.00% |
| RELA.PLT | 8.6KB | 7.9KB | -720.0B | -8.15% |
| FINI_ARRAY | 16.0B | 16.0B | 0.0B | 0.00% |
| DYNSTR | 42.1KB | 41.9KB | -207.0B | -0.48% |
| BSS | 44.1KB | 48.7KB | 4.6KB | 10.44% |
| DATA.REL.RO | 14.2KB | 13.2KB | -968.0B | -6.67% |
| SHSTRTAB | 506.0B | 524.0B | 18.0B | 3.56% |
| NOTE.GNU.BUILD-ID | 72.0B | 72.0B | 0.0B | 0.00% |
| INIT_ARRAY | 16.0B | 16.0B | 0.0B | 0.00% |
| NOTE.ABI-TAG | 64.0B | 64.0B | 0.0B | 0.00% |
| RELA.DYN | 76.5KB | 76.9KB | 456.0B | 0.58% |
| INIT | 48.0B | 48.0B | 0.0B | 0.00% |
| GNU_DEBUGALTLINK | 0.0B | 74.0B | 74.0B | - |
| DATA | 33.0KB | 33.5KB | 536.0B | 1.59% |
| INTERP | 54.0B | 54.0B | 0.0B | 0.00% |
| DYNSYM | 64.1KB | 63.7KB | -504.0B | -0.77% |
| EH_FRAME | 158.7KB | 155.0KB | -3.7KB | -2.33% |
| RODATA | 125.6KB | 124.2KB | -1.4KB | -1.13% |
| FINI | 40.0B | 40.0B | 0.0B | 0.00% |
| TEXT | 1.0MB | 1.0MB | -21.0KB | -2.00% |
| GOT | 8.4KB | 8.2KB | -200.0B | -2.31% |
| EH_FRAME_HDR | 19.4KB | 19.4KB | -8.0B | -0.04% |
| DYNAMIC | 1.1KB | 1.0KB | -32.0B | -2.94% |
| GNU.VERSION | 5.3KB | 5.3KB | -42.0B | -0.77% |
| GNU.VERSION_R | 352.0B | 352.0B | 0.0B | 0.00% |
| GNU.HASH | 19.2KB | 19.2KB | 36.0B | 0.18% |
| PLT | 5.8KB | 5.3KB | -480.0B | -8.06% |


### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)

### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0x80000000=EXCLUDE
