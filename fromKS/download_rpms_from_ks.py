#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get.py (tizen_ks_dep_fetch)

End-to-end tool for:
1) Parsing a Tizen KS (kickstart) script (from URL or file), following %include recursively,
   collecting packages from %packages blocks (with simple conditionals),
2) Using ONLY Tizen repo metadata (repodata/repomd.xml -> primary.xml[.gz])
   to resolve dependency closure via provides/requires,
3) Optionally downloading all resolved RPMs.

Config:
- Read a JSON config file via --config (all fields optional).
- CLI flags override the config.

No generic "linux repo" is used; only the Tizen repo you provide is consulted.
"""

from __future__ import annotations
import argparse
import gzip
import io
import json
import re
import sys
import shutil
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

# ---------------------------
# Logging
# ---------------------------
def info(msg: str) -> None:
    print(f"[INFO] {msg}")

def warn(msg: str) -> None:
    print(f"[WARN] {msg}")

def err(msg: str) -> None:
    print(f"[ERR ] {msg}", file=sys.stderr)

# ---------------------------
# Small helpers
# ---------------------------
def http_get(url: str) -> bytes:
    with urllib.request.urlopen(url) as r:
        return r.read()

def save_url_to(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)

def detect_host_arch() -> str:
    import platform
    a = platform.machine().lower()
    if a in ("x86_64", "amd64"):
        return "x86_64"
    if a in ("aarch64", "arm64"):
        return "aarch64"
    if a.startswith("armv7"):
        return "armv7l"
    return a

def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

# ---------------------------
# KS Parser (URL or file)
# ---------------------------
class KsParseResult:
    def __init__(self) -> None:
        self.includes: Set[str] = set()
        self.excludes: Set[str] = set()
        self.groups:   Set[str] = set()
        self.sources:  List[str] = []

    def merge(self, other: "KsParseResult") -> None:
        self.includes |= other.includes
        self.excludes |= other.excludes
        self.groups   |= other.groups
        self.sources  += other.sources

class ConditionalState:
    def __init__(self) -> None:
        self.stack: List[bool] = [True]
        self.branch_taken: List[bool] = []

    @property
    def active(self) -> bool:
        return all(self.stack)

    def push_ifarch(self, wanted_arches: List[str], actual_arch: str) -> None:
        cond = (actual_arch in wanted_arches)
        self.stack.append(cond)
        self.branch_taken.append(cond)

    def push_if_numeric(self, value: int) -> None:
        cond = (value != 0)
        self.stack.append(cond)
        self.branch_taken.append(cond)

    def else_(self) -> None:
        if not self.branch_taken or not self.stack:
            return
        taken = self.branch_taken[-1]
        self.stack[-1] = (not taken)

    def endif(self) -> None:
        if self.stack:
            self.stack.pop()
        if self.branch_taken:
            self.branch_taken.pop()
        if not self.stack:
            self.stack = [True]

def _strip_inline_comment(line: str) -> str:
    i = line.find('#')
    return line if i < 0 else line[:i]

def _split_multi_items(line: str) -> List[str]:
    return [tok for tok in line.strip().split() if tok]

def _normalize_item(tok: str) -> Tuple[str, str]:
    if not tok:
        return ("include", "")
    if tok.startswith('-'):
        name = tok[1:].strip()
        if name.startswith('@'):
            return ("exclude", '@' + name[1:].strip())
        return ("exclude", name)
    if tok.startswith('@'):
        return ("group", tok[1:].strip())
    if tok.startswith('+'):
        return ("include", tok[1:].strip())
    return ("include", tok.strip())

def _logical_lines(lines: List[str]) -> List[str]:
    out = []
    cur = ""
    for ln in lines:
        if ln.rstrip().endswith("\\"):
            cur += ln.rstrip()[:-1]
        else:
            cur += ln
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out

def _read_text_resource(resource: str, base_url: Optional[str]) -> Tuple[List[str], Optional[str]]:
    """
    Read a text resource from file or URL.
    Returns (lines, new_base_url) so that %include relative paths can be resolved.
    """
    if is_url(resource):
        data = http_get(resource)
        text = data.decode("utf-8", errors="replace")
        # base URL for resolving relative includes
        new_base = resource.rsplit('/', 1)[0] + '/'
        return text.splitlines(), new_base
    else:
        p = Path(resource).resolve()
        text = p.read_text(encoding="utf-8", errors="replace")
        new_base = str(p.parent) + '/'
        return text.splitlines(), new_base

def _resolve_include_path(inc: str, base_url: Optional[str]) -> str:
    if is_url(inc):
        return inc
    if base_url and base_url.startswith("http"):
        return urllib.parse.urljoin(base_url, inc)
    # local filesystem
    if base_url and not base_url.startswith("http"):
        return str(Path(base_url) / inc)
    return inc

def parse_ks(resource: str, arch: str, visited: Set[str] | None = None, base_url: Optional[str] = None) -> KsParseResult:
    if visited is None:
        visited = set()
    res = KsParseResult()

    # Avoid loops by a normalized key
    key = resource
    if key in visited:
        return res
    visited.add(key)

    try:
        lines, new_base = _read_text_resource(resource, base_url)
    except Exception as e:
        raise FileNotFoundError(f"Failed to read KS: {resource} ({e})")
    res.sources.append(resource)

    cond = ConditionalState()
    in_packages = False

    for raw in _logical_lines(lines):
        line = raw.strip()

        # includes (respect condition)
        if line.startswith("%include"):
            if not cond.active:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                inc = parts[1].strip()
                inc_path = _resolve_include_path(inc, new_base)
                child = parse_ks(inc_path, arch, visited=visited, base_url=new_base)
                res.merge(child)
            continue

        # conditionals
        if line.startswith("%ifarch"):
            tokens = line.split()
            arches = tokens[1:] if len(tokens) > 1 else []
            cond.push_ifarch(arches, arch)
            continue
        if line.startswith("%if "):
            rest = line[4:].strip()
            try:
                num = int(rest, 0)
            except ValueError:
                num = 0
            cond.push_if_numeric(num)
            continue
        if line == "%else":
            cond.else_(); continue
        if line == "%endif":
            cond.endif(); continue

        # packages block
        if line.startswith("%packages"):
            in_packages = True
            continue
        if line == "%end":
            in_packages = False
            continue

        if in_packages and cond.active:
            clean = _strip_inline_comment(line).strip()
            if not clean or clean.startswith("--"):
                continue
            for tok in _split_multi_items(clean):
                kind, name = _normalize_item(tok)
                if not name: continue
                if kind == "include":
                    res.includes.add(name)
                elif kind == "exclude":
                    res.excludes.add(name)
                elif kind == "group":
                    res.groups.add(name)

    return res

# ---------------------------
# Repo metadata (Tizen only)
# ---------------------------
PRIMARY_NS = "{http://linux.duke.edu/metadata/common}"
RPM_NS     = "{http://linux.duke.edu/metadata/rpm}"
REPO_NS    = "{http://linux.duke.edu/metadata/repo}"

@dataclass
class PkgMeta:
    name: str
    arch: str
    href: str
    repo_base: str                       # base repo URL that owns this pkg
    provides: Set[str] = field(default_factory=set)
    requires: Set[str] = field(default_factory=set)

class RepoIndex:
    def __init__(self) -> None:
        self.by_name: Dict[str, List[PkgMeta]] = {}
        self.by_provide: Dict[str, List[PkgMeta]] = {}

    def add(self, p: PkgMeta) -> None:
        self.by_name.setdefault(p.name, []).append(p)
        for cap in p.provides:
            self.by_provide.setdefault(cap, []).append(p)

    def pick_provider(self, cap: str, arch: Optional[str]) -> Optional[PkgMeta]:
        cands = self.by_provide.get(cap, [])
        if not cands:
            return None
        if arch:
            exact = [x for x in cands if x.arch == arch]
            if exact:
                # small heuristic: prefer pkg whose name equals capability
                for x in exact:
                    if x.name == cap:
                        return x
                return exact[0]
        noarch = [x for x in cands if x.arch == "noarch"]
        if noarch:
            for x in noarch:
                if x.name == cap:
                    return x
            return noarch[0]
        return cands[0]

    def merge_from(self, other: "RepoIndex") -> None:
        for name, lst in other.by_name.items():
            self.by_name.setdefault(name, []).extend(lst)
        for cap, lst in other.by_provide.items():
            self.by_provide.setdefault(cap, []).extend(lst)

def _find_repomd_url(repo_packages_url: str) -> str:
    """
    Given .../repos/standard/packages, try repodata/ under same or one level up.
    """
    # 1) same level
    cand = repo_packages_url.rstrip("/") + "/repodata/repomd.xml"
    try:
        http_get(cand)
        return cand
    except Exception:
        pass
    # 2) one up (typical tizen layout)
    parent = "/".join(repo_packages_url.rstrip("/").split("/")[:-1])
    cand2 = parent + "/repodata/repomd.xml"
    # Let exceptions propagate here if not found
    http_get(cand2)  # probe
    return cand2

def _primary_from_repomd(repomd_url: str) -> str:
    xml_bytes = http_get(repomd_url)
    root = ET.fromstring(xml_bytes)
    for data in root.findall(f"{REPO_NS}data"):
        if data.attrib.get("type") == "primary":
            loc = data.find(f"{REPO_NS}location")
            href = loc.attrib["href"]
            # Directory containing repomd.xml (usually .../repodata)
            repodir = "/".join(repomd_url.split("/")[:-1])
            # If href is "repodata/<file>", it is relative to the REPO ROOT (one level above repodata/)
            # Join with the parent of repodir to avoid "repodata/repodata/..."
            if href.startswith("repodata/"):
                base = "/".join(repodir.split("/")[:-1])  # repo root
            else:
                base = repodir
            return f"{base}/{href.lstrip('/')}"
    raise RuntimeError("primary metadata not found in repomd.xml")

def _parse_primary(primary_url: str, repo_base: str) -> RepoIndex:
    info(f"Fetching primary metadata: {primary_url}")
    raw = http_get(primary_url)
    if primary_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw

    idx = RepoIndex()
    root = ET.fromstring(data)
    for pkg in root.findall(f"{PRIMARY_NS}package"):
        name = pkg.findtext(f"{PRIMARY_NS}name", "")
        arch = pkg.findtext(f"{PRIMARY_NS}arch", "")
        loc  = pkg.find(f"{PRIMARY_NS}location")
        href = loc.attrib.get("href", "") if loc is not None else ""

        provides: Set[str] = set()
        requires: Set[str] = set()

        fmt = pkg.find(f"{PRIMARY_NS}format")
        if fmt is not None:
            for e in fmt.findall(f"{RPM_NS}provides/{RPM_NS}entry"):
                n = e.attrib.get("name", "").strip()
                if n: provides.add(n)
            for e in fmt.findall(f"{RPM_NS}requires/{RPM_NS}entry"):
                n = e.attrib.get("name", "").strip()
                if n and not n.startswith("rpmlib("):
                    requires.add(n)
        idx.add(PkgMeta(name=name, arch=arch, href=href, repo_base=repo_base, provides=provides, requires=requires))
    return idx


def _absolute_href_with_base(repo_base: str, href: str) -> str:
    """
    Build absolute RPM URL from primary.xml 'href' and the repo_base the pkg came from.

    Rules:
      - RPM files live under .../repos/standard/{packages|debug}/<arch>/...
      - If repo_base already ends with the arch segment (e.g. .../packages/aarch64/),
        avoid duplicating the arch when href also begins with "<arch>/".
      - Otherwise, join repo_base with href as-is.
    """
    rb = repo_base.rstrip("/")
    href_clean = href.lstrip("/")

    # Detect if repo_base already ends with an arch folder
    arch_suffix = None
    for arch_dir in ("aarch64", "x86_64", "noarch"):
        if rb.endswith("/" + arch_dir):
            arch_suffix = arch_dir
            break

    if arch_suffix and href_clean.startswith(arch_suffix + "/"):
        # repo_base already includes '<arch>', so don't duplicate it
        return f"{rb}/{href_clean[len(arch_suffix)+1:]}"
    else:
        # Normal case: repo_base ends with 'packages' or 'debug' (no arch)
        return f"{rb}/{href_clean}"

# ---------------------------
# Dependency resolver & downloader
# ---------------------------

def _build_merged_index(repo_bases: List[str]) -> "RepoIndex":
    merged = RepoIndex()
    for base in repo_bases:
        repomd = _find_repomd_url(base)
        primary = _primary_from_repomd(repomd)
        idx = _parse_primary(primary, repo_base=base)
        merged.merge_from(idx)
    return merged

def resolve_and_download(repo_packages_urls: List[str],
                         pkg_names: List[str],
                         arch: Optional[str],
                         outdir: Path,
                         do_download: bool) -> Tuple[List[str], List[str]]:
    """
    Resolve dependency closure starting from list of package names (from KS) across multiple repos.
    Return (resolved_pkg_files, missing_caps)
    """
    idx = _build_merged_index(repo_packages_urls)

    # bootstrap queue with the seed packages (by name)
    queue: List[PkgMeta] = []
    for name in pkg_names:
        metas = idx.by_name.get(name, [])
        if not metas:
            warn(f"Package not found in repo: {name}")
            continue
        # pick best by arch preference
        picked = None
        if arch:
            for m in metas:
                if m.arch == arch:
                    picked = m; break
        if not picked:
            for m in metas:
                if m.arch == "noarch":
                    picked = m; break
        if not picked and metas:
            picked = metas[0]
        if picked:
            queue.append(picked)

    visited_pkgs: Set[Tuple[str, str]] = set()
    missing_caps: List[str] = []
    downloaded_files: List[str] = []

    i = 0
    while i < len(queue):
        pkg = queue[i]; i += 1
        key = (pkg.name, pkg.arch)
        if key in visited_pkgs:
            continue
        visited_pkgs.add(key)

        # enqueue its requires
        for cap in sorted(pkg.requires):
            prov = idx.pick_provider(cap, arch or pkg.arch or "noarch")
            if not prov:
                missing_caps.append(cap)
                continue
            k2 = (prov.name, prov.arch)
            if k2 not in visited_pkgs:
                queue.append(prov)

        # download this pkg
        if do_download:
            url = _absolute_href_with_base(pkg.repo_base, pkg.href)
            dest = outdir / Path(pkg.href).name
            if dest.exists():
                info(f"Already exists: {dest.name}")
            else:
                try:
                    info(f"Downloading {pkg.name}.{pkg.arch} -> {dest.name}")
                    save_url_to(url, dest)
                except Exception as e:
                    warn(f"Download failed: {url} : {e}")
            downloaded_files.append(str(dest))

    return downloaded_files, missing_caps

# ---------------------------
# Output formatting
# ---------------------------
def format_list(packages: List[str], groups: List[str], excludes: List[str],
                fmt: str, show_groups: bool, sources: List[str]) -> str:
    pkgs = sorted([p for p in packages if p not in excludes and not p.startswith('@')])
    groups_sorted = sorted(groups)
    excludes_sorted = sorted(excludes)

    if fmt == "json":
        return json.dumps({
            "packages": pkgs,
            "groups": groups_sorted if show_groups else [],
            "excludes": excludes_sorted,
            "sources": sources
        }, ensure_ascii=False, indent=2)

    if fmt == "markdown":
        lines = []
        lines.append("# KS Package List")
        lines.append("")
        lines.append("## Packages (resolved)")
        for p in pkgs:
            lines.append(f"- `{p}`")
        if show_groups and groups_sorted:
            lines.append("")
            lines.append("## Groups / Patterns (@)")
            for g in groups_sorted:
                lines.append(f"- `@{g}`")
        if excludes_sorted:
            lines.append("")
            lines.append("## Excludes")
            for e in excludes_sorted:
                lines.append(f"- `{e}`")
        lines.append("")
        lines.append("**Parsed files:** " + ", ".join(f"`{s}`" for s in sources))
        return "\n".join(lines)

    # plain
    return "\n".join(pkgs)

# ---------------------------
# Config merge
# ---------------------------
def load_config(path: Optional[str]) -> dict:
    if not path:
        return {}
    try:
        text = Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except Exception as e:
        err(f"Failed to read config {path}: {e}")
        sys.exit(2)

def main():
    ap = argparse.ArgumentParser(description="Parse Tizen KS, list packages, and resolve/download dependencies using Tizen repo metadata.")
    ap.add_argument("--config", type=str, help="JSON config file")
    ap.add_argument("--ks", type=str, help="KS entry (URL or file).")
    ap.add_argument("--repo", type=str, action="append",
                    help="Tizen repo URL (…/repos/standard/packages or …/repos/standard/debug). Repeatable.")
    ap.add_argument("--arch", type=str, help="Arch (aarch64, x86_64, etc.).")
    ap.add_argument("--out", type=str, help="Download directory (default: ./rpms).")
    ap.add_argument("--format", choices=["plain", "json", "markdown"], help="List output format (default: plain).")
    ap.add_argument("--show-groups", action="store_true", help="Also print @groups in json/markdown.")
    ap.add_argument("--download", action="store_true", help="Download dependency closure RPMs.")
    args = ap.parse_args()

    cfg = load_config(args.config)

    # Merge: CLI overrides config
    ks_entry = args.ks or cfg.get("ks")
    arch = (args.arch or cfg.get("arch") or detect_host_arch()).lower()
    outdir = Path(args.out or cfg.get("out", "./rpms"))
    fmt = args.format or cfg.get("format", "plain")
    show_groups = args.show_groups or bool(cfg.get("show_groups", False))
    do_download = args.download or bool(cfg.get("download", False))

    # Build list of repos from config and CLI
    repos_cfg = cfg.get("repos")
    repo_single_cfg = cfg.get("repo")
    repos_cli = args.repo

    repo_list: List[str] = []
    if isinstance(repos_cfg, list):
        repo_list.extend(repos_cfg)
    if repo_single_cfg:
        repo_list.append(repo_single_cfg)
    if repos_cli:
        repo_list.extend(repos_cli)

    # normalize trailing slash
    repo_list = [r.rstrip("/") + "/" for r in repo_list]

    if not ks_entry:
        err("Missing --ks (URL or file). You can also set it in --config JSON.")
        sys.exit(2)
    if not repo_list:
        err("Missing repos. Provide at least one via --repo (repeatable) or config.repos[].")
        sys.exit(2)

    # 1) Parse KS (URL or file)
    try:
        ks = parse_ks(ks_entry, arch=arch, base_url=None)
    except FileNotFoundError as e:
        err(str(e)); sys.exit(2)
    packages = sorted([p for p in ks.includes if p not in ks.excludes and not p.startswith('@')])

    # 2) Print package list (before download)
    print(format_list(packages, list(ks.groups), list(ks.excludes), fmt, show_groups, ks.sources))

    # 3) Resolve & download (optional)
    if do_download:
        outdir.mkdir(parents=True, exist_ok=True)
        files, missing = resolve_and_download(repo_list, packages, arch, outdir, do_download=True)
        info(f"Resolved {len(files)} RPM file(s). Output: {outdir}")
        if missing:
            warn(f"Capabilities with no provider in repo: {len(missing)}")
            for cap in sorted(set(missing)):
                warn(f"  - {cap}")

if __name__ == "__main__":
    main()