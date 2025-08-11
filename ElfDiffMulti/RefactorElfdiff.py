#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, argparse
from collections import defaultdict
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS

# -----------------------------------
# -----------------------------------

SHT_TYPE_NAMES = {
    0:'SHT_NULL',1:'SHT_PROGBITS',2:'SHT_SYMTAB',3:'SHT_STRTAB',
    4:'SHT_RELA',5:'SHT_HASH',6:'SHT_DYNAMIC',7:'SHT_NOTE',
    8:'SHT_NOBITS',9:'SHT_REL',10:'SHT_SHLIB',11:'SHT_DYNSYM',
    0x6ffffff0: 'SHT_GNU_INCREMENTAL_INPUTS', 0x6ffffff1: 'SHT_GNU_ATTRIBUTES',
    0x6ffffff2: 'SHT_GNU_HASH', 0x6ffffff3: 'SHT_GNU_LIBLIST',
    0x6ffffff4: 'SHT_CHECKSUM', 0x6ffffff5: 'SHT_SUNW_move',
    0x6ffffff6: 'SHT_SUNW_COMDAT', 0x6ffffff7: 'SHT_SUNW_syminfo',
    0x6ffffffd: 'SHT_GNU_VERDEF', 0x6ffffffe: 'SHT_GNU_VERNEED',
    0x6fffffff: 'SHT_GNU_VERSYM',
    0x60000000: 'SHT_LOOS', 0x70000000: 'SHT_LOPROC',
    0x7fffffff: 'SHT_HIPROC', 0x80000000: 'SHT_LOUSER', 0xffffffff: 'SHT_HIUSER'
}
SHT_NAME_TO_CODE = {v:k for k,v in SHT_TYPE_NAMES.items()}
KNOWN_GROUPS = {
    'berkeley':{'TEXT':{'.text','.init','.fini'},'DATA':{'.data','.rodata'},'BSS':{'.bss'},
                'EXCLUDE':{'.comment','.symtab','.strtab'},'OTHERS':set()},
    'gnu':{'TEXT':{'.text','.init','.fini'},'DATA':{'.data','.rodata'},'BSS':{'.bss'},
           'EH_FRAME':{'.eh_frame','.eh_frame_hdr'},
           'DEBUG':{'.debug_info','.debug_abbrev','.debug_line','.debug_str'},
           'GNU_VERSION':{'.gnu.version','.gnu.version_d','.gnu.version_r'},
           'EXCLUDE':set(),'OTHERS':set()},
    'sysv':{},'custom':None
}

def format_group_name(g): return g.upper().lstrip('.')
def human_readable_size(sz):
    if not isinstance(sz,(int,float)): return str(sz)
    if sz == 0: return "0B"
    units=['B','K','M','G','T']; idx=0; val=float(sz)
    while val >= 1024 and idx < len(units)-1:
        val /= 1024; idx+=1
    return f"{val:.1f}{units[idx]}"

def list_elf_files(directory):
    files=[]
    for root,_,fnames in os.walk(directory):
        for fn in fnames:
            path=os.path.join(root,fn)
            if os.path.islink(path): continue
            try:
                with open(path,'rb') as fd:
                    if fd.read(4)==b'\x7fELF':
                        files.append(path)
            except: continue
    return files

def extract_type_info(sec):
    raw=sec['sh_type']
    if isinstance(raw,int): return raw,SHT_TYPE_NAMES.get(raw,f"UNKNOWN(0x{raw:08X})")
    elif isinstance(raw,str): return SHT_NAME_TO_CODE.get(raw,-1),raw
    return -1,"UNKNOWN"

def categorize_section_by_flags(sec):
    fl=sec['sh_flags']; _,tn=extract_type_info(sec)
    if fl & SH_FLAGS.SHF_EXECINSTR: return 'TEXT'
    elif (fl & SH_FLAGS.SHF_ALLOC) and not(fl & SH_FLAGS.SHF_EXECINSTR) and tn!='SHT_NOBITS': return 'DATA'
    elif tn=='SHT_NOBITS': return 'BSS'
    return None

def get_grouped_sizes(elf, mode, custom_sections=None):
    if mode=='custom':
        g={'CUSTOM':{}}
        for s in custom_sections or []:
            sec=elf.get_section_by_name(s)
            if sec:
                tc,tn=extract_type_info(sec)
                g['CUSTOM'][s]={'size':sec['sh_size'],'type_code':tc,'type_name':tn,'flags':int(sec['sh_flags'])}
        return g
    if mode=='sysv':
        g=defaultdict(dict); dbg_meta={'.stab','.stabstr','.comment'}
        for sec in elf.iter_sections():
            tc,tn=extract_type_info(sec); fl=int(sec['sh_flags'])
            grp='WARNINGS' if sec.name.startswith('.gnu.warning') else ('DEBUG_META' if sec.name in dbg_meta else sec.name)
            if sec.name not in g[grp]:
                g[grp][sec.name]={'size':0,'type_code':tc,'type_name':tn,'flags':fl}
            g[grp][sec.name]['size'] += sec['sh_size']
        return dict(g)
    gdef=KNOWN_GROUPS[mode]; g={k:{} for k in gdef}
    for sec in elf.iter_sections():
        tc,tn=extract_type_info(sec); fl=int(sec['sh_flags']); sz=sec['sh_size']
        if sec.name in gdef.get('EXCLUDE',set()):
            g['EXCLUDE'][sec.name]={'size':sz,'type_code':tc,'type_name':tn,'flags':fl}; continue
        grp_auto=categorize_section_by_flags(sec); assigned=False
        if grp_auto and grp_auto in g:
            g[grp_auto][sec.name]={'size':sz,'type_code':tc,'type_name':tn,'flags':fl}; assigned=True
        else:
            for gr,secset in gdef.items():
                if gr in ('OTHERS','EXCLUDE'): continue
                if sec.name in secset:
                    g[gr][sec.name]={'size':sz,'type_code':tc,'type_name':tn,'flags':fl}; assigned=True; break
        if not assigned:
            g['OTHERS'][sec.name]={'size':sz,'type_code':tc,'type_name':tn,'flags':fl}
    return {k:v for k,v in g.items() if v}

def analyze_directory(directory, mode, custom_sections=None):
    res={}; base=os.path.abspath(directory)
    for fp in list_elf_files(directory):
        rel=os.path.relpath(fp, base)
        try:
            with open(fp,'rb') as f:
                elf=ELFFile(f)
                res[rel]=get_grouped_sizes(elf, mode, custom_sections)
        except Exception as e:
            res[rel]={'error':str(e)}
    return res

def compare_results(old_res, new_res):
    """
    Compare group totals between old and new results.
    Returns per-file mapping of group differences with only totals.
    """
    diff = {}
    for filepath in new_res:
        if filepath in old_res:
            old_groups = old_res[filepath]
            new_groups = new_res[filepath]
            file_diff = {}
            for gname in set(old_groups.keys()).union(new_groups.keys()):
                old_total = sum(sec['size'] for sec in old_groups.get(gname, {}).values())
                new_total = sum(sec['size'] for sec in new_groups.get(gname, {}).values())
                file_diff[gname] = {
                    'old_total': old_total,
                    'new_total': new_total,
                    'delta_total': new_total - old_total
                }
            diff[filepath] = file_diff
    return diff


def summarize_group_totals(diff_results):
    summ={}
    for _,groups in diff_results.items():
        for g,gdata in groups.items():
            if g not in summ:
                summ[g]={'old_total':0,'new_total':0,'delta_total':0}
            summ[g]['old_total']+=gdata['total_old']
            summ[g]['new_total']+=gdata['total_new']
            summ[g]['delta_total']+=gdata['total_delta']
    return summ

# -----------------------------------
# 표 작성 관련
# -----------------------------------

def build_group_section_info(group_data):
    rows=[]
    for g, sections in group_data.items():
        for sec_name, meta in sections.items():
            rows.append((format_group_name(g), sec_name, meta['type_name'], f"0x{meta['flags']:X}"))
    return rows

def format_group_section_table_one_line(rows, markdown=False):
    """
    Build a group classification table (one line per group).
    Includes section list, type name, and detailed flags (names + hex value).
    """
    from collections import defaultdict

    # Group  sections list, type name, and flags
    grouped = defaultdict(lambda: {"sections": [], "type": None, "flags": None})
    for g, sec, tname, flags in rows:
        grouped[g]["sections"].append(sec)
        if grouped[g]["type"] is None:
            grouped[g]["type"] = tname
        if grouped[g]["flags"] is None:
            grouped[g]["flags"] = flags

    # Table header
    if markdown:
        lines = ["| Group | Sections | Type Name | Flags |",
                 "|-------|----------|-----------|-------|"]
    else:
        lines = ["Group   | Sections | Type Name     | Flags",
                 "-" * 70]

    # Build each row
    for g, info in grouped.items():
        sec_str = ", ".join(sorted(info["sections"]))
        t_str = info["type"] or ""

        # Get raw flags value
        f_str = info["flags"] or ""

        # Try decoding flag numeric value
        try:
            if isinstance(f_str, str) and f_str.startswith("0x"):
                flag_val = int(f_str, 16)
            else:
                flag_val = int(f_str, 0)

            # Collect human-readable names
            flag_names = []
            if flag_val & SH_FLAGS.SHF_WRITE:
                flag_names.append("WRITE")
            if flag_val & SH_FLAGS.SHF_ALLOC:
                flag_names.append("ALLOC")
            if flag_val & SH_FLAGS.SHF_EXECINSTR:
                flag_names.append("EXECUTE")
            if flag_val & SH_FLAGS.SHF_MERGE:
                flag_names.append("MERGE")
            if flag_val & SH_FLAGS.SHF_STRINGS:
                flag_names.append("STRINGS")
            if flag_val & SH_FLAGS.SHF_INFO_LINK:
                flag_names.append("INFO_LINK")
            if flag_val & SH_FLAGS.SHF_LINK_ORDER:
                flag_names.append("LINK_ORDER")
            if flag_val & SH_FLAGS.SHF_OS_NONCONFORMING:
                flag_names.append("OS_NONCONF")
            if flag_val & SH_FLAGS.SHF_GROUP:
                flag_names.append("GROUP")
            if flag_val & SH_FLAGS.SHF_TLS:
                flag_names.append("TLS")

            # Always append hex value without space before parentheses
            if flag_names:
                flag_str = "|".join(flag_names) + f"(0x{flag_val:X})"
            else:
                flag_str = f"(0x{flag_val:X})"

        except Exception:
            # Fallback to raw string if conversion fails
            flag_str = str(f_str)

        # Append line depending on format
        if markdown:
            lines.append(f"| {g} | {sec_str} | {t_str} | {flag_str} |")
        else:
            lines.append(f"{g:7} | {sec_str} | {t_str:13} | {flag_str}")

    return "\n".join(lines)

def format_group_sections_only_table(group_sections_map, markdown=False):
    if markdown:
        lines = ["| Group | Sections |","|-------|----------|"]
    else:
        lines = ["Group   | Sections","-"*50]
    for g, sections in group_sections_map.items():
        sec_str = ", ".join(sorted(sections))
        if markdown: lines.append(f"| {format_group_name(g)} | {sec_str} |")
        else: lines.append(f"{format_group_name(g):7} | {sec_str}")
    return "\n".join(lines)

def sort_groups(summary, sort_key='abs_diff', descending=True, limit=None):
    def get_key(item):
        g, d = item
        if sort_key == 'abs_diff':
            return abs(d['delta_total'])
        elif sort_key == 'abs_perc':
            return abs((d['delta_total'] / d['old_total'] * 100) if d['old_total'] else 0.0)
        elif sort_key == 'diff':
            return d['delta_total']
        elif sort_key == 'perc':
            return (d['delta_total'] / d['old_total'] * 100) if d['old_total'] else 0.0
    sorted_items = sorted(summary.items(), key=get_key, reverse=descending)
    if limit: sorted_items = sorted_items[:limit]
    return dict(sorted_items)

def format_top_groups_table(summary, readable=False, markdown=False):
    """
    Top-N Groups Table
    markdown=True  -> Markdown table format
    markdown=False -> Text table format
    """
    if markdown:
        lines = ["| Group | Old Total | New Total | Delta | % |",
                 "|-------|-----------|-----------|-------|---|"]
        for g, data in summary.items():
            ot = human_readable_size(data['old_total']) if readable else str(data['old_total'])
            nt = human_readable_size(data['new_total']) if readable else str(data['new_total'])
            dt = human_readable_size(data['delta_total']) if readable else str(data['delta_total'])
            perc = (data['delta_total'] / data['old_total'] * 100) if data['old_total'] else 0.0
            lines.append(f"| {format_group_name(g)} | {ot} | {nt} | {dt} | {perc:.1f}% |")
        return "\n".join(lines)
    else:
        lines = ["==== TOP-N GROUPS TABLE ===="]
        lines.append(f"{'Group':20} {'Old':>10} {'New':>10} {'Delta':>10}  %")
        for g, data in summary.items():
            ot = human_readable_size(data['old_total']) if readable else str(data['old_total'])
            nt = human_readable_size(data['new_total']) if readable else str(data['new_total'])
            dt = human_readable_size(data['delta_total']) if readable else str(data['delta_total'])
            perc = (data['delta_total'] / data['old_total'] * 100) if data['old_total'] else 0.0
            lines.append(f"{format_group_name(g):20} {ot:>10} {nt:>10} {dt:>10}  ({perc:.1f}%)")
        return "\n".join(lines) + "\n"


def format_group_total_summary_table(summary, group_sections_map, readable=False, markdown=False):
    sorted_items = sorted(summary.items(), key=lambda x: x[1]['delta_total'], reverse=True)
    if markdown:
        lines=["| Group | Old Total | New Total | Delta | % | Sections |",
               "|-------|-----------|-----------|-------|----|----------|"]
    else:
        lines=["Group   | Old Total | New Total | Delta     |    %   | Sections",
               "-"*90]
    for g, data in sorted_items:
        ot=human_readable_size(data['old_total']) if readable else str(data['old_total'])
        nt=human_readable_size(data['new_total']) if readable else str(data['new_total'])
        dtv=data['delta_total']
        dt=human_readable_size(dtv) if readable else str(dtv)
        perc=(dtv/data['old_total']*100) if data['old_total'] else 0.0
        sec_list=", ".join(sorted(group_sections_map.get(g, [])))
        if markdown:
            lines.append(f"| {format_group_name(g)} | {ot} | {nt} | {dt} | {perc:.1f}% | {sec_list} |")
        else:
            lines.append(f"{format_group_name(g):7} | {ot:9} | {nt:9} | {dt:9} | {perc:6.1f}% | {sec_list}")
    return "\n".join(lines)

def get_top_files_per_group(diff_results, top_groups, n_files):
    gfile_map={}
    for fp, groups in diff_results.items():
        for g in top_groups:
            if g in groups:
                gdata=groups[g]
                gfile_map.setdefault(g,{})
                gfile_map[g][fp]={'old_total':gdata['total_old'],'new_total':gdata['total_new'],'delta':gdata['total_delta']}
    for g in gfile_map:
        gfile_map[g]=dict(sorted(gfile_map[g].items(), key=lambda x: abs(x[1]['delta']), reverse=True)[:n_files])
    return gfile_map

def print_top_files_table(gfile_map, readable=False, markdown=False):
    if markdown:
        lines = ["| Group | File | Old Total | New Total | Delta | % |",
                 "|-------|------|-----------|-----------|-------|---|"]
        for g, files in gfile_map.items():
            for fp, val in files.items():
                ot=human_readable_size(val['old_total']) if readable else str(val['old_total'])
                nt=human_readable_size(val['new_total']) if readable else str(val['new_total'])
                dt=human_readable_size(val['delta']) if readable else str(val['delta'])
                perc=(val['delta']/val['old_total']*100) if val['old_total'] else 0.0
                sign="+" if val['delta']>0 else ""
                lines.append(f"| {format_group_name(g)} | {fp} | {ot} | {nt} | {sign}{dt} | {perc:.1f}% |")
    else:
        lines=["==== TOP FILES PER GROUP ===="]
        for g, files in gfile_map.items():
            lines.append(f"\n## Group: {format_group_name(g)}")
            for fp, val in files.items():
                ot=human_readable_size(val['old_total']) if readable else str(val['old_total'])
                nt=human_readable_size(val['new_total']) if readable else str(val['new_total'])
                dt=human_readable_size(val['delta']) if readable else str(val['delta'])
                perc=(val['delta']/val['old_total']*100) if val['old_total'] else 0.0
                sign="+" if val['delta']>0 else ""
                lines.append(f"  {fp}: old={ot}, new={nt}, delta={sign}{dt} ({perc:.1f}%)")
    return "\n".join(lines) + "\n"

# -----------------------------------
# 보고서 조립 / 저장
# -----------------------------------

def build_md_report(table_rows, group_summary, group_sections_map, args, files_map=None):
    parts = []
    parts.append(f"**Sort key:** {args.sort_key} | **Order:** {'Ascending' if args.ascending else 'Descending'}\n")
    
    parts.append("## Section Group classification rule\n")
    parts.append(format_group_section_table_one_line(table_rows, markdown=True))
    # Top-N groups table
    parts.append("\n---\n## Top-N Groups Table\n")
    parts.append(format_top_groups_table(group_summary, args.readable, markdown=True))
    # Sections in top-N groups
    parts.append("\n### Sections in Top-N Groups\n")
    parts.append(format_group_sections_only_table(group_sections_map, markdown=True))
    # Group total summary
    parts.append("\n---\n## Group Total Summary\n")
    parts.append(format_group_total_summary_table(group_summary, group_sections_map, args.readable, markdown=True))
    # Top files per group
    parts.append("\n---\n## Top Files per Group\n")
    if files_map:
        parts.append(print_top_files_table(files_map, args.readable, markdown=True))
    else:
        parts.append("_No top files to display._")
    return "\n".join(parts)



def build_txt_report(table_rows, group_summary, group_sections_map, args):
    txt=format_group_section_table_one_line(table_rows, markdown=False)
    txt+="\n\n"+format_top_groups_table(group_summary, args.readable)
    txt+="\n"+format_group_total_summary_table(group_summary, group_sections_map, args.readable, markdown=False)
    return txt

def save_report_files(basepath, prefix, mode, summary_txt, summary_md, files_txt, files_md):
    os.makedirs(basepath, exist_ok=True)
    with open(os.path.join(basepath, f"{prefix}{mode}_summary.md"), 'w', encoding='utf-8') as f: f.write(summary_md)
    with open(os.path.join(basepath, f"{prefix}{mode}_files.md"), 'w', encoding='utf-8') as f: f.write(files_md if files_md.strip() else "_No top files to display._")
    with open(os.path.join(basepath, f"{prefix}{mode}_summary.txt"), 'w', encoding='utf-8') as f: f.write(summary_txt)
    with open(os.path.join(basepath, f"{prefix}{mode}_files.txt"), 'w', encoding='utf-8') as f: f.write(files_txt)

# -----------------------------------
# MAIN 실행
# -----------------------------------

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("old_dir"); p.add_argument("new_dir")
    p.add_argument("--mode",choices=['berkeley','gnu','custom','sysv','all'],default='berkeley')
    p.add_argument("--readable",action="store_true")
    p.add_argument("--output-dir"); p.add_argument("--output-prefix",default="")
    p.add_argument("--top-n-groups",type=int,default=5)
    p.add_argument("--top-n-files",type=int,default=5)
    p.add_argument("--sort-key",choices=['abs_diff','abs_perc','diff','perc'],default='abs_diff')
    p.add_argument("--ascending",action="store_true",default=True)
    p.add_argument("--custom-sections",type=str, help="Comma-separated list of custom section names (e.g., .foo,.bar,.baz)"
    )

    args=p.parse_args()
    descending=not args.ascending

    custom_secs=[]
    if args.custom_sections:
        for item in args.custom_sections:
            custom_secs.extend([s.strip() for s in item.split(',') if s.strip()])

    # modes 
    modes = ['berkeley', 'gnu', 'sysv']
    if args.mode != 'all':
        modes = [args.mode]
    else:
        if custom_secs:  # custom sections provided → insert custom mode
            modes.insert(2, 'custom')


    for mode in modes:
        old_res=analyze_directory(args.old_dir,mode,custom_secs)
        new_res=analyze_directory(args.new_dir,mode,custom_secs)
        diff_res=compare_results(old_res,new_res)
        group_summary=summarize_group_totals(diff_res)
        if args.top_n_groups:
            group_summary=sort_groups(group_summary, sort_key=args.sort_key, descending=descending, limit=args.top_n_groups)

        group_sections_map={}
        for g in group_summary:
            all_secs=set()
            for fp, groups in new_res.items():
                if g in groups: all_secs.update(groups[g].keys())
            group_sections_map[g]=all_secs

        selected_group_data={}
        for fp, groups in new_res.items():
            for g in group_summary:
                if g in groups:
                    for s, meta in groups[g].items():
                        selected_group_data.setdefault(g,{})[s]=meta

        table_rows=build_group_section_info(selected_group_data)

        files_txt=""; files_md=""; files_map=None
        if args.top_n_files and diff_res:
            files_map=get_top_files_per_group(diff_res,list(group_summary.keys()),args.top_n_files)
            files_txt=print_top_files_table(files_map, args.readable, markdown=False)
            files_md=print_top_files_table(files_map, args.readable, markdown=True)

        summary_md=build_md_report(table_rows, group_summary, group_sections_map, args, files_map)
        summary_txt=build_txt_report(table_rows, group_summary, group_sections_map, args)

        print(summary_txt)
        if files_txt: print(files_txt)
        if args.output_dir:
            save_report_files(args.output_dir, args.output_prefix, mode, summary_txt, summary_md, files_txt, files_md)
