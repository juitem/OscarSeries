import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Try to import HtmlFrame from tkinterweb
try:
    from tkinterweb import HtmlFrame
except ImportError:
    HtmlFrame = None


# -------- Helpers --------

def run_command(cmd: str) -> str:
    import subprocess
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)


def run_with_elevation_if_needed(cmd: str) -> str:
    return run_command(cmd)


def htmlframe_set(frame, html: str, base_url: str | None = None):
    """
    Compatibility wrapper for different HTML widgets.
    """
    if hasattr(frame, "load_html"):
        try:
            if base_url:
                frame.load_html(html, baseurl=base_url)
            else:
                frame.load_html(html)
            return
        except Exception:
            pass
    for m in ("set_html", "set_content"):
        if hasattr(frame, m):
            getattr(frame, m)(html)
            return
    try:
        frame.config(state="normal")
        frame.delete("1.0", "end")
        frame.insert("1.0", html)
        frame.config(state="disabled")
    except Exception:
        pass


def render_markdown_to_html(md_text: str) -> tuple[str, str]:
    """
    Render Markdown to HTML with table support.
    Returns (html, engine_name).
    """
    try:
        import markdown2
        html = markdown2.markdown(
            md_text,
            extras=["tables", "fenced-code-blocks", "strike", "toc", "cuddled-lists"]
        )
        return html, "markdown2"
    except Exception:
        pass

    try:
        import markdown as md
        html = md.markdown(
            md_text,
            extensions=["extra", "tables", "fenced_code", "toc", "sane_lists", "admonition", "md_in_html"]
        )
        return html, "python-markdown"
    except Exception:
        from html import escape
        return f"<pre>{escape(md_text)}</pre>", "raw-pre"


# -------- File type helpers --------
MD_EXTS = {".md", ".mdx", ".markdown"}
HTML_EXTS = {".html", ".htm"}
CSV_EXTS = {".csv"}  # NEW: CSV support

ICON_MD = "📝"
ICON_HTML = "🌐"
ICON_CSV = "📊"  # NEW


def is_viewable_file(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return (ext in MD_EXTS) or (ext in HTML_EXTS) or (ext in CSV_EXTS)


def decorate_name(name: str, path: str, is_dir: bool) -> str:
    if is_dir:
        return name
    _, ext = os.path.splitext(path.lower())
    if ext in MD_EXTS:
        return f"{ICON_MD} {name}"
    if ext in HTML_EXTS:
        return f"{ICON_HTML} {name}"
    if ext in CSV_EXTS:
        return f"{ICON_CSV} {name}"
    return name


# -------- Main Application --------
class App(tk.Tk):
    def __init__(self, start_dir=None, initial_search: str | None = None):
        super().__init__()
        self.title("Markdown/HTML Tree Viewer")
        self.geometry("1200x700")

        self.status = tk.StringVar()
        self._build_ui()

        # Load initial directory
        if start_dir:
            self.load_root(start_dir)
        else:
            self.load_root(os.getcwd())

        # Apply initial search if provided
        self.initial_search = initial_search
        if isinstance(self.initial_search, str) and self.initial_search.strip():
            self.search_var.set(self.initial_search)
            self.apply_search()  # apply immediately

    def _build_ui(self):
        # Use grid at root level so we can pin toolbar at the top reliably
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)  # paned area grows

        # --- Top toolbar (row 0) ---
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(99, weight=1)  # spacer via grid if needed

        # Compact icon buttons/controls
        # Open folder: 📁
        ttk.Button(top, text="📁", width=3, command=self.choose_folder).pack(side=tk.LEFT, padx=(6, 4), pady=4)

        # Viewable-only toggle: 👁
        self.show_only_viewable = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top,
            text="👁",
            variable=self.show_only_viewable,
            command=self._apply_viewable_filter
        ).pack(side=tk.LEFT, padx=(4, 4), pady=4)

        # Extension filter checkboxes as icons
        self.ft_md = tk.BooleanVar(value=True)
        self.ft_html = tk.BooleanVar(value=True)
        self.ft_csv = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="📝", variable=self.ft_md, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0), pady=4)
        ttk.Checkbutton(top, text="🌐", variable=self.ft_html, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 0), pady=4)
        ttk.Checkbutton(top, text="📊", variable=self.ft_csv, command=self._apply_viewable_filter).pack(side=tk.LEFT, padx=(2, 8), pady=4)

        # Search icon + entry
        ttk.Label(top, text="🔎").pack(side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        entry.pack(side=tk.LEFT, padx=(0, 6))
        entry.bind("<KeyRelease>", self._on_search_key)
        self._search_job = None

        # --- Main paned area (row 1) ---
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(paned, width=300)
        paned.add(left, weight=1)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        # --- Treeview ---
        self.tree = ttk.Treeview(left, show="tree")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewOpen>>", self.on_open_node)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_node)

        # --- Right viewer ---
        if HtmlFrame is None:
            self.html = tk.Text(right, wrap="word")
            self.html.insert("1.0", "Install 'tkinterweb' for HTML preview:\n\n    pip install tkinterweb\n")
            self.html.config(state="disabled")
            self.html_is_webview = False
            self.status.set("Renderer: Text fallback")
        else:
            self.html = HtmlFrame(right, messages_enabled=False)
            self.html_is_webview = True
            self.status.set("Renderer: HtmlFrame")
        self.html.pack(fill=tk.BOTH, expand=True)

        # --- Status bar (row 2) ---
        ttk.Label(self, textvariable=self.status, anchor="w").grid(row=2, column=0, sticky="ew")

    def _ext_from_path(self, path: str) -> str:
        return os.path.splitext(path.lower())[1] if path else ""

    def _filetype_allowed(self, ext: str) -> bool:
        """
        Check extension checkboxes to decide if a file should be shown.
        Directories are handled elsewhere (always visible).
        """
        md_ok = getattr(self, "ft_md", None)
        html_ok = getattr(self, "ft_html", None)
        csv_ok = getattr(self, "ft_csv", None)
        if any(v is None for v in (md_ok, html_ok, csv_ok)):
            return True
        if ext in MD_EXTS:
            return bool(self.ft_md.get())
        if ext in HTML_EXTS:
            return bool(self.ft_html.get())
        if ext in CSV_EXTS:
            return bool(self.ft_csv.get())
        return False

    def choose_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.load_root(d)

    def load_root(self, root: str):
        """Reset the tree and set a fresh root with one dummy child."""
        self.root_dir = root
        self.tree.delete(*self.tree.get_children())
        node = self.tree.insert("", "end", text=root, open=True, values=(root,))
        # Ensure we only ever have one dummy under root
        self._insert_dummy_child(node)
        # Optional: if you keep any per-node caches elsewhere, reset them here
        # e.g., self.full_tree_cache = {}

    def _insert_dummy_child(self, node):
        """Insert a single dummy child so the node shows an expand arrow."""
        # Avoid inserting multiple dummies
        for c in self.tree.get_children(node):
            txt = self.tree.item(c, "text")
            if txt == "dummy":
                return
        # Mark dummy with a sentinel value to easily detect/remove later
        self.tree.insert(node, "end", text="dummy", values=("__DUMMY__",))

    def on_open_node(self, event):
        """Populate directory contents once when a node is expanded."""
        node_id = self.tree.focus()
        if not node_id:
            return

        # If this node already has any non-dummy child, bail to prevent duplication
        existing_children = self.tree.get_children(node_id)
        for cid in existing_children:
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            # normalize values to tuple
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            is_dummy = (txt == "dummy") or (vals and vals[0] == "__DUMMY__")
            if not is_dummy:
                return  # already populated; do nothing

        # Remove dummy rows (if any)
        for cid in list(existing_children):
            txt = self.tree.item(cid, "text")
            vals = self.tree.item(cid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            if (txt == "dummy") or (vals and vals[0] == "__DUMMY__"):
                self.tree.delete(cid)

        # Resolve directory path
        vals = self.tree.item(node_id, "values")
        if isinstance(vals, str):
            vals = (vals,) if vals else ()
        if not vals:
            return
        fullpath = vals[0]

        try:
            entries = sorted(os.listdir(fullpath))
        except Exception:
            return

        only_viewable = bool(self.show_only_viewable.get())

        for name in entries:
            p = os.path.join(fullpath, name)
            # in on_open_node() when inserting:
            if os.path.isdir(p):
                child = self.tree.insert(
                    node_id, "end",
                    text=decorate_name(name, p, is_dir=True),
                    open=False,
                    values=(p,),
                    tags=("dir",)
                )
                self._insert_dummy_child(child)
            else:
                ext = self._ext_from_path(p)
                # Respect "Viewable only" toggle AND extension checkboxes
                if only_viewable and not is_viewable_file(p):
                    continue
                if not self._filetype_allowed(ext):
                    continue
                tags = ("file_viewable",) if is_viewable_file(p) else ("file_other",)
                self.tree.insert(
                    node_id, "end",
                    text=decorate_name(name, p, is_dir=False),
                    values=(p,),
                    tags=tags
                )

    def on_select_node(self, event):
        node_id = self.tree.focus()
        if not node_id:
            return
        path = self.tree.item(node_id, "values")[0]
        if os.path.isfile(path):
            self.render_file(path)

    def _on_search_key(self, event):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(400, self.apply_search)

    def apply_search(self):
        term = self.search_var.get().lower().strip()
        self.tree.delete(*self.tree.get_children())
        root_id = self.tree.insert("", "end", text=self.root_dir, open=True, values=(self.root_dir,))

        only_viewable = bool(self.show_only_viewable.get())

        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            candidates = []
            if only_viewable:
                for fname in filenames:
                    if term in fname.lower():
                        p = os.path.join(dirpath, fname)
                        if is_viewable_file(p) and self._filetype_allowed(self._ext_from_path(p)):
                            candidates.append(p)
            else:
                for name in dirnames + filenames:
                    if term in name.lower():
                        p = os.path.join(dirpath, name)
                        # If it's a file, respect type checkboxes; directories always allowed
                        if os.path.isdir(p) or self._filetype_allowed(self._ext_from_path(p)):
                            candidates.append(p)

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

    def _apply_viewable_filter(self):
        """
        Hide/Show non-viewable files in place without rebuilding the tree.
        Directories are always visible. Preserves expansion, selection, and scroll.
        """
        if not hasattr(self, "tree"):
            return
        show_only = bool(self.show_only_viewable.get())

        # Traverse all items; detach or reattach non-viewable files
        stack = list(self.tree.get_children(""))
        while stack:
            iid = stack.pop()
            # Always push children for traversal
            stack.extend(self.tree.get_children(iid))

            # Get node meta
            vals = self.tree.item(iid, "values")
            if isinstance(vals, str):
                vals = (vals,) if vals else ()
            path = vals[0] if vals else ""
            is_dir = bool(path and os.path.isdir(path))
            if is_dir:
                # Directories must always be shown
                # If directory accidentally detached, reattach it
                try:
                    self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass
                continue

            # Files
            if not path or path == "__DUMMY__":
                continue
            viewable = is_viewable_file(path)
            ext = self._ext_from_path(path)
            allowed_by_checkbox = self._filetype_allowed(ext)
            hide = (show_only and not viewable) or (not allowed_by_checkbox)
            if hide:
                try:
                    self.tree.detach(iid)
                except Exception:
                    pass
            else:
                try:
                    self.tree.reattach(iid, self.tree.parent(iid), "end")
                except Exception:
                    pass

        # If a hidden (detached) item was selected, clear selection to avoid invalid state
        sel = self.tree.selection()
        for sid in sel:
            # A detached item has no visible ancestor chain; guard by checking existence in current children
            if sid not in self.tree.get_children(self.tree.parent(sid)):
                self.tree.selection_remove(sid)
                
    def render_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if (ext not in MD_EXTS) and (ext not in HTML_EXTS) and (ext not in CSV_EXTS):
            self._show_message(
                f"Preview not available: `{os.path.basename(path)}`\n\n"
                f"Only Markdown ({', '.join(sorted(MD_EXTS))}), HTML ({', '.join(sorted(HTML_EXTS))}), and CSV ({', '.join(sorted(CSV_EXTS))}) files are rendered."
            )
            return

        def work():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                self._show_message(str(e))
                return

            if ext in HTML_EXTS:
                html_body = text
                body = html_body.strip().lower()
                if ("<html" not in body) or ("</html>" not in body):
                    html_body = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
                abs_path = os.path.abspath(path)
                base_url = os.path.dirname(abs_path)

                def _apply_html():
                    if HtmlFrame is None:
                        # Fallback: show raw HTML as text
                        self._show_message(html_body)
                        mode = "Text(fallback)"
                    else:
                        # Minimal, stable path that worked previously: in-memory HTML + base_url
                        htmlframe_set(self.html, html_body, base_url=base_url)
                        mode = "HtmlFrame"
                    self.status.set(f"[HTML] Engine: pass-through | Renderer: {mode}")

                self.after(0, _apply_html)
            elif ext in CSV_EXTS:
                import csv, html as _html
                MAX_ROWS = 2000  # safety cap for very large CSVs
                MAX_COLS = 200
                rows = []
                truncated = False
                try:
                    with open(path, "r", encoding="utf-8", newline="") as f:
                        reader = csv.reader(f)
                        for ri, row in enumerate(reader):
                            if ri >= MAX_ROWS:
                                truncated = True
                                break
                            rows.append(row[:MAX_COLS])
                except Exception as e:
                    self._show_message(f"Failed to read CSV: {e}")
                    return

                def esc(x: str) -> str:
                    return _html.escape(x if x is not None else "")

                # Build HTML table; treat first row as header if present
                table_rows = []
                if rows:
                    header = rows[0]
                    thead = "<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr></thead>"
                    body_rows = rows[1:]
                else:
                    thead = ""
                    body_rows = []
                tbody = "<tbody>" + "".join(
                    "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in r) + "</tr>"
                    for r in body_rows
                ) + "</tbody>"
                note = "<p style='font-size:12px;color:#666;margin:8px 0 0;'>CSV preview"
                if truncated:
                    note += f" (showing first {MAX_ROWS} rows"
                    note += f", first {MAX_COLS} cols" if MAX_COLS else ""
                    note += ").</p>"
                else:
                    note += ".</p>"

                html_doc = f"""
                <html><head><meta charset="utf-8"/>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Ubuntu, 'Helvetica Neue', Arial, sans-serif; padding: 16px; line-height: 1.5; }}
                  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
                  thead th {{ background: #fafafa; position: sticky; top: 0; }}
                  .wrap {{ overflow: auto; max-height: 70vh; }}
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
            else:
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

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _show_message(self, text: str):
        if HtmlFrame is None:
            self.html.config(state="normal")
            self.html.delete("1.0", tk.END)
            notice = (
                "HTML preview is not available because 'tkinterweb' is not installed.\n"
                "Install it with:\n\n    pip install tkinterweb\n\n"
                "Showing raw text below:\n\n"
            )
            self.html.insert("1.0", notice + text)
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

    def _escape_html(self, text: str) -> str:
        import html
        return html.escape(text)


if __name__ == "__main__":
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Markdown/HTML Tree Viewer")
    parser.add_argument("path", nargs="?", default=None,
                        help="(Optional) start folder positional argument")
    parser.add_argument("-d", "--start-dir", dest="start_dir", default=None,
                        help="Start folder to load")
    # NEW: initial search term to prefill and apply in the Search box
    parser.add_argument("-s", "--search", dest="initial_search", default=None,
                        help="Initial search term applied on startup")
    args = parser.parse_args()

    # Prefer --start-dir if provided; otherwise fall back to positional path
    start_dir = args.start_dir or args.path

    if start_dir:
        # Normalize and validate
        start_dir = os.path.abspath(os.path.expanduser(start_dir))
        if not os.path.isdir(start_dir):
            print(f"Warning: '{start_dir}' is not a directory. Falling back to current working directory.",
                  file=sys.stderr)
            start_dir = None

    # Pass initial_search into App so the Search box is prefilled and applied
    app = App(start_dir=start_dir, initial_search=args.initial_search)
    app.mainloop()    