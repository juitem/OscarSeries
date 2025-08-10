#!/usr/bin/env python3
import os, sys, argparse
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

# --- Utilities ---
def human_readable_size(n):
    try: n=int(n)
    except (ValueError,TypeError): return str(n)
    sign="-" if n<0 else ""; n=abs(n)
    if n>=1024**2: return f"{sign}{n/1024**2:.2f} MB"
    if n>=1024: return f"{sign}{n/1024:.2f} KB"
    return f"{sign}{n} B"

def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def save_used_files_list(output_dir, file_set, filename="used_files.txt"):
    ensure_dir(output_dir)
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        for fname in sorted(file_set):
            f.write(fname + "\n")
    print(f"Saved used files list: {os.path.join(output_dir, filename)}")

def normalize_user_sections(raw_list):
    sections = set()
    for item in (raw_list or []):
        for token in item.replace(",", " ").split():
            token = token.strip()
            if token:
                sections.add(token)
    return sections

# --- ELF helpers ---
def get_elf_file_list(directory):
    return {os.path.relpath(os.path.join(r, f), directory)
            for r, _, fs in os.walk(directory)
            for f in fs if not os.path.islink(os.path.join(r, f))}

def is_elf_file(path):
    try:
        with open(path, 'rb') as f:
            ELFFile(f)
        return True
    except ELFError:
        return False
    except:
        return False

# --- Section Classification ---
def classify_section(mode, stype, sflag, sname):
    A, W, X = bool(sflag & 0x2), bool(sflag & 0x1), bool(sflag & 0x4)
    PROGBITS, NOBITS = (stype == 'SHT_PROGBITS'), (stype == 'SHT_NOBITS')
    if mode == "berkeley":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and not X and not W: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        return "Others", stype
    elif mode == "gnu":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        return "Others", stype
    elif mode == "sysv":
        return sname, stype
    return "Others", stype

# --- Summary Data Collection ---
def summarize_by_size_multi(d, mode, include=None, exclude=None, file_level=False,
                            allowed_files=None, user_sections=None):
    user_sections = set(user_sections or [])
    result, user_result = {}, {}
    for root, _, files in os.walk(d):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full): continue
            rel = os.path.relpath(full, d)
            if allowed_files and rel not in allowed_files: continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        sname = sec.name
                        stype = sec.header['sh_type']
                        sflag = sec.header['sh_flags']
                        sz = sec.header['sh_size']
                        if include and sname not in include: continue
                        if exclude and sname in exclude: continue
                        cls, _ = classify_section(mode, stype, sflag, sname)
                        key = sname if mode == "sysv" else cls
                        if file_level:
                            result.setdefault(key, {})
                            result[key][rel] = result[key].get(rel, 0) + sz
                        else:
                            result[key] = result.get(key, 0) + sz
                        if sname in user_sections:
                            if file_level:
                                user_result.setdefault(sname, {})
                                user_result[sname][rel] = user_result[sname].get(rel, 0) + sz
                            else:
                                user_result[sname] = user_result.get(sname, 0) + sz
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

# def merge_user_selected(df_main, df_user):
#     if df_user.empty:
#         return df_main
def merge_user_selected(df_main, df_user):
    if df_user.empty:
        return df_main
    total_size1 = df_user['size1'].sum()
    total_size2 = df_user['size2'].sum()
    total_diff  = df_user['diff'].sum()
    total_pct   = (total_diff / total_size1 * 100.0) if total_size1 else (100.0 if total_size2 else 0.0)
    section_list = sorted(df_user['section'].unique())
    user_row = {
        'section': f"User-Selected ({', '.join(section_list)})",
        'size1': total_size1,
        'size2': total_size2,
        'diff': total_diff,
        'diff_pct': total_pct
    }
    return pd.concat([df_main, pd.DataFrame([user_row])], ignore_index=True)


#####
    # user-selected 섹션 중 실제 값 있는 것만 필터링
    user_secs_with_data = set(df_user.loc[(df_user['size1'] > 0) | (df_user['size2'] > 0), 'section'].unique())
    filtered_main = df_main[~df_main['section'].isin(user_secs_with_data)]

    total_size1 = df_user['size1'].sum()
    total_size2 = df_user['size2'].sum()
    total_diff  = df_user['diff'].sum()
    total_pct   = (total_diff / total_size1 * 100.0) if total_size1 else (100.0 if total_size2 else 0.0)
    section_list = sorted(user_secs_with_data) if user_secs_with_data else sorted(df_user['section'].unique())
    user_row = {
        'section': f"User-Selected ({', '.join(section_list)})",
        'size1': total_size1,
        'size2': total_size2,
        'diff': total_diff,
        'diff_pct': total_pct
    }
    return pd.concat([filtered_main, pd.DataFrame([user_row])], ignore_index=True)

# --- Classification Table with Deduplication ---
def collect_section_classification_table(d, mode, allowed_files=None, user_sections=None):
    """Collect sections classification. Removes duplicate by showing only User-Selected row if matched."""
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
                        # If section is user-selected, skip adding original class row
                        if sec.name in user_sections:
                            rows.append({
                                "section": sec.name,
                                "class": f"User-Selected ({sec.name})",
                                "type": sec.header['sh_type'],
                                "flags": f"0x{sec.header['sh_flags']:x}"
                            })
                        else:
                            cls, _ = classify_section(mode, sec.header['sh_type'], sec.header['sh_flags'], sec.name)
                            rows.append({
                                "section": sec.name,
                                "class": cls,
                                "type": sec.header['sh_type'],
                                "flags": f"0x{sec.header['sh_flags']:x}"
                            })
            except:
                continue
    return pd.DataFrame(rows)


def aggregate_classification_by_class(df):
    if df.empty:
        return df
    return df.groupby('class').agg({
        'section': lambda x: ', '.join(sorted(set(x))),
        'type': lambda x: ', '.join(sorted(set(str(i) for i in x))),
        'flags': lambda x: ', '.join(sorted(set(str(i) for i in x)))
    }).reset_index()

# --- Category mapping ---
def get_category_section_map(d, mode, allowed_files=None, user_sections=None):
    cat_map = {}
    user_sections = set(user_sections or [])
    for root, _, files in os.walk(d):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full): continue
            rel = os.path.relpath(full, d)
            if allowed_files and rel not in allowed_files: continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        sname = sec.name
                        stype = sec.header['sh_type']
                        sflag = sec.header['sh_flags']
                        cls, _ = classify_section(mode, stype, sflag, sname)
                        if sname in user_sections:
                            cat_map.setdefault("User-Selected", set()).add(sname)
                        else:
                            cat_map.setdefault(cls, set()).add(sname)
            except:
                continue
    for cat in [".text", ".data", ".bss", "Others", "User-Selected"]:
        cat_map.setdefault(cat, set())
    return {k: sorted(v) for k, v in cat_map.items()}

# --- Top N ---
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
                status = "common"; diff = v2 - v1; pct = (diff / v1 * 100.0) if v1 else 100.0
            elif v1 is not None:
                status = "removed"; diff = -v1; pct = -100.0
            else:
                status = "added"; diff = v2; pct = 100.0
            diffs[(dname, bname, status)] = (v1 or 0, v2 or 0, diff, pct)
        sec_top[sec] = dict(sorted(diffs.items(), key=lambda x: abs(x[1][2]), reverse=True)[:n])
    for cat in [".text", ".data", ".bss", "Others", "User-Selected"]:
        sec_top.setdefault(cat, {})
    return sec_top

# --- Chart ---
def make_bar_chart(values, labels, title, path, top_sections=None):
    plt.figure(figsize=(12,5))
    plt.bar(labels, values, color='skyblue')
    plt.title(title)
    plt.xticks(rotation=45, ha='right')
    if top_sections is not None and not top_sections.empty:
        def box_text(df, title):
            text = f"{title}\n"
            for _, r in df.head(5).iterrows():
                text += f"{r['section']}: {human_readable_size(r['size1'])}, {human_readable_size(r['size2'])}, {human_readable_size(r['diff'])}, {r['diff_pct']:.1f}%\n"
            return text
        boxes = [
            (0.01, 0.95, box_text(top_sections[top_sections['diff'] > 0].sort_values('diff', ascending=False), "Top Diff +"), 'left'),
            (0.99, 0.95, box_text(top_sections[top_sections['diff_pct'] > 0].sort_values('diff_pct', ascending=False), "Top Diff % +"), 'right'),
            (0.01, 0.60, box_text(top_sections[top_sections['diff'] < 0].sort_values('diff'), "Top Diff -"), 'left'),
            (0.99, 0.60, box_text(top_sections[top_sections['diff_pct'] < 0].sort_values('diff_pct'), "Top Diff % -"), 'right'),
        ]
        for x, y, text, ha in boxes:
            plt.gca().text(x, y, text, transform=plt.gca().transAxes,
                           fontsize=8, va='top', ha=ha, bbox=dict(boxstyle='round', facecolor='white', alpha=0.6))
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# --- Reports ---
def md_format_table(df, cols):
    header = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join(["---"]*len(cols)) + " |\n"
    rows = "".join("| " + " | ".join(str(row[c]) for c in cols) + " |\n" for _, row in df.iterrows())
    return header + sep + rows

def save_md_html_reports(df_dict, top_files_dict, class_tables, cat_maps,
                         output_dir, prefix, cmd, include_topfiles=False):
    suffix = "_topfiles" if include_topfiles else ""
    md_content = f"# ELF Size Comparison Report\n\nExecuted: `{cmd}`\nGenerated: {datetime.now()}\n\n"
    html_content = f"<html><head><meta charset='utf-8'></head><body><h1>ELF Size Comparison Report</h1>"

    for mode in df_dict:
        df = df_dict[mode].copy()
        for col in ['size1', 'size2', 'diff']:
            df[col] = df[col].apply(human_readable_size)
        df['diff_pct'] = df['diff_pct'].map(lambda x: f"{x:.2f}%")
        md_content += f"## Mode: {mode}\n\n" + md_format_table(df, ['section','size1','size2','diff','diff_pct']) + "\n"
        html_content += f"<h2>{mode}</h2>" + df.to_html(index=False)

        comb = pd.concat([class_tables[mode].get("dir1", pd.DataFrame()),
                          class_tables[mode].get("dir2", pd.DataFrame())], ignore_index=True)
        if not comb.empty:
            agg_df = aggregate_classification_by_class(comb)
            md_content += md_format_table(agg_df, ['class','section','type','flags']) + "\n"
            html_content += agg_df.to_html(index=False)

        for dir_label in ["dir1", "dir2"]:
            # sysv 모드면 Category Summary 출력 생략
            if mode == "sysv":
                continue
            md_content += f"### {mode} Category Summary ({dir_label})\n"
            for cat in [".text", ".data", ".bss", "Others", "User-Selected"]:
                secs = cat_maps[mode][dir_label].get(cat, [])
                md_content += f"- {cat}: {', '.join(secs)}\n"

        if include_topfiles:
            md_content += f"### Top Files ({mode})\n"
            for sec, files in top_files_dict[mode].items():
                md_content += f"#### {sec}\n"
                rows = []
                for (d, fname, status),(s1,s2,diff,pct) in files.items():
                    rows.append({
                        'directory': d, 'file': fname, 'status': status,
                        'size1': human_readable_size(s1),
                        'size2': human_readable_size(s2),
                        'diff': human_readable_size(diff),
                        'diff_pct': f"{pct:.2f}%"
                    })
                if rows:
                    md_content += md_format_table(pd.DataFrame(rows), ['directory','file','status','size1','size2','diff','diff_pct']) + "\n"

    with open(os.path.join(output_dir, f"{prefix}{suffix}.md"), "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(os.path.join(output_dir, f"{prefix}{suffix}.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(os.path.join(output_dir, f"{prefix}{suffix}.txt"), "w", encoding="utf-8") as f:
        f.write(md_content.replace('|','').replace('-',' '))
    print(f"Saved {suffix or 'summary'} reports")

# --- 상세 PT_LOAD ---
def analyze_ptload_sections(filepath: str, mode: str):
    results = []
    try:
        with open(filepath, 'rb') as f:
            elf = ELFFile(f)
            for idx, seg in enumerate(elf.iter_segments()):
                if seg['p_type'] != 'PT_LOAD':
                    continue
                seg_start = seg['p_vaddr']
                seg_end = seg_start + seg['p_memsz']
                for sec in elf.iter_sections():
                    addr = sec['sh_addr']
                    size = sec['sh_size']
                    if addr >= seg_start and addr + size <= seg_end:
                        cls = classify_section(mode, sec.header['sh_type'], sec.header['sh_flags'], sec.name)[0]
                        results.append({
                            'file': os.path.basename(filepath),
                            'segment_index': idx,
                            'segment_memsz': seg['p_memsz'],
                            'section_name': sec.name,
                            'section_size': size,
                            'class': cls,
                            'type': sec.header['sh_type']
                        })
    except:
        pass
    return results

def summarize_sizeutil_per_file(directory, allowed_files=None):
    result = {}
    for root, _, files in os.walk(directory):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.islink(full): continue
            rel = os.path.relpath(full, directory)
            if allowed_files and rel not in allowed_files: continue
            try:
                with open(full, 'rb') as f:
                    elf = ELFFile(f)
                    result[rel] = sum(seg['p_memsz'] for seg in elf.iter_segments() if seg['p_type'] == "PT_LOAD")
            except:
                continue
    return result

def save_sizeutil_report_with_sections(d1, d2, allowed_files, prefix, mode):
    s1 = summarize_sizeutil_per_file(d1, allowed_files)
    s2 = summarize_sizeutil_per_file(d2, allowed_files)
    rows = []
    seg_rows = []
    for f in sorted(set(s1) | set(s2)):
        size1 = s1.get(f, 0)
        size2 = s2.get(f, 0)
        diff = size2 - size1
        pct = (diff / size1 * 100.0) if size1 else (100.0 if size2 else 0.0)
        rows.append({"file": f, "size1": size1, "size2": size2, "diff": diff, "diff_pct": pct})
        # 상세 PT_LOAD 섹션별 세그먼트 분석
        d1f = os.path.join(d1, f)
        d2f = os.path.join(d2, f)
        if os.path.exists(d1f):
            seg_rows.extend(analyze_ptload_sections(d1f, mode))
        if os.path.exists(d2f):
            seg_rows.extend(analyze_ptload_sections(d2f, mode))
    df_sum = pd.DataFrame(rows)
    df_seg = pd.DataFrame(seg_rows)
    df_sum.to_csv(f"{prefix}_sizeutil_summary.csv", index=False)
    if not df_seg.empty:
        df_seg.to_csv(f"{prefix}_sizeutil_segments.csv", index=False)
    with open(f"{prefix}_sizeutil_summary.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['file']}\t{human_readable_size(r['size1'])}\t{human_readable_size(r['size2'])}\t{human_readable_size(r['diff'])}\t{r['diff_pct']:.2f}%\n")
    plt.figure(figsize=(10,4))
    plt.bar([r["file"] for r in rows], [abs(r["diff"]) for r in rows], color='skyblue')
    plt.title("PT_LOAD memsz Diff per file")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(f"{prefix}_sizeutil_summary.png")
    plt.close()
    print(f"Saved PT_LOAD summary and segments at {prefix}_sizeutil_summary.csv/_segments.csv/.txt/.png")

# --- Main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir1")
    ap.add_argument("dir2")
    ap.add_argument("--display-mode", choices=["berkeley","gnu","sysv","all"], default="all")
    ap.add_argument("--top-n-sections", type=int, default=5)
    ap.add_argument("--top-n-files", type=int, default=10)
    ap.add_argument("--include-section", nargs="+", default=[])
    ap.add_argument("--exclude-section", nargs="+", default=[])
    ap.add_argument("--output-dir", default="out")
    ap.add_argument("--report-prefix", default="report")
    ap.add_argument("--all-files", action="store_true")
    ap.add_argument("--user-selected", nargs="+", default=[])
    ap.add_argument("--report-type", choices=["section","size","all"], default="all")
    args = ap.parse_args()

    user_sections = normalize_user_sections(args.user_selected)

    d1, d2 = os.path.abspath(args.dir1), os.path.abspath(args.dir2)
    files1, files2 = get_elf_file_list(d1), get_elf_file_list(d2)
    if args.all_files:
        allow1, allow2 = files1, files2
    else:
        common = files1 & files2
        allow1 = allow2 = {f for f in common if is_elf_file(os.path.join(d1, f))
                                              and is_elf_file(os.path.join(d2, f))}
    save_used_files_list(args.output_dir, allow1)

    modes = [args.display_mode] if args.display_mode != "all" else ["berkeley","gnu","sysv"]
    ensure_dir(args.output_dir)
    cmdline = " ".join(sys.argv)

    df_results, top_sections, top_files, class_tables, cat_maps = {}, {}, {}, {}, {}

    for mode in modes:
        if args.report_type in ("section", "all"):
            sum1, usr1 = summarize_by_size_multi(d1, mode, args.include_section, args.exclude_section,
                                                 allowed_files=allow1, user_sections=user_sections)
            sum2, usr2 = summarize_by_size_multi(d2, mode, args.include_section, args.exclude_section,
                                                 allowed_files=allow2, user_sections=user_sections)
            df_main = summarize_by_size_multi_df(sum1, sum2)
            df_user = summarize_by_size_multi_df(usr1, usr2)
            combined = merge_user_selected(df_main, df_user)
            # for cat in [".text", ".data", ".bss", "Others", "User-Selected"]:
            #     if not (combined['section'] == cat).any():
            #         combined = pd.concat([combined, pd.DataFrame([{"section": cat, "size1": 0, "size2": 0, "diff": 0, "diff_pct": 0}])], ignore_index=True)
            for cat in [".text", ".data", ".bss", "Others", "User-Selected"]:
                # 합산된 User-Selected(...) 행이 있으면 기본 User-Selected는 생성 안 함
                if cat == "User-Selected" and combined['section'].str.startswith("User-Selected").any():
                    continue
                if not (combined['section'] == cat).any():
                    combined = pd.concat([combined, pd.DataFrame([{
                        "section": cat, "size1": 0, "size2": 0, "diff": 0, "diff_pct": 0
                    }])], ignore_index=True)
            df_results[mode] = combined

            top_sections[mode] = get_top_sections(combined, args.top_n_sections)
            f1d, _ = summarize_by_size_multi(d1, mode, args.include_section, args.exclude_section,
                                             file_level=True, allowed_files=allow1, user_sections=user_sections)
            f2d, _ = summarize_by_size_multi(d2, mode, args.include_section, args.exclude_section,
                                             file_level=True, allowed_files=allow2, user_sections=user_sections)
            top_files[mode] = get_top_files_per_section(f1d, f2d, args.top_n_files)

            class_tables[mode] = {
                "dir1": collect_section_classification_table(d1, mode, allowed_files=allow1, user_sections=user_sections),
                "dir2": collect_section_classification_table(d2, mode, allowed_files=allow2, user_sections=user_sections)
            }
            cat_maps[mode] = {
                "dir1": get_category_section_map(d1, mode, allowed_files=allow1, user_sections=user_sections),
                "dir2": get_category_section_map(d2, mode, allowed_files=allow2, user_sections=user_sections)
            }
            make_bar_chart([abs(v) for v in combined['diff']], combined['section'],
                           f"{mode} Section Diff", os.path.join(args.output_dir, f"{mode}_section_diff.png"),
                           top_sections[mode])

        if args.report_type in ("size", "all"):
            prefix = os.path.join(args.output_dir, args.report_prefix) + "_sizeutil"
            save_sizeutil_report_with_sections(d1, d2, allow1, prefix, mode)

    if args.report_type in ("section", "all"):
        save_md_html_reports(df_results, top_files, class_tables, cat_maps,
                             args.output_dir, args.report_prefix, cmdline, include_topfiles=False)
        save_md_html_reports(df_results, top_files, class_tables, cat_maps,
                             args.output_dir, args.report_prefix, cmdline, include_topfiles=True)

if __name__ == "__main__":
    main()
