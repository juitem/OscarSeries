#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, argparse
from collections import defaultdict
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS, P_FLAGS

# ===== TYPE NAMES =====
SHT_TYPE_NAMES = {0: 'SHT_NULL', 1: 'SHT_PROGBITS', 8: 'SHT_NOBITS'}
SHT_NAME_TO_CODE = {v: k for k, v in SHT_TYPE_NAMES.items()}

# ===== KNOWN GROUPS PLACEHOLDER =====
KNOWN_GROUPS = {
    'berkeley': {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'RODATA': set(),
                 'EXCLUDE': set(), 'OTHERS': set()},
    'gnu': {'TEXT': set(), 'DATA': set(), 'BSS': set(), 'RODATA': set(),
            'EXCLUDE': set(), 'OTHERS': set()},
    'sysv': {'EXCLUDE': set(), 'OTHERS': set()}
}

# ===== UTIL =====
def human_readable_size(num):
    for unit in ['B','K','M','G']:
        if abs(num) < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}T"

def extract_type_info(section):
    tcode = section['sh_type']
    tname = SHT_TYPE_NAMES.get(tcode, 'UNKNOWN')
    return tcode, tname

# ===== GROUP NAME LOGIC =====
def berkeley_group_from_pt_load(elf, sec):
    """Improved PT_LOAD based classification: check file offset and virtual addr."""
    sh_type = sec['sh_type']
    sec_offset = sec['sh_offset']
    sec_addr = sec['sh_addr']
    for seg in elf.iter_segments():
        if seg['p_type'] == 'PT_LOAD':
            start = seg['p_offset']
            end = seg['p_offset'] + seg['p_filesz']
            mem_start = seg['p_vaddr']
            mem_end = seg['p_vaddr'] + seg['p_memsz']
            if (start <= sec_offset < end) or (mem_start <= sec_addr < mem_end):
                flags = seg['p_flags']
                if flags & P_FLAGS.PF_X:
                    return "TEXT"
                elif flags & P_FLAGS.PF_W:
                    return "BSS" if sh_type == SHT_NAME_TO_CODE['SHT_NOBITS'] else "DATA"
                else:
                    return "DATA"
    return "OTHERS"

def get_group_name(sec, mode, custom_secs, group_rule):
    sec_name = sec.name
    sh_type = sec['sh_type']
    sh_flags = int(sec['sh_flags'])
    base_group = None
    custom_group = None

    # Custom parallel group
    if custom_secs:
        for cs in custom_secs:
            if sec_name.startswith(cs):
                custom_group = cs.upper()

    # Mode-specific base group
    if mode == "berkeley":
        base_group = berkeley_group_from_pt_load(sec.elffile, sec)
    elif mode == "gnu":
        exec_instr = bool(sh_flags & SH_FLAGS.SHF_EXECINSTR)
        alloc = bool(sh_flags & SH_FLAGS.SHF_ALLOC)
        write = bool(sh_flags & SH_FLAGS.SHF_WRITE)
        if exec_instr:
            base_group = "TEXT"
        elif alloc and write:
            base_group = "BSS" if sh_type == SHT_NAME_TO_CODE['SHT_NOBITS'] else "DATA"
        elif alloc and not write:
            base_group = "RODATA"
        else:
            base_group = "OTHERS"
    elif mode == "sysv":
        dbg_meta = {'.stab', '.stabstr', '.comment'}
        if sec_name.startswith('.gnu.warning'):
            base_group = 'WARNINGS'
        elif sec_name in dbg_meta:
            base_group = 'DEBUG_META'
        else:
            base_group = sec_name[1:].upper() if sec_name.startswith('.') else sec_name.upper()
    elif mode == "custom":
        base_group = None
    else:
        base_group = "OTHERS"

    # KNOWN_GROUPS override
    if group_rule and mode in ("berkeley", "gnu", "sysv"):
        for group, secset in group_rule.items():
            if group == "EXCLUDE":
                continue
            if sec_name in secset:
                base_group = group
        if sec_name in group_rule.get("EXCLUDE", set()):
            base_group = "EXCLUDE"

    # Fallback
    if base_group is None and mode != "custom":
        exec_instr = bool(sh_flags & SH_FLAGS.SHF_EXECINSTR)
        alloc = bool(sh_flags & SH_FLAGS.SHF_ALLOC)
        write = bool(sh_flags & SH_FLAGS.SHF_WRITE)
        if exec_instr:
            base_group = "TEXT"
        elif alloc and write:
            base_group = "BSS" if sh_type == SHT_NAME_TO_CODE['SHT_NOBITS'] else "DATA"
        elif alloc and not write:
            base_group = "RODATA"
        else:
            base_group = "OTHERS"

    return base_group, custom_group

# ===== ANALYSIS =====
def analyze_directory(directory, mode, custom_secs, debug=False):
    results = {}
    found_any = False
    total_files = 0
    parsed_files = 0
    for root, _, files in os.walk(directory):
        for fn in files:
            total_files += 1
            path = os.path.join(root, fn)
            try:
                with open(path, 'rb') as f:
                    elf = ELFFile(f)
                    parsed_files += 1
                    group_rule = KNOWN_GROUPS.get(mode)
                    gdata = defaultdict(dict)
                    for sec in elf.iter_sections():
                        tcode, tname = extract_type_info(sec)
                        fl = int(sec['sh_flags'])
                        sz = sec['sh_size']
                        base_group, custom_group = get_group_name(sec, mode, custom_secs, group_rule)
                        if debug:
                            print(f"[SEC] {sec.name} size={sz} flags=0x{fl:X} -> base_group={base_group} custom_group={custom_group}")
                        if base_group:
                            gdata[base_group][sec.name] = {'size': sz, 'type_code': tcode, 'type_name': tname, 'flags': fl}
                        if custom_group:
                            gdata[custom_group][sec.name] = {'size': sz, 'type_code': tcode, 'type_name': tname, 'flags': fl}
                        found_any = True
                    results[path] = gdata
            except Exception as e:
                if debug:
                    print(f"[WARN] ELF parse failed for {path}: {e}")
                continue
    if debug:
        print(f"[DEBUG] Total files: {total_files}, Parsed ELF: {parsed_files}, Classified any section: {found_any}")
    return results

def compare_results(old_res,new_res):
    diff = {}
    for fp in new_res:
        if fp in old_res:
            fd = {}
            for g in set(old_res[fp])|set(new_res[fp]):
                old_total = sum(s['size'] for s in old_res[fp].get(g,{}).values())
                new_total = sum(s['size'] for s in new_res[fp].get(g,{}).values())
                fd[g]={'old_total':old_total,'new_total':new_total,'delta_total':new_total-old_total}
            diff[fp]=fd
    return diff

def summarize_group_totals(diff_res):
    summary = defaultdict(lambda:{'old_total':0,'new_total':0,'delta_total':0})
    for _, gm in diff_res.items():
        for g, v in gm.items():
            summary[g]['old_total'] += v['old_total']
            summary[g]['new_total'] += v['new_total']
            summary[g]['delta_total'] += v['delta_total']
    return dict(summary)

# ===== REPORT =====
def format_group_section_table(rows, readable=False, markdown=False):
    grouped = defaultdict(lambda: {"sections": [], "type": None, "flags": None})
    for g, sec, tname, flags in rows:
        grouped[g]["sections"].append(sec)
        if grouped[g]["type"] is None:
            grouped[g]["type"] = tname
        if grouped[g]["flags"] is None:
            grouped[g]["flags"] = flags
    if markdown:
        lines = ["| Group | Sections | Type Name | Flags |","|-------|----------|-----------|-------|"]
    else:
        lines = ["Group   | Sections | Type Name     | Flags","-"*70]
    for g, info in grouped.items():
        sec_str = ", ".join(sorted(info["sections"]))
        t_str = info["type"] or ""
        f_val = info["flags"] or 0
        flag_names = []
        if f_val & SH_FLAGS.SHF_WRITE: flag_names.append("WRITE")
        if f_val & SH_FLAGS.SHF_ALLOC: flag


def format_group_section_table(rows, readable=False, markdown=False):
    grouped = defaultdict(lambda: {"sections": [], "type": None, "flags": None})
    for g, sec, tname, flags in rows:
        grouped[g]["sections"].append(sec)
        if grouped[g]["type"] is None:
            grouped[g]["type"] = tname
        if grouped[g]["flags"] is None:
            grouped[g]["flags"] = flags
    if markdown:
        lines = ["| Group | Sections | Type Name | Flags |",
                 "|-------|----------|-----------|-------|"]
    else:
        lines = ["Group   | Sections | Type Name     | Flags","-"*70]
    for g, info in grouped.items():
        sec_str = ", ".join(sorted(info["sections"]))
        t_str = info["type"] or ""
        f_val = info["flags"] or 0
        flag_names = []
        if f_val & SH_FLAGS.SHF_WRITE: flag_names.append("WRITE")
        if f_val & SH_FLAGS.SHF_ALLOC: flag_names.append("ALLOC")
        if f_val & SH_FLAGS.SHF_EXECINSTR: flag_names.append("EXECUTE")
        if f_val & SH_FLAGS.SHF_MERGE: flag_names.append("MERGE")
        if f_val & SH_FLAGS.SHF_STRINGS: flag_names.append("STRINGS")
        flag_str = "|".join(flag_names) + f"(0x{f_val:X})" if flag_names else f"(0x{f_val:X})"
        if markdown:
            lines.append(f"| {g} | {sec_str} | {t_str} | {flag_str} |")
        else:
            lines.append(f"{g:7} | {sec_str} | {t_str:13} | {flag_str}")
    return "\n".join(lines)

def format_top_groups_table(summary, readable=False, markdown=False):
    if markdown:
        lines=["| Group | Old | New | Delta | % |","|---|---|---|---|---|"]
        for g,d in summary.items():
            ot = human_readable_size(d['old_total']) if readable else str(d['old_total'])
            nt = human_readable_size(d['new_total']) if readable else str(d['new_total'])
            dt = human_readable_size(d['delta_total']) if readable else str(d['delta_total'])
            perc = (d['delta_total']/d['old_total']*100) if d['old_total'] else 0.0
            lines.append(f"| {g} | {ot} | {nt} | {dt} | {perc:.1f}% |")
    else:
        lines=["==== TOP-N GROUPS TABLE ====",
               f"{'Group':15}{'Old':>10}{'New':>10}{'Delta':>10}  %"]
        for g,d in summary.items():
            ot = human_readable_size(d['old_total']) if readable else str(d['old_total'])
            nt = human_readable_size(d['new_total']) if readable else str(d['new_total'])
            dt = human_readable_size(d['delta_total']) if readable else str(d['delta_total'])
            perc = (d['delta_total']/d['old_total']*100) if d['old_total'] else 0.0
            lines.append(f"{g:15}{ot:>10}{nt:>10}{dt:>10}  ({perc:.1f}%)")
    return "\n".join(lines)

def save_report_files(basepath, prefix, mode, summary_txt, summary_md):
    os.makedirs(basepath, exist_ok=True)
    with open(os.path.join(basepath, f"{prefix}{mode}_summary.md"), 'w', encoding='utf-8') as f:
        f.write(summary_md)
    with open(os.path.join(basepath, f"{prefix}{mode}_summary.txt"), 'w', encoding='utf-8') as f:
        f.write(summary_txt)

def build_report(table_rows, group_summary, args, markdown=False):
    parts = []
    parts.append(f"**Sort key:** {args.sort_key} | **Order:** {'Ascending' if args.ascending else 'Descending'}\n" if markdown
                 else f"Sort key: {args.sort_key} | Order: {'Ascending' if args.ascending else 'Descending'}\n")
    parts.append("## Section Group classification rule\n" if markdown else "\n== Section Group classification rule ==")
    parts.append(format_group_section_table(table_rows, args.readable, markdown))
    parts.append("\n---\n## Top-N Groups Table\n" if markdown else "\n== Top-N Groups Table ==")
    parts.append(format_top_groups_table(group_summary, args.readable, markdown))
    return "\n".join(parts)

if __name__=="__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("old_dir"); ap.add_argument("new_dir")
    ap.add_argument("--mode", choices=["berkeley","gnu","sysv","custom","all"], default="berkeley")
    ap.add_argument("--custom-sections", dest="custom_sections", type=str)
    ap.add_argument("--readable", action="store_true")
    ap.add_argument("--top-n-groups", type=int, default=5)
    ap.add_argument("--sort-key", choices=["abs_diff","diff","abs_perc","perc"], default="abs_diff")
    ap.add_argument("--ascending", action="store_true")
    ap.add_argument("--output-dir", help="Directory to save reports")
    ap.add_argument("--output-prefix", default="", help="Prefix for output file names")
    args = ap.parse_args()

    descending = not args.ascending
    custom_secs = [s.strip() for s in args.custom_sections.split(',')] if args.custom_sections else []
    modes = [args.mode] if args.mode != "all" else ["berkeley","gnu","sysv"]
    if args.mode=="all" and custom_secs: modes.append("custom")

    for mode in modes:
        old_res = analyze_directory(args.old_dir, mode, custom_secs)
        new_res = analyze_directory(args.new_dir, mode, custom_secs)
        diff_res = compare_results(old_res, new_res)
        summary = summarize_group_totals(diff_res)
        sorted_summary = dict(sorted(
            summary.items(),
            key=lambda x: abs(x[1]['delta_total']) if args.sort_key=="abs_diff" else x[1]['delta_total'],
            reverse=descending
        )[:args.top_n_groups])

        # Section group rule 상세 표
        table_rows = []
        for g in sorted_summary:
            secs_meta = {}
            for fp, groups in new_res.items():
                if g in groups:
                    secs_meta.update({s: m for s, m in groups[g].items()})
            for s, meta in secs_meta.items():
                table_rows.append((g, s, meta['type_name'], meta['flags']))

        summary_txt = build_report(table_rows, sorted_summary, args, markdown=False)
        summary_md = build_report(table_rows, sorted_summary, args, markdown=True)

        print(f"\n=== MODE: {mode.upper()} ===")
        print(summary_txt)

        if args.output_dir:
            save_report_files(args.output_dir, args.output_prefix, mode, summary_txt, summary_md)
