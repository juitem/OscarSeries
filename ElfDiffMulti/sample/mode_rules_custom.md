# Classification Rule Table - Mode: custom

| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | MappingPass |
|-------|----------|----------|----------|----------|-------------|
|  |  | 0x5 | 0x0 | SHT_NULL | ✔ |
| DATA | .data, .data.rel.ro, .eh_frame, .eh_frame_hdr, .fini_array, .got, .init_array, .interp, .rela.plt, .rodata | 0x5; 0x6 | 0x2; 0x3; 0x42 | SHT_FINI_ARRAY; SHT_INIT_ARRAY; SHT_PROGBITS; SHT_RELA | ✔ |
| GNU | .gnu.hash, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .note.ABI-tag, .note.gnu.build-id | 0x5 | 0x0; 0x2 | SHT_GNU_HASH; SHT_GNU_VERNEED; SHT_GNU_VERSYM; SHT_NOTE; SHT_PROGBITS | ✔; ✖ |
| DYNAMIC | .dynamic, .dynstr, .dynsym, .rela.dyn | 0x5; 0x6 | 0x2; 0x3 | SHT_DYNAMIC; SHT_DYNSYM; SHT_RELA; SHT_STRTAB | ✔ |
| TEXT | .fini, .init, .plt, .text | 0x5 | 0x6 | SHT_PROGBITS | ✔ |
| BSS | .bss |  | 0x3 | SHT_NOBITS | ✖ |
| SHSTRTAB | .shstrtab |  | 0x0 | SHT_STRTAB | ✖ |

### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)
### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0xFF00000=OS_MASK (legacy range, SHF_MASKOS), 0x80000000=OS_MASK (OS-specific high bit, SHF_MASKOS), 0xF0000000=PROC_MASK (Processor-specific, SHF_MASKPROC)

