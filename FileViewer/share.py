#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple directory web sharing.
Usage:
    python share.py /path/to/dir -p 8000
"""

import os
import sys
import argparse
import html  # NEW: escape file/directory names
from urllib.parse import quote  # NEW: safe URLs for links
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

def main():
    parser = argparse.ArgumentParser(description="Share a directory over HTTP")
    parser.add_argument("directory", help="Directory to share")
    parser.add_argument("-p", "--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()

    root = os.path.abspath(os.path.expanduser(args.directory))
    if not os.path.isdir(root):
        print(f"Error: not a directory -> {root}", file=sys.stderr)
        sys.exit(2)

    os.chdir(root)

    class Handler(SimpleHTTPRequestHandler):
        ROOT = root  # absolute start directory (fixed across navigation)

        def _format_size(self, size: int) -> str:
            units = ["B", "KB", "MB", "GB", "TB"]
            for unit in units:
                if size < 1024:
                    return f"{size:.0f} {unit}"
                size /= 1024.0
            return f"{size:.0f} PB"
        """HTTP handler that adds per-type icons to directory listings."""

        # --- Icon & extension maps ---
        MD_EXTS = {".md", ".mdx", ".markdown"}
        HTML_EXTS = {".html", ".htm"}
        CSV_EXTS = {".csv"}
        TXT_EXTS = {".txt"}
        IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

        ICON_MD = "📝"
        ICON_HTML = "🌐"
        ICON_CSV = "📊"
        ICON_TXT = "📄"
        ICON_IMG = "🖼️"
        ICON_DIR = "📁"
        ICON_FILE = "📦"

        def end_headers(self):
            # Allow CORS for convenience
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def _icon_for(self, name: str, is_dir: bool) -> str:
            if is_dir:
                return self.ICON_DIR
            ext = os.path.splitext(name.lower())[1]
            if ext in self.MD_EXTS:
                return self.ICON_MD
            if ext in self.HTML_EXTS:
                return self.ICON_HTML
            if ext in self.CSV_EXTS:
                return self.ICON_CSV
            if ext in self.TXT_EXTS:
                return self.ICON_TXT
            if ext in self.IMG_EXTS:
                return self.ICON_IMG
            return self.ICON_FILE

        def list_directory(self, path):
            """Produce a directory listing with icons for known types.
            Largely based on `SimpleHTTPRequestHandler.list_directory` but simplified.
            """
            try:
                entries = os.listdir(path)
            except OSError:
                self.send_error(404, "No permission to list directory")
                return None
            entries.sort(key=str.lower)

            displaypath = html.escape(self.path, quote=False)
            enc = sys.getfilesystemencoding()
            title = f"Directory listing for {displaypath}"

            out = []
            out.append("<!DOCTYPE html>")
            out.append("<html><head>")
            out.append('<meta charset="utf-8">')
            out.append(f"<title>{title}</title>")
            # Basic styles for readability
            out.append("<style>\n"
                       "  :root{--fg:#111;--muted:#666;}\n"
                       "  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;padding:20px;color:var(--fg);}\n"
                       "  h1{font-size:1.1rem;margin:0 0 12px;}\n"
                       "  ul{list-style:none;padding:0;margin:0;}\n"
                       "  li{display:flex;gap:.5rem;align-items:center;padding:6px 4px;border-bottom:1px solid #eee;}\n"
                       "  li a{text-decoration:none;color:#0366d6;word-break:break-all;}\n"
                       "  .name{flex:1;}\n"
                       "  .size{color:var(--muted);font-variant-numeric:tabular-nums;}\n"
                       "  .icon{font-size:1.1em;line-height:1;display:inline-flex;align-items:center;justify-content:center;width:1.25em;}\n"
                       "  /* Emoji font fallbacks across platforms */\n"
                       "  .icon{font-family:'Apple Color Emoji','Segoe UI Emoji','Segoe UI Symbol','Noto Color Emoji','EmojiOne Color','Twemoji Mozilla',emoji,sans-serif;}\n"
                       "  .root{font-size:.8rem;color:var(--muted);margin:0 0 2px;}\n"
                       "  .rel{font-size:.9rem;color:var(--muted);margin:0 0 6px;}\n"
                       "  .basename{font-size:1.4rem;margin:0 0 12px;font-weight:600;}\n"
                       "</style>")
            out.append("</head><body>")
            cur_abs = os.path.abspath(path)
            root_abs = getattr(self, "ROOT", cur_abs)
            try:
                rel_path = os.path.relpath(cur_abs, root_abs)
            except Exception:
                rel_path = "."
            if rel_path == ".":
                rel_display = "."
            else:
                rel_display = rel_path

            root_html = html.escape(root_abs, quote=False)
            rel_html = html.escape(rel_display, quote=False)
            base_name = os.path.basename(cur_abs) or cur_abs
            base_html = html.escape(base_name, quote=False)

            out.append(f"<p class=\"root\">Shared Dir: {root_html}</p>")
            out.append(f"<p class=\"rel\">Current Dir: {rel_html}</p>")
            out.append(f"<div class=\"basename\">{base_html}</div>")
            # out.append(f"<h1>{title}</h1>")  # replaced by above

            out.append("<ul>")

            # Parent directory link
            if self.path not in ("/", ""):
                up = os.path.dirname(self.path.rstrip("/")) or "/"
                out.append(f"<li>⬆️ <a class=\"name\" href=\"{quote(up)}\">[..]</a></li>")

            for name in entries:
                fullname = os.path.join(path, name)
                display = html.escape(name, quote=False)
                link = quote(name)
                is_dir = os.path.isdir(fullname)
                ext = os.path.splitext(name.lower())[1]
                icon = self._icon_for(name, is_dir)
                if is_dir:
                    href = f"{link}/"
                    size_html = ""
                else:
                    href = link
                    try:
                        size = os.path.getsize(fullname)
                        size_html = f"<span class=\"size\">{self._format_size(size)}</span>"
                    except OSError:
                        size_html = ""

                # Basic textual fallback tag per type
                tag = "MD" if ext in self.MD_EXTS else \
                      "HTML" if ext in self.HTML_EXTS else \
                      "CSV" if ext in self.CSV_EXTS else \
                      "TXT" if ext in self.TXT_EXTS else \
                      "IMG" if ext in self.IMG_EXTS else \
                      ("DIR" if is_dir else "FILE")
                out.append(f"<li><span class=\"icon\" aria-hidden=\"true\">{icon}</span><span class=\"fallback\" aria-hidden=\"true\">[{tag}]</span> <a class=\"name\" href=\"{href}\">{display}</a> {size_html}</li>")

            out.append("</ul>")
            out.append("</body></html>")
            encoded = "\n".join(out).encode(enc, "surrogateescape")
            self.send_response(200)
            self.send_header("Content-Type", f"text/html; charset={enc}")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return None

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Serving '{root}' at http://localhost:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nServer stopped.")

if __name__ == "__main__":
    main()