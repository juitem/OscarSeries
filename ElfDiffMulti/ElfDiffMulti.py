import os
import sys
import argparse
import pandas as pd
from collections import defaultdict
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import P_FLAGS

EXEC_CMDLINE = " ".join(sys.argv)

def human_readable_size(n):
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1024 ** 2:
        return f"{sign}{n / (1024 ** 2):.2f} MB"
    elif n >= 1024:
        return f"{sign}{n / 1024:.2f} KB"
    else:
        return f"{sign}{n} B"

def get_elf_section_sizes_by_file(directory):
    file_section_info = {}
    base = os.path.abspath(directory)
    count = 0
    for root, _, files in os.walk(base, followlinks=False):
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
                            'type': s['sh_type']
                        }
                    rel_path = os.path.relpath(path, base)
                    file_section_info[rel_path] = {
                        'sections': sections,
                        'file_dir': os.path.dirname(rel_path),
                        'file_name': os.path.basename(rel_path)
                    }
                    count += 1
            except:
                continue
    return file_section_info, count

def compare_file_section_sizes(file_data1, file_data2, output_dir, top_n,
                               include_section=None, exclude_section=None,
                               only_common_files=True, print_to_console=True):
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    section_diffs = defaultdict(list)
    file_keys = set(file_data1) | set(file_data2)
    if only_common_files:
        file_keys = set(file_data1) & set(file_data2)
        if print_to_console:
            print(f"📎 Common files only: {len(file_keys)}")
    else:
        if print_to_console:
            print(f"📂 All files: {len(file_keys)}")

    for path in file_keys:
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
                'file_dir': meta1.get('file_dir') or meta2.get('file_dir') or '.',
                'file_name': meta1.get('file_name') or meta2.get('file_name') or path,
                'size1': s1, 'size2': s2, 'diff': diff, 'change_pct': pct
            })

    summary_rows = []
    csv_files = {}

    for sec, rows in section_diffs.items():
        df = pd.DataFrame(rows)
        total_size1 = int(df['size1'].sum())
        total_diff = int(df['diff'].sum())
        total_diff_pct = (total_diff / total_size1 * 100) if total_size1 else 0.0
        avg_change_pct = float(df['change_pct'].mean())
        summary_rows.append({
            'section': sec,
            'total_size1': total_size1,
            'total_size2': int(df['size2'].sum()),
            'total_diff': total_diff,
            'total_diff_pct': total_diff_pct,
            'avg_change_pct': avg_change_pct
        })

        variants = {
            f"top{top_n}_increase": df[df['diff'] > 0].nlargest(top_n, 'diff'),
            f"top{top_n}_decrease": df[df['diff'] < 0].nsmallest(top_n, 'diff'),
            f"top{top_n}_pct_increase": df[df['change_pct'] > 0].nlargest(top_n, 'change_pct'),
            f"top{top_n}_pct_decrease": df[df['change_pct'] < 0].nsmallest(top_n, 'change_pct'),
        }

        for suffix, df_sub in variants.items():
            key = f"{sec.replace('/', '_')}_{suffix}"
            if df_sub.empty:
                continue
            df_sub = df_sub.copy()
            df_sub["Change (%)"] = df_sub["change_pct"].map(lambda x: f"{x:.2f}%" if abs(x) != float("inf") else "∞")
            csv_files[key] = df_sub

            if output_dir:
                csv_path = os.path.join(output_dir, f"{key}.csv")
                df_sub.to_csv(csv_path, index=False)
                print(f"📄 CSV written: {csv_path}")

            if print_to_console:
                print(f"\n[{suffix}] Section: {sec}")
                for _, r in df_sub.iterrows():
                    print(f"  {r['file_dir']}/{r['file_name']}  Δ {r['diff']}  ({r['Change (%)']})")

    return pd.DataFrame(summary_rows), csv_files

def summarize_by_size_compatible(directory):
    result = {'.text': 0, '.data': 0, '.bss': 0}
    for root, _, files in os.walk(directory):
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, 'rb') as f:
                    elf = ELFFile(f)
                    sec_info = []
                    for sec in elf.iter_sections():
                        off = sec['sh_offset']
                        sz = sec['sh_size']
                        sec_info.append((off, off + sz, sec.name, sz))
                    for seg in elf.iter_segments():
                        if seg['p_type'] != 'PT_LOAD':
                            continue
                        flags = seg['p_flags']
                        start = seg['p_offset']
                        end = start + seg['p_filesz']
                        if flags & P_FLAGS.PF_X:
                            for s_start, s_end, name, sz in sec_info:
                                if s_start >= start and s_end <= end:
                                    result['.text'] += sz
                        elif flags & P_FLAGS.PF_W:
                            result['.data'] += seg['p_filesz']
                            if seg['p_memsz'] > seg['p_filesz']:
                                result['.bss'] += seg['p_memsz'] - seg['p_filesz']
            except:
                continue
    return result


import plotly.graph_objects as go

def chart_section_mode(df, outpath):
    df_top = df.sort_values('total_diff', ascending=False).head(10)
    fig = go.Figure([
        go.Bar(name="Total Diff (bytes)", x=df_top['section'], y=df_top['total_diff']),
        go.Bar(name="Total Diff %", x=df_top['section'], y=df_top['total_diff_pct']),
        go.Bar(name="Avg Change %", x=df_top['section'], y=df_top['avg_change_pct']),
    ])
    fig.update_layout(barmode='group', title="Top ELF Sections (By Diff)",
                      xaxis_title="Section", yaxis_title="Size / Percent")
    fig.write_image(outpath)
    print(f"📊 Section-mode bar chart saved: {outpath}")

def chart_size_mode(s1, s2, outpath):
    keys = sorted(set(s1) | set(s2))
    v1 = [s1.get(k, 0) for k in keys]
    v2 = [s2.get(k, 0) for k in keys]
    diff = [b - a for a, b in zip(v1, v2)]
    fig = go.Figure([
        go.Bar(name="Dir1", x=keys, y=v1),
        go.Bar(name="Dir2", x=keys, y=v2),
        go.Bar(name="Diff", x=keys, y=diff),
    ])
    fig.update_layout(barmode='group', title="GNU size-compatible Section Summary",
                      xaxis_title="Section", yaxis_title="Size (bytes)")
    fig.write_image(outpath)
    print(f"📊 Size-mode bar chart saved: {outpath}")

def write_markdown_summary(df, csv_files, path, top_n=10, human=False, chart_path=None):
    def fmt_size(v): return human_readable_size(v) if human else str(v)
    def fmt_pct(v): return f"{v:.2f}%" if isinstance(v, (float, int)) else str(v)
    md = "# 📊 ELF Section Comparison Report\n\n"
    if chart_path and os.path.exists(chart_path):
        md += f"![Bar Chart]({os.path.basename(chart_path)})\n\n"

    def section_table(title, frame):
        out = f"### {title}\n\n"
        out += "| Section | Dir1 | Dir2 | Diff | Diff % | Avg % |\n"
        out += "|---------|------|------|------|--------|--------|\n"
        for _, row in frame.iterrows():
            out += f"| {row['section']} | {fmt_size(row['total_size1'])} | {fmt_size(row['total_size2'])} | {fmt_size(row['total_diff'])} | {fmt_pct(row['total_diff_pct'])} | {fmt_pct(row['avg_change_pct'])} |\n"
        return out

    top_diff = df.sort_values('total_diff', ascending=False).head(top_n)
    top_pct = df[df['total_diff_pct'] > 0].sort_values('total_diff_pct', ascending=False).head(top_n)
    bot_diff = df.sort_values('total_diff').head(top_n)
    bot_pct = df[df['total_diff_pct'] < 0].sort_values('total_diff_pct').head(top_n)

    md += section_table("📈 Top Sections by Diff", top_diff)
    md += section_table("📈 Top Sections by Diff %", top_pct)
    md += section_table("📉 Negative Diff Sections", bot_diff)
    md += section_table("📉 Negative % Sections", bot_pct)
    md += section_table("📋 All Sections Summary", df)

    md += f"\n---\n\n_Command line:_ `{EXEC_CMDLINE}`\n"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"📝 Markdown written to {path}")

def write_size_summary_markdown(summary_pair, path, human=False, chart_path=None):
    def fmt(v): return human_readable_size(v) if human else str(v)
    def pct(a, b): return f"{((b - a)/a * 100):.2f}%" if a > 0 else ("∞" if b > 0 else "0.00%")
    s1, s2 = summary_pair
    keys = sorted(set(s1) | set(s2))
    md = "# 🔍 GNU size-style ELF Summary\n\n"
    md += "> **Note:** .text, .data, .bss columns follow the GNU size utility (gnu-like style) — code/data/bss sections are aggregated per GNU size rules.\n\n"
    if chart_path and os.path.exists(chart_path):
        md += f"![Chart]({os.path.basename(chart_path)})\n\n"
    md += "| Section | Dir1 | Dir2 | Diff | Diff (%) |\n"
    md += "|---------|------|------|------|-----------|\n"
    for k in keys:
        v1, v2 = s1.get(k, 0), s2.get(k, 0)
        md += f"| {k} | {fmt(v1)} | {fmt(v2)} | {fmt(v2 - v1)} | {pct(v1, v2)} |\n"
    md += f"\n---\n\n_Command line:_ `{EXEC_CMDLINE}`\n"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"📝 Size-mode Markdown written to {path}")

def write_html_summary(df, csv_files, path, top_n=10, human=False, chart_path=None):
    def fmt_size(v): return human_readable_size(v) if human else str(v)
    def fmt_pct(v): return f"{v:.2f}%" if isinstance(v, (float, int)) else str(v)
    html = f"<html><head><meta charset='utf-8'><title>ELF Section Report</title></head><body><h1>📊 ELF Section Report</h1>"
    if chart_path and os.path.exists(chart_path):
        html += f'<img src="{os.path.basename(chart_path)}" width="800"/><br/>'

    def section_table(title, frame):
        h = f"<h2>{title}</h2><table border=1><tr><th>Section</th><th>Dir1</th><th>Dir2</th><th>Diff</th><th>Diff %</th><th>Avg %</th></tr>"
        for _, r in frame.iterrows():
            h += f"<tr><td>{r['section']}</td><td>{fmt_size(r['total_size1'])}</td><td>{fmt_size(r['total_size2'])}</td><td>{fmt_size(r['total_diff'])}</td><td>{fmt_pct(r['total_diff_pct'])}</td><td>{fmt_pct(r['avg_change_pct'])}</td></tr>"
        h += "</table><br/>"
        return h

    top_diff = df.sort_values('total_diff', ascending=False).head(top_n)
    top_pct  = df[df['total_diff_pct'] > 0].sort_values('total_diff_pct', ascending=False).head(top_n)
    bot_diff = df.sort_values('total_diff').head(top_n)
    bot_pct  = df[df['total_diff_pct'] < 0].sort_values('total_diff_pct').head(top_n)

    html += section_table("Top Sections by Diff", top_diff)
    html += section_table("Top Sections by Diff %", top_pct)
    html += section_table("Negative Diff Sections", bot_diff)
    html += section_table("Negative % Sections", bot_pct)
    html += section_table("All Sections Summary", df)
    html += f"<hr><p><i>Command line: <code>{EXEC_CMDLINE}</code></i></p></body></html>"

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"🌐 HTML written to {path}")

def write_size_summary_html(summary_pair, path, human=False, chart_path=None):
    def fmt(v): return human_readable_size(v) if human else str(v)
    def pct(a, b): return f"{((b - a) / a * 100):.2f}%" if a > 0 else ("∞" if b > 0 else "0.00%")
    s1, s2 = summary_pair
    keys = sorted(set(s1) | set(s2))
    html = "<html><head><meta charset='utf-8'><title>GNU size-style Summary</title></head><body><h1>🔍 size-compatible Summary</h1>"
    html += "<p><b>Note:</b> .text, .data, .bss columns follow the GNU size utility (gnu-like style) — code/data/bss sections are aggregated per GNU size rules.</p>"
    if chart_path and os.path.exists(chart_path):
        html += f'<img src="{os.path.basename(chart_path)}" width="800"/><br/>'
    html += "<table border=1><tr><th>Section</th><th>Dir1</th><th>Dir2</th><th>Diff</th><th>Diff %</th></tr>"
    for k in keys:
        v1, v2 = s1.get(k, 0), s2.get(k, 0)
        html += f"<tr><td>{k}</td><td>{fmt(v1)}</td><td>{fmt(v2)}</td><td>{fmt(v2 - v1)}</td><td>{pct(v1, v2)}</td></tr>"
    html += f"</table><hr><p><i>Command line: <code>{EXEC_CMDLINE}</code></i></p></body></html>"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"🌐 Size-mode HTML written to {path}")

def write_xlsx_summary(summary_df, csv_files, path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        for name, df in csv_files.items():
            sheet_name = name[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"📊 Excel written to {path}")

def main():
    import io
    import contextlib

    parser = argparse.ArgumentParser(description="Compare ELF section sizes between two directories")

    # Required arguments
    parser.add_argument("dir1", help="Base directory with ELF files")
    parser.add_argument("dir2", help="Target directory with ELF files")

    # Display modes
    parser.add_argument("--display-mode", choices=["section", "size"], default="section",
        help="Comparison mode: 'section' (default) or 'size' (GNU size style)")

    # Top-N options (separated for sections/files)
    parser.add_argument("--top-n-sections", type=int, default=10,
        help="Number of top-level sections to show in reports (default=10)")
    parser.add_argument("--top-n-files", type=int, default=10,
        help="Number of top diff files per section (default=10)")

    # Filtering and CSV output folder
    parser.add_argument("--include-section", nargs="+", help="Only include specified section names")
    parser.add_argument("--exclude-section", nargs="+", help="Exclude specified section names")
    parser.add_argument("--all-files", action="store_true", help="Compare all ELF files (not only those present in both dirs)")
    parser.add_argument("--csv-output-dir", help="Directory to save per-section CSV changes")

    # Console/Log/Output settings
    parser.add_argument("--no-console-output", dest="print_to_console", action="store_false",
        help="Suppress all console print output")
    parser.add_argument("--console-output-file", help="Always save console summary to specified file (even if output is off)")

    # Report output
    parser.add_argument("--summary-markdown", help="Save summary as Markdown file")
    parser.add_argument("--summary-markdown-human", help="Save human-readable Markdown")
    parser.add_argument("--summary-html", help="Save summary as HTML")
    parser.add_argument("--summary-html-human", help="Save human-readable HTML")
    parser.add_argument("--summary-xlsx", help="Save summary and detail as Excel")
    parser.add_argument("--chart-path", default="section_chart.png", help="Bar chart file, section mode")
    parser.add_argument("--chart-path-size", default="size_chart.png", help="Bar chart, size mode")

    args = parser.parse_args()

    dir1 = os.path.abspath(args.dir1)
    dir2 = os.path.abspath(args.dir2)

    file_data1, count1 = get_elf_section_sizes_by_file(dir1)
    file_data2, count2 = get_elf_section_sizes_by_file(dir2)

    # ---- SIZE (GNU-like) mode ----
    if args.display_mode == "size":
        print("🔍 Running in GNU size-compatible analysis...\n")
        sum1 = summarize_by_size_compatible(dir1)
        sum2 = summarize_by_size_compatible(dir2)
        keys = sorted(set(sum1) | set(sum2))

        # Prepare console summary
        console_log = f"{'Section':<10} {'Dir1':>12} {'Dir2':>12} {'Diff':>12}\n"
        console_log += "-" * 48 + "\n"
        for k in keys:
            v1, v2 = sum1.get(k, 0), sum2.get(k, 0)
            console_log += f"{k:<10} {human_readable_size(v1):>12} {human_readable_size(v2):>12} {human_readable_size(v2 - v1):>12}\n"

        if args.print_to_console:
            print(console_log.strip())

        if args.console_output_file:
            with open(args.console_output_file, 'w', encoding='utf-8') as f:
                f.write(console_log)
            print(f"💾 Console summary written to: {args.console_output_file}")

        if args.chart_path_size:
            chart_size_mode(sum1, sum2, args.chart_path_size)
        if args.summary_markdown:
            write_size_summary_markdown((sum1, sum2), args.summary_markdown, human=False, chart_path=args.chart_path_size)
        if args.summary_markdown_human:
            write_size_summary_markdown((sum1, sum2), args.summary_markdown_human, human=True, chart_path=args.chart_path_size)
        if args.summary_html:
            write_size_summary_html((sum1, sum2), args.summary_html, human=False, chart_path=args.chart_path_size)
        if args.summary_html_human:
            write_size_summary_html((sum1, sum2), args.summary_html_human, human=True, chart_path=args.chart_path_size)
        return

    # ---- SECTION mode (default) ----
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
        log_text = buffer.getvalue()
        with open(args.console_output_file, 'w', encoding='utf-8') as f:
            f.write(log_text)
        print(f"💾 Console summary written to: {args.console_output_file}")
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
        write_markdown_summary(summary_df, csv_files, args.summary_markdown, top_n=args.top_n_sections, human=False, chart_path=args.chart_path)
    if args.summary_markdown_human:
        write_markdown_summary(summary_df, csv_files, args.summary_markdown_human, top_n=args.top_n_sections, human=True, chart_path=args.chart_path)
    if args.summary_html:
        write_html_summary(summary_df, csv_files, args.summary_html, top_n=args.top_n_sections, human=False, chart_path=args.chart_path)
    if args.summary_html_human:
        write_html_summary(summary_df, csv_files, args.summary_html_human, top_n=args.top_n_sections, human=True, chart_path=args.chart_path)
    if args.summary_xlsx:
        write_xlsx_summary(summary_df, csv_files, args.summary_xlsx)

    print(f"\n📦 Parsed {count1} files in dir1, {count2} in dir2.")
    if args.csv_output_dir:
        print(f"📁 CSV data saved to: {os.path.abspath(args.csv_output_dir)}")

if __name__ == "__main__":
    main()
