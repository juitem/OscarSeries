# rFileViewer — Tree + Preview (Markdown / HTML / CSV / TXT / Images)

This document summarizes the features and usage of `rFileViewer.py`.

---
## Key Features
- **Left Tree / Right Preview** layout
  - The tree expands quickly with **lazy loading**
  - **Directories are always shown**, files are toggled based on filter conditions
- **Top Toolbar**
  - **Open Folder**: Open a different starting directory
  - **Viewable only**: Show only viewable files (directories remain visible)
  - **Toggle by Extension**: 📝(MD), 🌐(HTML), 📊(CSV), 📄(TXT), 🖼️PNG, 🖼️JPG
  - **🔄 Refresh**: Refresh contents of the current (selected/root) directory only
  - **Share Script…**: Select a custom share script to use instead of `share.py`
  - **Search**: Filter based on **regular expressions** (case-insensitive)
- **File Preview (Right)**
  - **Markdown**: Convert to HTML using `markdown2` (preferred) or `python-markdown`, supports tables/code blocks
  - **HTML**: Render as-is (if partial fragment, wrap in a document for display), supports loading relative resources
  - **CSV**: Render as an HTML table (default limit: **up to 2,000 rows × 200 columns**)
  - **TXT**: Safely displayed inside `<pre>`
  - **Images**: Preview PNG/JPG/JPEG (load files via `file://` URL)
  - **If HtmlFrame is unavailable**, display **source in Text widget** (read-only guaranteed)
- **Copy/Open Tools (Top Right Toolbar & Context Menu)**
  - **Copy HTML / Copy Text**
  - **Copy as PNG (Data URL)**, **Copy as Bitmap** *(best effort per OS: Win/macOS/Linux)*
  - **Copy as Markdown / Copy as TXT** (source-based)
  - **Select All** (only in Text fallback for full selection)
  - **↗ Open**: Open file with system default application
- **Sharing (integrated with share.py)**
  - Right-click **directory in tree** → **Share On… / Share Off / Open Browser**
  - Shared folders show a **📡 icon** on the tree label
  - The **Share Script…** button allows replacing the script to run (default: `share.py` in the same folder)
- **Port Suggestion & Validation**
  - When starting sharing, automatically suggest a default port by searching for a **free port starting from last used port +1**
  - If the user inputs a port **already in use**, execution is blocked
  - Initial suggestion is **8000** (internal default 7999 → +1)
- **Exit Behavior (Cleaning up Sharing Processes)**
  - `--kill-on-terminate {true,false,ask}` (default **ask**)
    - `true`: Always terminate the sharing server on exit
    - `false`: Keep the sharing server running on exit
    - `ask`: Show a confirmation dialog **only if there is at least one shared folder** → terminate if Yes is selected
  - Closing the window (X), **Ctrl+C / SIGINT / SIGTERM** all apply the same policy
  - (POSIX) Sharing processes are launched in a **new session** to improve termination stability

---
## Usage
```bash
python3 rFileViewer.py [PATH] \
  -d, --start-dir DIR        # Starting directory (can be used instead of PATH) \
  -s, --search REGEX         # Regular expression search to apply immediately on launch \
      --view-alltype         # Show all file types at start (disable Viewable only) \
      --kill-on-terminate {true,false,ask}  # Sharing server handling policy on exit (default: ask)
```