import os, sys, argparse, pandas as pd
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError
from datetime import datetime
import matplotlib.pyplot as plt

# =================== Utility ===================
def human_readable_size(n):
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1024**2:
        return f"{sign}{n/1024**2:.2f} MB"
    if n >= 1024:
        return f"{sign}{n/1024:.2f} KB"
    return f"{sign}{n} B"

def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def make_bar_chart(values, labels, title, path, xlabel="", ylabel=""):
    plt.figure(figsize=(10,4))
    plt.bar(labels, values, color="skyblue")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# ================= ELF File List =================
def get_elf_file_list(directory):
    files = set()
    for root, _, fnames in os.walk(directory, followlinks=False):
        for n in fnames:
            full_path = os.path.join(root, n)
            if os.path.islink(full_path):
                continue
            files.add(os.path.relpath(full_path, directory))
    return files

def is_elf_file(path):
    try:
        with open(path, 'rb') as f:
            ELFFile(f)
        return True
    except ELFError:
        return False
    except:
        return False

# ================= Classification =================
def classify_section(mode, stype, sflag, sname):
    A = bool(sflag & 0x2); W = bool(sflag & 0x1); X = bool(sflag & 0x4)
    PROGBITS = (stype == 'SHT_PROGBITS'); NOBITS = (stype == 'SHT_NOBITS')
    if mode == "berkeley":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and not X and not W: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        else: return "not included", stype
    if mode == "gnu":
        if PROGBITS and A and X: return ".text", stype
        elif PROGBITS and A and W: return ".data", stype
        elif NOBITS and A and W: return ".bss", stype
        else: return "not included", stype
    if mode == "sysv":
        return sname, stype
    return "not included", stype

# ================= Summarization =================
def summarize_by_size_multi(directory, mode, include=None, exclude=None,
                            file_level=False, allowed_files=None):
    result = {}
    for root, _, files in os.walk(directory, followlinks=False):
        for name in files:
            full_path = os.path.join(root, name)
            if os.path.islink(full_path):
                continue
            rel_path = os.path.relpath(full_path, directory)
            if allowed_files is not None and rel_path not in allowed_files:
                continue
            try:
                with open(full_path, 'rb') as f:
                    elf = ELFFile(f)
                    for sec in elf.iter_sections():
                        stype = sec.header['sh_type']; sflag = sec.header['sh_flags']
                        sname = sec.name; sz = sec.header['sh_size']
                        if include and sname not in include: continue
                        if exclude and sname in exclude: continue
                        class_name, _stype = classify_section(mode, stype, sflag, sname)
                        key = sname if mode == "sysv" else class_name
                        if file_level:
                            result.setdefault(key, {})[rel_path] = result.get(key, {}).get(rel_path, 0) + sz
                        else:
                            result[key] = result.get(key, 0) + sz
            except:
                continue
    return result

def summarize_by_size_multi_df(sum1, sum2):
    keys = sorted(set(sum1) | set(sum2))
    rows=[]
    for k in keys:
        v1, v2 = sum1.get(k,0), sum2.get(k,0)
        diff = v2-v1
        pct = (diff/v1*100.0) if v1 else (100.0 if v2 else 0.0)
        rows.append(dict(section=k, size1=v1, size2=v2, diff=diff, diff_pct=pct))
    return pd.DataFrame(rows)

# ================= Condition Table =================
def get_condition_table(mode, dir1, dir2, allowed_files):
    if mode == "berkeley":
        conditions = [
            ("PROGBITS&ALLOC&EXECINSTR", lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x4), ".text"),
            ("PROGBITS&ALLOC&!X&!W",    lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and not(f&0x4) and not(f&0x1), ".text"),
            ("PROGBITS&ALLOC&WRITE",    lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x1), ".data"),
            ("NOBITS&ALLOC&WRITE",      lambda t,f: t=="SHT_NOBITS" and (f&0x2) and (f&0x1), ".bss"),
        ]
    elif mode == "gnu":
        conditions = [
            ("PROGBITS&ALLOC&EXECINSTR", lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x4), ".text"),
            ("PROGBITS&ALLOC&WRITE",     lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x1), ".data"),
            ("NOBITS&ALLOC&WRITE",       lambda t,f: t=="SHT_NOBITS" and (f&0x2) and (f&0x1), ".bss"),
        ]
    elif mode == "sysv":
        conditions = [
            ("SHT_PROGBITS,ALLOC,EXECINSTR", lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x4), None),
            ("SHT_PROGBITS,ALLOC,WRITE",     lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and (f&0x1), None),
            ("SHT_NOBITS,ALLOC,WRITE",       lambda t,f: t=="SHT_NOBITS" and (f&0x2) and (f&0x1), None),
            ("SHT_PROGBITS,ALLOC,!X,!W",     lambda t,f: t=="SHT_PROGBITS" and (f&0x2) and not(f&0x4) and not(f&0x1), None)
        ]
    else: return None

    def scan(basedir, allowed):
        inc=set(); result={}; allnames=set(); info={}
        for root,_,files in os.walk(basedir, followlinks=False):
            for name in files:
                full_path=os.path.join(root,name)
                if os.path.islink(full_path): continue
                rel=os.path.relpath(full_path,basedir)
                if allowed and rel not in allowed: continue
                try:
                    with open(full_path,'rb') as f:
                        elf=ELFFile(f)
                        for sec in elf.iter_sections():
                            t=sec.header['sh_type']; fbit=sec.header['sh_flags']
                            sname=sec.name; sz=sec.header['sh_size']
                            class_name,_stype=classify_section(mode,t,fbit,sname)
                            for cname,checker,out_class in conditions:
                                if checker(t,fbit):
                                    result.setdefault(cname,[]).append((sname,sz,class_name,t))
                                    inc.add(sname)
                            allnames.add(sname)
                            info[sname]=(class_name,t,sz)
                except: continue
        return result,allnames,info,inc

    scan1,all1,info1,inc1=scan(dir1,allowed_files)
    scan2,all2,info2,inc2=scan(dir2,allowed_files)

    rows=[]
    for cname,_,_ in conditions:
        merged={tpl[0]:(tpl[2],tpl[3]) for tpl in scan1.get(cname,[])}
        for tpl in scan2.get(cname,[]): merged.setdefault(tpl[0],(tpl[2],tpl[3]))
        names=sorted(merged.keys())
        total1=sum(sz for _,sz,_,_ in scan1.get(cname,[]))
        total2=sum(sz for _,sz,_,_ in scan2.get(cname,[]))
        diff=total2-total1; pct=(diff/total1*100.0) if total1 else (100.0 if total2 else 0.0)
        nameclass=[f"{n} [class:{merged[n][0]}] [type:{merged[n][1]}]" for n in names]
        rows.append(dict(condition=cname,section_names=", ".join(names),
                         section_name_class_type=", ".join(nameclass),
                         size1=total1,size2=total2,diff=diff,diff_pct=pct))
    # not included
    notinc=(all1|all2)-(inc1|inc2)
    if notinc:
        merged={}
        for n in notinc:
            info=info1.get(n) or info2.get(n)
            if info: merged[n]=info
        names=sorted(merged.keys())
        total1=sum(info1.get(n,(None,None,0))[2] for n in names)
        total2=sum(info2.get(n,(None,None,0))[2] for n in names)
        diff=total2-total1; pct=(diff/total1*100.0) if total1 else (100.0 if total2 else 0.0)
        nameclass=[f"{n} [class:{merged[n][0]}] [type:{merged[n][1]}]" for n in names]
        rows.append(dict(condition="not included",section_names=", ".join(names),
                         section_name_class_type=", ".join(nameclass),
                         size1=total1,size2=total2,diff=diff,diff_pct=pct))
    return pd.DataFrame(rows)

# ================= Top N =================
def get_top_files_per_section(f1,f2,top_n):
    section_top={}
    for sec in set(f1)|set(f2):
        diffs={}
        fs1,fs2=f1.get(sec,{}),f2.get(sec,{})
        for fname in set(fs1)|set(fs2):
            v1,v2=fs1.get(fname),fs2.get(fname)
            dpart,fpart=os.path.dirname(fname),os.path.basename(fname)
            if v1 is not None and v2 is not None:
                status="common"; diff=v2-v1; pct=(diff/v1*100.0) if v1 else (100.0 if v2 else 0.0)
            elif v1 is not None:
                status="removed"; diff=-v1; pct=-100.0
            else:
                status="add"; diff=v2; pct=100.0
            diffs[(dpart,fpart,status)]=(v1 or 0,v2 or 0,diff,pct)
        section_top[sec]=dict(sorted(diffs.items(),key=lambda x:abs(x[1][2]),reverse=True)[:top_n])
    return section_top

def get_top_sections(df, top_n):
    return df.sort_values("diff",key=abs,ascending=False).head(top_n)

# ================= Reporting (Markdown/HTML/Excel) =================
def save_report(df_dict, top_sections_dict, top_files_dict, condition_tables,
                out_prefix, top_n, cmdline_info):
    md=f"# ELF Size Comparison Report\n"
    md += f"\n**Execution Command:** `{cmdline_info}`\n"
    md += f"\nGenerated: {datetime.now()}\n\n"
    for mode in df_dict:
        cond_table=condition_tables.get(mode)
        if cond_table is not None:
            md += f"## {mode.upper()} Condition-based Section Table\n\n"
            md += "| Condition | Section Names | Section Name+Class+Type | Size1 | Size2 | Diff | Diff % |\n"
            md += "|-----------|--------------|------------------------|-------|-------|------|--------|\n"
            for _,r in cond_table.iterrows():
                md += f"| {r['condition']} | {r['section_names']} | {r['section_name_class_type']} | {human_readable_size(r['size1'])} | {human_readable_size(r['size2'])} | {human_readable_size(r['diff'])} | {r['diff_pct']:.2f}% |\n"
            md += "\n"
        df = df_dict[mode]
        md += f"## Mode: {mode}\n\n"
        md += "| Section | Size1 | Size2 | Diff | Diff % |\n|---------|-------|-------|------|--------|\n"
        for _,r in df.iterrows():
            md += f"| {r['section']} | {human_readable_size(r['size1'])} | {human_readable_size(r['size2'])} | {human_readable_size(r['diff'])} | {r['diff_pct']:.2f}% |\n"
    ensure_dir(os.path.dirname(out_prefix))
    with open(f"{out_prefix}.md",'w',encoding='utf-8') as f:
        f.write(md)
    print(f"[+] Markdown saved: {out_prefix}.md")

def save_excel(excel_path, df_dict, top_sections_dict, top_files_dict, cmdline_info, condition_tables):
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        pd.DataFrame([{"Execution Command": cmdline_info}]).to_excel(writer, sheet_name="Execution_Command", index=False)
        for mode, cond_df in condition_tables.items():
            if cond_df is not None:
                cond_df.to_excel(writer, sheet_name=f"{mode}_conditions"[:31], index=False)
        for mode, df in df_dict.items():
            df.to_excel(writer, sheet_name=f"{mode}_summary"[:31], index=False)
            top_sections_dict[mode].to_excel(writer, sheet_name=f"{mode}_top_sections"[:31], index=False)
            for sec, files in top_files_dict[mode].items():
                if not files: continue
                sec_df=pd.DataFrame([
                    {"directory":d,"file":f,"status":s,
                     "size1":vals[0],"size2":vals[1],"diff":vals[2],"diff_pct":vals[3]}
                    for (d,f,s),vals in files.items()
                ])
                sec_df.to_excel(writer, sheet_name=f"{mode}_{sec}"[:31], index=False)
    print(f"[+] Excel saved: {excel_path}")

# ================= Main =================
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("dir1"); ap.add_argument("dir2")
    ap.add_argument("--display-mode",choices=["berkeley","gnu","sysv","all"],default="berkeley")
    ap.add_argument("--top-n-files",type=int,default=10)
    ap.add_argument("--top-n-sections",type=int,default=5)
    ap.add_argument("--include-section",nargs="+")
    ap.add_argument("--exclude-section",nargs="+")
    ap.add_argument("--output-dir")
    ap.add_argument("--report-prefix")
    ap.add_argument("--excel-path")
    ap.add_argument("--all-files",action="store_true")
    args=ap.parse_args()

    dir1,dir2=os.path.abspath(args.dir1),os.path.abspath(args.dir2)
    files1,files2=get_elf_file_list(dir1),get_elf_file_list(dir2)

    if args.all_files:
        allowed1,allowed2=files1,files2
    else:
        common=files1 & files2
        valid=set()
        for rel in common:
            if is_elf_file(os.path.join(dir1,rel)) and is_elf_file(os.path.join(dir2,rel)):
                valid.add(rel)
        allowed1=allowed2=valid

    modes=[args.display_mode] if args.display_mode!="all" else ["berkeley","gnu","sysv"]
    outdir=args.output_dir or "out"
    ensure_dir(outdir)

    cmdline_info=" ".join(sys.argv)
    df_results={}; top_sections_dict={}; top_files_dict={}; condition_tables={}

    for mode in modes:
        sum1=summarize_by_size_multi(dir1,mode,args.include_section,args.exclude_section,allowed_files=allowed1)
        sum2=summarize_by_size_multi(dir2,mode,args.include_section,args.exclude_section,allowed_files=allowed2)
        df=summarize_by_size_multi_df(sum1,sum2)
        df_results[mode]=df
        ts=get_top_sections(df,args.top_n_sections); top_sections_dict[mode]=ts
        f1=summarize_by_size_multi(dir1,mode,args.include_section,args.exclude_section,file_level=True,allowed_files=allowed1)
        f2=summarize_by_size_multi(dir2,mode,args.include_section,args.exclude_section,file_level=True,allowed_files=allowed2)
        section_top=get_top_files_per_section(f1,f2,args.top_n_files)
        top_files_dict[mode]=section_top
        condition_tables[mode]=get_condition_table(mode,dir1,dir2,allowed1)

    if args.report_prefix:
        save_report(df_results, top_sections_dict, top_files_dict, condition_tables, args.report_prefix, args.top_n_files, cmdline_info)
    if args.excel_path:
        save_excel(args.excel_path, df_results, top_sections_dict, top_files_dict, cmdline_info, condition_tables)

if __name__=="__main__":
    main()
