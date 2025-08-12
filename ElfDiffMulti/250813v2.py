import os
import argparse
from collections import defaultdict
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS, P_FLAGS

mode_rules_dict = defaultdict(lambda: defaultdict(set))

# === ELF Section Type 상수 ===
SHT_NULL          = 0
SHT_PROGBITS      = 1
SHT_SYMTAB        = 2
SHT_STRTAB        = 3
SHT_RELA          = 4
SHT_HASH          = 5
SHT_DYNAMIC       = 6
SHT_NOTE          = 7
SHT_NOBITS        = 8
SHT_REL           = 9
SHT_SHLIB         = 10
SHT_DYNSYM        = 11
SHT_INIT_ARRAY    = 14
SHT_FINI_ARRAY    = 15
SHT_PREINIT_ARRAY = 16
SHT_GROUP         = 17
SHT_SYMTAB_SHNDX  = 18

# ==== 플래그 의미 해석 사전 ====
PT_FLAGS_MEANING = {
    P_FLAGS.PF_X: "PF_X (Execute)",
    P_FLAGS.PF_W: "PF_W (Write)",
    P_FLAGS.PF_R: "PF_R (Read)"
}

SH_FLAGS_MEANING = {
    SH_FLAGS.SHF_WRITE: "WRITE",
    SH_FLAGS.SHF_ALLOC: "ALLOC",
    SH_FLAGS.SHF_EXECINSTR: "EXEC",
    0x10: "MERGE",
    0x20: "STRINGS",
    0x40: "INFO_LINK",
    0x80: "LINK_ORDER",
    0x100: "OS_NONCONFORMING",
    0x200: "GROUP",
    0x400: "TLS",
    0x800: "COMPRESSED",
    0x80000000: "EXCLUDE"
}

def extract_type_info(section):
    """ELF 섹션의 타입 코드를 읽어서 표준 상수명으로 변환"""
    # 표준 ELF sh_type 매핑
    sht_map = {
        0x0:  "SHT_NULL",
        0x1:  "SHT_PROGBITS",
        0x2:  "SHT_SYMTAB",
        0x3:  "SHT_STRTAB",
        0x4:  "SHT_RELA",
        0x5:  "SHT_HASH",
        0x6:  "SHT_DYNAMIC",
        0x7:  "SHT_NOTE",
        0x8:  "SHT_NOBITS",
        0x9:  "SHT_REL",
        0x0A: "SHT_SHLIB",
        0x0B: "SHT_DYNSYM",
        0x0E: "SHT_INIT_ARRAY",
        0x0F: "SHT_FINI_ARRAY",
        0x10: "SHT_PREINIT_ARRAY",
        0x11: "SHT_GROUP",
        0x12: "SHT_SYMTAB_SHNDX",
        0x13: "SHT_NUM",
        # 필요한 경우 더 확장 가능
    }

    raw_type = section['sh_type']

    # 정수 타입 코드
    if isinstance(raw_type, int):
        tcode = raw_type
    else:
        # 문자열 타입일 수 있는 경우 처리
        try:
            tcode = int(raw_type)
        except (ValueError, TypeError):
            tcode = -1

    # 타입명 매핑
    tname = sht_map.get(tcode, f"UNKNOWN({tcode})")
    return tcode, tname


# === Group settings ===
KNOWN_GROUPS = {
    'berkeley': {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'OTHERS': set(), 'EXCLUDE': set()},
    'gnu':      {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'OTHERS': set(), 'EXCLUDE': set()},
    'sysv':     {'EXCLUDE': set(), 'OTHERS': set()}
}

EXTRA_SH_FLAGS = {
    0x10: "MERGE", 0x20: "STRINGS", 0x40: "INFO_LINK", 0x80: "LINK_ORDER",
    0x100: "OS_NONCONFORMING", 0x200: "GROUP", 0x400: "TLS", 0x800: "COMPRESSED",
    0x80000000: "EXCLUDE"
}

# ---- 유틸 ----
def md_safe(text):
    """Markdown 표 안전 처리"""
    if text is None:
        return ""
    return f"`{text}`"

def decode_pt_flags(flags):
    """PT_FLAGS int → PF_... 문자열"""
    if flags == "-" or flags is None:
        return "-"
    names = []
    if flags & P_FLAGS.PF_X: names.append("PF_X")
    if flags & P_FLAGS.PF_W: names.append("PF_W")
    if flags & P_FLAGS.PF_R: names.append("PF_R")
    return "|".join(names) + f"({flags})"

def decode_sh_flags(flags: int) -> str:
    names = []
    if flags & SH_FLAGS.SHF_WRITE:
        names.append("WRITE")
    if flags & SH_FLAGS.SHF_ALLOC:
        names.append("ALLOC")
    if flags & SH_FLAGS.SHF_EXECINSTR:
        names.append("EXEC")
    for bit, name in EXTRA_SH_FLAGS.items():
        if flags & bit:
            names.append(name)
    return "|".join(names) if names else "NONE"

def extract_type_info(section):
    raw_type = section['sh_type']
    if isinstance(raw_type, int):
        tcode = raw_type
    else:
        tmap = {'SHT_NULL':0, 'SHT_PROGBITS':1, 'SHT_NOBITS':8}
        tcode = tmap.get(str(raw_type).upper(), -1)
    tname = {0:'SHT_NULL', 1:'SHT_PROGBITS', 8:'SHT_NOBITS'}.get(tcode, 'UNKNOWN')
    return tcode, tname

def is_bss_section(sec):
    sh_flags = int(sec['sh_flags'])
    raw_type = sec['sh_type']
    sh_type = raw_type if isinstance(raw_type, int) else {'SHT_NOBITS': SHT_NOBITS}.get(str(raw_type).upper(), -1)
    alloc = bool(sh_flags & SH_FLAGS.SHF_ALLOC)
    write = bool(sh_flags & SH_FLAGS.SHF_WRITE)
    has_contents = (sec['sh_size'] > 0 and sh_type != SHT_NOBITS)
    return alloc and write and (sh_type == SHT_NOBITS or not has_contents)

def get_segment_flags_and_mapping(elf: ELFFile, sec):
    off, addr = sec['sh_offset'], sec['sh_addr']
    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        if ((seg['p_offset'] <= off < seg['p_offset'] + seg['p_filesz']) or
            (seg['p_vaddr'] <= addr < seg['p_vaddr'] + seg['p_memsz'])):
            return seg['p_flags'], True
    return "-", False

def berkeley_group_from_pt_load(elf, sec):
    sh_type = int(sec['sh_type']) if isinstance(sec['sh_type'], int) \
              else {'SHT_NOBITS': SHT_NOBITS}.get(str(sec['sh_type']).upper(), -1)
    off, addr = sec['sh_offset'], sec['sh_addr']
    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        in_file_range = seg['p_offset'] <= off < seg['p_offset'] + seg['p_filesz']
        in_mem_range  = seg['p_vaddr'] <= addr < seg['p_vaddr'] + seg['p_memsz']
        if not (in_file_range or in_mem_range):
            continue
        flags = seg['p_flags']
        if flags & P_FLAGS.PF_X:
            return "TEXT"
        elif flags & P_FLAGS.PF_W:
            return "BSS" if sh_type == SHT_NOBITS else "DATA"
        else:
            return "TEXT"
    return "OTHERS"

def human_readable_size(num):
    for unit in ['B','KB','MB','GB','TB']:
        if abs(num) < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"

# ----- 그룹 분류 -----
def get_group_name(sec, mode, exclude_secs, group_rule=None, debug=False):
    name = sec.name
    flags = int(sec['sh_flags'])
    execi = bool(flags & SH_FLAGS.SHF_EXECINSTR)
    alloc = bool(flags & SH_FLAGS.SHF_ALLOC)
    write = bool(flags & SH_FLAGS.SHF_WRITE)

    if name in exclude_secs:
        return "EXCLUDE"

    if group_rule:
        for group, secset in group_rule.items():
            if group != "EXCLUDE" and name in secset:
                return group
        if name in group_rule.get("EXCLUDE", set()):
            return "EXCLUDE"

    if mode == "berkeley":
        return berkeley_group_from_pt_load(sec.elffile, sec)
    elif mode == "gnu":
        if execi:
            return "TEXT"
        elif alloc:
            if write and is_bss_section(sec):
                return "BSS"
            else:
                return "DATA"
        else:
            return "OTHERS"
    elif mode == "sysv":
        # 첫 글자가 '.'이면 제거, 그리고 전부 대문자로 변환
        clean_name = name[1:] if name.startswith(".") else name
        return clean_name.upper()
    return "OTHERS"

def analyze_directory(directory, mode, exclude_secs, debug=False):
    results = {}
    for root, _, files in os.walk(directory):
        for fn in files:
            path = os.path.join(root, fn)
            relpath = os.path.relpath(path, start=directory)
            try:
                with open(path, 'rb') as f:
                    elf = ELFFile(f)
                    gmap = defaultdict(dict)
                    for sec in elf.iter_sections():
                        sec.elffile = elf
                        tcode, tname = extract_type_info(sec)

                        sh_flags_val = int(sec['sh_flags'])
                        sz = sec['sh_size']

                        # 그룹 분류
                        group = get_group_name(
                            sec, mode, exclude_secs,
                            KNOWN_GROUPS.get(mode),
                            debug
                        )

                        # 분석 결과 저장 (섹션별 size/type/flags)
                        gmap[group][sec.name] = {
                            'size': sz,
                            'type_name': tname,
                            'flags': sh_flags_val
                        }

                        # 세그먼트 플래그 / 매핑 여부
                        pt_flags_val, mapping_pass = get_segment_flags_and_mapping(elf, sec)
                        mode_rules_dict[mode][group].add((
                            sec.name,         # 0: 섹션명
                            pt_flags_val,     # 1: PT_FLAGS int
                            sh_flags_val,     # 2: SH_FLAGS int
                            tname,            # 3: SH_TYPE str
                            mapping_pass      # 4: bool
                        ))
                    results[relpath] = gmap
            except Exception as e:
                if debug:
                    print(f"[WARN] Fail to parse {path}: {e}")
    return results

# === Compare & summarize ===
def compare_results(old_res, new_res):
    diff = {}
    for fp in set(old_res) | set(new_res):
        fd = {}
        old_groups = old_res.get(fp, {})
        new_groups = new_res.get(fp, {})
        for g in set(old_groups) | set(new_groups):
            oldt = sum(s['size'] for s in old_groups.get(g, {}).values())
            newt = sum(s['size'] for s in new_groups.get(g, {}).values())
            fd[g] = {'old_total': oldt, 'new_total': newt, 'delta_total': newt - oldt}
        diff[fp] = fd
    return diff

def summarize_group_totals(diff_res):
    summ = defaultdict(lambda: {'old_total':0, 'new_total':0, 'delta_total':0})
    for _, gm in diff_res.items():
        for g, v in gm.items():
            summ[g]['old_total'] += v['old_total']
            summ[g]['new_total'] += v['new_total']
            summ[g]['delta_total'] += v['delta_total']


    return dict(summ)


def to_hex_str(values):
    """정수 값 집합을 0xHEX 문자열로 변환 (중복 제거, 정렬, 자료형 방어)"""
    hex_list = []
    for v in values:
        try:
            hex_list.append(f"0x{int(v):X}")
        except (ValueError, TypeError):
            continue
    return "; ".join(sorted(hex_list))

def generate_md_report(output_path, mode, summary, readable=False):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Analysis Report - Mode: {mode}\n\n")
        f.write("| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | MappingPass |\n")
        f.write("|-------|----------|----------|----------|----------|-------------|\n")

        for group, entries in mode_rules_dict[mode].items():
            secs = ", ".join(sorted({e[0] for e in entries}))

            pt_flags_str = to_hex_str({e[1] for e in entries})
            sh_flags_str = to_hex_str({e[2] for e in entries})
            sh_types_str = "; ".join(sorted({e[3] for e in entries}))
            mpass_str    = "; ".join(sorted({"✔" if e[4] else "✖" for e in entries}))

            f.write(f"| {group} | {secs} | {pt_flags_str} | {sh_flags_str} | {sh_types_str} | {mpass_str} |\n")

        # Summary
        f.write("\n| Group | Old Total | New Total | Delta | Delta% |\n")
        f.write("|-------|-----------|-----------|-------|--------|\n")
        for g, vals in summary.items():
            old_val, new_val, delta_val = vals['old_total'], vals['new_total'], vals['delta_total']
            if readable:
                old_str, new_str, delta_str = human_readable_size(old_val), human_readable_size(new_val), human_readable_size(delta_val)
            else:
                old_str, new_str, delta_str = str(old_val), str(new_val), str(delta_val)
            delta_pct = f"{(delta_val / old_val) * 100:.2f}%" if old_val != 0 else "-"
            f.write(f"| {g} | {old_str} | {new_str} | {delta_str} | {delta_pct} |\n")

        # Legend - 가로 한 줄
        pt_items = [f"0x{bit:X}={desc}" for bit, desc in PT_FLAGS_MEANING.items()]
        f.write("\n\n### PT_FLAGS Legend\n" + ", ".join(pt_items) + "\n")
        sh_items = [f"0x{bit:X}={desc}" for bit, desc in SH_FLAGS_MEANING.items()]
        f.write("\n### SH_FLAGS Legend\n" + ", ".join(sh_items) + "\n")
def write_mode_rules_md(output_dir):
    for mode, groups in mode_rules_dict.items():
        path = os.path.join(output_dir, f"mode_rules_{mode}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Classification Rule Table - Mode: {mode}\n\n")
            f.write("| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | MappingPass |\n")
            f.write("|-------|----------|----------|----------|----------|-------------|\n")

            for group, entries in groups.items():
                secs = ", ".join(sorted({e[0] for e in entries}))

                pt_flags_str = to_hex_str({e[1] for e in entries})
                sh_flags_str = to_hex_str({e[2] for e in entries})
                sh_types_str = "; ".join(sorted({e[3] for e in entries}))
                mpass_str    = "; ".join(sorted({"✔" if e[4] else "✖" for e in entries}))

                f.write(f"| {group} | {secs} | {pt_flags_str} | {sh_flags_str} | {sh_types_str} | {mpass_str} |\n")

            # Legend - 가로 한 줄
            pt_items = [f"0x{bit:X}={desc}" for bit, desc in PT_FLAGS_MEANING.items()]
            f.write("\n\n### PT_FLAGS Legend\n" + ", ".join(pt_items) + "\n")
            sh_items = [f"0x{bit:X}={desc}" for bit, desc in SH_FLAGS_MEANING.items()]
            f.write("\n### SH_FLAGS Legend\n" + ", ".join(sh_items) + "\n")

        print(f"[INFO] Saved mode_rules table for '{mode}' to {path}")


# ---- main ----
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("old_dir"); parser.add_argument("new_dir")
    parser.add_argument("--mode", choices=["berkeley","gnu","sysv","all"], default="berkeley")
    parser.add_argument("--exclude-sections", default="")
    parser.add_argument("--readable", action="store_true")
    parser.add_argument("--top-n-groups", type=int, default=5)
    parser.add_argument("--top-n-files", type=int, default=3)
    parser.add_argument("--sort-by", choices=["abs","pos","neg","pos_pct","neg_pct","combined"], default="abs")
    parser.add_argument("--sort-order", choices=["asc","desc"], default="desc")
    parser.add_argument("--output-dir"); parser.add_argument("--output-prefix", default="")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--plot-exclude-groups", default="")
    parser.add_argument("--common-files", action='store_true')
    args = parser.parse_args()

    exclude_secs = [s.strip() for s in args.exclude_sections.split(',')] if args.exclude_sections else []
    modes = [args.mode] if args.mode != "all" else ["berkeley","gnu","sysv"]

    old_res_dict, new_res_dict = {}, {}
    for mode in modes:
        old_res = analyze_directory(args.old_dir, mode, exclude_secs, args.debug)
        new_res = analyze_directory(args.new_dir, mode, exclude_secs, args.debug)
        if args.common_files:
            common_files = set(old_res) & set(new_res)
            old_res = {k:v for k,v in old_res.items() if k in common_files}
            new_res = {k:v for k,v in new_res.items() if k in common_files}
        old_res_dict[mode] = old_res
        new_res_dict[mode] = new_res

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    for mode in modes:
        diff = compare_results(old_res_dict[mode], new_res_dict[mode])
        summary = summarize_group_totals(diff)
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            generate_md_report(os.path.join(args.output_dir, f"{args.output_prefix}report_{mode}.md"), mode, summary, readable=args.readable)
        for g, vals in summary.items():
            print(f"{mode}\t{g}\told={vals['old_total']}\tnew={vals['new_total']}\tΔ={vals['delta_total']}")
    if args.output_dir:
        write_mode_rules_md(args.output_dir)
