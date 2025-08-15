#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File Tree + Preview (Markdown/HTML/CSV/TXT)
- Left: Lazy-loaded file tree
- Right: Preview pane with HtmlFrame (tkinterweb) if available, else Text fallback
- Top toolbar: Open Folder, Viewable only (directories always visible), Search
- Status bar at bottom
- CLI: --start-dir, --search
"""

import os
import sys
import csv
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Optional HTML viewer
try:
    from tkinterweb import HtmlFrame  # pip install tkinterweb
except Exception:
    HtmlFrame = None

# ---------- Supported extensions & icons ----------
MD_EXTS   = {".md", ".mdx", ".markdown"}
HTML_EXTS = {".html", ".htm"}
CSV_EXTS  = {".csv"}
TXT_EXTS  = {".txt"}

ICON_MD   = "📝"
ICON_HTML = "🌐"
ICON_CSV  = "📊"
ICON_TXT  = "📄"

VIEWABLE_EXTS = MD_EXTS | HTML_EXTS | CSV_EXTS | TXT_EXTS


# ---------- HTML loader compatibility wrapper ----------
def htmlframe_set(frame, html: str, base_url: str | None = None):
    """
    Try multiple APIs to show HTML in tkinterweb (or compatible widgets).
    Fallback: treat the target as a Text widget and dump HTML source.
    """
    # tkinterweb.HtmlFrame path
    if hasattr(frame, "load_html"):
        if base_url:
            try:
                frame.load_html(html, baseurl=base_url)  # common signature
                return
            except TypeError:
                # Some versions do not accept baseurl kwarg
                try:
                    frame.load_html(html)
                    return
                except Exception:
                    pass
            except Exception:
                try:
                    frame.load_html(html)
                    return
                except Exception:
                    pass
        else:
            try:
                frame.load_html(html)
                return
            except Exception:
                pass

    # Generic widget APIs sometimes seen in alternatives
    for m in ("set_html", "set_content"):
        if hasattr(frame, m):
            try:
                getattr(frame, m)(html)
                return
            except Exception:
                pass

    # Fallback to Text widget style
    try:
        frame.config(state="normal")
        frame.delete("1.0", "end")
        frame.insert("1.0", html)
        frame.config(state="disabled")
    except Exception:
        pass


# ---------- Markdown -> HTML with table support ----------
def render_markdown_to_html(md_text: str) -> tuple[str, str]:
    """
    Convert Markdown text to HTML. Returns (html, engine_name).
    """
    # Preferred: markdown2 (rich extras)
    try:
        import markdown2  # pip install markdown2
        html = markdown2.markdown(
            md_text,
            extras=["tables", "fenced-code-blocks", "strike", "toc", "cuddled-lists"]
        )
        return html, "markdown2"
    except Exception:
        pass

    # Fallback: Python-Markdown
    try:
        import markdown as md  # pip install markdown
        html = md.markdown(
            md_text,
            extensions=["extra", "tables", "fenced_code", "toc", "sane_lists", "admonition", "md_in_html"]
        )
        return html, "python-markdown"
    except Exception:
        from html import escape
        return f"<pre>{escape(md_text)}</pre>", "raw-pre"


# ---------- Utility helpers ----------
def is_viewable_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in VIEWABLE_EXTS

def decorate_name(name: str, path: str, is_dir: bool) -> str:
    """Return label with icon for known file types."""
    if is_dir:
        return name
    _, ext = os.path.splitext(path.lower())
    if ext in MD_EXTS:
        return f"{ICON_MD} {name}"
    if ext in HTML_EXTS:
        return f"{ICON_HTML} {name}"
    if ext in CSV_EXTS:
        return f"{ICON_CSV} {name}"
    if ext in TXT_EXTS:
        return f"{ICON_TXT} {name}"
    return name


# ---------- Tk app ----------
class App(tk.Tk):
    def __init__(self, start_dir: str | None = None, initial_search: str | None = None):
        super().__init__()
        self.title("Tree + Preview (MD/HTML/CSV/TXT)")
        self.geometry("1280x860")

        self.status = tk.StringVar(value="Ready.")
        self._build_ui()

        # Initial directory
        self.root_dir = None
        if start_dir:
            self.load_root(start_dir)
        else:
            self.load_root(os.getcwd())

        # Apply initial search if provided
        if isinstance(initial_search, str) and initial_search.strip():
            self.search_var.set(initial_search)
            self.apply_search()  # immediate

    # ---------- UI ----------
    def _build_ui(self):
        # Top toolbar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, side=tk.TOP, padx=8, pady=6)

        ttk.Button(top, text="Open Folder", command=self.choose_folder).pack(side=tk.LEFT)

        self.show_only_viewable = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top,
            text="Viewable only",
            variable=self.show_only_viewable,
            command=self._apply_viewable_filter  # in-place filter (preserves state)
        ).pack(side=tk.LEFT, padx=(12, 6))

        ttk.Label(top, text="Search:").pack(side=tk.LEFT, padx=(12, 6))
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        entry.pack(side=tk.LEFT)
        entry.bind("<KeyRelease>", self._on_search_key)
        self._search_job = None

        # Main split
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Left (tree)
        left = ttk.Frame(paned, width=360)
        paned.add(left, weight=1)

        self.tree = ttk.Treeview(left, columns=("fullpath",), show="tree")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewOpen>>", self.on_open_node)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_node)

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        # Right (preview)
        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        if HtmlFrame is None:
            self.html = tk.Text(right, wrap="word")
            self.html.insert("1.0",
                "Install 'tkinterweb' for rich HTML preview:\n\n    pip install tkinterweb\n\n"
                "Currently using plain Text fallback."
            )
            self.html.config(state="disabled")
            self.html_is_webview = False
            self.status.set("Renderer: Text fallback")
        else:
            self.html = HtmlFrame(right, messages_enabled=False)
            self.html_is_webview = True
            self.status.set("Renderer: HtmlFrame")
        self.html.pack(fill=tk.BOTH, expand=True)

        # Status bar
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=4)

    # ---------- Tree / loading ----------
    def choose_folder(self):
        d = filedialog.askdirectory(title="Choose a folder")
        if d:
            self.load_root(d)

    def load_root(self, root: str):
        """Reset the tree and set a fresh root with a single dummy child."""
        self.root_dir = root
        self.tree.delete(*self.tree.get_children())
        root_id = self.tree.insert("", "end", text=root, open=True, values=(root,))
        self._insert_dummy_child(root_id)

    def _insert_dummy_child(self, node_id):
        """Insert one dummy child so the node shows a disclosure arrow."""
        for c in self.tree.get_children(node_id):
            if self.tree.item(c, "text") == "dummy":
                return
        self.tree.insert(node_id, "end", text="dummy", values=("__DUMMY__",))

    def on_open_node(self, _evt):
        """Populate a directory node once when expanded; no duplicate children."""
        node_id = self.tree.focus()
        if not node_id:
            return

        # If already populated with a real child (non-dummy), bail
        for cid in self.tree.get_children(node_id):
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            is_dummy = (txt == "dummy") or (vals and vals[0] == "__DUMMY__")
            if not is_dummy:
                return

        # Remove dummies
        for cid in list(self.tree.get_children(node_id)):
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            if (txt == "dummy") or (vals and vals[0] == "__DUMMY__"):
                self.tree.delete(cid)

        # Get directory path
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        if not vals:
            return
        fullpath = vals[0]

        try:
            entries = sorted(os.listdir(fullpath), key=str.lower)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list directory:\n{e}")
            return

        show_only = bool(self.show_only_viewable.get())

        for name in entries:
            p = os.path.join(fullpath, name)
            if os.path.isdir(p):
                child = self.tree.insert(
                    node_id, "end",
                    text=decorate_name(name, p, is_dir=True),
                    open=False,
                    values=(p,)
                )
                self._insert_dummy_child(child)
            else:
                if show_only and not is_viewable_file(p):
                    continue
                self.tree.insert(
                    node_id, "end",
                    text=decorate_name(name, p, is_dir=False),
                    values=(p,)
                )

    # ---------- Selection / preview ----------
    def on_select_node(self, _evt):
        sel = self.tree.selection()
        if not sel:
            return
        node_id = sel[0]
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        if not vals or vals[0] in ("", "__DUMMY__"):
            return

        path = vals[0]
        if os.path.isfile(path):
            self.render_file(path)

    # ---------- Search ----------
    def _on_search_key(self, _evt):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.apply_search)

    def apply_search(self):
        term = (self.search_var.get() or "").strip().lower()
        if not self.root_dir:
            return
        self.tree.delete(*self.tree.get_children())

        root_id = self.tree.insert("", "end", text=self.root_dir, open=True, values=(self.root_dir,))

        if not term:
            self._insert_dummy_child(root_id)
            return

        show_only = bool(self.show_only_viewable.get())

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            candidates = []
            if show_only:
                for fname in filenames:
                    if term in fname.lower():
                        p = os.path.join(dirpath, fname)
                        if is_viewable_file(p):
                            candidates.append(p)
            else:
                for name in dirnames + filenames:
                    if term in name.lower():
                        candidates.append(os.path.join(dirpath, name))

            for p in candidates:
                parent_id = root_id
                rel = os.path.relpath(p, self.root_dir)
                parts = [] if rel == "." else rel.split(os.sep)
                walk = self.root_dir
                for part in parts[:-1]:
                    walk = os.path.join(walk, part)
                    found = None
                    for c in self.tree.get_children(parent_id):
                        if self.tree.item(c, "text") == os.path.basename(walk):
                            found = c
                            break
                    if not found:
                        found = self.tree.insert(parent_id, "end", text=os.path.basename(walk), open=True, values=(walk,))
                    parent_id = found

                base = os.path.basename(p)
                is_dir = os.path.isdir(p)
                self.tree.insert(
                    parent_id, "end",
                    text=decorate_name(base, p, is_dir=is_dir),
                    open=False,
                    values=(p,)
                )

    # ---------- In-place filter (preserve expand/scroll/selection) ----------
    def _apply_viewable_filter(self):
        if not hasattr(self, "tree"):
            return
        show_only = bool(self.show_only_viewable.get())

        stack = list(self.tree.get_children(""))
        while stack:
            iid = stack.pop()
            stack.extend(self.tree.get_children(iid))

            vals = self.tree.item(iid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            path = vals[0] if vals else ""

            if not path or path == "__DUMMY__":
                continue

            if os.path.isdir(path):
                # Always show directories
                try:
                    self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass
            else:
                viewable = is_viewable_file(path)
                hide = (show_only and not viewable)
                try:
                    if hide:
                        self.tree.detach(iid)
                    else:
                        self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass

        # Clear selection if it points to a detached item
        for sid in list(self.tree.selection()):
            parent = self.tree.parent(sid)
            if sid not in self.tree.get_children(parent):
                self.tree.selection_remove(sid)

    # ---------- Rendering ----------
    def render_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext not in VIEWABLE_EXTS:
            self._show_message(
                f"Preview not available: {os.path.basename(path)}\n\n"
                f"Supported: {', '.join(sorted(VIEWABLE_EXTS))}"
            )
            return

        def work():
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    text = f.read()
            except Exception as e:
                self._show_message(f"Open error: {e}")
                return

            if ext in HTML_EXTS:
                # Pass-through HTML; wrap if fragment; use base_url so relative assets resolve
                html_body = text
                body = html_body.strip().lower()
                if ("<html" not in body) or ("</html>" not in body):
                    html_body = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
                base_url = os.path.dirname(os.path.abspath(path))

                def _apply_html():
                    if HtmlFrame is None:
                        self._show_message(html_body)
                        mode = "Text(fallback)"
                    else:
                        htmlframe_set(self.html, html_body, base_url=base_url)
                        mode = "HtmlFrame"
                    self.status.set(f"[HTML] Renderer: {mode}")
                self.after(0, _apply_html)
                return

            if ext in MD_EXTS:
                html_body, engine = render_markdown_to_html(text)
                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  pre, code {{ background: #f6f8fa; }}
                  pre {{ padding: 12px; overflow: auto; border-radius: 6px; }}
                  h1,h2,h3,h4 {{ margin-top: 1.2em; }}
                  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
                  thead th {{ background: #fafafa; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
                </style></head><body>{html_body}</body></html>
                """
                def _apply_md():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[Markdown] Engine: {engine} | Renderer: {mode}")
                self.after(0, _apply_md)
                return

            if ext in CSV_EXTS:
                # Render CSV as an HTML table (safety caps)
                MAX_ROWS = 2000
                MAX_COLS = 200
                rows, truncated = [], False
                try:
                    with open(path, "r", encoding="utf-8", newline="") as f:
                        rdr = csv.reader(f)
                        for ri, row in enumerate(rdr):
                            if ri >= MAX_ROWS:
                                truncated = True
                                break
                            rows.append(row[:MAX_COLS])
                except Exception as e:
                    self._show_message(f"CSV read error: {e}")
                    return

                from html import escape as esc
                if rows:
                    header = rows[0]
                    thead = "<thead><tr>" + "".join(f"<th>{esc(h or '')}</th>" for h in header) + "</tr></thead>"
                    body_rows = rows[1:]
                else:
                    thead = ""
                    body_rows = []

                tbody = "<tbody>" + "".join(
                    "<tr>" + "".join(f"<td>{esc(cell or '')}</td>" for cell in r) + "</tr>"
                    for r in body_rows
                ) + "</tbody>"

                note = "<p style='font-size:12px;color:#666;margin:8px 0 0;'>CSV preview"
                if truncated:
                    note += f" (showing first {MAX_ROWS} rows, first {MAX_COLS} cols)</p>"
                else:
                    note += ".</p>"

                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
                  thead th {{ background: #fafafa; position: sticky; top: 0; }}
                  .wrap {{ overflow: auto; max-height: 72vh; }}
                </style></head>
                <body>
                  {note}
                  <div class="wrap">
                    <table>
                      {thead}
                      {tbody}
                    </table>
                  </div>
                </body></html>
                """
                def _apply_csv():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[CSV] Renderer: {mode}")
                self.after(0, _apply_csv)
                return

            if ext in TXT_EXTS:
                from html import escape as esc
                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  pre {{ padding: 12px; overflow: auto; background:#f6f8fa; border-radius: 6px; }}
                </style></head><body>
                  <pre>{esc(text)}</pre>
                </body></html>
                """
                def _apply_txt():
                    self._set_html(html_doc)
                    mode = "HtmlFrame" if getattr(self, "html_is_webview", False) else "Text(fallback)"
                    self.status.set(f"[TXT] Renderer: {mode}")
                self.after(0, _apply_txt)
                return

        threading.Thread(target=work, daemon=True).start()

    # ---------- HTML/text helpers ----------
    def _show_message(self, text: str):
        if HtmlFrame is None:
            self.html.config(state="normal")
            self.html.delete("1.0", tk.END)
            self.html.insert("1.0", text)
            self.html.config(state="disabled")
        else:
            safe = (
                "<html><head><meta charset='utf-8'></head>"
                "<body style='font-family:sans-serif;white-space:pre-wrap;padding:16px;'>"
                f"{self._escape_html(text)}</body></html>"
            )
            htmlframe_set(self.html, safe)

    def _set_html(self, html: str):
        if HtmlFrame is None:
            self._show_message(html)
        else:
            htmlframe_set(self.html, html)

    @staticmethod
    def _escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- CLI ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tree + Preview (MD/HTML/CSV/TXT)")
    parser.add_argument("path", nargs="?", default=None,
                        help="(Optional) start folder positional argument")
    parser.add_argument("-d", "--start-dir", dest="start_dir", default=None,
                        help="Start folder to load")
    parser.add_argument("-s", "--search", dest="initial_search", default=None,
                        help="Initial search term applied on startup")
    args = parser.parse_args()

    start_dir = args.start_dir or args.path
    if start_dir:
        start_dir = os.path.abspath(os.path.expanduser(start_dir))
        if not os.path.isdir(start_dir):
            print(f"Warning: '{start_dir}' is not a directory. Falling back to current working directory.",
                  file=sys.stderr)
            start_dir = None

    app = App(start_dir=start_dir, initial_search=args.initial_search)
    app.mainloop()
