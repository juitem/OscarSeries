# Classification Rule Table - Mode: berkeley

| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | MappingPass |
|-------|----------|----------|----------|----------|-------------|
| TEXT | , .dynstr, .dynsym, .eh_frame, .eh_frame_hdr, .fini, .gnu.hash, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init, .interp, .note.ABI-tag, .note.gnu.build-id, .plt, .rela.dyn, .rela.plt, .rodata, .shstrtab, .text | 0x5 | 0x0; 0x2; 0x42; 0x6 | SHT_DYNSYM; SHT_GNU_HASH; SHT_GNU_VERNEED; SHT_GNU_VERSYM; SHT_NOTE; SHT_NULL; SHT_PROGBITS; SHT_RELA; SHT_STRTAB | ✔ |
| DATA | .data, .data.rel.ro, .dynamic, .fini_array, .got, .init_array | 0x6 | 0x3 | SHT_DYNAMIC; SHT_FINI_ARRAY; SHT_INIT_ARRAY; SHT_PROGBITS | ✔ |
| BSS | .bss | 0x6 | 0x3 | SHT_NOBITS | ✔ |


### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)

### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0x80000000=EXCLUDE
