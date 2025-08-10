# ELF Size Comparison Report

Executed: `./diff11 ./10 ./9 --display-mode=all --output-dir=out2 --top-n-sections 10 --user-selected=.gnu.hash,.data,.text --output-dir=out4 --report-type=all --exclude-section=.gnu.hash,.text`
Generated: 2025-08-10 09:29:03.264233

## Mode: berkeley

| section | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- |
| .bss | 48.66 KB | 87.94 KB | 39.27 KB | 80.70% |
| .data | 55.02 KB | 101.39 KB | 46.38 KB | 84.29% |
| .text | 1.30 MB | 2.38 MB | 1.08 MB | 82.91% |
| Others | 217.24 KB | 406.11 KB | 188.87 KB | 86.94% |
| User-Selected (.data, .gnu.hash, .text) | 1.05 MB | 1.95 MB | 918.12 KB | 85.00% |

| class | section | type | flags |
| --- | --- | --- | --- |
| .bss | .bss | SHT_NOBITS | 0x3 |
| .data | .data.rel.ro, .got | SHT_PROGBITS | 0x3 |
| .text | .eh_frame, .eh_frame_hdr, .fini, .init, .interp, .plt, .rodata | SHT_PROGBITS | 0x2, 0x6 |
| Others | , .dynamic, .dynstr, .dynsym, .fini_array, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init_array, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .shstrtab | SHT_DYNAMIC, SHT_DYNSYM, SHT_FINI_ARRAY, SHT_GNU_verneed, SHT_GNU_versym, SHT_INIT_ARRAY, SHT_NOTE, SHT_NULL, SHT_PROGBITS, SHT_RELA, SHT_STRTAB | 0x0, 0x2, 0x3, 0x42 |
| User-Selected (.data) | .data | SHT_PROGBITS | 0x3 |
| User-Selected (.gnu.hash) | .gnu.hash | SHT_GNU_HASH | 0x2 |
| User-Selected (.text) | .text | SHT_PROGBITS | 0x6 |

### berkeley Category Summary (dir1)
- .text: .eh_frame, .eh_frame_hdr, .fini, .init, .interp, .plt, .rodata
- .data: .data.rel.ro, .got
- .bss: .bss
- Others: , .dynamic, .dynstr, .dynsym, .fini_array, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init_array, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .shstrtab
- User-Selected: .data, .gnu.hash, .text
### berkeley Category Summary (dir2)
- .text: .eh_frame, .eh_frame_hdr, .fini, .init, .interp, .plt, .rodata
- .data: .data.rel.ro, .got
- .bss: .bss
- Others: , .dynamic, .dynstr, .dynsym, .fini_array, .gnu.version, .gnu.version_r, .gnu_debuglink, .init_array, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .shstrtab
- User-Selected: .data, .gnu.hash, .text
### Top Files (berkeley)
#### .bss
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 4.70 KB | 43.97 KB | 39.27 KB | 836.44% |
| usr/bin | bash2 | common | 43.97 KB | 43.97 KB | 0 B | 0.00% |

#### .data
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 4.32 KB | 50.70 KB | 46.38 KB | 1073.42% |
| usr/bin | bash2 | common | 50.70 KB | 50.70 KB | 0 B | 0.00% |

#### .text
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 113.76 KB | 1.19 MB | 1.08 MB | 970.37% |
| usr/bin | bash2 | common | 1.19 MB | 1.19 MB | 0 B | 0.00% |

#### Others
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 14.19 KB | 203.05 KB | 188.87 KB | 1331.31% |
| usr/bin | bash2 | common | 203.05 KB | 203.05 KB | 0 B | 0.00% |

#### User-Selected
## Mode: gnu

| section | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- |
| .bss | 48.66 KB | 87.94 KB | 39.27 KB | 80.70% |
| .data | 55.02 KB | 101.39 KB | 46.38 KB | 84.29% |
| .text | 1.01 MB | 1.86 MB | 868.63 KB | 84.11% |
| Others | 515.97 KB | 940.14 KB | 424.18 KB | 82.21% |
| User-Selected (.data, .gnu.hash, .text) | 1.05 MB | 1.95 MB | 918.12 KB | 85.00% |

| class | section | type | flags |
| --- | --- | --- | --- |
| .bss | .bss | SHT_NOBITS | 0x3 |
| .data | .data.rel.ro, .got | SHT_PROGBITS | 0x3 |
| .text | .fini, .init, .plt | SHT_PROGBITS | 0x6 |
| Others | , .dynamic, .dynstr, .dynsym, .eh_frame, .eh_frame_hdr, .fini_array, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init_array, .interp, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .rodata, .shstrtab | SHT_DYNAMIC, SHT_DYNSYM, SHT_FINI_ARRAY, SHT_GNU_verneed, SHT_GNU_versym, SHT_INIT_ARRAY, SHT_NOTE, SHT_NULL, SHT_PROGBITS, SHT_RELA, SHT_STRTAB | 0x0, 0x2, 0x3, 0x42 |
| User-Selected (.data) | .data | SHT_PROGBITS | 0x3 |
| User-Selected (.gnu.hash) | .gnu.hash | SHT_GNU_HASH | 0x2 |
| User-Selected (.text) | .text | SHT_PROGBITS | 0x6 |

### gnu Category Summary (dir1)
- .text: .fini, .init, .plt
- .data: .data.rel.ro, .got
- .bss: .bss
- Others: , .dynamic, .dynstr, .dynsym, .eh_frame, .eh_frame_hdr, .fini_array, .gnu.version, .gnu.version_r, .gnu_debugaltlink, .gnu_debuglink, .init_array, .interp, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .rodata, .shstrtab
- User-Selected: .data, .gnu.hash, .text
### gnu Category Summary (dir2)
- .text: .fini, .init, .plt
- .data: .data.rel.ro, .got
- .bss: .bss
- Others: , .dynamic, .dynstr, .dynsym, .eh_frame, .eh_frame_hdr, .fini_array, .gnu.version, .gnu.version_r, .gnu_debuglink, .init_array, .interp, .note.ABI-tag, .note.gnu.build-id, .rela.dyn, .rela.plt, .rodata, .shstrtab
- User-Selected: .data, .gnu.hash, .text
### Top Files (gnu)
#### .bss
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 4.70 KB | 43.97 KB | 39.27 KB | 836.44% |
| usr/bin | bash2 | common | 43.97 KB | 43.97 KB | 0 B | 0.00% |

#### .data
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 4.32 KB | 50.70 KB | 46.38 KB | 1073.42% |
| usr/bin | bash2 | common | 50.70 KB | 50.70 KB | 0 B | 0.00% |

#### .text
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 82.05 KB | 950.68 KB | 868.63 KB | 1058.60% |
| usr/bin | bash2 | common | 950.68 KB | 950.68 KB | 0 B | 0.00% |

#### Others
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 45.90 KB | 470.07 KB | 424.18 KB | 924.20% |
| usr/bin | bash2 | common | 470.07 KB | 470.07 KB | 0 B | 0.00% |

#### User-Selected
## Mode: sysv

| section | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- |
|  | 0 B | 0 B | 0 B | 0.00% |
| .bss | 48.66 KB | 87.94 KB | 39.27 KB | 80.70% |
| .data | 33.54 KB | 65.78 KB | 32.24 KB | 96.13% |
| .data.rel.ro | 13.23 KB | 21.14 KB | 7.91 KB | 59.74% |
| .dynamic | 1.03 KB | 1.03 KB | 0 B | 0.00% |
| .dynstr | 41.94 KB | 80.90 KB | 38.96 KB | 92.91% |
| .dynsym | 63.66 KB | 121.22 KB | 57.56 KB | 90.43% |
| .eh_frame | 155.04 KB | 289.23 KB | 134.19 KB | 86.55% |
| .eh_frame_hdr | 19.43 KB | 35.90 KB | 16.47 KB | 84.76% |
| .fini | 40 B | 40 B | 0 B | 0.00% |
| .fini_array | 16 B | 16 B | 0 B | 0.00% |
| .gnu.hash | 19.25 KB | 38.38 KB | 19.12 KB | 99.35% |
| .gnu.version | 5.30 KB | 10.10 KB | 4.80 KB | 90.43% |
| .gnu.version_r | 352 B | 352 B | 0 B | 0.00% |
| .gnu_debugaltlink | 74 B | 0 B | -74 B | -100.00% |
| .gnu_debuglink | 104 B | 104 B | 0 B | 0.00% |
| .got | 8.24 KB | 14.47 KB | 6.23 KB | 75.55% |
| .init | 48 B | 48 B | 0 B | 0.00% |
| .init_array | 16 B | 16 B | 0 B | 0.00% |
| .interp | 54 B | 54 B | 0 B | 0.00% |
| .note.ABI-tag | 64 B | 64 B | 0 B | 0.00% |
| .note.gnu.build-id | 72 B | 72 B | 0 B | 0.00% |
| .plt | 5.34 KB | 7.22 KB | 1.88 KB | 35.09% |
| .rela.dyn | 76.95 KB | 142.64 KB | 65.70 KB | 85.38% |
| .rela.plt | 7.92 KB | 10.73 KB | 2.81 KB | 35.50% |
| .rodata | 124.20 KB | 208.85 KB | 84.65 KB | 68.15% |
| .shstrtab | 524 B | 506 B | -18 B | -3.44% |
| .text | 1.00 MB | 1.85 MB | 866.75 KB | 84.37% |
| User-Selected (.data, .gnu.hash, .text) | 1.05 MB | 1.95 MB | 918.12 KB | 85.00% |
| Others | 0 B | 0 B | 0 B | 0.00% |

| class | section | type | flags |
| --- | --- | --- | --- |
|  |  | SHT_NULL | 0x0 |
| .bss | .bss | SHT_NOBITS | 0x3 |
| .data.rel.ro | .data.rel.ro | SHT_PROGBITS | 0x3 |
| .dynamic | .dynamic | SHT_DYNAMIC | 0x3 |
| .dynstr | .dynstr | SHT_STRTAB | 0x2 |
| .dynsym | .dynsym | SHT_DYNSYM | 0x2 |
| .eh_frame | .eh_frame | SHT_PROGBITS | 0x2 |
| .eh_frame_hdr | .eh_frame_hdr | SHT_PROGBITS | 0x2 |
| .fini | .fini | SHT_PROGBITS | 0x6 |
| .fini_array | .fini_array | SHT_FINI_ARRAY | 0x3 |
| .gnu.version | .gnu.version | SHT_GNU_versym | 0x2 |
| .gnu.version_r | .gnu.version_r | SHT_GNU_verneed | 0x2 |
| .gnu_debugaltlink | .gnu_debugaltlink | SHT_PROGBITS | 0x0 |
| .gnu_debuglink | .gnu_debuglink | SHT_PROGBITS | 0x0 |
| .got | .got | SHT_PROGBITS | 0x3 |
| .init | .init | SHT_PROGBITS | 0x6 |
| .init_array | .init_array | SHT_INIT_ARRAY | 0x3 |
| .interp | .interp | SHT_PROGBITS | 0x2 |
| .note.ABI-tag | .note.ABI-tag | SHT_NOTE | 0x2 |
| .note.gnu.build-id | .note.gnu.build-id | SHT_NOTE | 0x2 |
| .plt | .plt | SHT_PROGBITS | 0x6 |
| .rela.dyn | .rela.dyn | SHT_RELA | 0x2 |
| .rela.plt | .rela.plt | SHT_RELA | 0x42 |
| .rodata | .rodata | SHT_PROGBITS | 0x2 |
| .shstrtab | .shstrtab | SHT_STRTAB | 0x0 |
| User-Selected (.data) | .data | SHT_PROGBITS | 0x3 |
| User-Selected (.gnu.hash) | .gnu.hash | SHT_GNU_HASH | 0x2 |
| User-Selected (.text) | .text | SHT_PROGBITS | 0x6 |

### Top Files (sysv)
#### 
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 0 B | 0 B | 0 B | 100.00% |
| usr/bin | bash2 | common | 0 B | 0 B | 0 B | 100.00% |

#### .data
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 664 B | 32.89 KB | 32.24 KB | 4972.29% |
| usr/bin | bash2 | common | 32.89 KB | 32.89 KB | 0 B | 0.00% |

#### .bss
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 4.70 KB | 43.97 KB | 39.27 KB | 836.44% |
| usr/bin | bash2 | common | 43.97 KB | 43.97 KB | 0 B | 0.00% |

#### .dynstr
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 1.49 KB | 40.45 KB | 38.96 KB | 2621.55% |
| usr/bin | bash2 | common | 40.45 KB | 40.45 KB | 0 B | 0.00% |

#### .gnu.version
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 260 B | 5.05 KB | 4.80 KB | 1889.23% |
| usr/bin | bash2 | common | 5.05 KB | 5.05 KB | 0 B | 0.00% |

#### .init
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 24 B | 24 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 24 B | 24 B | 0 B | 0.00% |

#### .plt
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 1.73 KB | 3.61 KB | 1.88 KB | 108.11% |
| usr/bin | bash2 | common | 3.61 KB | 3.61 KB | 0 B | 0.00% |

#### .interp
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 27 B | 27 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 27 B | 27 B | 0 B | 0.00% |

#### .note.gnu.build-id
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 36 B | 36 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 36 B | 36 B | 0 B | 0.00% |

#### .rela.dyn
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 5.62 KB | 71.32 KB | 65.70 KB | 1167.92% |
| usr/bin | bash2 | common | 71.32 KB | 71.32 KB | 0 B | 0.00% |

#### .gnu_debugaltlink
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | removed | 74 B | 0 B | -74 B | -100.00% |

#### .note.ABI-tag
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 32 B | 32 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 32 B | 32 B | 0 B | 0.00% |

#### .gnu_debuglink
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 52 B | 52 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 52 B | 52 B | 0 B | 0.00% |

#### .eh_frame
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 10.43 KB | 144.62 KB | 134.19 KB | 1287.11% |
| usr/bin | bash2 | common | 144.62 KB | 144.62 KB | 0 B | 0.00% |

#### .gnu.hash
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 64 B | 19.19 KB | 19.12 KB | 30600.00% |
| usr/bin | bash2 | common | 19.19 KB | 19.19 KB | 0 B | 0.00% |

#### .rela.plt
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 2.55 KB | 5.37 KB | 2.81 KB | 110.09% |
| usr/bin | bash2 | common | 5.37 KB | 5.37 KB | 0 B | 0.00% |

#### .fini
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 20 B | 20 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 20 B | 20 B | 0 B | 0.00% |

#### .text
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 80.28 KB | 947.03 KB | 866.75 KB | 1079.70% |
| usr/bin | bash2 | common | 947.03 KB | 947.03 KB | 0 B | 0.00% |

#### .dynsym
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 3.05 KB | 60.61 KB | 57.56 KB | 1889.23% |
| usr/bin | bash2 | common | 60.61 KB | 60.61 KB | 0 B | 0.00% |

#### .eh_frame_hdr
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 1.48 KB | 17.95 KB | 16.47 KB | 1112.40% |
| usr/bin | bash2 | common | 17.95 KB | 17.95 KB | 0 B | 0.00% |

#### .data.rel.ro
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 2.66 KB | 10.57 KB | 7.91 KB | 296.77% |
| usr/bin | bash2 | common | 10.57 KB | 10.57 KB | 0 B | 0.00% |

#### .rodata
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 19.78 KB | 104.43 KB | 84.65 KB | 428.01% |
| usr/bin | bash2 | common | 104.43 KB | 104.43 KB | 0 B | 0.00% |

#### .got
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 1.01 KB | 7.23 KB | 6.23 KB | 617.83% |
| usr/bin | bash2 | common | 7.23 KB | 7.23 KB | 0 B | 0.00% |

#### .dynamic
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 528 B | 528 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 528 B | 528 B | 0 B | 0.00% |

#### .shstrtab
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 271 B | 253 B | -18 B | -6.64% |
| usr/bin | bash2 | common | 253 B | 253 B | 0 B | 0.00% |

#### .init_array
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 8 B | 8 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 8 B | 8 B | 0 B | 0.00% |

#### .fini_array
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 8 B | 8 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 8 B | 8 B | 0 B | 0.00% |

#### .gnu.version_r
| directory | file | status | size1 | size2 | diff | diff_pct |
| --- | --- | --- | --- | --- | --- | --- |
| usr/bin | bash | common | 176 B | 176 B | 0 B | 0.00% |
| usr/bin | bash2 | common | 176 B | 176 B | 0 B | 0.00% |

#### Others
#### User-Selected
