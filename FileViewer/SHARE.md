with open("/mnt/data/test.md", "w", encoding="utf-8") as f:
    f.write("""# Features of `share.py`

The `share.py` script is a **simple HTTP-based directory sharing tool** with a built-in file browser.  
Here are its key features:

## 📂 Directory Sharing
- Serves any given directory over HTTP with `python share.py /path/to/dir -p 8000`.
- Supports configurable port via `-p` / `--port` (default: `8000`).
- Ensures safe navigation by restricting access to the specified root directory.

## 🗂️ Directory Listing (Tree View)
- Displays a **two-pane UI**:
  - **Left pane**: directory tree (folders first, sorted alphabetically).
  - **Right pane**: file preview area.
- Uses emojis/icons to represent file types:
  - 📁 Directory
  - 📝 Markdown
  - 🌐 HTML
  - 📊 CSV
  - 📄 Text
  - 🖼️ Image
  - 📦 Other files

## 🔎 File Preview Support
- **Markdown (`.md`, `.mdx`, `.markdown`)**:
  - Rendered to HTML using `markdown2` or `python-markdown`.
  - If both fail, falls back to raw `<pre>` text.
- **HTML (`.html`, `.htm`)**:
  - Displayed inside an `<iframe>`.
- **Images (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.tiff`)**:
  - Displayed with proper scaling and border styling.
- **CSV (`.csv`)**:
  - Rendered as a styled HTML table.
- **Text (`.txt`)**:
  - Displayed inside a `<pre>` block.

## 📥 File Operations (Context Menu)
- Right-click on a file in the tree opens a **custom context menu** with options:
  - **Download** → via `/__api/download?p=...` (forces `Content-Disposition: attachment`).
  - **Copy link** → copies the encoded file URL to clipboard.
  - **Save as…** → triggers browser “Save As” dialog using `<a download>`.

## ⚙️ API Endpoints
- `GET /__api/list?p=path` → returns JSON with directory entries.
- `GET /__api/render_md?p=path` → returns rendered Markdown HTML + engine info.
- `GET /__api/download?p=path` → returns file as attachment with proper MIME type.

## 🛡️ Security
- Implements `_safe_join` to ensure all paths remain inside the shared root.
- Uses `Access-Control-Allow-Origin: *` for convenient cross-origin preview.

## 🎨 UI Styling
- Clean modern CSS with flex layout.
- Responsive two-pane interface with context menu.
- Styled tables, pre blocks, and Markdown output.

---

✅ In summary, `share.py` is a **portable mini file server** with a **rich in-browser file explorer**, supporting previews for Markdown, HTML, CSV, text, and images, along with secure file downloads.
""")