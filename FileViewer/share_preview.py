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
from urllib.parse import quote, urlparse, parse_qs  # NEW: safe URLs for links and query parsing
import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import mimetypes

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

        def _is_within_root(self, abs_path: str) -> bool:
            try:
                root_abs = os.path.abspath(self.ROOT)
                target = os.path.abspath(abs_path)
                return os.path.commonpath([root_abs]) == os.path.commonpath([root_abs, target])
            except Exception:
                return False

        def _safe_join(self, base: str, *paths: str) -> str:
            candidate = os.path.abspath(os.path.join(base, *paths))
            if not self._is_within_root(candidate):
                return base
            return candidate

        def _scan_dir(self, path: str):
            """Return directory entries as a list of dicts with dirs first."""
            try:
                names = os.listdir(path)
            except OSError:
                return []
            entries = []
            for name in names:
                full = os.path.join(path, name)
                is_dir = os.path.isdir(full)
                size = 0
                if not is_dir:
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                entries.append({
                    "name": name,
                    "is_dir": bool(is_dir),
                    "size": int(size),
                })
            # dirs-first sorting, then case-insensitive name
            entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
            return entries

        def _render_markdown(self, md_text: str) -> tuple[str, str]:
            """Render Markdown to HTML. Returns (html, engine_name)."""
            try:
                import markdown2
                html_out = markdown2.markdown(
                    md_text,
                    extras=[
                        "tables",
                        "fenced-code-blocks",
                        "strike",
                        "toc",
                        "cuddled-lists",
                    ],
                )
                return html_out, "markdown2"
            except Exception:
                pass
            try:
                import markdown as md
                html_out = md.markdown(
                    md_text,
                    extensions=[
                        "extra",
                        "tables",
                        "fenced_code",
                        "toc",
                        "sane_lists",
                        "admonition",
                        "md_in_html",
                    ],
                )
                return html_out, "python-markdown"
            except Exception:
                # Fallback: escape into <pre>
                import html as _html
                return f"<pre>{_html.escape(md_text)}</pre>", "raw-pre"

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/__api/list":
                qs = parse_qs(parsed.query or "")
                rel = qs.get("p", ["."])[0]
                # Resolve to absolute path under ROOT
                current_dir = self._safe_join(self.ROOT, rel)
                data = {
                    "root": self.ROOT,
                    "cwd": current_dir,
                    "rel": os.path.relpath(current_dir, self.ROOT),
                    "entries": self._scan_dir(current_dir),
                }
                enc = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(enc)))
                self.end_headers()
                self.wfile.write(enc)
                return
            if parsed.path == "/__api/render_md":
                qs = parse_qs(parsed.query or "")
                rel = qs.get("p", [None])[0]
                if not rel:
                    self.send_error(400, "Missing p")
                    return
                abs_path = self._safe_join(self.ROOT, rel)
                if not os.path.isfile(abs_path):
                    self.send_error(404, "Not a file")
                    return
                _, ext = os.path.splitext(abs_path.lower())
                if ext not in self.MD_EXTS:
                    self.send_error(415, "Unsupported type")
                    return
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                except Exception as e:
                    self.send_error(500, f"Read error: {e}")
                    return
                html_body, engine = self._render_markdown(md_text)
                # Wrap with minimal styling for readability
                html_doc = (
                    "<div class=\"md-body\">" + html_body + "</div>"
                )
                payload = {"html": html_doc, "engine": engine}
                enc = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(enc)))
                self.end_headers()
                self.wfile.write(enc)
                return
            if parsed.path == "/__api/download":
                qs = parse_qs(parsed.query or "")
                rel = qs.get("p", [None])[0]
                if not rel:
                    self.send_error(400, "Missing p")
                    return
                abs_path = self._safe_join(self.ROOT, rel)
                if not os.path.isfile(abs_path):
                    self.send_error(404, "Not a file")
                    return
                ctype, _ = mimetypes.guess_type(abs_path)
                ctype = ctype or "application/octet-stream"
                try:
                    fs = os.stat(abs_path)
                    with open(abs_path, "rb") as f:
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(fs.st_size))
                        filename = os.path.basename(abs_path)
                        self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
                        self.end_headers()
                        self.wfile.write(f.read())
                    return
                except Exception as e:
                    self.send_error(500, f"Read error: {e}")
                    return
            # Fallback to default handling (serves files/dirs). For dirs, our overridden
            # list_directory() will render the two-pane UI.
            return super().do_GET()

        def _format_size(self, size: int) -> str:
            units = ["B", "KB", "MB", "GB", "TB"]
            for unit in units:
                if size < 1024:
                    return f"{size:.0f} {unit}"
                size /= 1024.0
            return f"{size:.0f} PB"
        # HTTP handler that adds per-type icons to directory listings.

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
            """Render a two-pane UI with a left tree and right file preview.
            Folder-first sorting is applied by the JSON API (/__api/list).
            """
            enc = sys.getfilesystemencoding()

            displaypath = html.escape(self.path, quote=False)
            title = f"Directory listing for {displaypath}"

            out = []
            out.append("<!DOCTYPE html>")
            out.append("<html><head>")
            out.append('<meta charset="utf-8">')
            out.append(f"<title>{title}</title>")
            out.append("<style>\n"
                       "  :root{--fg:#111;--muted:#666;--border:#e5e7eb;}\n"
                       "  *{box-sizing:border-box;}\n"
                       "  body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;color:var(--fg);height:100vh;display:flex;flex-direction:column;}\n"
                       "  header{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;gap:12px;align-items:center;}\n"
                       "  header .meta{color:var(--muted);font-size:.85rem;}\n"
                       "  main{flex:1;display:flex;min-height:0;}\n"
                       "  #tree{width:360px;max-width:50vw;border-right:1px solid var(--border);overflow:auto;padding:10px;}\n"
                       "  #preview{flex:1;overflow:auto;padding:10px;}\n"
                       "  .item{display:flex;align-items:center;gap:.5rem;padding:4px 2px;border-radius:6px;cursor:pointer;}\n"
                       "  .item:hover{background:#f8fafc;}\n"
                       "  .icon{width:1.25em;display:inline-flex;justify-content:center;}\n"
                       "  .size{color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto;}\n"
                       "  .folder{font-weight:600;}\n"
                       "  .crumbs{font-size:.9rem;color:var(--muted);}\n"
                       "  pre{background:#f6f8fa;padding:12px;border-radius:8px;overflow:auto;}\n"
                       "  table{border-collapse:collapse;width:100%;}\n"
                       "  th,td{border:1px solid #ddd;padding:6px 8px;vertical-align:top;}\n"
                       "  iframe{width:100%;height:80vh;border:1px solid var(--border);border-radius:8px;}\n"
                       "  .md-body{line-height:1.6;}\n"
                       "  .md-body h1,.md-body h2,.md-body h3{margin-top:1.2em;}\n"
                       "  .md-body pre{background:#f6f8fa;padding:12px;border-radius:8px;overflow:auto;}\n"
                       "  .md-body code{background:#f6f8fa;padding:2px 4px;border-radius:4px;}\n"
                       "  #ctx{position:fixed;z-index:1000;background:#fff;border:1px solid var(--border);border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.1);display:none;min-width:180px;}\n"
                       "  #ctx .mi{padding:10px 12px;cursor:pointer;}\n"
                       "  #ctx .mi:hover{background:#f8fafc;}\n"
                       "</style>")
            out.append("</head><body>")

            root_abs = getattr(self, "ROOT", os.path.abspath(path))
            cur_abs = os.path.abspath(path)
            try:
                rel_path = os.path.relpath(cur_abs, root_abs)
            except Exception:
                rel_path = "."

            out.append("<header>")
            out.append(f"<div><strong>Shared Dir</strong>: <code>{html.escape(root_abs, False)}</code></div>")
            out.append(f"<div class=\"meta\">Current: <code id=rel>{html.escape(rel_path, False)}</code></div>")
            out.append("</header>")

            out.append("<main>")
            out.append("  <section id=tree></section>")
            out.append("  <section id=preview><em>Select a file to preview (csv, html, md, txt).</em></section>")
            out.append("</main>")
            out.append("<div id=ctx></div>")

            # Client-side app
            out.append("<script>\n" + r'''
const ICONS = { DIR:"📁", MD:"📝", HTML:"🌐", CSV:"📊", TXT:"📄", IMG:"🖼️", FILE:"📦" };
const exts = {
  md: new Set([".md",".mdx",".markdown"]),
  html: new Set([".html",".htm"]),
  csv: new Set([".csv"]),
  txt: new Set([".txt"]),
  img: new Set([".png",".jpg",".jpeg",".gif",".webp",".bmp",".tiff"])  
};
function extType(name){
  const lower = name.toLowerCase();
  const dot = lower.lastIndexOf('.');
  const ext = dot>=0? lower.slice(dot) : '';
  if(exts.md.has(ext)) return 'MD';
  if(exts.html.has(ext)) return 'HTML';
  if(exts.csv.has(ext)) return 'CSV';
  if(exts.txt.has(ext)) return 'TXT';
  if(exts.img.has(ext)) return 'IMG';
  return 'FILE';
}
function fmtSize(n){
  const u=["B","KB","MB","GB","TB"]; let i=0; let x=n; while(x>=1024 && i<u.length-1){x/=1024;i++;}
  return `${x.toFixed(x<10&&i>0?1:0)} ${u[i]}`;
}
async function apiList(rel){
  const url = new URL('/__api/list', location.origin);
  if(rel) url.searchParams.set('p', rel);
  const r = await fetch(url);
  if(!r.ok) throw new Error('List failed');
  return await r.json();
}
function el(tag, attrs={}, ...kids){
  const e=document.createElement(tag);
  for(const [k,v] of Object.entries(attrs)){
    if(k=="class") e.className=v; else if(k=="html") e.innerHTML=v; else e.setAttribute(k,v);
  }
  for(const k of kids) e.append(k);
  return e;
}
function ctxHide(){ const c = document.getElementById('ctx'); c.style.display='none'; c.innerHTML=''; }
function ctxShow(x,y, items){
  const c = document.getElementById('ctx');
  c.innerHTML='';
  for(const it of items){
    const div = el('div',{class:'mi'}, it.label);
    div.addEventListener('click', ()=>{ ctxHide(); it.onClick(); });
    c.append(div);
  }
  c.style.left = x+"px"; c.style.top = y+"px"; c.style.display='block';
}
window.addEventListener('click', ctxHide);
window.addEventListener('contextmenu', (e)=>{
  // Close menu if right-clicking elsewhere without a handler
  if(!e.target.closest('#ctx')) return; // let our own handlers manage
});
async function copyToClipboard(text){
  try{ await navigator.clipboard.writeText(text); }
  catch(e){ console.warn('Clipboard failed', e); }
}
function buildTree(container, data){
  container.innerHTML='';
  const list = el('div');
  // Parent link
  if(data.rel !== '.' && data.rel !== ''){
    const upRel = data.rel.split('/').slice(0,-1).join('/')||'.';
    const up = el('div',{class:'item folder'}, el('span',{class:'icon'},ICONS.DIR), el('span',{},'..')); 
    up.addEventListener('click', ()=>load(upRel));
    list.append(up);
  }
  for(const ent of data.entries){
    const type = ent.is_dir ? 'DIR' : extType(ent.name);
    const row = el('div',{class:'item '+(ent.is_dir?'folder':'')},
      el('span',{class:'icon'},ICONS[type]||ICONS.FILE),
      el('span',{class:'name'},ent.name),
      ent.is_dir? el('span') : el('span',{class:'size'}, fmtSize(ent.size))
    );
    // Right-click context menu for files
    if(!ent.is_dir){
      row.addEventListener('contextmenu', (ev)=>{
        ev.preventDefault();
        const relPath = (data.rel && data.rel!=='.') ? data.rel + '/' + ent.name : ent.name;
        const pathEnc = '/' + relPath.split('/').map(encodeURIComponent).join('/');
        const downloadUrl = new URL('/__api/download', location.origin);
        downloadUrl.searchParams.set('p', relPath);
        ctxShow(ev.clientX, ev.clientY, [
          {label:'Download', onClick: ()=>{ window.open(downloadUrl.toString(), '_blank'); }},
          {label:'Copy link', onClick: ()=>{ copyToClipboard(location.origin + pathEnc); }},
          {label:'Save as…', onClick: ()=>{ const a=document.createElement('a'); a.href=pathEnc; a.setAttribute('download', ent.name); document.body.appendChild(a); a.click(); a.remove(); }},
        ]);
      });
    }
    row.addEventListener('click', ()=>{
      if(ent.is_dir){
        const next = data.rel && data.rel!=='.' ? data.rel + '/' + ent.name : ent.name;
        load(next);
      } else {
        const relPath = (data.rel && data.rel!=='.') ? data.rel + '/' + ent.name : ent.name;
        previewFile(relPath, ent.name);
      }
    });
    list.append(row);
  }
  container.append(list);
}
async function previewFile(relPath, displayName){
  const right = document.getElementById('preview');
  right.innerHTML = `<div class="crumbs"><code>${displayName}</code></div>`;
  const lower = displayName.toLowerCase();
  const ext = lower.slice(lower.lastIndexOf('.'));
  const isMD = exts.md.has(ext);
  const pathEnc = '/' + relPath.split('/').map(encodeURIComponent).join('/');
  if(exts.html.has(ext)){
    const iframe = el('iframe',{src: pathEnc});
    right.append(iframe);
    return;
  }
  if(exts.img.has(ext)){
    const img = document.createElement('img');
    img.src = pathEnc;
    img.alt = displayName;
    img.style.maxWidth = '100%';
    img.style.height = 'auto';
    img.style.border = '1px solid var(--border)';
    img.style.borderRadius = '8px';
    img.addEventListener('error', ()=>{
      const note = el('div', {class: 'crumbs'}, 'Image failed to load. Check file name/encoding.');
      right.append(note);
    });
    right.append(img);
    return;
  }
  if(isMD){
    try{
      const url = new URL('/__api/render_md', location.origin);
      url.searchParams.set('p', relPath);
      const res = await fetch(url);
      const obj = await res.json();
      const wrap = el('div',{class:'md-body'});
      wrap.innerHTML = obj.html; // html returned already wrapped with .md-body
      right.append(wrap);
      const engineInfo = el('div',{class:'crumbs'}, `Rendered by: ${obj.engine}`);
      right.append(engineInfo);
    }catch(e){
      right.append(el('div',{}, 'Failed to render markdown: '+e.message));
    }
    return;
  }
  try{
    const res = await fetch(pathEnc);
    const text = await res.text();
    if(exts.csv.has(ext)){
      const lines = text.split(/\r?\n/).filter(Boolean);
      const table = el('table');
      if(lines.length){
        const head = lines[0].split(',');
        const thead = el('thead');
        const tr = el('tr');
        for(const h of head) tr.append(el('th',{}, h));
        thead.append(tr); table.append(thead);
        const tbody = el('tbody');
        for(let i=1;i<lines.length;i++){
          const trb = el('tr');
          for(const c of lines[i].split(',')) trb.append(el('td',{}, c));
          tbody.append(trb);
        }
        table.append(tbody);
      }
      right.append(table);
    } else {
      // md/txt and others -> simple preformatted view
      const pre = el('pre');
      pre.textContent = text;
      right.append(pre);
    }
  }catch(e){
    right.append(el('div',{}, 'Failed to load file: '+e.message));
  }
}
async function load(rel){
  const data = await apiList(rel);
  document.getElementById('rel').textContent = data.rel;
  buildTree(document.getElementById('tree'), data);
}
load(document.getElementById('rel').textContent);
'''+"\n</script>")

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