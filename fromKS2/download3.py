#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate direct download links for packages and matching debug packages from a Tizen snapshot `.packages` file.

Usage:
  python3 download3.py --packages-url "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250904.211228/images/standard/tizen-headed-aarch64/tizen-unified_20250904.211228_tizen-headed-aarch64.packages" \
                        --out-csv links.csv \
                        --out-list links.txt

Alternatively, you can provide a config file:
  python3 download3.py --config config.json

Example config.json:
{
  "packages_url": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/.../tizen-headed-aarch64.packages",
  "out_csv": "links.csv",
  "out_list": "links.txt",
  "arch": "aarch64",
  "extra_snapshot_roots": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250902.051246/"
  ],
  "relaxed": true,
  "repo_subpaths": [
    "repos/standard/",
    "repos/main/"
  ]
}

Notes:
- Besides the snapshot inferred from packages_url, you can add more snapshot roots via `extra_snapshot_roots`.
- The script searches under each root: `repos/standard/packages/`, `repos/standard/debug/`, and `repos/standard/source/`.
- It outputs both a CSV (with columns) and a plain list of URLs (one per line) for easy use with wget/curl.
- Comments and code are in English as requested.
- Diagnostics: add `--verbose` to print where each artifact was found (which root), and CSV now includes `found_*_root` columns so you can see which snapshot root provided the file.
- Also writes a `missing.csv` (configurable via --missing-csv) containing only rows with any missing artifact URL.
- Matching policy: by default, filenames must match exactly `<name>-<verrel>.<arch>.rpm` (and `.noarch.rpm` fallback). If `--relaxed` or `"relaxed": true` in config is set, the script will, when exact match fails, search for the newest candidate by name+arch within the repo (lexicographically max filename), e.g. any `Open3D-*.aarch64.rpm`.
- Repo subpaths: you can specify extra repo subpaths under each snapshot root via `repo_subpaths` (default: ["repos/standard/"]). Each subpath is searched for `packages/`, `debug/`, and `source/`.
"""

import argparse
import csv
import html
import io
import json
import re
import sys
from urllib.parse import urlparse, urljoin
import requests
from typing import List

# -----------------------------
# Helpers
# -----------------------------

def _die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def infer_snapshot_root(packages_url: str) -> str:
    # Expect something like: .../tizen-unified_YYYYMMDD.HHMMSS/images/standard/<profile>/tizen-unified_..._... .packages
    m = re.search(r"(.*/tizen-unified_\d{8}\.\d{6}/)", packages_url)
    if not m:
        _die("Could not infer snapshot root from URL. Make sure it contains 'tizen-unified_YYYYMMDD.HHMMSS/'.")
    return m.group(1)


def build_repo_urls(snapshot_root: str, repo_base: str):
    pkgs_dir = urljoin(snapshot_root, urljoin(repo_base, "packages/"))
    debug_dir = urljoin(snapshot_root, urljoin(repo_base, "debug/"))
    src_dir = urljoin(snapshot_root, urljoin(repo_base, "source/"))
    return pkgs_dir, debug_dir, src_dir


def list_dir_filenames(index_url: str, subdir: str = "") -> set:
    # The directory listing is a simple HTML with <a href="filename"> entries.
    url = urljoin(index_url, subdir)
    txt = fetch_text(url)
    names = set()
    for href in re.findall(r"href=\"([^\"]+)\"", txt):
        href = html.unescape(href)
        # Skip parent links and directories (they end with '/')
        if href.endswith('/'):
            continue
        names.add(href)
    return names


def parse_packages_lines(text: str):
    """
    Yield dicts: {name, arch, verrel}
    Lines look like:
      GraphicsMagick.aarch64 1.3.45-2 platform/upstream/GraphicsMagick#<commit>
    """
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Extract first two tokens: <name.arch> <ver-rel>
        m = re.match(r"^(?P<namearch>\S+)\s+(?P<verrel>\S+)", line)
        if not m:
            continue
        namearch = m.group('namearch')
        verrel = m.group('verrel')
        # Split name.arch (the last dot splits arch)
        nm = re.match(r"^(?P<name>.+)\.(?P<arch>[^\.]+)$", namearch)
        if not nm:
            continue
        yield {
            'name': nm.group('name'),
            'arch': nm.group('arch'),
            'verrel': verrel,
        }


def main():
    ap = argparse.ArgumentParser(description="Make download links for packages and debuginfo from a Tizen snapshot .packages file")
    ap.add_argument('--packages-url', help='URL to the .packages file for the image')
    ap.add_argument('--out-csv', default='links.csv', help='Output CSV file path')
    ap.add_argument('--out-list', default='links.txt', help='Output plain list of URLs file path')
    ap.add_argument('--arch', default=None, help='Filter by arch (e.g., aarch64). Default: take from each line')
    ap.add_argument('--config', help='Path to JSON config file with parameters')
    ap.add_argument('--verbose', action='store_true', help='Print per-item diagnostics about roots and missing artifacts')
    ap.add_argument('--missing-csv', default='missing.csv', help='Output CSV containing only rows missing any artifact URL')
    ap.add_argument('--relaxed', action='store_true', help='When exact match fails, pick the newest filename by name+arch within repo')
    ap.add_argument('--repo-subpaths', nargs='*', help='Override repo subpaths list (e.g., repos/standard/ repos/main/)')
    args = ap.parse_args()

    config_data = {}
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as cf:
            config_data = json.load(cf)

    packages_url = args.packages_url or config_data.get('packages_url')
    out_csv = args.out_csv if args.out_csv != 'links.csv' or 'out_csv' not in config_data else config_data.get('out_csv')
    out_list = args.out_list if args.out_list != 'links.txt' or 'out_list' not in config_data else config_data.get('out_list')
    arch = args.arch or config_data.get('arch')

    relaxed = bool(args.relaxed or config_data.get('relaxed', False))
    repo_subpaths = args.repo_subpaths or config_data.get('repo_subpaths') or ["repos/standard/"]
    # normalize subpaths to end with '/'
    repo_subpaths = [p if p.endswith('/') else p + '/' for p in repo_subpaths]

    if not packages_url:
        _die("Missing required --packages-url argument or 'packages_url' in config file.")

    snapshot_root = infer_snapshot_root(packages_url)
    extra_roots = config_data.get('extra_snapshot_roots', []) or []
    # Normalize to end with '/'
    extra_roots = [r if r.endswith('/') else r + '/' for r in extra_roots]
    roots = [snapshot_root] + [r for r in extra_roots if r != snapshot_root]

    # Aggregate indexes across all roots and repo subpaths
    key_list = []  # list of (root, repo_base)
    pkg_files_by_key_arch = {}  # {(root, repo_base): {arch: set(filenames)}}
    debug_files_by_key = {}     # {(root, repo_base): set(filenames)}
    src_files_by_key = {}       # {(root, repo_base): set(filenames)}

    for root in roots:
        for repo_base in repo_subpaths:
            key = (root, repo_base)
            key_list.append(key)
            pkgs_dir, debug_dir, src_dir = build_repo_urls(root, repo_base)

            # packages/*/<arch>/
            try:
                pkgs_index_text = fetch_text(pkgs_dir)
            except Exception:
                pkgs_index_text = ""
            arch_dirs = re.findall(r"href=\"([^\"]+/)\"", pkgs_index_text)
            arch_dirs = [d for d in arch_dirs if d.rstrip('/') in {'aarch64','armv7l','x86_64','riscv64','noarch'}]

            arch_map = {}
            for d in arch_dirs:
                arch_name = d.rstrip('/')
                try:
                    files = list_dir_filenames(pkgs_dir, subdir=d)
                except Exception:
                    files = set()
                arch_map[arch_name] = files
            pkg_files_by_key_arch[key] = arch_map

            # debug/
            try:
                debug_files_by_key[key] = list_dir_filenames(debug_dir)
            except Exception:
                debug_files_by_key[key] = set()

            # source/
            try:
                src_files_by_key[key] = list_dir_filenames(src_dir)
            except Exception:
                src_files_by_key[key] = set()

    # Fetch packages file
    packages_txt = fetch_text(packages_url)

    rows = []
    out_urls = []

    def _pick_newest(candidates: List[str]) -> str:
        return max(candidates) if candidates else ""

    def resolve_pkg_url(name: str, verrel: str, arch: str):
        # Exact by arch
        for (root, repo_base) in key_list:
            pkgs_dir, _, _ = build_repo_urls(root, repo_base)
            files_by_arch = pkg_files_by_key_arch.get((root, repo_base), {})
            fname = f"{name}-{verrel}.{arch}.rpm"
            if fname in files_by_arch.get(arch, set()):
                return urljoin(urljoin(pkgs_dir, f"{arch}/"), fname), root
        # Exact noarch
        for (root, repo_base) in key_list:
            pkgs_dir, _, _ = build_repo_urls(root, repo_base)
            files_by_arch = pkg_files_by_key_arch.get((root, repo_base), {})
            fname = f"{name}-{verrel}.noarch.rpm"
            if fname in files_by_arch.get('noarch', set()):
                return urljoin(urljoin(pkgs_dir, 'noarch/'), fname), root
        if relaxed:
            # Relaxed: pick newest by name+arch or name+noarch
            best = ("", "")
            # arch
            for (root, repo_base) in key_list:
                pkgs_dir, _, _ = build_repo_urls(root, repo_base)
                files = pkg_files_by_key_arch.get((root, repo_base), {}).get(arch, set())
                cands = [fn for fn in files if fn.startswith(f"{name}-") and fn.endswith(f".{arch}.rpm")]
                chosen = _pick_newest(cands)
                if chosen:
                    best = (urljoin(urljoin(pkgs_dir, f"{arch}/"), chosen), root)
            if best[0]:
                return best
            # noarch
            for (root, repo_base) in key_list:
                pkgs_dir, _, _ = build_repo_urls(root, repo_base)
                files = pkg_files_by_key_arch.get((root, repo_base), {}).get('noarch', set())
                cands = [fn for fn in files if fn.startswith(f"{name}-") and fn.endswith(".noarch.rpm")]
                chosen = _pick_newest(cands)
                if chosen:
                    best = (urljoin(urljoin(pkgs_dir, 'noarch/'), chosen), root)
            if best[0]:
                return best
        return "", ""

    def resolve_debug_url(name: str, verrel: str, arch: str, kind: str):
        # Exact
        target = f"{name}-{kind}-{verrel}.{arch}.rpm"
        for (root, repo_base) in key_list:
            _, debug_dir, _ = build_repo_urls(root, repo_base)
            if target in debug_files_by_key.get((root, repo_base), set()):
                return urljoin(debug_dir, target), root
        if relaxed:
            # Relaxed by name+arch
            best = ("", "")
            for (root, repo_base) in key_list:
                _, debug_dir, _ = build_repo_urls(root, repo_base)
                files = debug_files_by_key.get((root, repo_base), set())
                cands = [fn for fn in files if fn.startswith(f"{name}-{kind}-") and fn.endswith(f".{arch}.rpm")]
                chosen = _pick_newest(cands)
                if chosen:
                    best = (urljoin(debug_dir, chosen), root)
            if best[0]:
                return best
        return "", ""

    def resolve_source_url(name: str, verrel: str):
        # Exact
        target = f"{name}-{verrel}.src.rpm"
        for (root, repo_base) in key_list:
            _, _, src_dir = build_repo_urls(root, repo_base)
            if target in src_files_by_key.get((root, repo_base), set()):
                return urljoin(src_dir, target), root
        if relaxed:
            # Relaxed by name only
            best = ("", "")
            for (root, repo_base) in key_list:
                _, _, src_dir = build_repo_urls(root, repo_base)
                files = src_files_by_key.get((root, repo_base), set())
                cands = [fn for fn in files if fn.startswith(f"{name}-") and fn.endswith('.src.rpm')]
                chosen = _pick_newest(cands)
                if chosen:
                    best = (urljoin(src_dir, chosen), root)
            if best[0]:
                return best
        return "", ""

    for item in parse_packages_lines(packages_txt):
        name = item['name']
        item_arch = arch or item['arch']
        verrel = item['verrel']

        pkg_url, pkg_root = resolve_pkg_url(name, verrel, item_arch)
        dbginfo_url, dbginfo_root = resolve_debug_url(name, verrel, item_arch, "debuginfo")
        dbgsrc_url, dbgsrc_root = resolve_debug_url(name, verrel, item_arch, "debugsource")
        src_url, src_root = resolve_source_url(name, verrel)

        # Record
        rows.append({
            'name': name,
            'arch': item_arch,
            'verrel': verrel,
            'package_url': pkg_url,
            'debuginfo_url': dbginfo_url,
            'debugsource_url': dbgsrc_url,
            'source_url': src_url,
            'found_pkg_root': pkg_root,
            'found_debuginfo_root': dbginfo_root,
            'found_debugsource_root': dbgsrc_root,
            'found_source_root': src_root,
        })

        # Add to flat list only existing URLs
        if pkg_url:
            out_urls.append(pkg_url)
        if dbginfo_url:
            out_urls.append(dbginfo_url)
        if dbgsrc_url:
            out_urls.append(dbgsrc_url)
        if src_url:
            out_urls.append(src_url)

        if args.verbose:
            missing = []
            if not pkg_url: missing.append('pkg')
            if not dbginfo_url: missing.append('debuginfo')
            if not dbgsrc_url: missing.append('debugsource')
            if not src_url: missing.append('source')
            miss_str = ','.join(missing) if missing else 'none'
            print(f"[DIAG] {name}-{verrel}.{item_arch} -> pkg={bool(pkg_url)} dbginfo={bool(dbginfo_url)} dbgsrc={bool(dbgsrc_url)} src={bool(src_url)} missing=[{miss_str}] roots(pkg/dbg/src)={[pkg_root or '-']}/[{dbginfo_root or '-'}]/[{src_root or '-'}]")

    # Write CSV
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['name','arch','verrel','package_url','debuginfo_url','debugsource_url','source_url','found_pkg_root','found_debuginfo_root','found_debugsource_root','found_source_root'])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Write URLs list
    with open(out_list, 'w', encoding='utf-8') as f:
        for u in out_urls:
            f.write(u + "\n")

    # Write missing-only CSV
    missing_rows = [r for r in rows if (not r['package_url'] or not r['debuginfo_url'] or not r['debugsource_url'] or not r['source_url'])]
    missing_csv = args.missing_csv if 'missing_csv' in args else 'missing.csv'
    with open(missing_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['name','arch','verrel','package_url','debuginfo_url','debugsource_url','source_url','found_pkg_root','found_debuginfo_root','found_debugsource_root','found_source_root'])
        w.writeheader()
        for r in missing_rows:
            w.writerow(r)

    print(f"[OK] Wrote {len(rows)} package rows to {out_csv}")
    print(f"[OK] Wrote {len(out_urls)} URLs to {out_list}")
    print(f"[OK] Wrote {len(missing_rows)} missing rows to {missing_csv}")


if __name__ == '__main__':
    main()
