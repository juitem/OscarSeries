import os
import sys
import argparse
import pandas as pd
from collections import defaultdict
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import P_FLAGS
from datetime import datetime

EXEC_CMDLINE = " ".join(sys.argv)
NOW_TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def human_readable_size(n):
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1024 ** 2:
        return f"{sign}{n / 1024 ** 2:.2f} MB"
    elif n >= 1024:
        return f"{sign}{n / 1024:.2f} KB"
    else:
        return f"{sign}{n} B"

def get_elf_section_sizes_by_file(directory):
    info = {}
    base = os.path.abspath(directory)
    count = 0

    for root, _, files in os.walk(base):
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, 'rb') as f:
                    elf = ELFFile(f)
                    sections = {}
                    for s in elf.iter_sections():
                        sections[s.name] = {
                            'size': s['sh_size'],
                            'flags': s['sh_flags'],
                            'type': s['sh_type'],
                        }
                    rel = os.path.relpath(path, base)
                    info[rel] = {
                        'sections': sections,
                        'file_dir': os.path.dirname(rel),
                        'file_name': os.path.basename(rel),
                    }
                    count += 1
            except:
                continue

    return info, count

def compare_file_section_sizes(file_data1, file_data2, output_dir, top_n,
                               include_section=None, exclude_section=None,
                               only_common_files=True, print_to_console=True):
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    section_diffs = defaultdict(list)
    files = set(file_data1) & set(file_data2) if only_common_files else set(file_data1) | set(file_data2)

    for path in files:
        sec1 = file_data1.get(path, {}).get('sections', {})
        sec2 = file_data2.get(path, {}).get('sections', {})
        meta1 = file_data1.get(path, {})
        meta2 = file_data2.get(path, {})

        for sec in set(sec1) | set(sec2):
            if include_section and sec not in include_section:
                continue
            if exclude_section and sec in exclude_section:
                continue

            s1 = sec1.get(sec, {}).get('size', 0)
            s2 = sec2.get(sec, {}).get('size', 0)
            diff = s2 - s1
            pct = (diff / s1 * 100.0) if s1 > 0 else (100.0 if s2 > 0 else 0.0)

            section_diffs[sec].append({
                'file_dir': meta1.get('file_dir') or meta2.get('file_dir'),
                'file_name': meta1.get('file_name') or meta2.get('file_name'),
                'size1': s1,
                'size2': s2,
                'diff': diff,
                'change_pct': pct
            })

    summary_rows = []
    csv_files = {}

    for sec, rows in section_diffs.items():
        df = pd.DataFrame(rows)
        total_size1 = df['size1'].sum()
        total_diff = df['diff'].sum()
        total_diff_pct = (total_diff / total_size1 * 100.0) if total_size1 > 0 else 0.0
        avg_pct = df['change_pct'].mean()

        summary_rows.append({
            'section': sec,
            'total_size1': int(total_size1),
            'total_size2': int(df['size2'].sum()),
            'total_diff': int(total_diff),
            'total_diff_pct': total_diff_pct,
            'avg_change_pct': avg_pct
        })

        variants = {
            f"top{top_n}_increase": df[df['diff'] > 0].nlargest(top_n, 'diff'),
            f"top{top_n}_decrease": df[df['diff'] < 0].nsmallest(top_n, 'diff'),
            f"top{top_n}_pct_increase": df[df['change_pct'] > 0].nlargest(top_n, 'change_pct'),
            f"top{top_n}_pct_decrease": df[df['change_pct'] < 0].nsmallest(top_n, 'change_pct'),
        }

        for key, df_sub in variants.items():
            if df_sub.empty:
                continue
            df_sub = df_sub.copy()
            df_sub['Change (%)']  = df_sub['change_pct'].map(lambda x: f"{x:.2f}%" if abs(x) < float("inf") else "∞")
            df_sub['Dir1 (HR)']   = df_sub['size1'].map(human_readable_size)
            df_sub['Dir2 (HR)']   = df_sub['size2'].map(human_readable_size)
            df_sub['Diff (HR)']   = df_sub['diff'].map(human_readable_size)

            key_id = f"{sec.replace('/', '_')}_{key}"
            csv_files[key_id] = df_sub

            if output_dir:
                out_path = os.path.join(output_dir, f"{key_id}.csv")
                df_sub.to_csv(out_path, index=False)
                print(f" CSV written to: {out_path}")

            if print_to_console:
                print(f"\n[{key}] Section: {sec}")
                for _, r in df_sub.iterrows():
                    print(f"  {r['file_dir']}/{r['file_name']} Δ {r['diff']} ({r['Change (%)']})")

    summary_df = pd.DataFrame(summary_rows)
    return summary_df, csv_files

def compare_file_section_sizes(file_data1, file_data2, output_dir, top_n,
                               include_section=None, exclude_section=None,
                               only_common_files=True, print_to_console=True):
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    section_diffs = defaultdict(list)
    files = set(file_data1) & set(file_data2) if only_common_files else set(file_data1) | set(file_data2)

    for path in files:
        sec1 = file_data1.get(path, {}).get('sections', {})
        sec2 = file_data2.get(path, {}).get('sections', {})
        meta1 = file_data1.get(path, {})
        meta2 = file_data2.get(path, {})

        for sec in set(sec1) | set(sec2):
            if include_section and sec not in include_section:
                continue
            if exclude_section and sec in exclude_section:
                continue

            s1 = sec1.get(sec, {}).get('size', 0)
            s2 = sec2.get(sec, {}).get('size', 0)
            diff = s2 - s1
            pct = (diff / s1 * 100.0) if s1 > 0 else (100.0 if s2 > 0 else 0.0)

            section_diffs[sec].append({
                'file_dir': meta1.get('file_dir') or meta2.get('file_dir'),
                'file_name': meta1.get('file_name') or meta2.get('file_name'),
                'size1': s1,
                'size2': s2,
                'diff': diff,
                'change_pct': pct
            })

    summary_rows = []
    csv_files = {}

    for sec, rows in section_diffs.items():
        df = pd.DataFrame(rows)
        total_size1 = df['size1'].sum()
        total_diff = df['diff'].sum()
        total_diff_pct = (total_diff / total_size1 * 100.0) if total_size1 > 0 else 0.0
        avg_pct = df['change_pct'].mean()

        summary_rows.append({
            'section': sec,
            'total_size1': int(total_size1),
            'total_size2': int(df['size2'].sum()),
            'total_diff': int(total_diff),
            'total_diff_pct': total_diff_pct,
            'avg_change_pct': avg_pct
        })

        variants = {
            f"top{top_n}_increase": df[df['diff'] > 0].nlargest(top_n, 'diff'),
            f"top{top_n}_decrease": df[df['diff'] < 0].nsmallest(top_n, 'diff'),
            f"top{top_n}_pct_increase": df[df['change_pct'] > 0].nlargest(top_n, 'change_pct'),
            f"top{top_n}_pct_decrease": df[df['change_pct'] < 0].nsmallest(top_n, 'change_pct'),
        }

        for key, df_sub in variants.items():
            if df_sub.empty:
                continue
            df_sub = df_sub.copy()
            df_sub['Change (%)']  = df_sub['change_pct'].map(lambda x: f"{x:.2f}%" if abs(x) < float("inf") else "∞")
            df_sub['Dir1 (HR)']   = df_sub['size1'].map(human_readable_size)
            df_sub['Dir2 (HR)']   = df_sub['size2'].map(human_readable_size)
            df_sub['Diff (HR)']   = df_sub['diff'].map(human_readable_size)

            key_id = f"{sec.replace('/', '_')}_{key}"
            csv_files[key_id] = df_sub

            if output_dir:
                out_path = os.path.join(output_dir, f"{key_id}.csv")
                df_sub.to_csv(out_path, index=False)
                print(f" CSV written to: {out_path}")

            if print_to_console:
                print(f"\n[{key}] Section: {sec}")
                for _, r in df_sub.iterrows():
                    print(f"  {r['file_dir']}/{r['file_name']} Δ {r['diff']} ({r['Change (%)']})")

    summary_df = pd.DataFrame(summary_rows)
    return summary_df, csv_files

## PART 1-3: summarize_by_size_compatible()

def summarize_by_size_compatible(directory):
    result = {
        '.text': 0,
        '.data': 0,
        '.bss': 0
    }

    for root, _, files in os.walk(directory):
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, 'rb') as f:
                    elf = ELFFile(f)

                    section_info = []
                    for sec in elf.iter_sections():
                        off = sec['sh_offset']
                        sz = sec['sh_size']
                        section_info.append((off, off + sz, sec.name, sz))

                    for seg in elf.iter_segments():
                        if seg['p_type'] != 'PT_LOAD':
                            continue
                        flags = seg['p_flags']
                        start = seg['p_offset']
                        end = start + seg['p_filesz']

                        if flags & P_FLAGS.PF_X:
                            for s_start, s_end, name, sz in section_info:
                                if s_start >= start and s_end <= end:
                                    result['.text'] += sz
                        elif flags & P_FLAGS.PF_W:
                            result['.data'] += seg['p_filesz']
                            if seg['p_memsz'] > seg['p_filesz']:
                                result['.bss'] += seg['p_memsz'] - seg['p_filesz']
            except:
                continue

    return result

def summarize_by_size_compatible_df(sum1, sum2):
    records = []
    keys = sorted(set(sum1) | set(sum2))
    for k in keys:
        v1 = sum1.get(k, 0)
        v2 = sum2.get(k, 0)
        diff = v2 - v1
        pct = (diff / v1 * 100.0) if v1 > 0 else (100.0 if v2 > 0 else 0.0)
        records.append({
            'section': k,
            'size1': v1,
            'size2': v2,
            'diff': diff,
            'diff_pct': pct
        })
    return pd.DataFrame(records)


import plotly.graph_objects as go

def chart_section_mode(df, outpath):
    df_top = df.sort_values('total_diff', ascending=False).head(10)

    fig = go.Figure([
        go.Bar(name="Total Diff", x=df_top['section'], y=df_top['total_diff']),
        go.Bar(name="Diff %", x=df_top['section'], y=df_top['total_diff_pct']),
        go.Bar(name="Avg Change %", x=df_top['section'], y=df_top['avg_change_pct']),
    ])

    fig.update_layout(
        title="Top ELF Sections by Total Diff",
        barmode="group",
        xaxis_title="Section",
        yaxis_title="Bytes / %"
    )

    fig.write_image(outpath)
    print(f" Section diff chart saved to: {outpath}")

## PART 2-2: chart_size_mode()

def chart_size_mode(sum1, sum2, outpath):
    keys = sorted(set(sum1) | set(sum2))
    v1 = [sum1.get(k, 0) for k in keys]
    v2 = [sum2.get(k, 0) for k in keys]
    diff = [b - a for a, b in zip(v1, v2)]

    fig = go.Figure([
        go.Bar(name="Dir1", x=keys, y=v1),
        go.Bar(name="Dir2", x=keys, y=v2),
        go.Bar(name="Diff", x=keys, y=diff),
    ])

    fig.update_layout(
        title="Section Size Comparison (GNU-style)",
        barmode="group",
        xaxis_title="Section",
        yaxis_title="Bytes"
    )

    fig.write_image(outpath)
    print(f" Size chart saved to: {outpath}")

# PART 2-3: Size 모드 리포트 함수


## write_size_summary_markdown()

def write_size_summary_markdown(df, path, top_n=5, human=False):
    def fmt_size(n): return human_readable_size(n) if human else str(n)
    def fmt_pct(p): return f"{p:.2f}%" if isinstance(p, (float, int)) else str(p)

    md = f"# ELF Size Comparison Report (GNU-style)\n\n"
    md += f"- Generated: `{NOW_TIMESTAMP}`\n"
    md += f"- Command: `{EXEC_CMDLINE}`\n\n"

    top = df[df["diff"] > 0].sort_values("diff", ascending=False).head(top_n)
    bottom = df[df["diff"] < 0].sort_values("diff").head(top_n)

    md += f"## Top {top_n} Sections by Increase\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in top.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    md += f"\n## Top {top_n} Sections by Decrease\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in bottom.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    md += "\n## All Sections Summary\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in df.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f" Size mode Markdown report saved to: {path}")

def write_size_summary_html(df, path, top_n=5, human=False):
    def fmt_size(n): return human_readable_size(n) if human else str(n)
    def fmt_pct(p): return f"{p:.2f}%" if isinstance(p, (float, int)) else str(p)

    html = "<html><head><meta charset='utf-8'><title>ELF Size Report</title></head><body>\n"
    html += "<h1> ELF Size Comparison Report (GNU-style)</h1>\n"
    html += f"<p><b>Generated:</b> {NOW_TIMESTAMP}<br/>\n<b>Command:</b> <code>{EXEC_CMDLINE}</code></p>\n"

    def table(title, subset):
        h = f"<h2>{title}</h2>\n"
        h += "<table border='1'><tr><th>Section</th><th>Dir1</th><th>Dir2</th><th>Diff</th><th>Diff %</th></tr>\n"
        for _, r in subset.iterrows():
            h += f"<tr><td>{r['section']}</td><td>{fmt_size(r['size1'])}</td><td>{fmt_size(r['size2'])}</td><td>{fmt_size(r['diff'])}</td><td>{fmt_pct(r['diff_pct'])}</td></tr>\n"
        h += "</table><br/>\n"
        return h

    top = df[df["diff"] > 0].sort_values("diff", ascending=False).head(top_n)
    bottom = df[df["diff"] < 0].sort_values("diff").head(top_n)

    html += table(f" Top {top_n} Sections by Increase", top)
    html += table(f" Top {top_n} Sections by Decrease", bottom)
    html += table(" All Sections Summary", df)

    html += f"<hr><p><i>Generated: {NOW_TIMESTAMP}<br/>Command: <code>{EXEC_CMDLINE}</code></i></p></body></html>"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f" Size mode HTML report saved to: {path}")

def write_section_top_file_report_md(csv_files, path, top_n=10):
    from collections import defaultdict

    md = f"# ELF Per Section Top Comparison Report\n\n"
    md += f"- Generated: `{NOW_TIMESTAMP}`\n"
    md += f"- Command: `{EXEC_CMDLINE}`\n\n"

    grouped = defaultdict(list)
    for key, df in csv_files.items():
        if not key.endswith(f"top{top_n}_increase"):
            continue
        section = key.replace(f"_top{top_n}_increase", "").replace("_", "/")
        grouped[section].append(df)

    for sec in sorted(grouped):
        md += f"## Section `{sec}`\n\n"
        for df_sub in grouped[sec]:
            md += f"Top {top_n} increased ELF files by size:\n\n"
            md += "| File | Dir | Dir1 (HR) | Dir2 (HR) | Diff (HR) | Change (%) |\n"
            md += "|------|-----|------------|------------|------------|--------------|\n"
            for _, r in df_sub.iterrows():
                md += f"| {r['file_name']} | {r['file_dir']} | {r['Dir1 (HR)']} | {r['Dir2 (HR)']} | {r['Diff (HR)']} | {r['Change (%)']} |\n"
            md += "\n"

    md += "---\n This report lists top changed files per section.\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f" Top files per section (Markdown) saved to: {path}")

def write_section_top_file_report_html(csv_files, path, top_n=10):
    from collections import defaultdict

    html = "<html><head><meta charset='utf-8'><title>Top Files per Section</title></head><body>\n"
    html += "<h1> ELF Per Section Top Comparison Report</h1>\n"
    html += f"<p><b>Generated:</b> {NOW_TIMESTAMP}<br/>\n<b>Command:</b> <code>{EXEC_CMDLINE}</code></p>\n"

    grouped = defaultdict(list)
    for key, df in csv_files.items():
        if not key.endswith(f"top{top_n}_increase"):
            continue
        section = key.replace(f"_top{top_n}_increase", "").replace("_", "/")
        grouped[section].append(df)

    for sec in sorted(grouped):
        html += f"<h2> Section <code>{sec}</code></h2>\n"
        for df_sub in grouped[sec]:
            html += "<p>Top increased files by size:</p>\n"
            html += "<table border='1'><tr><th>File</th><th>Dir</th><th>Dir1 (HR)</th><th>Dir2 (HR)</th><th>Diff (HR)</th><th>Change (%)</th></tr>\n"
            for _, r in df_sub.iterrows():
                html += f"<tr><td>{r['file_name']}</td><td>{r['file_dir']}</td><td>{r['Dir1 (HR)']}</td><td>{r['Dir2 (HR)']}</td><td>{r['Diff (HR)']}</td><td>{r['Change (%)']}</td></tr>\n"
            html += "</table><br/>\n"

    html += f"<hr><p><i>Generated: {NOW_TIMESTAMP}<br/>Command: <code>{EXEC_CMDLINE}</code></i></p></body></html>"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f" Top files per section (HTML) saved to: {path}")

# PART 2-3: Size mode report

## write_size_summary_markdown()

def write_size_summary_markdown(df, path, top_n=5, human=False):
    def fmt_size(n): return human_readable_size(n) if human else str(n)
    def fmt_pct(p): return f"{p:.2f}%" if isinstance(p, (float, int)) else str(p)

    md = f"# ELF Size Comparison Report (GNU-style)\n\n"
    md += f"- Generated: `{NOW_TIMESTAMP}`\n"
    md += f"- Command: `{EXEC_CMDLINE}`\n\n"

    top = df[df["diff"] > 0].sort_values("diff", ascending=False).head(top_n)
    bottom = df[df["diff"] < 0].sort_values("diff").head(top_n)

    md += f"## Top {top_n} Sections by Increase\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in top.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    md += f"\n## Top {top_n} Sections by Decrease\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in bottom.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    md += "\n## All Sections Summary\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff % |\n"
    md += "|---------|------|------|------|--------|\n"
    for _, r in df.iterrows():
        md += f"| {r['section']} | {fmt_size(r['size1'])} | {fmt_size(r['size2'])} | {fmt_size(r['diff'])} | {fmt_pct(r['diff_pct'])} |\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f" Size mode Markdown report saved to: {path}")

def write_size_summary_html(df, path, top_n=5, human=False):
    def fmt_size(n): return human_readable_size(n) if human else str(n)
    def fmt_pct(p): return f"{p:.2f}%" if isinstance(p, (float, int)) else str(p)

    html = "<html><head><meta charset='utf-8'><title>ELF Size Report</title></head><body>\n"
    html += "<h1> ELF Size Comparison Report (GNU-style)</h1>\n"
    html += f"<p><b>Generated:</b> {NOW_TIMESTAMP}<br/>\n<b>Command:</b> <code>{EXEC_CMDLINE}</code></p>\n"

    def table(title, subset):
        h = f"<h2>{title}</h2>\n"
        h += "<table border='1'><tr><th>Section</th><th>Dir1</th><th>Dir2</th><th>Diff</th><th>Diff %</th></tr>\n"
        for _, r in subset.iterrows():
            h += f"<tr><td>{r['section']}</td><td>{fmt_size(r['size1'])}</td><td>{fmt_size(r['size2'])}</td><td>{fmt_size(r['diff'])}</td><td>{fmt_pct(r['diff_pct'])}</td></tr>\n"
        h += "</table><br/>\n"
        return h

    top = df[df["diff"] > 0].sort_values("diff", ascending=False).head(top_n)
    bottom = df[df["diff"] < 0].sort_values("diff").head(top_n)

    html += table(f" Top {top_n} Sections by Increase", top)
    html += table(f" Top {top_n} Sections by Decrease", bottom)
    html += table(" All Sections Summary", df)

    html += f"<hr><p><i>Generated: {NOW_TIMESTAMP}<br/>Command: <code>{EXEC_CMDLINE}</code></i></p></body></html>"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f" Size mode HTML report saved to: {path}")

def write_section_top_file_report_md(csv_files, path, top_n=10):
    from collections import defaultdict

    md = f"# ELF Per Section Top Comparison Report\n\n"
    md += f"- Generated: `{NOW_TIMESTAMP}`\n"
    md += f"- Command: `{EXEC_CMDLINE}`\n\n"

    grouped = defaultdict(list)
    for key, df in csv_files.items():
        if not key.endswith(f"top{top_n}_increase"):
            continue
        section = key.replace(f"_top{top_n}_increase", "").replace("_", "/")
        grouped[section].append(df)

    for sec in sorted(grouped):
        md += f"## Section `{sec}`\n\n"
        for df_sub in grouped[sec]:
            md += f"Top {top_n} increased ELF files by size:\n\n"
            md += "| File | Dir | Dir1 (HR) | Dir2 (HR) | Diff (HR) | Change (%) |\n"
            md += "|------|-----|------------|------------|------------|--------------|\n"
            for _, r in df_sub.iterrows():
                md += f"| {r['file_name']} | {r['file_dir']} | {r['Dir1 (HR)']} | {r['Dir2 (HR)']} | {r['Diff (HR)']} | {r['Change (%)']} |\n"
            md += "\n"

    md += "---\n This report lists top changed files per section.\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f" Top files per section (Markdown) saved to: {path}")

def write_section_top_file_report_html(csv_files, path, top_n=10):
    from collections import defaultdict

    html = "<html><head><meta charset='utf-8'><title>Top Files per Section</title></head><body>\n"
    html += "<h1> ELF Per Section Top Comparison Report</h1>\n"
    html += f"<p><b>Generated:</b> {NOW_TIMESTAMP}<br/>\n<b>Command:</b> <code>{EXEC_CMDLINE}</code></p>\n"

    grouped = defaultdict(list)
    for key, df in csv_files.items():
        if not key.endswith(f"top{top_n}_increase"):
            continue
        section = key.replace(f"_top{top_n}_increase", "").replace("_", "/")
        grouped[section].append(df)

    for sec in sorted(grouped):
        html += f"<h2> Section <code>{sec}</code></h2>\n"
        for df_sub in grouped[sec]:
            html += "<p>Top increased files by size:</p>\n"
            html += "<table border='1'><tr><th>File</th><th>Dir</th><th>Dir1 (HR)</th><th>Dir2 (HR)</th><th>Diff (HR)</th><th>Change (%)</th></tr>\n"
            for _, r in df_sub.iterrows():
                html += f"<tr><td>{r['file_name']}</td><td>{r['file_dir']}</td><td>{r['Dir1 (HR)']}</td><td>{r['Dir2 (HR)']}</td><td>{r['Diff (HR)']}</td><td>{r['Change (%)']}</td></tr>\n"
            html += "</table><br/>\n"

    html += f"<hr><p><i>Generated: {NOW_TIMESTAMP}<br/>Command: <code>{EXEC_CMDLINE}</code></i></p></body></html>"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f" Top files per section (HTML) saved to: {path}")

def main():
    import io
    import contextlib

    parser = argparse.ArgumentParser(description="Compare ELF section sizes between two directories")

    parser.add_argument("dir1", help="Base directory with ELF files")
    parser.add_argument("dir2", help="Target directory with ELF files")

    parser.add_argument("--display-mode", choices=["section", "size"], default="section",
                        help="Comparison mode: 'section' (default) or 'size'")

    parser.add_argument("--top-n-sections", type=int, default=10, help="Top N sections to display")
    parser.add_argument("--top-n-files", type=int, default=10, help="Top N files per section")

    parser.add_argument("--include-section", nargs="+", help="Only include specified sections")
    parser.add_argument("--exclude-section", nargs="+", help="Exclude specified sections")
    parser.add_argument("--all-files", action="store_true", help="Compare all ELF files, not just common")

    parser.add_argument("--csv-output-dir", help="Directory to store CSVs")
    parser.add_argument("--no-console-output", dest="print_to_console", action="store_false",
                        help="Suppress printing to stdout")
    parser.add_argument("--console-output-file", help="Save text output to file")

    parser.add_argument("--summary-markdown", help="Markdown report path")
    parser.add_argument("--summary-markdown-human", help="Human-readable Markdown")
    parser.add_argument("--summary-html", help="HTML report path")
    parser.add_argument("--summary-html-human", help="Human-readable HTML")
    parser.add_argument("--summary-xlsx", help="Excel report path")

    parser.add_argument("--chart-path", default="chart.png", help="Section chart path")
    parser.add_argument("--chart-path-size", default="size_chart.png", help="Size mode chart path")

    parser.add_argument("--top-section-report-markdown", help="Markdown per section top file report")
    parser.add_argument("--top-section-report-html", help="HTML per section top file report")

    args = parser.parse_args()

    dir1 = os.path.abspath(args.dir1)
    dir2 = os.path.abspath(args.dir2)

    file_data1, count1 = get_elf_section_sizes_by_file(dir1)
    file_data2, count2 = get_elf_section_sizes_by_file(dir2)

    if args.display_mode == "size":
        sum1 = summarize_by_size_compatible(dir1)
        sum2 = summarize_by_size_compatible(dir2)
        df = summarize_by_size_compatible_df(sum1, sum2)

        if args.print_to_console:
            print("\nGNU SizeLike     Dir1        Dir2        Diff        Diff %")
            print("-" * 58)
            for _, row in df.iterrows():
                print(f"{row['section']:<10} {human_readable_size(row['size1']):>10} "
                      f"{human_readable_size(row['size2']):>10} {human_readable_size(row['diff']):>10} "
                      f"{row['diff_pct']:>9.2f}%")

        if args.console_output_file:
            with open(args.console_output_file, "w", encoding="utf-8") as f:
                f.write(df.to_string(index=False))
                f.write(f"\n\nGenerated: {NOW_TIMESTAMP}\nCommand: {EXEC_CMDLINE}\n")
            print(f" Console log saved to: {args.console_output_file}")

        if args.chart_path_size:
            chart_size_mode(sum1, sum2, args.chart_path_size)

        if args.summary_markdown:
            write_size_summary_markdown(df, args.summary_markdown, top_n=args.top_n_sections, human=False)
        if args.summary_markdown_human:
            write_size_summary_markdown(df, args.summary_markdown_human, top_n=args.top_n_sections, human=True)
        if args.summary_html:
            write_size_summary_html(df, args.summary_html, top_n=args.top_n_sections, human=False)
        if args.summary_html_human:
            write_size_summary_html(df, args.summary_html_human, top_n=args.top_n_sections, human=True)
        if args.summary_xlsx:
            with pd.ExcelWriter(args.summary_xlsx, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Summary", index=False)
                sheet = writer.book["Summary"]
                sheet.insert_rows(1)
                sheet["A1"] = f"Generated: {NOW_TIMESTAMP}"
                sheet.insert_rows(2)
                sheet["A2"] = f"Command: {EXEC_CMDLINE}"
            print(f" Excel saved to: {args.summary_xlsx}")
        return

    # Section mode
    if args.console_output_file:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            summary_df, csv_files = compare_file_section_sizes(
                file_data1, file_data2,
                output_dir=args.csv_output_dir,
                top_n=args.top_n_files,
                include_section=args.include_section,
                exclude_section=args.exclude_section,
                only_common_files=not args.all_files,
                print_to_console=args.print_to_console
            )
        log_output = buffer.getvalue()
        with open(args.console_output_file, "w", encoding="utf-8") as f:
            f.write(log_output)
            f.write(f"\n\nGenerated: {NOW_TIMESTAMP}\nCommand: {EXEC_CMDLINE}\n")
        print(f" Console output saved to: {args.console_output_file}")
    else:
        summary_df, csv_files = compare_file_section_sizes(
            file_data1, file_data2,
            output_dir=args.csv_output_dir,
            top_n=args.top_n_files,
            include_section=args.include_section,
            exclude_section=args.exclude_section,
            only_common_files=not args.all_files,
            print_to_console=args.print_to_console
        )

    if args.chart_path:
        chart_section_mode(summary_df, args.chart_path)

    if args.summary_markdown:
        write_markdown_summary(summary_df, csv_files, args.summary_markdown,
                               top_n=args.top_n_sections, human=False, chart_path=args.chart_path)
    if args.summary_markdown_human:
        write_markdown_summary(summary_df, csv_files, args.summary_markdown_human,
                               top_n=args.top_n_sections, human=True, chart_path=args.chart_path)
    if args.summary_html:
        write_html_summary(summary_df, csv_files, args.summary_html,
                           top_n=args.top_n_sections, human=False, chart_path=args.chart_path)
    if args.summary_html_human:
        write_html_summary(summary_df, csv_files, args.summary_html_human,
                           top_n=args.top_n_sections, human=True, chart_path=args.chart_path)
    if args.summary_xlsx:
        write_xlsx_summary(summary_df, csv_files, args.summary_xlsx)

    if args.top_section_report_markdown:
        write_section_top_file_report_md(csv_files, args.top_section_report_markdown, top_n=args.top_n_files)
    if args.top_section_report_html:
        write_section_top_file_report_html(csv_files, args.top_section_report_html, top_n=args.top_n_files)

    print(f"\n Compared {count1} ELF files in dir1, {count2} in dir2.")
    if args.csv_output_dir:
        print(f" CSV written to: {os.path.abspath(args.csv_output_dir)}")

if __name__ == "__main__":
    main()
