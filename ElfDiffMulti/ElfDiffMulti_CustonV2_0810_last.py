#!/usr/bin/env python3
import os
import sys
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from elftools.elf.elffile import ELFFile
from matplotlib.ticker import FuncFormatter

# --- Utility Functions ---
def human_readable_size(n):
    try:
        n = int(n)
    except:
        return str(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1024 ** 2:
        return f"{sign}{n / 1024 ** 2:.2f} MB"
    if n >= 1024:
        return f"{sign}{n / 1024:.2f} KB"
    return f"{sign}{n} B"

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def save_used_files_list(output_dir, file_set, filename="used_files.txt"):
    ensure_dir(output_dir)
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        for fname in sorted(file_set):
            f.write(fname + "\n")

def normalize_user_sections_with_comma(input_list):
    """
    Normalize user section list by splitting only on commas.
    Args:
        input_list (list of strings)
    Returns:
        set of normalized section names
    """
    sections = set()
    for item in (input_list or []):
        parts = item.split(",")
        for token in parts:
            token = token.strip()
            if token:
                sections.add(token)
    return sections

# --- ELF Helpers ---
def get_elf_file_list(directory):
    return {os.path.relpath(os.path.join(r, f), directory)
            for r, _, fs in os.walk(directory)
            for f in fs if not os.path.islink(os.path.join(r, f))}

def is_elf_file(path):
    try:
        with open(path, 'rb') as f:
            ELFFile(f)
        return True
    except:
        return False

# --- Classification ---
def classify_section(mode, stype, sflag, sname):
    A, W, X = bool(sflag & 0x2), bool(sflag & 0x1), bool(sflag & 0x4)
    PROGBITS, NOBITS = (stype == 'SHT_PROGBITS'), (stype == 'SHT_NOBITS')
    if mode == "berkeley":
        if PROGBITS and A and X:
            return "text", stype
        elif PROGBITS and A and not X and not W:
            return "text", stype
        elif PROGBITS and A and W:
            return "data", stype
        elif NOBITS and A and W:
            return "bss", stype
        return "others", stype
    elif mode == "gnu":
        if PROGBITS and A and X:
            return "text", stype
        elif PROGBITS and A and W:
            return "data", stype
        elif NOBITS and A and W:
            return "bss", stype
        return "others", stype
    elif mode == "sysv":
        # sysv uses actual section name as class
        return sname, stype
    return "others", stype

# --- Section Size Summary ---
def summarize_by_size_multi(d, mode, include=None, exclude=None, file_level=False,
                            allowed_files=None, user_sections=None):
    """
    Summarize ELF sections by size for the given directory.

    Rules:
    - Filtering is always based on the actual section name (sec_name)
    - If a section is in both 'exclude' and 'user_sections':
        -> skip adding to normal result
        -> add only to user_result
    - If a section is only in 'exclude':
        -> skip entirely
    - If a section is only in 'user_sections':
        -> add to normal result AND user_result
    """
    user_sections = set(user_sections or [])
    exclude = set(exclude or [])
    include = set(include or [])
    result, user_result = {}, {}

    for root, _, files in os.walk(d):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, d)
            if allowed_files and rel not in allowed_files:
                continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        sec_name = sec.name
                        stype = sec.header['sh_type']
                        sflag = sec.header['sh_flags']
                        sz = sec.header['sh_size']
                        cls, _ = classify_section(mode, stype, sflag, sec_name)

                        # Case 1: section is in exclude
                        if sec_name in exclude:
                            if sec_name in user_sections:
                                # Add ONLY to user_result, skip normal result
                                if file_level:
                                    user_result.setdefault(sec_name, {})
                                    user_result[sec_name][rel] = user_result[sec_name].get(rel, 0) + sz
                                else:
                                    user_result[sec_name] = user_result.get(sec_name, 0) + sz
                            # In both cases (exclude only or exclude+user), skip normal result
                            continue

                        # Case 2: normal aggregation
                        key = sec_name if mode == "sysv" else cls
                        if file_level:
                            result.setdefault(key, {})
                            result[key][rel] = result[key].get(rel, 0) + sz
                        else:
                            result[key] = result.get(key, 0) + sz

                        # If also user-selected, add to user_result too
                        if sec_name in user_sections:
                            if file_level:
                                user_result.setdefault(sec_name, {})
                                user_result[sec_name][rel] = user_result[sec_name].get(rel, 0) + sz
                            else:
                                user_result[sec_name] = user_result.get(sec_name, 0) + sz
            except:
                continue
    return result, user_result

def summarize_by_size_multi_df(sum1, sum2):
    keys = sorted(set(sum1) | set(sum2))
    rows = []
    for k in keys:
        v1, v2 = sum1.get(k, 0), sum2.get(k, 0)
        diff = v2 - v1
        pct = (diff / v1 * 100.0) if v1 else (100.0 if v2 else 0.0)
        rows.append({"section": k, "size1": v1, "size2": v2, "diff": diff, "diff_pct": pct})
    return pd.DataFrame(rows)

def merge_user_selected(df_main, df_user):
    if df_user.empty:
        return df_main
    user_secs_with_data = set(df_user['section'].unique())
    filtered_main = df_main[~df_main['section'].str.startswith("User-Selected")]
    total_size1 = df_user['size1'].sum()
    total_size2 = df_user['size2'].sum()
    total_diff = df_user['diff'].sum()
    total_pct = (total_diff / total_size1 * 100.0) if total_size1 else (100.0 if total_size2 else 0.0)
    user_row = {
        'section': f"User-Selected ({', '.join(sorted(user_secs_with_data))})",
        'size1': total_size1,
        'size2': total_size2,
        'diff': total_diff,
        'diff_pct': total_pct
    }
    return pd.concat([filtered_main, pd.DataFrame([user_row])], ignore_index=True)

# --- Top-N helpers ---
def get_top_sections(df, n):
    return df.sort_values("diff", key=abs, ascending=False).head(n)

def get_top_files_per_section(f1, f2, n):
    sec_top = {}
    for sec in set(f1) | set(f2):
        diffs = {}
        fs1, fs2 = f1.get(sec, {}), f2.get(sec, {})
        for fname in set(fs1) | set(fs2):
            v1, v2 = fs1.get(fname), fs2.get(fname)
            dname, bname = os.path.dirname(fname), os.path.basename(fname)
            if v1 is not None and v2 is not None:
                status = "common"
                diff = v2 - v1
                pct = (diff / v1 * 100.0) if v1 else 100.0
            elif v1 is not None:
                status = "removed"
                diff = -v1
                pct = -100.0
            else:
                status = "added"
                diff = v2
                pct = 100.0
            diffs[(dname, bname, status)] = (v1 or 0, v2 or 0, diff, pct)
        sec_top[sec] = dict(sorted(diffs.items(), key=lambda x: abs(x[1][2]), reverse=True)[:n])
    return sec_top

# --- Classification table ---
def collect_section_classification_table(d, mode, allowed_files=None, user_sections=None):
    rows = []
    user_sections = set(user_sections or [])
    for root, _, files in os.walk(d):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, d)
            if allowed_files and rel not in allowed_files:
                continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        sec_name = sec.name
                        stype = sec.header['sh_type']
                        sflag = sec.header['sh_flags']
                        if sec_name in user_sections:
                            rows.append({
                                "section name": sec_name,
                                "class": f"User-Selected ({sec_name})",
                                "type": stype,
                                "flags": f"0x{sflag:x}"
                            })
                        else:
                            cls, _ = classify_section(mode, stype, sflag, sec_name)
                            rows.append({
                                "section name": sec_name,
                                "class": cls,
                                "type": stype,
                                "flags": f"0x{sflag:x}"
                            })
            except:
                continue
    return pd.DataFrame(rows)

def aggregate_classification_by_class(df):
    if df.empty:
        return df
    return df.groupby('class').agg({
        'section name': lambda x: ', '.join(sorted(set(x))),
        'type': lambda x: ', '.join(sorted(set(str(i) for i in x))),
        'flags': lambda x: ', '.join(sorted(set(str(i) for i in x)))
    }).reset_index()

# --- Charting ---
def human_readable_formatter(x, pos):
    try:
        x_int = int(x)
    except:
        return str(x)
    if x_int >= 1024 ** 2:
        return f'{x_int / 1024 ** 2:.1f} MB'
    elif x_int >= 1024:
        return f'{x_int / 1024:.1f} KB'
    else:
        return f'{x_int} B'

formatter = FuncFormatter(human_readable_formatter)

# Top-N boxes inside chart
def add_top_n_diff_boxes(ax, df, top_n, x_positions, y_start, box_width, box_height, fontsize=9):
    boxes_data = []

    top_pos_diff = df[df['diff'] > 0].sort_values('diff', ascending=False).head(top_n)
    boxes_data.append(("+Diff", top_pos_diff))

    top_neg_diff = df[df['diff'] < 0].sort_values('diff').head(top_n)
    boxes_data.append(("-Diff", top_neg_diff))

    top_pos_diff_pct = df[df['diff_pct'] > 0].sort_values('diff_pct', ascending=False).head(top_n)
    boxes_data.append(("+Diff%", top_pos_diff_pct))

    top_neg_diff_pct = df[df['diff_pct'] < 0].sort_values('diff_pct').head(top_n)
    boxes_data.append(("-Diff%", top_neg_diff_pct))

    box_style = dict(boxstyle='round,pad=0.5', facecolor='gray', alpha=0.25, edgecolor='none')

    # Positions: (x, y, horizontal alignment, vertical alignment)
    positions = [
        (0.01, 0.99, 'left', 'top'),     # top-left
        (0.99, 0.99, 'right', 'top'),    # top-right
        (0.01, 0.01, 'left', 'bottom'),  # bottom-left
        (0.99, 0.01, 'right', 'bottom')  # bottom-right
    ]

    for i, (title, top_df) in enumerate(boxes_data):
        lines = [title]
        for _, row in top_df.iterrows():
            line = (f"{row['section']}: "
                    f"{human_readable_size(row['size1'])}, "
                    f"{human_readable_size(row['size2'])}, "
                    f"{human_readable_size(row['diff'])}, "
                    f"{row['diff_pct']:.2f}%")
            lines.append(line)
        text = "\n".join(lines)

        x, y, ha, va = positions[i]
        ax.text(x, y, text, transform=ax.transAxes,
                fontsize=fontsize, verticalalignment=va, horizontalalignment=ha,
                fontfamily='monospace', bbox=box_style)

def make_section_diff_chart_with_log_y(
    size1_list, size2_list, diff_list, diff_pct_list, labels, title, path, top_n=10
):
    x = np.arange(len(labels))
    width = 0.6

    fig, ax = plt.subplots(figsize=(14, 7))

    # For log scale, zero or negative bars set to 1 minimum
    bar_values = [abs(d) if d > 0 else 1 for d in diff_list]
    ax.bar(x, bar_values, width, color='skyblue')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_title(f"{title}")
    ax.set_ylabel("Size (Bytes)")

    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(human_readable_formatter))

    ax.text(
        0.55, 0.95, "Resized Y-axis to log scale", transform=ax.transAxes,
        fontsize=10, color='red', ha='right', va='bottom',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor='red')
    )

    import pandas as pd
    combined_df = pd.DataFrame({
        'section': labels,
        'size1': size1_list,
        'size2': size2_list,
        'diff': diff_list,
        'diff_pct': diff_pct_list,
    })

    box_width = 0.22
    box_height = 0.4
    x_positions = [0.02, 0.27, 0.52, 0.77]
    y_start = 0.95

    add_top_n_diff_boxes(ax, combined_df, top_n, x_positions, y_start, box_width, box_height)

    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# --- Segment sizeutil analysis (formerly PT_LOAD) ---
def summarize_segment_per_file(directory, allowed_files=None):
    """
    Summarize total PT_LOAD segment sizes (p_memsz) for each ELF file in a directory.
    """
    result = {}
    for root, _, files in os.walk(directory):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, directory)
            if allowed_files and rel not in allowed_files:
                continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    total_size = sum(seg['p_memsz'] for seg in elf.iter_segments() if seg['p_type'] == 'PT_LOAD')
                    result[rel] = total_size
            except Exception:
                continue
    return result

# 
def save_segment_report_with_sections(d1, d2, allowed_files, prefix, mode):
    s1 = summarize_segment_per_file(d1, allowed_files)
    s2 = summarize_segment_per_file(d2, allowed_files)

    # Calculate total segment sizes for both directories
    total_size1 = sum(s1.values())
    total_size2 = sum(s2.values())
    total_diff = total_size2 - total_size1
    total_pct = (total_diff / total_size1 * 100.0) if total_size1 else (100.0 if total_size2 else 0.0)

    rows = []
    for f in sorted(set(s1) | set(s2)):
        size1 = s1.get(f, 0)
        size2 = s2.get(f, 0)
        diff = size2 - size1
        pct = (diff / size1 * 100.0) if size1 else (100.0 if size2 else 0.0)
        rows.append({
            "file": f, "size1": size1, "size2": size2,
            "diff": diff, "diff_pct": pct
        })

    # Save detailed CSV and TXT report as is
    df_sum = pd.DataFrame(rows)
    ensure_dir(os.path.dirname(prefix))
    df_sum.to_csv(f"{prefix}_segment_summary.csv", index=False)

    with open(f"{prefix}_segment_summary.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['file']}\t{human_readable_size(r['size1'])}"
                    f"\t{human_readable_size(r['size2'])}"
                    f"\t{human_readable_size(r['diff'])}"
                    f"\t{r['diff_pct']:.2f}%\n")

    # Generate total segment size bar chart (per mode, only one PNG)
    plt.figure(figsize=(6, 4))
    plt.bar(["Old", "New"], [total_size1, total_size2], color=['gray', 'skyblue'])
    plt.title(f"{mode} Segment Total Size")
    plt.gca().yaxis.set_major_formatter(formatter)
    plt.tight_layout()
    plt.savefig(f"{prefix}_segment.png")
    plt.close()

    print(f"[Segment {mode}] Summary saved: {prefix}_segment_summary.csv / .txt / .png")

# --- Markdown & HTML report helpers ---
def md_format_table(df, cols):
    header = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |\n"
    rows = "".join("| " + " | ".join(str(row[c]) for c in cols) + " |\n" for _, row in df.iterrows())
    return header + sep + rows

def save_md_html_reports(df_dict, top_files_dict, class_tables, output_dir, prefix, cmd, include_topfiles=False):
    """
    Save Markdown (.md) and HTML (.html) reports summarizing ELF size comparison.

    Args:
      df_dict: dict of DataFrames keyed by mode, containing section-level summaries
      top_files_dict: dict of top files info keyed by mode
      class_tables: dict of classification DataFrames keyed by mode
      output_dir: output directory path
      prefix: filename prefix for outputs
      cmd: command line string to add as report metadata
      include_topfiles: bool, whether to include detailed top-files info in the report
    """
    import os
    import pandas as pd
    from datetime import datetime

    md_content = f"# ELF Size Comparison Report\n\nExecuted: `{cmd}`\nGenerated: {datetime.now()}\n\n"

    # Helper to format table as Markdown
    def md_format_table(df, cols):
        header = "| " + " | ".join(cols) + " |\n"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |\n"
        rows = "".join("| " + " | ".join(str(row[c]) for c in cols) + " |\n" for _, row in df.iterrows())
        return header + sep + rows

    def human_readable_size(n):
        try:
            n = int(n)
        except:
            return str(n)
        sign = "-" if n < 0 else ""
        n = abs(n)
        if n >= 1024 ** 2:
            return f"{sign}{n / 1024 ** 2:.2f} MB"
        if n >= 1024:
            return f"{sign}{n / 1024:.2f} KB"
        return f"{sign}{n} B"

    for mode in df_dict:
        df = df_dict[mode].copy()
        for col in ['size1', 'size2', 'diff']:
            df[col] = df[col].apply(human_readable_size)
        df['diff_pct'] = df['diff_pct'].map(lambda x: f"{x:.2f}%")
        md_content += f"## Mode: {mode}\n\n"
        md_content += md_format_table(df, ['section', 'size1', 'size2', 'diff', 'diff_pct']) + "\n"

        if class_tables.get(mode) is not None and not class_tables[mode].empty:
            agg_df = class_tables[mode].groupby('class').agg({
                'section name': lambda x: ', '.join(sorted(set(x))),
                'type': lambda x: ', '.join(sorted(set(str(i) for i in x))),
                'flags': lambda x: ', '.join(sorted(set(str(i) for i in x)))
            }).reset_index()

            md_content += "### Classification Table\n"
            md_content += md_format_table(agg_df, ['class', 'section name', 'type', 'flags']) + "\n"

        if include_topfiles:
            md_content += f"### Top Files ({mode})\n"
            for sec, files in top_files_dict.get(mode, {}).items():
                md_content += f"#### {sec}\n"
                rows = []
                for (d, fname, status), (s1, s2, diff, pct) in files.items():
                    rows.append({
                        'directory': d, 'file': fname, 'status': status,
                        'size1': human_readable_size(s1),
                        'size2': human_readable_size(s2),
                        'diff': human_readable_size(diff),
                        'diff_pct': f"{pct:.2f}%"
                    })
                if rows:
                    md_content += md_format_table(pd.DataFrame(rows), ['directory', 'file', 'status', 'size1', 'size2', 'diff', 'diff_pct']) + "\n"

    # Write Markdown file
    md_filepath = os.path.join(output_dir, f"{prefix}{'_topfiles' if include_topfiles else ''}.md")
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Convert Markdown to HTML and save (if markdown package is installed)
    try:
        import markdown
        html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        html_filepath = os.path.join(output_dir, f"{prefix}{'_topfiles' if include_topfiles else ''}.html")
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
    except ImportError:
        print("Warning: markdown package not installed; HTML reports are not generated.")


# def save_md_html_reports(df_dict, top_files_dict, class_tables, output_dir, prefix, cmd, include_topfiles=False):
#     md_content = f"# ELF Size Comparison Report\n\nExecuted: `{cmd}`\nGenerated: {datetime.now()}\n\n"
#     for mode in df_dict:
#         df = df_dict[mode].copy()
#         for col in ['size1', 'size2', 'diff']:
#             df[col] = df[col].apply(human_readable_size)
#         df['diff_pct'] = df['diff_pct'].map(lambda x: f"{x:.2f}%")
#         md_content += f"## Mode: {mode}\n\n" + md_format_table(df, ['section', 'size1', 'size2', 'diff', 'diff_pct']) + "\n"
#         if not class_tables.get(mode) is None and not class_tables[mode].empty:
#             agg_df = aggregate_classification_by_class(class_tables[mode])
#             md_content += "### Classification Table\n"
#             md_content += md_format_table(agg_df, ['class', 'section name', 'type', 'flags']) + "\n"
#         if include_topfiles:
#             md_content += f"### Top Files ({mode})\n"
#             for sec, files in top_files_dict.get(mode, {}).items():
#                 md_content += f"#### {sec}\n"
#                 rows = []
#                 for (d, fname, status), (s1, s2, diff, pct) in files.items():
#                     rows.append({
#                         'directory': d, 'file': fname, 'status': status,
#                         'size1': human_readable_size(s1),
#                         'size2': human_readable_size(s2),
#                         'diff': human_readable_size(diff),
#                         'diff_pct': f"{pct:.2f}%"
#                     })
#                 if rows:
#                     md_content += md_format_table(pd.DataFrame(rows), ['directory', 'file', 'status', 'size1', 'size2', 'diff', 'diff_pct']) + "\n"
#     with open(os.path.join(output_dir, f"{prefix}{'_topfiles' if include_topfiles else ''}.md"), "w", encoding="utf-8") as f:
#         f.write(md_content)

# --- Main function ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir1")
    ap.add_argument("dir2")
    ap.add_argument("--display-mode", choices=["berkeley", "gnu", "sysv", "all"], default="all")
    ap.add_argument("--exclude-section", nargs="+", default=[])
    ap.add_argument("--user-selected", nargs="+", default=[])
    ap.add_argument("--output-dir", default="out")
    ap.add_argument("--top-n-sections", type=int, default=5)
    ap.add_argument("--top-n-files", type=int, default=10)
    ap.add_argument("--all-files", action="store_true")
    ap.add_argument("--report-type", type=str, default="all",
                    help="Comma separated list to specify reports: section, segment, gnu, berkeley, sysv, all")
    ap.add_argument("--report-prefix", default="report")
    args = ap.parse_args()

    exclude_secs = normalize_user_sections_with_comma(args.exclude_section)
    user_secs = normalize_user_sections_with_comma(args.user_selected)

    d1, d2 = os.path.abspath(args.dir1), os.path.abspath(args.dir2)
    files1, files2 = get_elf_file_list(d1), get_elf_file_list(d2)

    if args.all_files:
        allow1, allow2 = files1, files2
    else:
        common = files1 & files2
        allow1 = {f for f in common if is_elf_file(os.path.join(d1, f))}
        allow2 = {f for f in common if is_elf_file(os.path.join(d2, f))}

    ensure_dir(args.output_dir)
    save_used_files_list(args.output_dir, allow1)
    cmdline = " ".join(sys.argv)

    requested_reports = set(x.strip().lower() for x in args.report_type.split(",") if x.strip())
    if "all" in requested_reports:
        requested_reports = {"section", "segment", "gnu", "berkeley", "sysv"}

    section_report_modes = {"gnu", "berkeley", "sysv"}
    modes_to_report = set()

    for r in requested_reports:
        if r in section_report_modes:
            modes_to_report.add(r)

    if "section" in requested_reports or (not modes_to_report and ("all" in requested_reports or not requested_reports)):
        modes_to_report.update(section_report_modes)

    df_results, top_sections, top_files, class_tables = {}, {}, {}, {}

    if "section" in requested_reports or modes_to_report:
        for mode in sorted(modes_to_report):
            sum1, usr1 = summarize_by_size_multi(d1, mode, None, exclude_secs, False, allow1, user_secs)
            sum2, usr2 = summarize_by_size_multi(d2, mode, None, exclude_secs, False, allow2, user_secs)
            df_main = summarize_by_size_multi_df(sum1, sum2)
            df_user = summarize_by_size_multi_df(usr1, usr2)
            combined = merge_user_selected(df_main, df_user)

            if mode != "sysv":
                for cat in ["text", "data", "bss", "others", "User-Selected"]:
                    if cat == "User-Selected":
                        exists = combined['section'].str.startswith("User-Selected").any()
                    else:
                        exists = (combined['section'] == cat).any()
                    if not exists:
                        combined = pd.concat([combined, pd.DataFrame([{
                            'section': cat,
                            'size1': 0,
                            'size2': 0,
                            'diff': 0,
                            'diff_pct': 0
                        }])], ignore_index=True)



            df_results[mode] = combined
            top_sections[mode] = get_top_sections(combined, args.top_n_sections)

            f1d, _ = summarize_by_size_multi(d1, mode, None, exclude_secs, True, allow1, user_secs)
            f2d, _ = summarize_by_size_multi(d2, mode, None, exclude_secs, True, allow2, user_secs)
            top_files[mode] = get_top_files_per_section(f1d, f2d, args.top_n_files)

            class_tables[mode] = collect_section_classification_table(
                d1, mode, allowed_files=allow1, user_sections=user_secs
            )

            # Draw section diff chart with log y-axis and Top-N boxes
            make_section_diff_chart_with_log_y(
                combined['size1'].tolist(), combined['size2'].tolist(),
                combined['diff'].tolist(), combined['diff_pct'].tolist(),
                combined['section'].tolist(),
                f"{mode} Section Diff",
                os.path.join(args.output_dir, f"{mode}_section_diff.png"),
                top_n=args.top_n_sections
            )

        # Save summary reports - without top files
        save_md_html_reports(
            df_results, top_files, class_tables,
            args.output_dir, args.report_prefix + "_summary", cmdline,
            include_topfiles=False
        )

        # Save detailed top-files reports
        save_md_html_reports(
            df_results, top_files, class_tables,
            args.output_dir, args.report_prefix + "_top_files", cmdline,
            include_topfiles=False
        )
        # Save detailed top-files reports
        save_md_html_reports(
            df_results, top_files, class_tables,
            args.output_dir, args.report_prefix + "_top_files", cmdline,
            include_topfiles=True
        )


    if "segment" in requested_reports or "size" in requested_reports:
        for mode in sorted(modes_to_report) if modes_to_report else ["berkeley", "gnu", "sysv"]:
            prefix = os.path.join(args.output_dir, f"{args.report_prefix}_{mode}")
            save_segment_report_with_sections(d1, d2, allow1, prefix, mode)


if __name__ == "__main__":
    main()
