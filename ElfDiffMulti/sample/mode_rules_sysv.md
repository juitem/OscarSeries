# Classification Rule Table - Mode: sysv

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
| BSS | .bss |  | 0x3 | SHT_NOBITS | ✖ |
| GNU_DEBUGLINK | .gnu_debuglink |  | 0x0 | SHT_PROGBITS | ✖ |
| SHSTRTAB | .shstrtab |  | 0x0 | SHT_STRTAB | ✖ |
| GNU_DEBUGALTLINK | .gnu_debugaltlink |  | 0x0 | SHT_PROGBITS | ✖ |

### PT_FLAGS Legend
0x1=PF_X (Execute), 0x2=PF_W (Write), 0x4=PF_R (Read)
### SH_FLAGS Legend
0x1=WRITE, 0x2=ALLOC, 0x4=EXEC, 0x10=MERGE, 0x20=STRINGS, 0x40=INFO_LINK, 0x80=LINK_ORDER, 0x100=OS_NONCONFORMING, 0x200=GROUP, 0x400=TLS, 0x800=COMPRESSED, 0xFF00000=OS_MASK (legacy range, SHF_MASKOS), 0x80000000=OS_MASK (OS-specific high bit, SHF_MASKOS), 0xF0000000=PROC_MASK (Processor-specific, SHF_MASKPROC)

