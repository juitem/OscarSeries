import os
import shlex
import sys
import argparse
from collections import defaultdict
import re
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS, P_FLAGS

# =============================
# Global Constants and Settings
# =============================

# Known group templates for each mode
KNOWN_GROUPS = {
    'berkeley': {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'OTHERS': set(), 'EXCLUDE': set()},
    'gnu':      {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'OTHERS': set(), 'EXCLUDE': set()},
    'sysv':     {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'OTHERS': set(), 'EXCLUDE': set()},
    'custom':   {'TEXT': set(), 'DATA': set(), 'BSS': set(),'EXCLUDE':set(),
                 'DYNAMIC': set(),'OTHERS':set(),}
}
USE_REGEX = False  # Use regex for matching section names
if USE_REGEX:
    KNOWN_RULES = {
        'berkeley': {
            'OTHERS': set(),'EXCLUDE': set()
        },
        'gnu': {
            'OTHERS': set(), 'EXCLUDE': set()
        },
        'sysv': {
        'OTHERS': set(), 'EXCLUDE': set()
        },
        'custom': {
            'TEXT':   [r''],
            'DATA':   [r''],
            'DYNAMIC':[r'*dyn*'],
            'BSS':    [r'\*bss\*'],
            'OTHERS': [r''],
            'EXCLUDE':[r'\.*note\*']
        }
    }

# #KNOWN_RULES = {}            
if USE_REGEX:
    # KNOWN_RULES → KNOWN_GROUPS 자동 반영
    for mode, rules in KNOWN_RULES.items():
        if mode not in KNOWN_GROUPS:
            KNOWN_GROUPS[mode] = {}
        for gname in rules.keys():
            if gname not in KNOWN_GROUPS[mode]:
                KNOWN_GROUPS[mode][gname] = set()


# Dictionary to store mode rules: {mode: {group: set(entries)}}
mode_rules_dict = defaultdict(lambda: defaultdict(set))

# ELF Section Type constants
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

# PT_FLAGS and SH_FLAGS meaning maps
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
    # OS-specific masks
    0x0FF00000: "OS_MASK (legacy range, SHF_MASKOS)",
    0x80000000: "OS_MASK (OS-specific high bit, SHF_MASKOS)",
    # Processor-specific mask
    0xF0000000: "PROC_MASK (Processor-specific, SHF_MASKPROC)"
}

# =========================
# Utility / Helper Functions
# =========================

def human_readable_size(num_bytes):
    """Convert byte value to human-readable string with always +/- sign except zero."""
    if num_bytes > 0:
        sign = "+"
    elif num_bytes < 0:
        sign = "-"
    else:
        sign = ""
    value = abs(num_bytes)

    if value < 1024:
        return f"{sign}{value}B"
    elif value < 1024 ** 2:
        return f"{sign}{value / 1024:.1f}KB"
    elif value < 1024 ** 3:
        return f"{sign}{value / 1024 ** 2:.1f}MB"
    else:
        return f"{sign}{value / 1024 ** 3:.1f}GB"

def format_size(value, readable=False):
    """Format a numeric size value, either as raw bytes string or human-readable with sign."""
    if readable:
        return human_readable_size(value)
    else:
        return str(value)

def to_hex_str(values):
    """Convert a set of numeric values to sorted hex string separated by semicolons."""
    hex_list = []
    for v in values:
        try:
            hex_list.append(f"0x{int(v):X}")
        except (TypeError, ValueError):
            continue
    return "; ".join(sorted(hex_list))

def md_safe(text):
    """Escape text for safe Markdown output."""
    if text is None:
        return ""
    return f"`{text}`"

def decode_pt_flags(flags):
    """Decode PT_FLAGS integer to string with PF_ names."""
    if flags == "-" or flags is None:
        return "-"
    names = []
    if flags & P_FLAGS.PF_X:
        names.append("PF_X")
    if flags & P_FLAGS.PF_W:
        names.append("PF_W")
    if flags & P_FLAGS.PF_R:
        names.append("PF_R")
    return "|".join(names) + f"({flags})"

def decode_sh_flags(flags: int) -> str:
    """Decode SH_FLAGS integer to string description."""
    names = []
    if flags & SH_FLAGS.SHF_WRITE:
        names.append("WRITE")
    if flags & SH_FLAGS.SHF_ALLOC:
        names.append("ALLOC")
    if flags & SH_FLAGS.SHF_EXECINSTR:
        names.append("EXEC")
    for bit, name in SH_FLAGS_MEANING.items():
        # Ignore duplicates to not double list known bits
        if bit in (SH_FLAGS.SHF_WRITE, SH_FLAGS.SHF_ALLOC, SH_FLAGS.SHF_EXECINSTR):
            continue
        if flags & bit:
            names.append(name)
    return "|".join(names) if names else "NONE"

def is_bss_section(sec):
    """Check if ELF section qualifies as BSS (uninitialized data section)."""
    sh_flags = int(sec['sh_flags'])
    raw_type = sec['sh_type']
    sh_type = raw_type if isinstance(raw_type, int) else {'SHT_NOBITS': SHT_NOBITS}.get(str(raw_type).upper(), -1)
    alloc = bool(sh_flags & SH_FLAGS.SHF_ALLOC)
    write = bool(sh_flags & SH_FLAGS.SHF_WRITE)
    has_contents = (sec['sh_size'] > 0 and sh_type != SHT_NOBITS)
    return alloc and write and (sh_type == SHT_NOBITS or not has_contents)

def extract_type_info(section):
    """Return (type_code, type_name) for ELF section with extended SHT map."""
    sht_map = {
        0x0: "SHT_NULL",
        0x1: "SHT_PROGBITS",
        0x2: "SHT_SYMTAB",
        0x3: "SHT_STRTAB",
        0x4: "SHT_RELA",
        0x5: "SHT_HASH",
        0x6: "SHT_DYNAMIC",
        0x7: "SHT_NOTE",
        0x8: "SHT_NOBITS",
        0x9: "SHT_REL",
        0x0A: "SHT_SHLIB",
        0x0B: "SHT_DYNSYM",
        0x0E: "SHT_INIT_ARRAY",
        0x0F: "SHT_FINI_ARRAY",
        0x10: "SHT_PREINIT_ARRAY",
        0x11: "SHT_GROUP",
        0x12: "SHT_SYMTAB_SHNDX",
        # GNU extensions
        0x6ffffff6: "SHT_GNU_HASH",
        0x6ffffffe: "SHT_GNU_VERNEED",
        0x6fffffff: "SHT_GNU_VERSYM",
        0x6ffffffd: "SHT_GNU_VERDEF"
    }
    rev_sht_map = {v: k for k, v in sht_map.items()}

    raw_type = section['sh_type']
    if isinstance(raw_type, int):
        tcode = raw_type
    elif hasattr(raw_type, '__int__'):
        tcode = int(raw_type)
    elif isinstance(raw_type, str):
        tcode = rev_sht_map.get(raw_type.upper(), -1)
    else:
        tcode = -1
    tname = sht_map.get(tcode, f"UNKNOWN({tcode})")
    return tcode, tname

# def get_segment_flags_and_mapping(elf: ELFFile, sec):
#     off, addr = sec['sh_offset'], sec['sh_addr']
#     for seg in elf.iter_segments():
#         if seg['p_type'] != 'PT_LOAD':
#             continue
#         if ((seg['p_offset'] <= off < seg['p_offset'] + seg['p_filesz']) or
#             (seg['p_vaddr'] <= addr < seg['p_vaddr'] + seg['p_memsz'])):
#             return seg['p_flags'], True
#     return "-", False

def get_segment_flags_and_mapping(elf, section):
    """Return PT_FLAGS for the segment mapping this section and if mapping passes."""
    pt_flags_val = "-"
    mapping_pass = False

    sec_off  = section['sh_offset']
    sec_endf = sec_off + section['sh_size']
    sec_addr = section['sh_addr']
    sec_enda = sec_addr + section['sh_size']

    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        seg_off  = seg['p_offset']
        seg_endf = seg_off + seg['p_filesz']
        seg_addr = seg['p_vaddr']
        seg_enda = seg_addr + seg['p_memsz']
        if (sec_off >= seg_off and sec_endf <= seg_endf and
            sec_addr >= seg_addr and sec_enda <= seg_enda):
            pt_flags_val = seg['p_flags']
            mapping_pass = True
            break
    return pt_flags_val, mapping_pass

def berkeley_group_from_pt_load(elf, sec):
    """Classify group in 'berkeley' mode by PT_LOAD segment flags."""
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

def sort_items(items, sort_by, is_group=True):
    """Sort groups or files according to sort_by rule."""
    def calc_pct(delta, old):
        return (delta / old) * 100 if old else 0.0

    if is_group:
        if sort_by == '+diff':
            items = [i for i in items if i[1]['delta_total'] >= 0]
            return sorted(items, key=lambda x: x[1]['delta_total'], reverse=True)
        elif sort_by == '-diff':
            items = [i for i in items if i[1]['delta_total'] <= 0]
            return sorted(items, key=lambda x: x[1]['delta_total'])
        elif sort_by == 'abs_diff':
            return sorted(items, key=lambda x: abs(x[1]['delta_total']), reverse=True)
        elif sort_by == '+diff_pct':
            items = [i for i in items if calc_pct(i[1]['delta_total'], i[1]['old_total']) >= 0]
            return sorted(items, key=lambda x: calc_pct(x[1]['delta_total'], x[1]['old_total']), reverse=True)
        elif sort_by == '-diff_pct':
            items = [i for i in items if calc_pct(i[1]['delta_total'], i[1]['old_total']) <= 0]
            return sorted(items, key=lambda x: calc_pct(x[1]['delta_total'], x[1]['old_total']))
        elif sort_by == 'abs_diff_pct':
            return sorted(items, key=lambda x: abs(calc_pct(x[1]['delta_total'], x[1]['old_total'])), reverse=True)

    else:
        if sort_by == '+diff':
            items = [f for f in items if f['Diff'] >= 0]
            return sorted(items, key=lambda f: f['Diff'], reverse=True)
        elif sort_by == '-diff':
            items = [f for f in items if f['Diff'] <= 0]
            return sorted(items, key=lambda f: f['Diff'])
        elif sort_by == 'abs_diff':
            return sorted(items, key=lambda f: abs(f['Diff']), reverse=True)
        elif sort_by == '+diff_pct':
            items = [f for f in items if f['DiffPct'] >= 0]
            return sorted(items, key=lambda f: f['DiffPct'], reverse=True)
        elif sort_by == '-diff_pct':
            items = [f for f in items if f['DiffPct'] <= 0]
            return sorted(items, key=lambda f: f['DiffPct'])
        elif sort_by == 'abs_diff_pct':
            return sorted(items, key=lambda f: abs(f['DiffPct']), reverse=True)

    return items


def handle_sort_pair_option(sort_by, items, top_n, is_group=True):
    """
    Support double sign patterns:
      '++diff', '--diff', '+-diff', '-+diff', same with _pct
    Returns: list of tuples (sort_key, sorted_items)
    """
    results = []
    if len(sort_by) >= 3 and sort_by[0] in "+-" and sort_by[1] in "+-":
        metric = sort_by[2:]
        first = sort_by[0] + metric
        second = sort_by[1] + metric
        first_list = sort_items(items, first, is_group=is_group)[:top_n]
        second_list = sort_items(items, second, is_group=is_group)[:top_n]
        results.append((first, first_list))
        results.append((second, second_list))
    else:
        sorted_list = sort_items(items, sort_by, is_group=is_group)[:top_n]
        results.append((sort_by, sorted_list))

    return results


def parse_sort_by_option(option_val):
    """Group Filter + Key split"""
    if ':' in option_val:
        group_part, sort_part = option_val.split(':', 1)
        groups = [g.strip() for g in group_part.split(',') if g.strip()]
        return groups, sort_part
    else:
        return None, option_val


# =============================
# Diff & Summary
# =============================
def compare_results(old_res, new_res):
    diff = {}
    for fp in set(old_res) | set(new_res):
        fd = {}
        old_groups, new_groups = old_res.get(fp, {}), new_res.get(fp, {})
        for g in set(old_groups) | set(new_groups):
            oldt = sum(s['size'] for s in old_groups.get(g, {}).values()) if g in old_groups else 0
            newt = sum(s['size'] for s in new_groups.get(g, {}).values()) if g in new_groups else 0
            fd[g] = {'old_total': oldt, 'new_total': newt, 'delta_total': newt - oldt}
        diff[fp] = fd
    return diff

# def summarize_group_totals(diff_res, mode):
#     summ = {g:{'old_total':0,'new_total':0,'delta_total':0}
#             for g in KNOWN_GROUPS[mode] if g != 'EXCLUDE'}

def summarize_group_totals(diff_res, mode):
    if USE_REGEX:
    # KNOWN_GROUPS + KNOWN_RULES의 그룹명 모두 취합
        all_groups = set(KNOWN_GROUPS[mode].keys()) | set(KNOWN_RULES.get(mode, {}).keys())
    else:
        all_groups = set(KNOWN_GROUPS[mode].keys())  #| set(KNOWN_RULES.get(mode, {}).keys())

    summ = {g: {'old_total':0, 'new_total':0, 'delta_total':0} for g in all_groups}

#    all_groups.discard('EXCLUDE')

    for _, gm in diff_res.items():
        for g, v in gm.items():
            if g not in summ:
                summ[g] = {'old_total':0,'new_total':0,'delta_total':0}
            summ[g]['old_total'] += v['old_total']
            summ[g]['new_total'] += v['new_total']
            summ[g]['delta_total'] += v['delta_total']
    return summ


# def summarize_group_totals(diff_res):
######
#  #   summ = defaultdict(lambda: {'old_total':0, 'new_total':0, 'delta_total':0})
#     summ={g:{'old_total':0,'new_total':0,'delta_total':0} for g in KNOWN_GROUPS[mode] if g!='EXCLUDE'}

    # for _, gm in diff_res.items():
    #     for g,v in gm.items():
    #         if g not in summ:
    #             summ[g] = {'old_total':0,'new_total':0,'delta_total':0}
    #         summ[g]['old_total'] += v['old_total']
    #         summ[g]['new_total'] += v['new_total']
    #         summ[g]['delta_total'] += v['delta_total']
    # return dict(summ)


# =============================
# Report & Output
# =============================
def generate_md_report(output_path, mode, summary, readable=False, args=None):
    """Generate summary markdown report for a mode."""
    with open(output_path, "w", encoding="utf-8") as f:
        if args:
            cmd_line = " ".join(shlex.quote(x) for x in sys.argv)
            f.write(f"**Run Command:** `{cmd_line}`\n\n")

        f.write(f"# Analysis Report - Mode: {mode}\n\n")
        f.write("| Group | Sections | PT_FLAGS | SH_FLAGS | SH_TYPES | FILE&VM<br>Mapping |\n")
        f.write("|-------|----------|----------|----------|----------|-------------------|\n")

        for group, entries in mode_rules_dict[mode].items():
            secs = ", ".join(sorted({e[0] for e in entries}))
            #pt_flags_str = to_hex_str({e[1] for e in entries})

            raw_flags = {e[1] for e in entries if isinstance(e[1], int)}
            if not raw_flags:             # 값 자체가 없거나 "-", None 등일 때
                pt_flags_str = "-"
            else:
                pt_flags_str = to_hex_str(raw_flags)
                # if pt_flags_str == "0x0":  # 0 단독이면 대시로
                #     pt_flags_str = "-"
                # else: ### added debug
                #     print(f"[DEBUG] PT_FLAGS for group '{group}': {pt_flags_str}") if readable else None
                #     exit(1)

            sh_flags_str = to_hex_str({e[2] for e in entries})
            sh_types_str = "; ".join(sorted({e[3] for e in entries}))

            # ✅ mapping_pass count summary
            mpass_counts = defaultdict(int)
            for e in entries:
                mpass_counts["✔" if e[4] else "✖"] += 1
            mpass_str = "; ".join(f"{k}({v})" for k, v in sorted(mpass_counts.items()))

            f.write(f"| {group} | {secs} | {pt_flags_str} | {sh_flags_str} | {sh_types_str} | {mpass_str} |\n")

        # Legend for this table
        pt_items = [f"0x{bit:X}={desc}" for bit, desc in PT_FLAGS_MEANING.items()]
        sh_items = [f"0x{bit:X}={desc}" for bit, desc in SH_FLAGS_MEANING.items()]
        f.write("\n### PT_FLAGS Legend\n" + ", ".join(pt_items) + "\n")
        f.write("### SH_FLAGS Legend\n" + ", ".join(sh_items) + "\n\n")

        # Summary table
        f.write("| Group | Old Total | New Total | Delta | Delta% |\n")
        f.write("|-------|-----------|-----------|-------|--------|\n")
        for g, vals in summary.items():
            old_val, new_val, delta_val = vals['old_total'], vals['new_total'], vals['delta_total']
            old_str = format_size(old_val, readable)
            new_str = format_size(new_val, readable)
            delta_str = format_size(delta_val, readable)
            delta_pct = f"{(delta_val / old_val) * 100:.2f}%" if old_val else "-"
            f.write(f"| {g} | {old_str} | {new_str} | {delta_str} | {delta_pct} |\n")

def print_console_diff(summary, mode, readable=False):
    print(f"[{mode.upper()}] Diff Results:")
    for g, vals in summary.items():
        old_total, new_total, delta_total = vals['old_total'], vals['new_total'], vals['delta_total']
        pct_str = f"{(delta_total / old_total) * 100:+.2f}%" if old_total else "-"
        print(f"  {g:15s} {format_size(old_total, readable):>8} → {format_size(new_total, readable):>8} "
              f"({format_size(delta_total, readable)} / {pct_str})")

def get_top_files(diff_res, group_name):
    files_info = []
    for relpath, groups in diff_res.items():
        if group_name not in groups:
            continue
        vals = groups[group_name]
        old_t, new_t = vals["old_total"], vals["new_total"]
        delta_t = vals["delta_total"]
        status = "Common" if old_t and new_t else ("Removed" if old_t else "Added")
        delta_pct = (delta_t / old_t) * 100 if old_t else 0
        files_info.append({
            "STATUS": status, "RelativeDir": os.path.dirname(relpath) or ".",
            "Filename": os.path.basename(relpath), "OldSize": old_t,
            "NewSize": new_t, "Diff": delta_t, "DiffPct": delta_pct
        })
    return files_info

def write_top_n_files_md(path, group_files_map, readable=False, mode_name=None):
    with open(path, "w", encoding="utf-8") as f:
        if mode_name:
            f.write(f"# Top-N Files Report - Mode: {mode_name}\n\n")
        for group, files in group_files_map.items():
            f.write(f"## Group: {group}\n\n")
            f.write("| STATUS | Relative directory | Filename | Old size | New size | Diff | Diff% |\n")
            f.write("|--------|--------------------|----------|----------|----------|------|-------|\n")
            for fi in files:
                f.write(f"| {fi['STATUS']} | {fi['RelativeDir']} | {fi['Filename']} | "
                        f"{format_size(fi['OldSize'], readable)} | {format_size(fi['NewSize'], readable)} | "
                        f"{format_size(fi['Diff'], readable)} | {fi['DiffPct']:+.2f}% |\n")
            f.write("\n")
if USE_REGEX:
    def assign_group(mode, section_name):
        for g, names in KNOWN_GROUPS[mode].items():
            if section_name in names and g != 'EXCLUDE':
                return g
        if USE_REGEX:
            for g, patterns in KNOWN_RULES.get(mode, {}).items():
                for pat in patterns:
                    if re.match(pat, section_name) and g != 'EXCLUDE':
                        return g
        return 'no'  # Default group if no match found


def get_group_name(sec, mode, exclude_secs, group_rule=None, debug=False):
    """Determine the group name of a section based on mode rules and group rules."""
    name = sec.name
    flags = int(sec['sh_flags'])
    execi = bool(flags & SH_FLAGS.SHF_EXECINSTR)
    alloc = bool(flags & SH_FLAGS.SHF_ALLOC)
    write = bool(flags & SH_FLAGS.SHF_WRITE)

    # ? do we need ? handle input from command line
    if name in exclude_secs:
        return "EXCLUDE"

    if name == None:
        return "EXCLUDE"

    if USE_REGEX:
        if True:
            preDefinedName=assign_group(mode, name)
            if preDefinedName != 'no':
                return preDefinedName

    if group_rule:
        for group, secset in group_rule.items():
            if group != "EXCLUDE" and name in secset:
                return group
            # if name in group_rule.get("EXCLUDE", set()):
            #     return "EXCLUDE"

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
        clean_name = name[1:] if name.startswith(".") else name
        return clean_name.upper()
    elif mode == "custom":
        if name.startswith('.gnu'):
            return "GNU"
        if re.search(r"dyn",name):
            return "DYNAMIC"
        if name.startswith('.note'):
            return "GNU"
        if execi:
            return "TEXT"
        elif alloc:
            if write and is_bss_section(sec):
                return "BSS"
            else:
                return "DATA"
        else:
            clean_name = name[1:] if name.startswith(".") else name
            return clean_name.upper()
    return "OTHERS"

def analyze_directory(directory, mode, exclude_secs, debug=False):
    """Analyze all ELF files in directory, collect sections info grouped by mode."""
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

                        # group classification
                        group = get_group_name(
                            sec, mode, exclude_secs,
                            KNOWN_GROUPS.get(mode),
                            debug
                        )

                        gmap[group][sec.name] = {
                            'size': sz,
                            'type_name': tname,
                            'flags': sh_flags_val
                        }

                        pt_flags_val, mapping_pass = get_segment_flags_and_mapping(elf, sec)
                        mode_rules_dict[mode][group].add(
                            (sec.name, pt_flags_val, sh_flags_val, tname, mapping_pass)
                        )
                    results[relpath] = gmap
            except Exception as e:
                    if debug:
                        # ✅ 디버그 모드에서는 즉시 확인 & 종료
                        raise
                    else:
                        print(f"[WARN] Failed to parse {path}: {e}")
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

# def summarize_group_totals(diff_res):
#     """Aggregate totals by group from per-file diffs."""
#     summ = defaultdict(lambda: {'old_total':0, 'new_total':0, 'delta_total':0})
#     for _, gm in diff_res.items():
#         for g, v in gm.items():
#             summ[g]['old_total'] += v['old_total']
#             summ[g]['new_total'] += v['new_total']
#             summ[g]['delta_total'] += v['delta_total']
#     return dict(summ)


def write_mode_rules_md(output_dir):
    """Write classification rule tables for each mode to markdown files."""
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
                mpass_str = "; ".join(sorted({"✔" if e[4] else "✖" for e in entries}))
                f.write(f"| {group} | {secs} | {pt_flags_str} | {sh_flags_str} | {sh_types_str} | {mpass_str} |\n")
            # Legends
            pt_items = [f"0x{bit:X}={desc}" for bit, desc in PT_FLAGS_MEANING.items()]
            sh_items = [f"0x{bit:X}={desc}" for bit, desc in SH_FLAGS_MEANING.items()]
            f.write("\n### PT_FLAGS Legend\n" + ", ".join(pt_items) + "\n")
            f.write("### SH_FLAGS Legend\n" + ", ".join(sh_items) + "\n\n")
        print(f"[INFO] Saved mode_rules table for '{mode}' to {path}")

def print_console_diff(summary, mode, readable=False):
    """Print group diff results to console with optional human-readable format."""
    print(f"[{mode.upper()}] Diff Results:")
    for group, vals in summary.items():
        old_total = vals['old_total']
        new_total = vals['new_total']
        delta_total = vals['delta_total']

        if old_total != 0:
            delta_pct = (delta_total / old_total) * 100
            pct_str = f"{delta_pct:+.2f}%"
        else:
            pct_str = "-"

        print(f"  {group:15s} "
              f"{format_size(old_total, readable):>8} → {format_size(new_total, readable):>8} "
              f"({format_size(delta_total, readable)} / {pct_str})")

# =========================
# Main CLI Handling
# =========================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("old_dir"); parser.add_argument("new_dir")
    parser.add_argument("--mode", choices=list(KNOWN_GROUPS.keys())+["all"], default="berkeley")
    parser.add_argument("--exclude-sections", default="")
    parser.add_argument("--readable", action="store_true")
    parser.add_argument("--top-n-groups", default="all")
    parser.add_argument("--top-n-files", type=int, default=10)
    parser.add_argument("--sort-group-by",default="+-diff",
                    help="Group sort method; supports patterns like 'TEXT,DATA:+diff'")
    parser.add_argument("--sort-file-by", default="+-diff",
        choices=["abs_diff","+diff","-diff","abs_diff_pct","+diff_pct","-diff_pct",
                 "++diff","--diff","+-diff","-+diff","++diff_pct","--diff_pct","+-diff_pct","-+diff_pct"])
    parser.add_argument("--top-n-files-mode", default="custom",
        help='Comma-separated list of modes for which to output top-N file reports. "all" = all modes.')
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--output-prefix", default="")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--plot-exclude-groups", default="")
    parser.add_argument("--common-files", action='store_true',default=True, help="Compare only common files in old and new directories")

    args = parser.parse_args()

    valid_modes = set(KNOWN_GROUPS.keys()) | {"all"}
    selected_modes_for_files = [
        m.strip() for m in args.top_n_files_mode.split(',')
        if m.strip() in valid_modes
    ]
    if not selected_modes_for_files:
        selected_modes_for_files = None
    # all?
    generate_files_for_all_modes = (
        selected_modes_for_files is not None and "all" in selected_modes_for_files
            )

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    exclude_secs = [s.strip() for s in args.exclude_sections.split(',')] if args.exclude_sections else []
    if args.mode != "all":
        modes = [args.mode]
    else:
        modes = list(KNOWN_GROUPS.keys())

    old_res_dict = {}
    new_res_dict = {}
    for mode in modes:
        old_res = analyze_directory(args.old_dir, mode, exclude_secs, args.debug)
        new_res = analyze_directory(args.new_dir, mode, exclude_secs, args.debug)
        if args.common_files:
            common_files = set(old_res) & set(new_res)
            old_res = {k: v for k, v in old_res.items() if k in common_files}
            new_res = {k: v for k, v in new_res.items() if k in common_files}
        old_res_dict[mode] = old_res
        new_res_dict[mode] = new_res

        diff = compare_results(old_res_dict[mode], new_res_dict[mode])
        summary = summarize_group_totals(diff,mode)


        # 📌 summary 보고서 저장
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            generate_md_report(
                os.path.join(args.output_dir, f"{args.output_prefix}report_{mode}.md"),
                mode, summary, readable=args.readable, args=args
            )

        # 📌 sort-group-by 해석 + 필터 적용
        group_filter, group_sort_key = parse_sort_by_option(args.sort_group_by)
        items = [(g, v) for g, v in summary.items() if not group_filter or g in group_filter]

        group_sort_results = handle_sort_pair_option(
            # args.sort_group_by,
            # list(summary.items()),
            # int(args.top_n_groups) if args.top_n_groups != "all" else len(summary),
            # is_group=True
            group_sort_key, items,
            int(args.top_n_groups) if args.top_n_groups != "all" else len(items),
            is_group=True

        )

        for sort_key, group_list in group_sort_results:
            print(f"\n[Top {len(group_list)} groups by {sort_key}]")
            print_console_diff(dict(group_list), mode, readable=args.readable)
            # selected_modes_for_files 이 None이면 전부 건너뜀
            if (
                selected_modes_for_files is None or
                (
                    not generate_files_for_all_modes and
                    mode not in selected_modes_for_files
                )
            ):
                continue  # 이번 모드에서 Top-N 파일 생성 안 함

            for g, _ in group_list:
                files_for_group = get_top_files(diff, g)
                file_sort_results = handle_sort_pair_option(
                    args.sort_file_by, files_for_group, args.top_n_files, is_group=False
                )
                for f_sort_key, file_list in file_sort_results:
                    if args.output_dir:
                        out_fn = f"{args.output_prefix}top_{args.top_n_files}_files_{mode}_{g}_{f_sort_key}.md"
                        write_top_n_files_md(
                            os.path.join(args.output_dir, out_fn),
                            {g: file_list}, readable=args.readable, mode_name=mode
                        )
        # Print diff results to console
        # print_console_diff(summary, mode, readable=args.readable)
        # # Print summary line per group in legacy tab-separated format (optional)
        # for g, vals in summary.items():
        #     print(f"{mode}\t{g}\told={vals['old_total']}\tnew={vals['new_total']}\tΔ={vals['delta_total']}")

        # Generate Markdown report
        # if args.output_dir:
        #     os.makedirs(args.output_dir, exist_ok=True)
        #     generate_md_report(os.path.join(args.output_dir, f"{args.output_prefix}report_{mode}.md"), mode, summary, readable=args.readable)

    if args.output_dir:
        write_mode_rules_md(args.output_dir)
