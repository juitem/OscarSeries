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
import bz2
import sqlite3
import tempfile
import os

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
# NOTE on XML Namespaces:
# These URIs come from the RPM-MD (Yum/DNF/createrepo) metadata specification and
# are used by many distributions including Tizen. They are *identifiers* that appear
# inside XML files (repomd.xml, primary.xml) and are not fetched as network URLs.
# Tizen reuses the same standard metadata format, so the namespace URIs remain
# 'http://linux.duke.edu/...'. Changing them would break XML parsing because the
# element names in Tizen metadata are bound to these exact namespaces.
PRIMARY_NS = "{http://linux.duke.edu/metadata/common}"
RPM_NS     = "{http://linux.duke.edu/metadata/rpm}"
REPO_NS    = "{http://linux.duke.edu/metadata/repo}"
FILELISTS_NS = "{http://linux.duke.edu/metadata/filelists}"
OTHER_NS = "{http://linux.duke.edu/metadata/other}"

@dataclass
class PkgMeta:
    name: str
    arch: str
    href: str
    repo_base: str                       # base repo URL that owns this pkg
    provides: Set[str] = field(default_factory=set)
    requires: Set[str] = field(default_factory=set)
    pkgid: Optional[str] = None
def _other_from_repomd(repomd_url: str) -> Optional[str]:
    """
    Return absolute URL to other metadata if present (type='other' or 'other_db').
    """
    xml_bytes = http_get(repomd_url)
    root = ET.fromstring(xml_bytes)
    for t in ("other", "other_db"):
        for data in root.findall(f"{REPO_NS}data"):
            if data.attrib.get("type") == t:
                loc = data.find(f"{REPO_NS}location")
                if loc is None:
                    continue
                href = loc.attrib.get("href", "")
                repodir = "/".join(repomd_url.split("/")[:-1])
                if href.startswith("repodata/"):
                    base = "/".join(repodir.split("/")[:-1])
                else:
                    base = repodir
                return f"{base}/{href.lstrip('/')}"
    return None

def _parse_other(other_url: str) -> Dict[Tuple[str, str], str]:
    """
    Parse other metadata and return a map {(name, arch): pkgid}.
    We primarily use 'pkgid' attribute on <package>. Some schemas may also embed
    <checksum>, but pkgid is the most portable identifier here.
    """
    info(f"Fetching other metadata: {other_url}")
    raw = http_get(other_url)
    if other_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw
    out: Dict[Tuple[str, str], str] = {}
    try:
        root = ET.fromstring(data)
        for pkg in root.findall(f"{OTHER_NS}package"):
            name = pkg.attrib.get("name", "").strip()
            arch = pkg.attrib.get("arch", "").strip()
            pkgid = pkg.attrib.get("pkgid", "").strip()
            if name and arch and pkgid:
                out[(name, arch)] = pkgid
        # Fallback: some schemas may not namespace 'package' under OTHER_NS
        if not out:
            for pkg in root.findall(".//package"):
                name = pkg.attrib.get("name", "").strip()
                arch = pkg.attrib.get("arch", "").strip()
                pkgid = pkg.attrib.get("pkgid", "").strip()
                if name and arch and pkgid:
                    out[(name, arch)] = pkgid
    except Exception as e:
        warn(f"Failed to parse other metadata: {e}")
    return out

class RepoIndex:
    def __init__(self) -> None:
        self.by_name: Dict[str, List[PkgMeta]] = {}
        self.by_provide: Dict[str, List[PkgMeta]] = {}
        self.by_file: Dict[str, List[PkgMeta]] = {}

    def add(self, p: PkgMeta) -> None:
        self.by_name.setdefault(p.name, []).append(p)
        for cap in p.provides:
            self.by_provide.setdefault(cap, []).append(p)

    def add_file_provide(self, filepath: str, p: PkgMeta) -> None:
        # Treat absolute file paths as capabilities as well
        self.by_file.setdefault(filepath, []).append(p)
        self.by_provide.setdefault(filepath, []).append(p)

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
        for fp, lst in getattr(other, "by_file", {}).items():
            self.by_file.setdefault(fp, []).extend(lst)

    def find_pkg(self, name: str, arch: str) -> Optional[PkgMeta]:
        lst = self.by_name.get(name, [])
        for m in lst:
            if m.arch == arch:
                return m
        return lst[0] if lst else None

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

# ---------------------------
# Repo sibling helpers
# ---------------------------
def _derive_packages_repo(debug_repo: str) -> str:
    """
    From a debug repo URL, derive the sibling packages repo URL.
    Examples:
      .../repos/standard/debug/           -> .../repos/standard/packages/
      .../repos/standard/debug/aarch64/   -> .../repos/standard/packages/aarch64/
      .../repos/standard/debug/x86_64/    -> .../repos/standard/packages/x86_64/
    If the input isn't a debug path, return it unchanged.
    """
    d = debug_repo.rstrip("/") + "/"
    return d.replace("/repos/standard/debug/aarch64/", "/repos/standard/packages/aarch64/") \
            .replace("/repos/standard/debug/x86_64/", "/repos/standard/packages/x86_64/") \
            .replace("/repos/standard/debug/", "/repos/standard/packages/")

def _derive_debug_repo(packages_repo: str) -> str:
    """
    From a packages repo URL, derive the sibling debug repo URL.
    Examples:
      .../repos/standard/packages/           -> .../repos/standard/debug/
      .../repos/standard/packages/aarch64/   -> .../repos/standard/debug/aarch64/
      .../repos/standard/packages/x86_64/    -> .../repos/standard/debug/x86_64/
    If the input isn't a packages path, return it unchanged.
    """
    p = packages_repo.rstrip("/") + "/"
    return p.replace("/repos/standard/packages/aarch64/", "/repos/standard/debug/aarch64/") \
            .replace("/repos/standard/packages/x86_64/", "/repos/standard/debug/x86_64/") \
            .replace("/repos/standard/packages/", "/repos/standard/debug/")

def _split_resolve_download_repos(repo_bases: List[str], derive_pairs: bool = True) -> Tuple[List[str], List[str]]:
    """
    Given a list of repos from the user, build:
      - resolve_pkgs: PACKAGES repos for dependency resolution
      - download_dbg: DEBUG repos for downloading debug variants
    If derive_pairs is True (default), for any entry that is /debug/, derive its /packages/ sibling,
    and for any entry that is /packages/, derive its /debug/ sibling.
    If derive_pairs is False, use repo_bases as-is for both roles.
    """
    resolve_pkgs: List[str] = []
    download_dbg: List[str] = []
    for r in repo_bases:
        r_norm = r.rstrip("/") + "/"
        if "/repos/standard/debug/" in r_norm:
            # provided DEBUG -> resolve with PACKAGES (derived)
            if derive_pairs:
                resolve_pkgs.append(_derive_packages_repo(r_norm))
            else:
                resolve_pkgs.append(r_norm)
            download_dbg.append(r_norm)
        elif "/repos/standard/packages/" in r_norm:
            # provided PACKAGES -> derive DEBUG for download
            resolve_pkgs.append(r_norm)
            if derive_pairs:
                download_dbg.append(_derive_debug_repo(r_norm))
            else:
                download_dbg.append(r_norm)
        else:
            # Unknown pattern; pass-through
            resolve_pkgs.append(r_norm)
            download_dbg.append(r_norm)
    resolve_pkgs = [x.rstrip("/") + "/" for x in resolve_pkgs]
    download_dbg = [x.rstrip("/") + "/" for x in download_dbg]
    return resolve_pkgs, download_dbg

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

# ---------------------------
# Filelists metadata helpers (for file path provides)
# ---------------------------
def _filelists_from_repomd(repomd_url: str) -> Optional[str]:
    """
    Return absolute URL to filelists metadata if present (type='filelists' or 'filelists_db').
    """
    xml_bytes = http_get(repomd_url)
    root = ET.fromstring(xml_bytes)
    for t in ("filelists", "filelists_db"):
        for data in root.findall(f"{REPO_NS}data"):
            if data.attrib.get("type") == t:
                loc = data.find(f"{REPO_NS}location")
                if loc is None:
                    continue
                href = loc.attrib.get("href", "")
                repodir = "/".join(repomd_url.split("/")[:-1])
                if href.startswith("repodata/"):
                    base = "/".join(repodir.split("/")[:-1])
                else:
                    base = repodir
                return f"{base}/{href.lstrip('/')}"
    return None


def _parse_filelists(filelists_url: str) -> List[Tuple[str, str, List[str]]]:
    """
    Parse filelists metadata.
    Supports:
      - XML/plain or XML.gz
      - SQLite (.sqlite) or SQLite.bz2 (.sqlite.bz2)
    Returns a list of (name, arch, [files]).
    """
    info(f"Fetching filelists metadata: {filelists_url}")
    raw = http_get(filelists_url)

    # ---- SQLite path (filelists_db) ----
    if ".sqlite" in filelists_url:
        # decompress if bz2
        if filelists_url.endswith(".bz2"):
            try:
                data = bz2.decompress(raw)
            except Exception:
                # Some servers return raw sqlite even with .bz2 suffix; fall back to raw
                data = raw
        else:
            data = raw

        # write to a temp file so sqlite3 can open it
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        try:
            tmp.write(data)
            tmp.close()
            res: List[Tuple[str, str, List[str]]] = []
            conn = sqlite3.connect(tmp.name)
            try:
                cur = conn.cursor()
                # discover table names
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in cur.fetchall()}

                # figure out file table and column layout
                files_tbl = None
                if "files" in tables:
                    files_tbl = "files"
                elif "filelist" in tables:
                    files_tbl = "filelist"

                if not files_tbl or "packages" not in tables:
                    return res  # unknown schema

                # get column info
                def has_column(tbl: str, col: str) -> bool:
                    cur.execute(f"PRAGMA table_info({tbl})")
                    return any(row[1] == col for row in cur.fetchall())

                # Build SQL to produce (pkg_name, pkg_arch, fullpath)
                if files_tbl == "files":
                    # Common schema: files(name TEXT, type TEXT, pkgKey INTEGER, ...), packages(id/pkgKey, name, arch)
                    # Some schemas store full path in 'name'; others split into dirname/filename.
                    if has_column("files", "dirname") and has_column("files", "filename"):
                        sql = """
                            SELECT p.name, p.arch,
                                   CASE WHEN f.dirname='/' THEN '/'||f.filename ELSE f.dirname||'/'||f.filename END AS path
                            FROM packages AS p
                            JOIN files AS f ON p.pkgKey = f.pkgKey
                        """
                    else:
                        # assume 'name' is full path
                        sql = """
                            SELECT p.name, p.arch, f.name AS path
                            FROM packages AS p
                            JOIN files AS f ON p.pkgKey = f.pkgKey
                        """
                else:
                    # filelist table (older schemas)
                    # columns may be: dirname, filename, pkgKey
                    if has_column("filelist", "dirname") and has_column("filelist", "filename"):
                        sql = """
                            SELECT p.name, p.arch,
                                   CASE WHEN f.dirname='/' THEN '/'||f.filename ELSE f.dirname||'/'||f.filename END AS path
                            FROM packages AS p
                            JOIN filelist AS f ON p.pkgKey = f.pkgKey
                        """
                    else:
                        # fallback if only 'name' exists
                        sql = """
                            SELECT p.name, p.arch, f.name AS path
                            FROM packages AS p
                            JOIN filelist AS f ON p.pkgKey = f.pkgKey
                        """

                for pkg_name, pkg_arch, path in cur.execute(sql):
                    if not path:
                        continue
                    p = str(path).strip()
                    if p.startswith("/"):
                        # collect by (name, arch)
                        # We'll group below to return unique paths per package
                        res.append((str(pkg_name), str(pkg_arch), [p]))
                # Group per (name,arch)
                out: Dict[Tuple[str, str], Set[str]] = {}
                for n, a, files in res:
                    out.setdefault((n, a), set()).update(files)
                return [(n, a, sorted(list(paths))) for (n, a), paths in out.items()]
            finally:
                conn.close()
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    # ---- XML path ----
    # handle XML plain or gzip
    if filelists_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw
    res2: List[Tuple[str, str, List[str]]] = []
    root = ET.fromstring(data)
    for pkg in root.findall(f"{FILELISTS_NS}package"):
        name = pkg.attrib.get("name", "").strip()
        arch = pkg.attrib.get("arch", "").strip()
        if not name:
            continue
        files: List[str] = []
        for fe in pkg.findall(f"{FILELISTS_NS}file"):
            fp = (fe.text or "").strip()
            if fp and fp.startswith("/"):
                files.append(fp)
        res2.append((name, arch, files))
    return res2


def _augment_index_with_filelists(idx: "RepoIndex", repo_base: str) -> None:
    """
    Load filelists metadata for the given repo base and augment the index so that
    absolute file paths (e.g., "/usr/bin/awk") are also considered as 'provides'.
    """
    try:
        repomd = _find_repomd_url(repo_base)
        furl = _filelists_from_repomd(repomd)
        if not furl:
            return
        entries = _parse_filelists(furl)
        # Map (name,arch) -> PkgMeta for quick attach
        for (pname, parch, files) in entries:
            owner = None
            # Prefer exact arch match if present in this repo index
            lst = idx.by_name.get(pname, [])
            for m in lst:
                if m.arch == parch:
                    owner = m
                    break
            if owner is None and lst:
                owner = lst[0]
            if owner is None:
                continue
            for fp in files:
                idx.add_file_provide(fp, owner)
    except Exception as e:
        warn(f"Filelists metadata not available for {repo_base}: {e}")

# ---------------------------
# Group metadata helpers (comps, for preset/group expansion)
# ---------------------------
def _group_from_repomd(repomd_url: str) -> Optional[str]:
    """
    Return the absolute URL to the 'group' (comps) metadata if present in repomd.xml.
    Tizen/createrepo may expose it as type='group' or 'group_gz'.
    """
    xml_bytes = http_get(repomd_url)
    root = ET.fromstring(xml_bytes)
    for t in ("group", "group_gz"):
        for data in root.findall(f"{REPO_NS}data"):
            if data.attrib.get("type") == t:
                loc = data.find(f"{REPO_NS}location")
                if loc is None:
                    continue
                href = loc.attrib.get("href", "")
                repodir = "/".join(repomd_url.split("/")[:-1])
                # If href begins with 'repodata/', it is relative to repo root (one up from repodata/)
                if href.startswith("repodata/"):
                    base = "/".join(repodir.split("/")[:-1])
                else:
                    base = repodir
                return f"{base}/{href.lstrip('/')}"
    return None

def _parse_groups_xml(groups_url: str) -> Dict[str, List[str]]:
    """
    Parse comps/groups metadata. Returns map: group_id -> [package names].
    We accumulate 'mandatory' and 'default' package entries.
    """
    info(f"Fetching group metadata: {groups_url}")
    raw = http_get(groups_url)
    if groups_url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        data = gzip.decompress(raw)
    else:
        data = raw
    res: Dict[str, List[str]] = {}
    root = ET.fromstring(data)
    # comps schemas vary; try both common namespaces and no-namespace
    # Pattern: <group><id>...</id> ... <packagelist><packagereq type="mandatory|default" ...>
    for g in root.findall(".//group"):
        gid = g.findtext("id", "").strip()
        if not gid:
            continue
        pkgs: List[str] = []
        for preq in g.findall(".//packagereq"):
            t = (preq.attrib.get("type", "") or "").lower()
            if t in ("mandatory", "default"):
                name = (preq.text or "").strip()
                if name:
                    pkgs.append(name)
        if pkgs:
            res[gid] = pkgs
    return res

def _build_groups_index(repo_bases: List[str]) -> Dict[str, List[str]]:
    """
    Build a merged groups index from a list of repos (first hit wins for a group id).
    """
    groups: Dict[str, List[str]] = {}
    for base in repo_bases:
        try:
            repomd = _find_repomd_url(base)
            gurl = _group_from_repomd(repomd)
            if not gurl:
                continue
            gmap = _parse_groups_xml(gurl)
            for gid, lst in gmap.items():
                groups.setdefault(gid, lst)
        except Exception as e:
            warn(f"Group metadata not available for {base}: {e}")
    return groups

def _parse_primary(primary_url: str, repo_base: str, other_map: Optional[Dict[Tuple[str, str], str]] = None) -> RepoIndex:
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
        pkgid = None
        if other_map is not None:
            pkgid = other_map.get((name, arch))
        idx.add(PkgMeta(name=name, arch=arch, href=href, repo_base=repo_base,
                        provides=provides, requires=requires, pkgid=pkgid))
    return idx


def _absolute_href_with_base(repo_base: str, href: str) -> str:
    """
    Build absolute RPM URL from primary.xml 'href' and the repo_base the pkg came from.

    Rules:
      - RPM files usually live under .../repos/standard/{packages|debug}/<arch>/...
      - However, some Tizen DEBUG repos store RPMs directly under .../debug/ (no arch folder),
        while primary.xml 'href' may still be prefixed with '<arch>/'.
      - Handle both layouts robustly:
         * If repo_base already ends with the arch segment, avoid duplicating it.
         * If repo_base ends with '/debug/' (no arch) and href starts with '<arch>/', strip the arch.
         * Otherwise, join repo_base with href as-is.
    """
    rb = repo_base.rstrip("/")
    href_clean = href.lstrip("/")

    # Detect if repo_base already ends with an arch folder
    arch_suffix = None
    for arch_dir in ("aarch64", "x86_64", "armv7l", "riscv64", "noarch"):
        if rb.endswith("/" + arch_dir):
            arch_suffix = arch_dir
            break

    # Case 1: repo_base already has the arch suffix and href also starts with it -> avoid duplication
    if arch_suffix and href_clean.startswith(arch_suffix + "/"):
        return f"{rb}/{href_clean[len(arch_suffix)+1:]}"

    rb = repo_base.rstrip("/")
    href_clean = href.lstrip("/")

    # Remove trailing arch directory from repo_base, if present
    arch_dirs = ("aarch64", "x86_64", "armv7l", "riscv64", "noarch")
    repo_root = rb
    for arch_dir in arch_dirs:
        if rb.endswith("/" + arch_dir):
            repo_root = rb[: -(len(arch_dir) + 1)]
            break

    # Simple join from repo_root (typically ends with /packages or /debug)
    return f"{repo_root}/{href_clean}"


# ---------------------------
# Debug repo flattened layout helper
# ---------------------------
from typing import List
def _debug_url_candidates(repo_base: str, href: str) -> List[str]:
    """
    Generate possible download URLs for debug repos that may be laid out either as:
      A) .../repos/standard/debug/<arch>/<file>
      B) .../repos/standard/debug/<file>     (flattened, no arch dir)
    We return a small list of candidates in preferred order.
    """
    urls: List[str] = []
    # candidate 1: naive join with current logic
    url_main = _absolute_href_with_base(repo_base, href)
    urls.append(url_main)

    rb = repo_base.rstrip("/")
    href_clean = href.lstrip("/")

    # detect arch prefix in href (e.g., "aarch64/<file>")
    arch_in_href = None
    for arch_dir in ("aarch64", "x86_64", "armv7l", "riscv64", "noarch"):
        if href_clean.startswith(arch_dir + "/"):
            arch_in_href = arch_dir
            break

    # If repo_base contains '/debug/', try flattened layout variants.
    if "/repos/standard/debug/" in rb:
        # Case A: href starts with arch -> drop the arch segment
        if arch_in_href:
            # .../debug/<file>
            urls.append(f"{rb}/{href_clean[len(arch_in_href)+1:]}")
            # If repo_base ends with '/<arch>', also try removing that arch from base
            for arch_dir in ("aarch64", "x86_64", "armv7l", "riscv64", "noarch"):
                suffix = "/" + arch_dir
                if rb.endswith(suffix):
                    parent = rb[: -len(suffix)]
                    urls.append(f"{parent}/{href_clean[len(arch_in_href)+1:]}")
                    break
        else:
            # Case B: href does NOT start with arch, but repo_base may end with '/<arch>'
            # Try removing the arch from base: .../debug/<file>
            for arch_dir in ("aarch64", "x86_64", "armv7l", "riscv64", "noarch"):
                suffix = "/" + arch_dir
                if rb.endswith(suffix):
                    parent = rb[: -len(suffix)]
                    urls.append(f"{parent}/{href_clean}")
                    break

    # de-duplicate while preserving order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

# ---------------------------
# Dependency resolver & downloader
# ---------------------------


def _build_merged_index(repo_bases: List[str]) -> "RepoIndex":
    merged = RepoIndex()
    for base in repo_bases:
        repomd = _find_repomd_url(base)
        other_map: Optional[Dict[Tuple[str, str], str]] = None
        try:
            other_url = _other_from_repomd(repomd)
            if other_url:
#                info(f"Fetching other metadata: {other_url}")   # ✅ 추가
                other_map = _parse_other(other_url)
        except Exception as e:
            warn(f"Other metadata not available for {base}: {e}")
        primary = _primary_from_repomd(repomd)
        idx = _parse_primary(primary, repo_base=base, other_map=other_map)
        _augment_index_with_filelists(idx, base)
        merged.merge_from(idx)
    return merged


def resolve_and_download(resolve_repo_urls: List[str],
                         debug_repo_urls: List[str],
                         pkg_names: List[str],
                         arch: Optional[str],
                         outdir: Path,
                         do_download: bool,
                         mode: str = "debug",
                         with_debugsource: bool = False,
                         include_noarch: bool = False) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
    """
    Resolve dependency closure starting from list of package names (from KS) across multiple repos.
    Return (resolved_pkg_files, missing_caps, used_urls)
    """
    mode = (mode or "debug").lower()
    if mode not in ("base", "debug", "both"):
        raise ValueError(f"Invalid mode: {mode}")

    idx_resolve = _build_merged_index(resolve_repo_urls)
    idx_debug   = _build_merged_index(debug_repo_urls)

    # bootstrap queue with the seed packages (by name)
    queue: List[PkgMeta] = []
    for name in pkg_names:
        metas = idx_resolve.by_name.get(name, [])
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
    used_urls: List[Tuple[str, str]] = []  # (dest_path_str, url_used)

    i = 0
    while i < len(queue):
        pkg = queue[i]; i += 1
        key = (pkg.name, pkg.arch)
        if key in visited_pkgs:
            continue
        visited_pkgs.add(key)

        # enqueue its requires
        for cap in sorted(pkg.requires):
            # Note: file path requirements like "/usr/bin/awk" are now satisfied via filelists augmentation
            prov = idx_resolve.pick_provider(cap, arch or pkg.arch or "noarch")
            if not prov:
                missing_caps.append(cap)
                continue
            k2 = (prov.name, prov.arch)
            if k2 not in visited_pkgs:
                queue.append(prov)

    # Perform downloads according to mode
    if do_download:
        base_pkgs_seen = sorted({name for (name, _arch) in visited_pkgs})

        if mode in ("base", "both"):
            # Download base packages from resolve index
            for name, arch_seen in sorted(visited_pkgs):
                metas = idx_resolve.by_name.get(name, [])
                picked = None
                for m in metas:
                    if m.arch == arch_seen:
                        picked = m; break
                if not picked and metas:
                    picked = metas[0]
                if not picked:
                    continue
                # Skip downloading noarch when not requested (resolution may still use noarch)
                if (picked.arch == "noarch") and not include_noarch:
                    continue
                url = _absolute_href_with_base(picked.repo_base, picked.href)
                dest = outdir / Path(picked.href).name
                if dest.exists():
                    info(f"Already exists: {dest.name}")
                    used_urls.append((str(dest), url))
                else:
                    try:
                        info(f"Downloading {picked.name}.{picked.arch} (base) -> {dest.name}")
                        save_url_to(url, dest)
                        used_urls.append((str(dest), url))
                    except Exception as e:
                        warn(f"Download failed: {url} : {e}")
                        continue
                downloaded_files.append(str(dest))
        if mode in ("debug", "both"):
            # Download -debuginfo/-debugsource from debug repos
            for base_name in base_pkgs_seen:
                suffixes = ["-debuginfo"]
                if with_debugsource:
                    suffixes.append("-debugsource")
                for suffix in suffixes:
                    dbg_name = f"{base_name}{suffix}"
                    metas = idx_debug.by_name.get(dbg_name, [])
                    if not metas:
                        continue
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
                    if not picked:
                        continue
                    # Skip downloading noarch debuginfo when not requested
                    if (picked.arch == "noarch") and not include_noarch:
                        continue
                    dest = outdir / Path(picked.href).name
                    if dest.exists():
                        info(f"Already exists: {dest.name}")
                        candidates = _debug_url_candidates(picked.repo_base, picked.href)
                        if candidates:
                            used_urls.append((str(dest), candidates[0]))
                    else:
                        candidates = _debug_url_candidates(picked.repo_base, picked.href)
                        last_err = None
                        chosen_url = None
                        for attempt, url in enumerate(candidates, start=1):
                            try:
                                info(f"Downloading {picked.name}.{picked.arch} (debug) -> {dest.name} [try {attempt}/{len(candidates)}]")
                                save_url_to(url, dest)
                                chosen_url = url
                                last_err = None
                                break
                            except Exception as e:
                                last_err = e
                                warn(f"Download failed: {url} : {e}")
                        if last_err is not None:
                            # couldn't fetch with any candidate; skip recording as downloaded
                            continue
                        if chosen_url:
                            used_urls.append((str(dest), chosen_url))
                    # record file presence for both existing and newly downloaded cases
                    downloaded_files.append(str(dest))
    return downloaded_files, missing_caps, used_urls

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
    ap.add_argument("--mode", choices=["base", "debug", "both"], default=None,
                    help="What to download after resolving with packages repos: base RPMs, debug RPMs, or both.")
    ap.add_argument("--no-derive-pairs", action="store_true",
                    help="Do not derive sibling packages/debug repos; use repos exactly as provided.")
    ap.add_argument("--with-debugsource", action="store_true",
                    help="Also download -debugsource packages along with -debuginfo (default: off).")
    ap.add_argument("--include-noarch", action="store_true",
                    help="Also download noarch RPMs (default: off; deps may resolve via noarch but downloads are skipped).")
    ap.add_argument("--csv-out", type=str, default=None,
                    help="If set, write a CSV of successfully downloaded files with their source URL.")
    args = ap.parse_args()

    cfg = load_config(args.config)

    # Merge: CLI overrides config
    ks_entry = args.ks or cfg.get("ks")
    arch = (args.arch or cfg.get("arch") or detect_host_arch()).lower()
    outdir = Path(args.out or cfg.get("out", "./rpms"))
    fmt = args.format or cfg.get("format", "plain")
    show_groups = args.show_groups or bool(cfg.get("show_groups", False))
    do_download = args.download or bool(cfg.get("download", False))

    mode_cfg = cfg.get("mode")
    mode = args.mode or mode_cfg or "debug"
    derive_pairs = not args.no_derive_pairs
    derive_pairs = bool(cfg.get("derive_pairs", derive_pairs))
    with_debugsource = bool(cfg.get("with_debugsource", False)) or bool(args.with_debugsource)
    # noarch packages are allowed for dependency resolution,
    # but actual downloading of noarch RPMs is controlled by this flag (default off).
    include_noarch = bool(cfg.get("include_noarch", False)) or bool(args.include_noarch)
    csv_out = args.csv_out if args.csv_out is not None else cfg.get("csv_out")
    csv_path = Path(csv_out) if csv_out else None

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

    # Expand KS pseudo-packages/presets via repo group metadata (comps)
    # Use resolve repos (packages side) to build groups index.
    # We need repos prepared earlier; if not downloading we still build with provided repos.
    # Build resolve/debug repo lists first (so we can create group index on resolve repos).
    resolve_repos, debug_repos = _split_resolve_download_repos(repo_list, derive_pairs=derive_pairs)
    groups_index = _build_groups_index(resolve_repos)

    expanded: List[str] = []
    skipped: List[str] = []
    for name in packages:
        # treat as group id if present in groups_index
        if name in groups_index:
            expanded.extend(groups_index[name])
            skipped.append(name)
        else:
            expanded.append(name)
    if skipped:
        info(f"Expanded {len(skipped)} preset/group token(s) via comps: {', '.join(skipped)}")
    packages = sorted(set(expanded))

    # 2) Print package list (before download)
    print(format_list(packages, list(ks.groups), list(ks.excludes), fmt, show_groups, ks.sources))

    # 3) Resolve & download (optional)
    if do_download:
        outdir.mkdir(parents=True, exist_ok=True)
        # resolve_repos, debug_repos already computed above
        files, missing, used_urls = resolve_and_download(
            resolve_repos, debug_repos, packages, arch, outdir,
            do_download=True, mode=mode, with_debugsource=with_debugsource,
            include_noarch=include_noarch
        )
        info(f"Resolved {len(files)} RPM file(s). Output: {outdir}")
        # Write CSV if requested
        if csv_path and used_urls:
            try:
                import csv
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                with open(csv_path, "w", newline="", encoding="utf-8") as fcsv:
                    w = csv.writer(fcsv)
                    w.writerow(["file", "url"])  # header
                    for dest, url in used_urls:
                        w.writerow([dest, url])
                info(f"Wrote CSV: {csv_path}")
            except Exception as e:
                warn(f"Failed to write CSV {csv_path}: {e}")
        if missing:
            warn(f"Capabilities with no provider in repo: {len(missing)}")
            for cap in sorted(set(missing)):
                warn(f"  - {cap}")

if __name__ == "__main__":
    main()