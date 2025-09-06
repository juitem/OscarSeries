# fromKS: Tizen KS → Package List/Downloader (Principle Documentation)

This document explains in detail the entire principle of how the `download.py`/`download_debug-rpms_from_ks.py` (same family) programs read the **Tizen KS (Kickstart) script**, perform **package/dependency resolution**, and download **base RPM / debug (-debuginfo / -debugsource)** from the **Tizen repo**.

---

## Key Objectives

- **No image is actually created.** Only extract the **necessary packages** from KS, and download RPMs from the repo if desired.
- **No use of generic Linux metadata servers.** Only use the `repodata` from the **user-provided Tizen repos**.
- **Expand KS preset/group tokens** (e.g., `building-blocks-root-Preset_*`) into **actual package names** using comps (group) metadata.
- **Support debug-only mode.** Parse using packages metadata, but download from debug repo focusing on `-debuginfo`.  
  (`-debugsource` is **off by default**, can be **enabled via config/CLI**)
- **Support parallel downloading and metadata parsing (`--parallel`)**
- **Configurable HTTP timeout (`--timeout`) and retry count (`--retries`)**
- **Record successfully downloaded files and URLs in CSV (`--csv-out`)**

---

## Overview
```
        ┌─────────────┐
        │   KS(.ks)   │  <-- Process %include, %ifarch, etc.
        └─────┬───────┘
              │           (1) Parse KS
              ▼
      ┌──────────────┐
      │ Package Seed │  <-- include/exclude, @group(token)
      └──────┬───────┘
             │           (2) Expand groups (comps)
             ▼
  ┌────────────────────┐
  │ Actual Package List │
  └─────────┬──────────┘
            │           (3) Dependency Resolution
            ▼
    ┌──────────────┐
    │ Dependency Closure │  <-- calculated via provides/requires
    └──────┬───────┘
           │           (4) Download (optional)
           │
   ┌───────▼────────┐
   │ base / debug    │  <-- mode: base|debug|both
   └─────────────────┘
```

---

## KS Parser (1): What and How It Reads

- **Input**: URL or local file
- **Supports**:
  - `%include <path>`: **recursive inclusion** (relative paths resolved based on KS URL)
  - `%ifarch aarch64 x86_64` / `%if 1` / `%else` / `%endif`: **simple conditional branching**
  - `%packages ... %end` block:  
    - normal package names  
    - `-package-name` (exclude)  
    - `@group` (group token)  
- **Output**:  
  - `includes`: packages/tokens to include  
  - `excludes`: exclusion list  
  - `groups`: `@group` tokens  
  - `sources`: list of parsed KS files (root + includes)

> 📝 Line continuation with `\` allowed; comments after `#` are removed.

---

## Group Expansion (2): Preset/Group Tokens → Actual Packages

- **Why?** Snapshot KS files often contain **group/preset IDs** instead of actual packages.
- **How?**
  1. Find `type="group"` (or `group_gz`) entry in `repodata/repomd.xml`
  2. Fetch **comps XML**, and extract `<group><id>...</id> ... <packagereq type="mandatory|default">name</packagereq>` as **actual package names**
  3. If KS tokens (like `building-blocks-*`) match comps group IDs, replace them with the group's **package list**

> Result: KS **token seed** → **actual package seed** conversion.

---

## Repo Indexing (3): Reading Metadata for Dependency Resolution

- **Input**: user-provided `repos[]` (can be packages/debug path)
- **Automatic pair inference**:
  - If input is `.../packages/`, automatically infer corresponding `.../debug/` in the same snapshot (and vice versa)
  - Reason:  
    - Dependency resolution is more reliable using **packages side `primary.xml`**  
    - Downloads happen from **packages** (base) or **debug** (debug) depending on mode
- **repomd.xml → primary.xml(.gz)**:
  - Locate `type="primary"` entry's `href` in `repodata/repomd.xml` and build **absolute URL**
  - Read **all packages** from `primary.xml`:
    - `name`, `arch`, `href`, `provides{}`, `requires{}`
- **Namespace (important)**: `http://linux.duke.edu/...`  
  - This is an **XML schema identifier**, not a network address.  
  - Tizen uses the same **RPM-MD format**, so the namespace must remain intact for parsing.

---

## Dependency Resolution (3-2): Building Closure via provides/requires

- **Queue-based** (similar to BFS expansion)
  1. Pick seed packages (including expanded groups) by name→metadata (arch priority: `aarch64` → `noarch` → any)
  2. Map each package's `requires` capabilities to **providers** in `provides`
  3. Add unvisited packages to the queue
- **Result**: `visited_pkgs` is the **resolved closure** (package set)
- **Note**: Depending on repo combinations (mixed snapshots), some **unresolved capabilities** may remain, summarized as WARN.

---

## Downloading (4): base/debug/both by mode

- `--mode` or config `"mode"`:
  - `base` : only **base RPMs** (from `packages`)
  - `debug`: only **debug RPMs** (from `debug`, focusing on `-debuginfo`, excluding `-debugsource` by default)
  - `both` : both
- **`-debugsource` off by default**  
  - Only added if `--with-debugsource` or config `"with_debugsource": true`
- **Path concatenation issues (important)**  
  - Some snapshots place debug repo files **directly under `/debug/` root** without arch folders.
  - Meanwhile, `primary.xml`'s `href` may have arch prefix like `aarch64/<file>`.
  - Hence, the program tries these **candidate (fallback) URLs** sequentially:
    1) `repo_base` + `href` (standard)
    2) If debug repo and `href` starts with `aarch64/...`, remove prefix and try `/debug/<file>`
    3) If `repo_base` ends with `/debug/aarch64` and `href` is filename only, try parent `/debug/<file>`
  - Try each candidate → stop on success / try next on failure

---

## Parallel Processing & CSV Output

- `--parallel` option controls the number of workers for downloading and metadata parsing.  
  Default is 2× CPU cores, minimum 4, maximum 16.
- `--timeout` sets HTTP request timeout in seconds, default 30.
- `--retries` sets retry count on failure, default 2.
- `--csv-out` or config `"csv_out"` saves successfully downloaded file paths and actual URLs to a CSV file.
- CSV example:
  ```
  file,url
  ./rpms-base-UplusB-snapshot/package1.rpm,https://download.tizen.org/snapshots/.../package1.rpm
  ./rpms-base-UplusB-snapshot/package2.rpm,https://download.tizen.org/snapshots/.../package2.rpm
  ```

---

## Configuration File (JSON) Examples

> **As requested**: ① base only ② debug only ③ both  
> `with_debugsource` is **always false** (default)  
> Parallel, timeout, retries, and CSV output options added

### 1) `basic.json` — base only
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "base",
  "derive_pairs": true,
  "out": "./rpms-base-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "with_debugsource": false,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-base-UplusB-snapshot.csv"
}
```

### 2) `debug.json` — debug only (`-debuginfo`)
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "debug",
  "with_debugsource": false,
  "derive_pairs": true,
  "out": "./rpms-debug-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-debug-UplusB-snapshot.csv"
}
```

### 3) `both.json` — base + debug
```json
{
  "ks": "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/builddata/images/standard/image-configurations/tizen-headless-aarch64.ks",
  "repos": [
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20250805.212546/repos/standard/packages/",
    "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Unified/tizen-unified_20250401.210430/repos/standard/packages/aarch64/"
  ],
  "arch": "aarch64",
  "mode": "both",
  "with_debugsource": false,
  "derive_pairs": true,
  "out": "./rpms-both-UplusB-snapshot",
  "format": "markdown",
  "show_groups": true,
  "download": true,
  "parallel": 12,
  "timeout": 30,
  "retries": 2,
  "csv_out": "./rpms-both-UplusB-snapshot.csv"
}
```

---

## Usage Examples

```bash
# 1) base only
python3 ./download_debug-rpms_from_ks.py --config ./basic.json

# 2) debug only (-debuginfo)
python3 ./download_debug-rpms_from_ks.py --config ./debug.json

# 3) both
python3 ./download_debug-rpms_from_ks.py --config ./both.json

# To temporarily include -debugsource (default is false)
python3 ./download_debug-rpms_from_ks.py --config ./debug.json --with-debugsource

# Parallel 12, timeout 20 seconds, retry 3 times, CSV output specified
python3 ./download_debug-rpms_from_ks.py --config ./both.json --parallel 12 --timeout 20 --retries 3 --csv-out ./rpms-both-UplusB-snapshot.csv

# Config file values are defaults; CLI options take precedence.
```

---

## Log Guide

- `Fetching group metadata:` … `group.xml[.gz]` → loading comps needed for group expansion
- `Fetching primary metadata:` … `primary.xml[.gz]` → loading package index for dependency resolution
- `Expanded N preset/group token(s)` → KS tokens expanded into actual packages
- `Downloading ... (base)` / `(debug)` → actual file saved
- `try 1/2` → trying fallback URL
- `Capabilities with no provider ...` → unresolved requires under current repo combination (consider adding repos/snapshots)

---

## Frequently Asked Questions (FAQ)

**Q1. Why is the namespace `linux.duke.edu`?**  
A. It is the **schema identifier** for RPM-MD format (XML), **not a network request**. Changing it breaks XML parsing.

**Q2. Why is `repodata/repomd.xml` mixed in two levels?**  
A. Tizen may have `repodata/primary.xml.gz`'s `href` relative to repo root. So absolute URLs are built relative to the parent of `repomd.xml`.

**Q3. Why does the debug repo URL often return 404?**  
A. Some snapshots place debug repo files **directly under `/debug/` root** (no arch folder). The program tries fallback URLs automatically.

**Q4. Why are no actual package names visible in KS?**  
A. This is normal. Most are managed by **group tokens**. This tool expands them to actual lists via comps.

**Q5. What does the CSV output file look like?**  
A. It has header `file,url` listing each downloaded RPM path and its actual URL. Existing files are recorded with the first candidate URL.

---

## Limitations & Tips

- **Mixed snapshots** (e.g., Base=2025-08, Unified=2025-04): some requires may remain **unresolved** due to group/package version differences.
- **Performance**: The tool downloads a lot of metadata on each run. Consider caching/parallel options if needed.
- **Security**: Only accesses provided URLs. Use `urllib`-level proxy environment variables for proxy/mirror environments.

---

## Extension Ideas

- **--save-manifest**: save resolved package/version list as JSON/CSV
- **--parallel N**: parallelize downloads
- **--only PATTERN**: filter and download only specific patterns
- **--exclude-debugsource** (default) and more toggle options (e.g., `--only-debuginfo`)

---

## Conclusion

- KS → (group expansion) → dependency closure → (mode-based) base/debug download
- Only use **Tizen repo metadata**
- Robustly handle snapshot/repo layout differences (especially debug) with **fallback URLs**
- `-debugsource` is **off by default**, enable only when needed via option