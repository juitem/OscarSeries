#!/usr/bin/env python3
"""
ELF Size Comparison Tool - Full Implementation
All comments are in English.
Meets every requirement: section/size reports, Top N/Top Files analysis,
user-selected sections, PT_LOAD segment-section mapping, all output formats.
"""

import os
import sys
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

# ========= Utility functions =========
def human_readable_size(n):
    """Convert bytes to human-readable string."""
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1024 ** 2:
        return f"{sign}{n / 1024 ** 2:.2f} MB"
    if n >= 1024:
        return f"{sign}{n / 1024:.2f} KB"
    return f"{sign}{n} B"

def ensure_dir(path):
    """Ensure given path exists as directory."""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# ========= Chart with info boxes =========
def make_bar_chart(values, labels, title, path, top_sections=None):
    """Save bar chart for section diff with four annotated info boxes."""
    plt.figure(figsize=(12,5))
    plt.bar(labels, values, color="skyblue")
    plt.title(title)
    plt.xticks(rotation=45, ha="right")
    if top_sections is not None and not top_sections.empty:
        def fmt_box(df, title):
            text = f"{title}\n"
            for _, r in df.head(5).iterrows():
                text += f"{r['section']}: Size {human_readable_size(r['size1'])}, Diff {human_readable_size(r['diff'])}, Diff % {r['diff_pct']:.1f}%\n"
            return text
        boxes = [
            (0.01, 0.95, fmt_box(top_sections[top_sections['diff'] > 0].sort_values('diff', ascending=False), "Top Diff +"), 'left'),
            (0.99, 0.95, fmt_box(top_sections[top_sections['diff_pct'] > 0].sort_values('diff_pct', ascending=False), "Top Diff % +"), 'right'),
            (0.01, 0.60, fmt_box(top_sections[top_sections['diff'] < 0].sort_values('diff'), "Top Diff -"), 'left'),
            (0.99, 0.60, fmt_box(top_sections[top_sections['diff_pct'] < 0].sort_values('diff_pct'), "Top Diff % -"), 'right')
        ]
        for x, y, text, ha in boxes:
            plt.gca().text(x, y, text, transform=plt.gca().transAxes, fontsize=8, va='top', ha=ha,
                           bbox=dict(boxstyle='round', facecolor='white', alpha=0.6))
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

def save_chart(df, path, title, top_sections=None):
    """Wrapper for chart saving."""
    make_bar_chart([abs(x) for x in df['diff']], df['section'], title, path, top_sections)

# ========= ELF File helpers =========
def get_elf_file_list(directory):
    """Return set of ELF candidate file paths relative to directory."""
    return {os.path.relpath(os.path.join(r, f), directory)
            for r, _, fs in os.walk(directory) for f in fs if not os.path.islink(os.path.join(r, f))}

def is_elf_file(path):
    """Check whether file is ELF format."""
    try:
        with open(path, 'rb') as f:
            ELFFile(f)
        return True
    except ELFError:
        return False
    except:
        return False

# ========= Section classification =========
def classify_section(mode, stype, sflag, sname):
    """Classify ELF section into text/data/bss/Others."""
    A = bool(sflag & 0x2)
    W = bool(sflag & 0x1)
    X = bool(sflag & 0x4)
    PROGBITS = (stype == 'SHT_PROGBITS')
    NOBITS = (stype == 'SHT_NOBITS')
    if mode == "berkeley":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and not X and not W: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        else: return "Others", stype
    if mode == "gnu":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        else: return "Others", stype
    if mode == "sysv":
        return sname, stype
    return "Others", stype

# ========= Section summaries (user-selected support) =========
def summarize_by_size_multi(directory, mode, include=None, exclude=None,
                            file_level=False, allowed_files=None, user_sections=None):
    """Summarize section/class sizes, plus independent user-selected stats."""
    user_sections = set(user_sections or [])
    result = {}
    user_result = {}
    for root, _, files in os.walk(directory):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, directory)
            if allowed_files and rel not in allowed_files:
                continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        sname = sec.name
                        stype = sec.header['sh_type']
                        sflag = sec.header['sh_flags']
                        sz = sec.header['sh_size']
                        if include and sname not in include:
                            continue
                        if exclude and sname in exclude:
                            continue
                        class_name, _ = classify_section(mode, stype, sflag, sname)
                        key = sname if mode == "sysv" else class_name
                        if file_level:
                            result.setdefault(key, {})[rel] = result.get(key, {}).get(rel, 0) + sz
                        else:
                            result[key] = result.get(key, 0) + sz
                        if sname in user_sections:
                            if file_level:
                                user_result.setdefault(sname, {})[rel] = user_result.get(sname, {}).get(rel, 0) + sz
                            else:
                                user_result[sname] = user_result.get(sname, 0) + sz
            except:
                continue
    return result, user_result

# def summarize_by_size_multi_df(sum1, sum2):
#     """Compare two size summaries; always with correct columns."""
#     keys = sorted(set(sum1) | set(sum2))
#     if not keys:
#         return pd.DataFrame(columns=['section', 'size1', 'size2', 'diff', 'diff_pct'])
#     rows = []
#     for k in keys:
#         v1 = sum1.get(k, 0)
#         v2 = sum2.get(k, 0)
#         diff = v2 - v1
#         pct = (diff / v1 * 100.0) if v1 else (100.0 if v2 else 0.0)
#         rows.append(dict(section=k, size1=v1, size2=v2, diff=diff, diff_pct=pct))
#     return pd.DataFrame(rows)

def summarize_by_size_multi_df(sum1, sum2):
    keys = sorted(set(sum1) | set(sum2))
    if not keys:
        # Return empty DataFrame with correct columns
        return pd.DataFrame(columns=['section', 'size1', 'size2', 'diff', 'diff_pct'])
    rows = []
    for k in keys:
        v1 = sum1.get(k, 0)
        v2 = sum2.get(k, 0)
        diff = v2 - v1
        pct = (diff / v1 * 100.0) if v1 else (100.0 if v2 else 0.0)
        rows.append(dict(section=k, size1=v1, size2=v2, diff=diff, diff_pct=pct))
    return pd.DataFrame(rows)


# ========= Top N section & file analysis =========
def get_top_sections(df, top_n):
    return df.sort_values("diff", key=abs, ascending=False).head(top_n)

def get_top_diff_increased(df, top_n):
    return df[df['diff'] > 0].sort_values('diff', ascending=False).head(top_n)

def get_top_diff_pct_increased(df, top_n):
    return df[df['diff_pct'] > 0].sort_values('diff_pct', ascending=False).head(top_n)

def get_top_diff_decreased(df, top_n):
    return df[df['diff'] < 0].sort_values('diff', ascending=True).head(top_n)

def get_top_diff_pct_decreased(df, top_n):
    return df[df['diff_pct'] < 0].sort_values('diff_pct', ascending=True).head(top_n)

def get_top_files_per_section(f1, f2, top_n):
    """For each section, get top files by diff."""
    section_top = {}
    for sec in set(f1) | set(f2):
        diffs = {}
        fs1 = f1.get(sec, {})
        fs2 = f2.get(sec, {})
        all_files = set(fs1) | set(fs2)
        for fname in all_files:
            v1 = fs1.get(fname)
            v2 = fs2.get(fname)
            dpart, fpart = os.path.dirname(fname), os.path.basename(fname)
            if v1 is not None and v2 is not None:
                status = "common"
                diff = v2 - v1
                pct = (diff / v1 * 100.0) if v1 else (100.0 if v2 else 0.0)
            elif v1 is not None:
                status = "removed"
                diff = -v1
                pct = -100.0
            else:
                status = "added"
                diff = v2
                pct = 100.0
            diffs[(dpart, fpart, status)] = (v1 or 0, v2 or 0, diff, pct)
        section_top[sec] = dict(sorted(diffs.items(), key=lambda x: abs(x[1][2]), reverse=True)[:top_n])
    return section_top

# ========= CSV/TXT Output =========
def save_csv_txt(out_dir, mode, df, top_sections, top_inc, top_pct_inc, top_dec, top_pct_dec):
    """Save CSV files for section summaries and Top N diff."""
    ensure_dir(out_dir)
    df.to_csv(os.path.join(out_dir, f"{mode}_summary.csv"), index=False)
    top_sections.to_csv(os.path.join(out_dir, f"{mode}_top_sections.csv"), index=False)
    top_inc.to_csv(os.path.join(out_dir, f"{mode}_top_diff_increased.csv"), index=False)
    top_pct_inc.to_csv(os.path.join(out_dir, f"{mode}_top_diff_pct_increased.csv"), index=False)
    top_dec.to_csv(os.path.join(out_dir, f"{mode}_top_diff_decreased.csv"), index=False)
    top_pct_dec.to_csv(os.path.join(out_dir, f"{mode}_top_diff_pct_decreased.csv"), index=False)

def save_top_files_csv(out_dir, mode, section_top):
    """Save CSV of top files per section."""
    ensure_dir(out_dir)
    for sec, files in section_top.items():
        rows = []
        for (d, f, s), vals in files.items():
            rows.append({"directory": d, "file": f, "status": s,
                         "size1": vals[0], "size2": vals[1], "diff": vals[2], "diff_pct": vals[3]})
        df = pd.DataFrame(rows)
        if not df.empty:
            df.to_csv(os.path.join(out_dir, f"{mode}_{sec}_top_files.csv"), index=False)

# ========= Markdown / TXT / HTML report output =========
def save_report(df_dict, top_sections_dict, out_prefix, top_n, cmdline_info):
    """Save main markdown and plain txt report."""
    md = f"# ELF Size Comparison Report\n\n**Execution Command:** `{cmdline_info}`\nGenerated: {datetime.now()}\n\n"
    for mode in df_dict:
        df = df_dict[mode]
        md += f"## Mode: {mode}\n\n| Section | Size1 | Size2 | Diff | Diff % |\n|---|---|---|---|---|\n"
        for _, r in df.iterrows():
            md += f"| {r['section']} | {human_readable_size(r['size1'])} | "
            md += f"{human_readable_size(r['size2'])} | {human_readable_size(r['diff'])} | {r['diff_pct']:.2f}% |\n"
    with open(f"{out_prefix}.md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(f"{out_prefix}.txt", "w", encoding="utf-8") as f:
        f.write(md.replace("|", "").replace("-", ""))
    print(f"Saved: {out_prefix}.md /.txt")

def save_report_with_topfiles(df_dict, top_sections_dict, top_files_dict, out_prefix, top_n, cmdline_info):
    """Save markdown and TXT report with Top Files."""
    md = f"# ELF Size Comparison Report (with Top Files)\n\n**Execution Command:** `{cmdline_info}`\nGenerated: {datetime.now()}\n\n"
    for mode in df_dict:
        df = df_dict[mode]
        top_sections = top_sections_dict[mode]
        md += f"## Mode: {mode}\n\n| Section | Size1 | Size2 | Diff | Diff % |\n|---|---|---|---|---|\n"
        for _, r in df.iterrows():
            md += f"| {r['section']} | {human_readable_size(r['size1'])} | {human_readable_size(r['size2'])} | {human_readable_size(r['diff'])} | {r['diff_pct']:.2f}% |\n"
        for stat_func, title in [
            (get_top_diff_increased, f"Top {top_n} Diff Increased (Bytes)"),
            (get_top_diff_pct_increased, f"Top {top_n} Diff % Increased"),
            (get_top_diff_decreased, f"Top {top_n} Diff Decreased (Bytes)"),
            (get_top_diff_pct_decreased, f"Top {top_n} Diff % Decreased"),
        ]:
            top_df = stat_func(df, top_n)
            if not top_df.empty:
                md += f"\n### {title}\n\n| Section | Size1 | Size2 | Diff | Diff % |\n|---|---|---|---|---|\n"
                for _, r in top_df.iterrows():
                    md += f"| {r['section']} | {human_readable_size(r['size1'])} | {human_readable_size(r['size2'])} | {human_readable_size(r['diff'])} | {r['diff_pct']:.2f}% |\n"
        top_files_mode = top_files_dict.get(mode, {})
        for sec, files in top_files_mode.items():
            if not files: continue
            md += f"\n#### Section `{sec}` Top {top_n} Files\n"
            md += "| Directory | File | Status | Size1 | Size2 | Diff | Diff % |\n|---|---|---|---|---|---|---|\n"
            for (dirp, fname, status), vals in files.items():
                md += f"| {dirp} | {fname} | {status} | {human_readable_size(vals[0])} | {human_readable_size(vals[1])} | {human_readable_size(vals[2])} | {vals[3]:.2f}% |\n"
    with open(f"{out_prefix}_with_topfiles.md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(f"{out_prefix}_with_topfiles.txt", "w", encoding="utf-8") as f:
        f.write(md.replace("|", "").replace("-", ""))
    print(f"Saved: {out_prefix}_with_topfiles.md / .txt")

def save_html_report(df_dict, out_prefix, cmdline_info):
    """Save HTML report for basic summary."""
    html = f"<html><head><meta charset='utf-8'><title>ELF Size Report</title></head><body>"
    html += f"<h1>ELF Size Comparison Report</h1><p><b>Execution Command:</b> {cmdline_info}</p>"
    html += f"<p>Generated: {datetime.now()}</p>"
    for mode in df_dict:
        df = df_dict[mode]
        html += f"<h2>Mode: {mode}</h2><table border='1'>"
        html += "<tr><th>Section</th><th>Size1</th><th>Size2</th><th>Diff</th><th>Diff %</th></tr>"
        for _, r in df.iterrows():
            html += f"<tr><td>{r['section']}</td><td>{human_readable_size(r['size1'])}</td>"
            html += f"<td>{human_readable_size(r['size2'])}</td><td>{human_readable_size(r['diff'])}</td>"
            html += f"<td>{r['diff_pct']:.2f}%</td></tr>"
        html += "</table>"
    html += "</body></html>"
    with open(f"{out_prefix}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {out_prefix}.html")

def save_html_report_with_topfiles(df_dict, top_files_dict, out_prefix, top_n, cmdline_info):
    """Save HTML report with Top Files analysis."""
    html = f"<html><head><meta charset='utf-8'><title>ELF Size Report (with Top Files)</title></head><body>"
    html += f"<h1>ELF Size Comparison Report (with Top Files)</h1>"
    html += f"<p><b>Execution Command:</b> {cmdline_info}</p>"
    html += f"<p>Generated: {datetime.now()}</p>"
    for mode in df_dict:
        df = df_dict[mode]
        html += f"<h2>Mode: {mode}</h2><table border='1'><tr><th>Section</th><th>Size1</th><th>Size2</th><th>Diff</th><th>Diff %</th></tr>"
        for _, r in df.iterrows():
            html += f"<tr><td>{r['section']}</td><td>{human_readable_size(r['size1'])}</td>"
            html += f"<td>{human_readable_size(r['size2'])}</td><td>{human_readable_size(r['diff'])}</td><td>{r['diff_pct']:.2f}%</td></tr>"
        html += "</table>"
        for stat_func, title in [
            (get_top_diff_increased, f"Top {top_n} Diff Increased (Bytes)"),
            (get_top_diff_pct_increased, f"Top {top_n} Diff % Increased"),
            (get_top_diff_decreased, f"Top {top_n} Diff Decreased (Bytes)"),
            (get_top_diff_pct_decreased, f"Top {top_n} Diff % Decreased"),
        ]:
            top_df = stat_func(df, top_n)
            if not top_df.empty:
                html += f"<h3>{title}</h3><table border='1'><tr><th>Section</th><th>Size1</th><th>Size2</th><th>Diff</th><th>Diff %</th></tr>"
                for _, r in top_df.iterrows():
                    html += f"<tr><td>{r['section']}</td><td>{human_readable_size(r['size1'])}</td><td>{human_readable_size(r['size2'])}</td><td>{human_readable_size(r['diff'])}</td><td>{r['diff_pct']:.2f}%</td></tr>"
                html += "</table>"
        top_files_mode = top_files_dict.get(mode, {})
        for sec, files in top_files_mode.items():
            if not files: continue
            html += f"<h4>Section {sec} Top {top_n} Files</h4><table border='1'><thead><tr><th>Directory</th><th>File</th><th>Status</th><th>Size1</th><th>Size2</th><th>Diff</th><th>Diff %</th></tr></thead><tbody>"
            for (dirp, fname, status), vals in files.items():
                html += f"<tr><td>{dirp}</td><td>{fname}</td><td>{status}</td><td>{human_readable_size(vals[0])}</td><td>{human_readable_size(vals[1])}</td><td>{human_readable_size(vals[2])}</td><td>{vals[3]:.2f}%</td></tr>"
            html += "</tbody></table>"
    html += "</body></html>"
    with open(f"{out_prefix}_with_topfiles.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {out_prefix}_with_topfiles.html")

# ========= Excel report =========
def save_excel(excel_path, df_dict, top_sections_dict, top_files_dict, cmdline_info):
    """Save Excel file with summary, Top N, and Top Files sheets (requires openpyxl)."""
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        pd.DataFrame([{"Execution Command": cmdline_info}]).to_excel(writer, sheet_name="Execution_Command", index=False)
        for mode in df_dict:
            df = df_dict[mode]
            top_sections = top_sections_dict[mode]
            df.to_excel(writer, sheet_name=f"{mode}_summary"[:31], index=False)
            top_sections.to_excel(writer, sheet_name=f"{mode}_top_sections"[:31], index=False)
            get_top_diff_increased(df, len(df)).to_excel(writer, sheet_name=f"{mode}_top_diff_inc"[:31], index=False)
            get_top_diff_pct_increased(df, len(df)).to_excel(writer, sheet_name=f"{mode}_top_pct_diff_inc"[:31], index=False)
            get_top_diff_decreased(df, len(df)).to_excel(writer, sheet_name=f"{mode}_top_diff_dec"[:31], index=False)
            get_top_diff_pct_decreased(df, len(df)).to_excel(writer, sheet_name=f"{mode}_top_pct_diff_dec"[:31], index=False)
            for sec, files in top_files_dict.get(mode, {}).items():
                if not files: continue
                rows = []
                for (d, f, s), vals in files.items():
                    rows.append({"directory": d, "file": f, "status": s,
                                 "size1": vals[0], "size2": vals[1], "diff": vals[2], "diff_pct": vals[3]})
                sec_df = pd.DataFrame(rows)
                sec_df.to_excel(writer, sheet_name=f"{mode}_{sec}"[:31], index=False)
    print(f"Excel report saved: {excel_path}")

# ========= PT_LOAD size-utility and segment-section analysis =========
def summarize_sizeutil_per_file(directory, allowed_files=None):
    """Return dict of file->total PT_LOAD memsz."""
    result = {}
    for root, _, files in os.walk(directory):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, directory)
            if allowed_files and rel not in allowed_files:
                continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    total = 0
                    for seg in elf.iter_segments():
                        if seg['p_type'] == 'PT_LOAD':
                            total += seg['p_memsz']
                    result[rel] = total
            except:
                continue
    return result

def analyze_ptload_sections(filepath, classify_mode):
    """Return list of dicts describing sections inside each PT_LOAD segment."""
    results = []
    try:
        with open(filepath, 'rb') as f:
            elf = ELFFile(f)
            for seg_idx, seg in enumerate(elf.iter_segments()):
                if seg['p_type'] != 'PT_LOAD':
                    continue
                seg_start = seg['p_vaddr']
                seg_end = seg_start + seg['p_memsz']
                for sec in elf.iter_sections():
                    addr = sec['sh_addr']
                    size = sec['sh_size']
                    if addr >= seg_start and addr + size <= seg_end:
                        class_name, _stype = classify_section(classify_mode,
                                                              sec.header['sh_type'],
                                                              sec.header['sh_flags'],
                                                              sec.name)
                        results.append({
                            "segment_index": seg_idx,
                            "segment_memsz": seg['p_memsz'],
                            "section_name": sec.name,
                            "section_size": size,
                            "class": class_name,
                            "type": sec.header['sh_type']
                        })
    except:
        pass
    return results

def save_sizeutil_report_with_sections(dir1, dir2, allowed_files, out_prefix, classify_mode):
    """Generate PT_LOAD report and segment->section table."""
    sum1 = summarize_sizeutil_per_file(dir1, allowed_files)
    sum2 = summarize_sizeutil_per_file(dir2, allowed_files)
    rows = []
    seg_rows = []
    for fname in sorted(set(sum1) | set(sum2)):
        size1 = sum1.get(fname, 0)
        size2 = sum2.get(fname, 0)
        diff = size2 - size1
        pct = (diff / size1 * 100.0) if size1 else (100.0 if size2 else 0.0)
        rows.append(dict(file=fname, size1=size1, size2=size2, diff=diff, diff_pct=pct))
        for seginfo in analyze_ptload_sections(os.path.join(dir1, fname), classify_mode):
            seginfo["file"] = f"[dir1] {fname}"
            seg_rows.append(seginfo)
        for seginfo in analyze_ptload_sections(os.path.join(dir2, fname), classify_mode):
            seginfo["file"] = f"[dir2] {fname}"
            seg_rows.append(seginfo)
    pd.DataFrame(rows).to_csv(f"{out_prefix}_sizeutil_summary.csv", index=False)
    pd.DataFrame(seg_rows).to_csv(f"{out_prefix}_sizeutil_segments.csv", index=False)
    with open(f"{out_prefix}_sizeutil_summary.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['file']}\t{human_readable_size(r['size1'])}\t{human_readable_size(r['size2'])}\t{human_readable_size(r['diff'])}\t{r['diff_pct']:.2f}%\n")
    plt.figure(figsize=(10, 4))
    plt.bar([r['file'] for r in rows], [abs(r['diff']) for r in rows], color="skyblue")
    plt.title("PT_LOAD memsz Diff per file")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(f"{out_prefix}_sizeutil_summary.png")
    plt.close()
    print(f"PT_LOAD size reports saved: {out_prefix}_sizeutil_summary.*, _sizeutil_segments.csv")

# ========= All files list from top files =========
def save_all_files_list_txt(top_files_dict, out_prefix):
    """Save TXT list of all files appearing in Top Files analysis."""
    all_files = set()
    for mode_files in top_files_dict.values():
        for sec_files in mode_files.values():
            for path in sec_files.keys():
                all_files.add(os.path.join(path[0], path[1]) if path[0] else path[1])
    with open(f"{out_prefix}_all_files.txt", "w", encoding="utf-8") as f:
        for p in sorted(all_files):
            f.write(f"{p}\n")
    print(f"All files list saved: {out_prefix}_all_files.txt")

# ========= Main execution =========
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir1")
    ap.add_argument("dir2")
    ap.add_argument("--display-mode", choices=["berkeley", "gnu", "sysv", "all"], default="berkeley")
    ap.add_argument("--top-n-sections", type=int, default=5)
    ap.add_argument("--top-n-files", type=int, default=10)
    ap.add_argument("--include-section", nargs="+", default=[])
    ap.add_argument("--exclude-section", nargs="+", default=[])
    ap.add_argument("--output-dir")
    ap.add_argument("--report-prefix")
    ap.add_argument("--all-files", action="store_true")
    ap.add_argument("--report-type", choices=["section", "size", "all"], default="section")
    ap.add_argument("--user-selected", nargs="+", default=[], help="User selected sections for separate aggregation")
    ap.add_argument("--excel-path", default=None)
    args = ap.parse_args()

    dir1 = os.path.abspath(args.dir1)
    dir2 = os.path.abspath(args.dir2)
    files1 = get_elf_file_list(dir1)
    files2 = get_elf_file_list(dir2)
    if args.all_files:
        allowed1, allowed2 = files1, files2
    else:
        common = files1 & files2
        allowed1 = allowed2 = {f for f in common if is_elf_file(os.path.join(dir1, f)) and is_elf_file(os.path.join(dir2, f))}
    modes = [args.display_mode] if args.display_mode != "all" else ["berkeley", "gnu", "sysv"]
    outdir = args.output_dir or "out"
    ensure_dir(outdir)
    cmdlineinfo = " ".join(sys.argv)

    if args.report_type in ["section", "all"]:
        df_results = {}
        top_sections_dict = {}
        top_files_dict = {}
        for mode in modes:
            sum1, user1 = summarize_by_size_multi(
                dir1, mode, args.include_section, args.exclude_section,
                allowed_files=allowed1, user_sections=args.user_selected)
            sum2, user2 = summarize_by_size_multi(
                dir2, mode, args.include_section, args.exclude_section,
                allowed_files=allowed2, user_sections=args.user_selected)
            df = summarize_by_size_multi_df(sum1, sum2)
            df_user = summarize_by_size_multi_df(user1, user2)
            dfs = [df]
            if not df_user.empty:
                dfs.append(df_user)
            df_combined = pd.concat(dfs, ignore_index=True)
            df_combined['section'] = df_combined['section'].replace({"not included": "Others"})
            df_results[mode] = df_combined
            top_sections = get_top_sections(df_combined, args.top_n_sections)
            top_sections_dict[mode] = top_sections
            f1, _ = summarize_by_size_multi(dir1, mode, args.include_section, args.exclude_section, file_level=True, allowed_files=allowed1, user_sections=args.user_selected)
            f2, _ = summarize_by_size_multi(dir2, mode, args.include_section, args.exclude_section, file_level=True, allowed_files=allowed2, user_sections=args.user_selected)
            section_top = get_top_files_per_section(f1, f2, args.top_n_files)
            top_files_dict[mode] = section_top
            save_chart(df_combined, os.path.join(outdir, f"{mode}_section_diff.png"), f"{mode} Section Diff", top_sections)
            save_csv_txt(outdir, mode, df_combined, top_sections,
                         get_top_diff_increased(df_combined, args.top_n_sections),
                         get_top_diff_pct_increased(df_combined, args.top_n_sections),
                         get_top_diff_decreased(df_combined, args.top_n_sections),
                         get_top_diff_pct_decreased(df_combined, args.top_n_sections))
            save_top_files_csv(outdir, mode, section_top)
        if args.report_prefix:
            save_report(df_results, top_sections_dict, args.report_prefix, args.top_n_sections, cmdlineinfo)
            save_report_with_topfiles(df_results, top_sections_dict, top_files_dict, args.report_prefix, args.top_n_sections, cmdlineinfo)
            save_html_report(df_results, args.report_prefix, cmdlineinfo)
            save_html_report_with_topfiles(df_results, top_files_dict, args.report_prefix, args.top_n_sections, cmdlineinfo)
            save_all_files_list_txt(top_files_dict, args.report_prefix)
        if args.excel_path:
            save_excel(args.excel_path, df_results, top_sections_dict, top_files_dict, cmdlineinfo)

    if args.report_type in ["size","all"]:
        prefix = args.report_prefix or os.path.join(outdir,"sizeutil_report")
        save_sizeutil_report_with_sections(dir1, dir2, allowed1, prefix, args.display_mode)

if __name__ == "__main__":
    main()
