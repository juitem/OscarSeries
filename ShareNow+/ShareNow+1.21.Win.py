import os
import time
from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string, Response, stream_with_context
from werkzeug.utils import secure_filename
import logging
import argparse
import pyperclip
import json
import base64
import threading
import queue
from io import BytesIO
from PIL import Image

# For Windows clipboard access
try:
    import win32clipboard
    import win32con
    IS_WINDOWS = True
except ImportError:
    IS_WINDOWS = False
    logging.warning("win32clipboard module not found. Clipboard sharing (especially images/HTML) will be limited or unavailable on non-Windows systems.")

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Global variables
BASE_DIR = None
SHARE_CLIPBOARD = False
REALTIME_CLIPBOARD = False
POLLING_INTERVAL = 1

clipboard_queue = queue.Queue()
last_clipboard_content = {}

# --- Custom Jinja2 Filter for JavaScript String Escaping ---
def js_string(value):
    """
    Escapes a string for safe inclusion in JavaScript within an HTML attribute.
    """
    return json.dumps(value)[1:-1]

app.jinja_env.filters['js_string'] = js_string

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'mp3', 'mp4', 'py', 'html', 'css', 'js', 'json', 'xml', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

def allowed_file(filename):
    """Checks if a file's extension is in the allowed list."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_path(rel_path):
    """Ensures that the requested path is within the BASE_DIR."""
    normalized_path = os.path.normpath(rel_path)
    abs_path = os.path.abspath(os.path.join(BASE_DIR, normalized_path))

    if not abs_path.startswith(BASE_DIR):
        app.logger.warning(f"Attempted directory traversal detected: {rel_path} -> {abs_path}")
        abort(403, description="Access denied: Path outside base directory.")
    return abs_path

# --- Clipboard Handling Functions for Windows ---
def get_clipboard_content():
    """
    Retrieves plain text, HTML, and image content from the Windows clipboard.
    Image data (DIB) is converted to PNG and returned as base64.
    Returns a dictionary with 'text_plain', 'text_html', 'image_png_base64' keys.
    """
    detected_content = {}
    clipboard_access_errors = []

    if not IS_WINDOWS:
        detected_content['error'] = "This server is not running on Windows or pywin32 is not installed. Clipboard features are limited."
        detected_content['text_plain'] = pyperclip.paste() # Try to get text via pyperclip anyway
        return detected_content

    try:
        win32clipboard.OpenClipboard()
        # 1. Get plain text
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            try:
                text_content = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                if text_content:
                    detected_content['text_plain'] = text_content
            except Exception as e:
                clipboard_access_errors.append(f"Error getting plain text: {e}")

        # 2. Get HTML content
        # HTML format requires specific handling as it's not a standard CF_* constant
        # The clipboard format for HTML is often named "HTML Format" or "text/html"
        # We need to register it or use a known one if available
        html_format_id = win32clipboard.RegisterClipboardFormat("HTML Format")
        if win32clipboard.IsClipboardFormatAvailable(html_format_id):
            try:
                html_content_bytes = win32clipboard.GetClipboardData(html_format_id)
                # HTML clipboard content usually starts with meta information
                # We need to parse it to get the actual HTML fragment
                html_str = html_content_bytes.decode('utf-8', errors='ignore')
                # Find the actual HTML fragment within the clipboard data
                # Clipboard HTML format details: https://docs.microsoft.com/en-us/windows/win32/dataxchg/html-clipboard-format
                start_html_tag = ""
                end_html_tag = ""
                start_index = html_str.find(start_html_tag)
                end_index = html_str.find(end_html_tag)

                if start_index != -1 and end_index != -1:
                    html_fragment = html_str[start_index + len(start_html_tag):end_index]
                    detected_content['text_html'] = html_fragment
                else:
                    # If fragment markers not found, try to use the whole content if it looks like HTML
                    if "<html" in html_str.lower() or "<body" in html_str.lower():
                         detected_content['text_html'] = html_str
                    else:
                        app.logger.debug("HTML clipboard content did not contain standard fragment markers.")
                        clipboard_access_errors.append("HTML clipboard content not in expected format.")
            except Exception as e:
                clipboard_access_errors.append(f"Error getting HTML: {e}")
        else:
            app.logger.debug("HTML clipboard format not available.")


        # 3. Get Image content (DIB format)
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
            try:
                dib_data = win32clipboard.GetClipboardData(win32con.CF_DIB)
                # DIB data is a BITMAPINFOHEADER followed by pixel data
                # Pillow can usually open this directly from a BytesIO stream
                image_stream = BytesIO(dib_data)
                img = Image.open(image_stream)

                # Convert to PNG for display in web browser
                output_buffer = BytesIO()
                # Handle transparency by converting to RGBA if not already
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                img.save(output_buffer, format='PNG', optimize=True)
                image_png_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                detected_content['image_png_base64'] = image_png_base64
            except Exception as e:
                clipboard_access_errors.append(f"Error getting/converting image: {e}")
        else:
            app.logger.debug("Image (DIB) clipboard format not available.")

    except Exception as e:
        app.logger.error(f"Failed to open clipboard: {e}")
        detected_content['error'] = f"Failed to access clipboard: {e}"
        # If clipboard opening fails, try pyperclip for plain text as a fallback
        try:
            text_content = pyperclip.paste()
            if text_content:
                detected_content['text_plain'] = text_content
        except pyperclip.PyperclipException as py_e:
            clipboard_access_errors.append(f"pyperclip fallback failed: {py_e}")
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception as e:
            app.logger.warning(f"Error closing clipboard: {e}")

    if clipboard_access_errors:
        detected_content['clipboard_warnings'] = "; ".join(clipboard_access_errors)

    # Note: Markdown is not a native Windows clipboard format, so it's not directly supported.
    # If text_plain contains markdown, it will be treated as plain text.

    return detected_content

# --- Background thread for clipboard polling ---
def clipboard_polling_thread():
    """
    This thread periodically checks the clipboard for new content.
    If content changes, it puts the new content into a queue for SSE clients.
    """
    global last_clipboard_content
    while True:
        if REALTIME_CLIPBOARD:
            current_clipboard_content = get_clipboard_content()
            # It's important to compare serializable content for dictionary comparison
            # Convert any BytesIO/Image objects to something comparable if not already done.
            # get_clipboard_content already returns base64 strings, so direct comparison should work.
            if current_clipboard_content != last_clipboard_content:
                app.logger.info("Clipboard content changed, pushing update to clients.")
                clipboard_queue.put(current_clipboard_content)
                last_clipboard_content = current_clipboard_content
        time.sleep(POLLING_INTERVAL)

@app.route('/')
def index():
    """
    Renders the main HTML page of the file server.
    Initial clipboard content is fetched and included if sharing is enabled.
    """
    clipboard_data = {}

    if SHARE_CLIPBOARD:
        clipboard_data = get_clipboard_content()
        global last_clipboard_content
        last_clipboard_content = clipboard_data

    return render_template_string(TEMPLATE,
                                  clipboard_data=clipboard_data,
                                  SHARE_CLIPBOARD=SHARE_CLIPBOARD,
                                  REALTIME_CLIPBOARD=REALTIME_CLIPBOARD)

@app.route('/api/list', methods=['GET'])
def api_list_dir():
    """API endpoint to list the contents of a directory."""
    rel = request.args.get('path', '')
    abs_dir = safe_path(rel)

    if not os.path.isdir(abs_dir):
        app.logger.info(f"Requested path is not a directory or does not exist: {abs_dir}")
        return jsonify(error="Not a directory or does not exist", path=rel), 400

    if not os.access(abs_dir, os.R_OK):
        app.logger.warning(f"Permission denied to read directory: {abs_dir}")
        return jsonify(error="Permission denied: Cannot read directory"), 403

    dirs, files = [], []
    try:
        for name in sorted(os.listdir(abs_dir), key=lambda x: x.lower()):
            full = os.path.join(abs_dir, name)
            item = {'name': name, 'is_dir': os.path.isdir(full)}
            (dirs if item['is_dir'] else files).append(item)
    except OSError as e:
        app.logger.error(f"Server error listing directory {abs_dir}: {e}")
        return jsonify(error="Server error: Could not list directory contents"), 500

    parent = os.path.dirname(rel) if rel else None
    if parent == "": parent = None

    return jsonify({'cwd': rel, 'items': dirs + files, 'parent': parent})

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """API endpoint to handle file and directory uploads."""
    rel = request.form.get('dir', '')
    abs_dir = safe_path(rel)

    if not os.path.isdir(abs_dir):
        app.logger.info(f"Upload target is not a directory or does not exist: {abs_dir}")
        return jsonify(error="Invalid target directory or does not exist"), 400

    if not os.access(abs_dir, os.W_OK):
        app.logger.warning(f"Permission denied to write to directory: {abs_dir}")
        return jsonify(error="Permission denied: Target directory is not writable"), 403

    files = request.files.getlist('files[]')
    if not files:
        app.logger.info("No files provided for upload.")
        return jsonify(error="No files provided for upload"), 400

    uploaded_count = 0
    errors = []

    for f in files:
        if f.filename == '':
            errors.append(f"Skipping file with no filename (empty filename).")
            continue

        path_components = f.filename.split(os.path.sep)
        sanitized_components = [secure_filename(comp) for comp in path_components if comp]

        if not sanitized_components:
            errors.append(f"Skipping file due to invalid or empty path after sanitization: {f.filename}")
            continue

        final_relative_path = os.path.join(*sanitized_components)
        final_save_path = os.path.join(abs_dir, final_relative_path)

        if '.' in final_save_path and not allowed_file(final_save_path):
             errors.append(f"File '{f.filename}' has an disallowed extension. Skipping.")
             app.logger.warning(f"Upload attempt with disallowed extension: {final_save_path}")
             #continue


        try:
            os.makedirs(os.path.dirname(final_save_path), exist_ok=True)
            f.save(final_save_path)
            uploaded_count += 1
            app.logger.info(f"Successfully uploaded: {final_save_path}")
        except Exception as e:
            errors.append(f"Failed to upload {f.filename}: {e}")
            app.logger.error(f"Error saving file {final_save_path}: {e}")

    if errors:
        status_code = 500 if uploaded_count == 0 else 200
        return jsonify(success=False, uploaded_count=uploaded_count, errors=errors, message="Some files failed to upload."), status_code

    return jsonify(success=True, uploaded_count=uploaded_count)

@app.route('/api/download', methods=['GET'])
def api_download():
    """API endpoint to handle file downloads."""
    rel = request.args.get('path', '')
    abs_file = safe_path(rel)

    if not os.path.isfile(abs_file):
        app.logger.info(f"Requested path for download is not a file or does not exist: {abs_file}")
        abort(404, description="File not found or is a directory.")

    if not os.access(abs_file, os.R_OK):
        app.logger.warning(f"Permission denied to read file: {abs_file}")
        abort(403, description="Permission denied: Cannot read file.")

    dirn = os.path.dirname(abs_file)
    fname = os.path.basename(abs_file)

    return send_from_directory(dirn, fname, as_attachment=True, mimetype='application/octet-stream')

@app.route('/api/clipboard/download/<file_type>', methods=['GET'])
def api_clipboard_download(file_type):
    """API endpoint to provide clipboard content as a downloadable file."""
    if not SHARE_CLIPBOARD:
        abort(403, description="Clipboard sharing is not enabled.")

    clipboard_data = get_clipboard_content()

    if file_type == 'text' and 'text_plain' in clipboard_data:
        return app.response_class(
            clipboard_data['text_plain'],
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment;filename=clipboard_text.txt'}
        )
    elif file_type == 'html' and 'text_html' in clipboard_data:
        return app.response_class(
            clipboard_data['text_html'],
            mimetype='text/html',
            headers={'Content-Disposition': 'attachment;filename=clipboard_html.html'}
        )
    elif file_type == 'png' and 'image_png_base64' in clipboard_data:
        try:
            image_binary_data = base64.b64decode(clipboard_data['image_png_base64'])
            return app.response_class(
                image_binary_data,
                mimetype='image/png',
                headers={'Content-Disposition': 'attachment;filename=clipboard_image.png'}
            )
        except Exception as e:
            app.logger.error(f"Error decoding base64 image for download: {e}")
            abort(500, description="Error processing image for download.")
    else:
        abort(404, description=f"Clipboard content not available in requested format: {file_type}. Supported: plain text, HTML, PNG.")

@app.route('/api/clipboard/refresh', methods=['GET'])
def api_clipboard_refresh():
    """API endpoint to manually refresh clipboard data and return it as JSON."""
    if not SHARE_CLIPBOARD:
        return jsonify(error="Clipboard sharing is not enabled."), 403

    current_clipboard_content = get_clipboard_content()
    global last_clipboard_content
    last_clipboard_content = current_clipboard_content
    return jsonify(current_clipboard_content)

@app.route('/api/clipboard/stream')
def clipboard_stream():
    """Server-Sent Events (SSE) endpoint for real-time clipboard updates."""
    if not SHARE_CLIPBOARD or not REALTIME_CLIPBOARD:
        return Response("Clipboard sharing or realtime updates not enabled.", status=403)

    def generate():
        while True:
            try:
                clipboard_data = clipboard_queue.get(timeout=POLLING_INTERVAL + 1)
                yield f"data: {json.dumps(clipboard_data)}\n\n"
            except queue.Empty:
                yield ":keepalive\n\n"
            except Exception as e:
                app.logger.error(f"Error in SSE stream: {e}")
                break

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/ping')
def ping():
    """Simple API endpoint to check server health."""
    return jsonify(ok=True)

# --- Main HTML Template (Same as before, with minor adjustment for Markdown) ---
TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Simple File Server Type-C (Text & Image Clipboard)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📁</text></svg>">
<style>
body {
    font-family: 'Segoe UI', 'Arial', sans-serif; margin:0; background:#f8fafc;
    color: #333;
}
#conn_status {
    display:none; background:#d32f2f; color:#fff;
    padding:10px;text-align:center;font-weight:bold;position:fixed;top:0;left:0;right:0;z-index:999;
}
#container {
    max-width: 900px; margin: 72px auto 0 auto; background: #fff;
    border-radius:12px; box-shadow:0 2px 12px #aaa3;
    padding:32px;
}
@media (max-width:650px) {
    #container { padding:12px; margin-top: 50px;}
    h2 { font-size:19px;}
    li { font-size:14px;}
    .section { margin:18px 0 0 0;}
}
h2 { margin-bottom:15px; color:#08488d;}
#pathbar {
    margin-bottom:20px; display:flex; align-items: center;
    gap: 10px; flex-wrap: wrap;
}
#topbtn, #upbtn {
    border: none; background:#def; color:#0561a9;
    font-size:15px; border-radius:5px; padding:4px 12px;
    cursor: pointer; transition:.15s ease-in-out;
}
#topbtn:hover, #upbtn:hover { background: #cbeafd;}
#curpath {
    font-weight:500; color:#0a2754;
    flex-grow: 1;
    word-break: break-all;
}
ul#listing {
    border:1px solid #e4eaf2; border-radius:8px; padding:0 12px; background:#fafdff;
    margin:0 0 8px 0; min-height:40px; list-style: none;
}
.icon {
    display: inline-block;
    width: 20px;
    height: 20px;
    vertical-align: middle;
    margin-right: 5px;
    font-size: 1.2em;
    line-height: 1;
}
li {
    display: flex;
    align-items: center;
    gap: 0px;
    border-bottom: 1px solid #edf1f6; height:36px; font-size:16px;
    padding-left: 5px;
}
li.folder { font-weight:bold; color:#1461b0; cursor:pointer;}
li:last-child { border-bottom:none;}
li a {
    text-decoration:none; color:#384c66; transition:.1s ease-in-out;
    display: flex; align-items: center; gap: 0px;
    flex-grow: 1;
}
li a:hover {color:#217cee;}
.section { margin: 32px 0 0 0; padding-top: 15px; border-top: 1px dashed #e4eaf2;}
.section:first-of-type { border-top: none; padding-top: 0; margin-top: 0;}
.form-row { display:flex; align-items:center; gap:10px; margin-top:8px; flex-wrap: wrap;}
input[type="file"] {
    border: 1px solid #c3d0e5; border-radius:6px; background:#fcfdff; font-size:15px;
    padding: 6px;
    flex-grow: 1;
    min-width: 180px;
}
button[type="button"], .btn {
    border:none; color:#fff; background:#407bcd; border-radius:5px;
    padding:7px 16px; font-size:15px; cursor:pointer; transition: .13s ease-in-out;
    white-space: nowrap;
}
button[type="button"]:hover, .btn:hover { background:#265fa3;}
.progress-span {
    height:18px; display:inline-block; color:#16622f; min-width:52px; margin-left:8px;
    font-size: 14px;
}
.progress-span.success { color: #28a745; font-weight: bold; }
.progress-span.error { color: #dc3545; font-weight: bold; }

#clipboard-section {
    background: #e6f0ff;
    border: 1px solid #cce0ff;
    border-radius: 8px;
    padding: 15px;
    margin-top: 20px;
}
#clipboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}
#clipboard-content {
    background: #ffffff;
    border: 1px solid #d0e0f0;
    border-radius: 5px;
    padding: 10px;
    margin-top: 10px;
    min-height: 40px;
    overflow-x: auto;
    word-break: break-all;
}
#clipboard-content img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 5px 0;
    border: 1px solid #eee;
}
.clipboard-action-btn {
    background: #28a745;
    margin-left: 5px;
}
.clipboard-action-btn:hover {
    background: #218838;
}
.toggle-on { background: #28a745 !important; }
.toggle-off { background: #dc3545 !important; }
.clipboard-content-item {
    margin-bottom: 10px;
    padding-bottom: 10px;
    border-bottom: 1px dashed #eee;
}
.clipboard-content-item:last-child {
    border-bottom: none;
    padding-bottom: 0;
}
</style>
</head>
<body>
<div id="conn_status">SERVER CONNECTION LOST</div>
<div id="container">
    <h2>ShareNow - Type C v1.11 (Text & Image Clipboard)</h2>
    <div id="pathbar">
        <button id="topbtn" type="button">⭱ Top</button>
        <button id="upbtn" style="display:none" type="button">⬅ Up</button>
        <span id="curpath"></span>
    </div>
    <ul id="listing"></ul>
    <div class="section">
        <h4>File Upload</h4>
        <div class="form-row">
            <input type="file" id="fileInput" multiple>
            <button id="uploadFileBtn" type="button" class="btn">Upload Files</button>
            <span id="fileUploadProgress" class="progress-span"></span>
        </div>
    </div>
    <div class="section">
        <h4>Directory Upload</h4>
        <div class="form-row">
            <input type="file" id="dirInput" webkitdirectory directory multiple>
            <button id="uploadDirBtn" type="button" class="btn">Upload Directory</button>
            <span id="dirUploadProgress" class="progress-span"></span>
        </div>
    </div>

    <div class="section" id="clipboard-section">
        <div id="clipboard-header">
            <h4>Shared Clipboard Content (from Server)</h4>
            {% if SHARE_CLIPBOARD %}
                <button type="button" class="btn clipboard-action-btn" id="realtimeClipboardToggle">
                    {% if REALTIME_CLIPBOARD %}Turn Realtime Off{% else %}Turn Realtime On{% endif %}
                </button>
            {% endif %}
        </div>
        <div id="clipboard-content">
            {% if SHARE_CLIPBOARD %}
                {% if clipboard_data.text_plain %}
                    <div class="clipboard-content-item">
                        <h5>Plain Text Content:</h5>
                        <p>{{ clipboard_data.text_plain | e }}</p>
                        <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('{{ clipboard_data.text_plain | js_string }}')">Copy Text to My Clipboard</button>
                        <a href="/api/clipboard/download/text" class="btn clipboard-action-btn">Download as .txt</a>
                    </div>
                {% elif clipboard_data.text_error %}
                    <p style="color:red;">Error accessing text clipboard: {{ clipboard_data.text_error }}</p>
                {% endif %}

                {% if clipboard_data.text_html %}
                    <div class="clipboard-content-item">
                        <h5>HTML Content:</h5>
                        <div style="border: 1px dashed #ccc; padding: 5px; max-height: 200px; overflow-y: auto;">
                            {{ clipboard_data.text_html | safe }}
                        </div>
                        <p style="font-size: 0.8em; color: #666;">(Rendered directly. Download for source.)</p>
                        <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('{{ clipboard_data.text_html | js_string }}')">Copy HTML to My Clipboard</button>
                        <a href="/api/clipboard/download/html" class="btn clipboard-action-btn">Download as .html</a>
                    </div>
                {% elif clipboard_data.text_html_error %}
                    <p style="color:red;">Error accessing HTML clipboard: {{ clipboard_data.text_html_error }}</p>
                {% endif %}

                {# Markdown content is not directly supported on Windows clipboard. It will fall under plain text. #}
                {# The following block is commented out as it relies on text/markdown MIME type which is not standard on Windows #}
                {#
                {% if clipboard_data.text_markdown %}
                    <div class="clipboard-content-item">
                        <h5>Markdown Content:</h5>
                        <pre style="background:#f0f0f0; padding:10px; border-radius:5px; max-height: 200px; overflow-y: auto;">{{ clipboard_data.text_markdown | e }}</pre>
                        <p style="font-size: 0.8em; color: #666;">(Raw Markdown. Server could convert to HTML if 'markdown' library is installed.)</p>
                        <a href="/api/clipboard/download/markdown" class="btn clipboard-action-btn">Download as .md</a>
                    </div>
                {% elif clipboard_data.text_markdown_error %}
                    <p style="color:red;">Error accessing Markdown clipboard: {{ clipboard_data.text_markdown_error }}</p>
                {% endif %}
                #}

                {% if clipboard_data.image_png_base64 %}
                    <div class="clipboard-content-item">
                        <h5>Image Content (PNG):</h5>
                        <img src="data:image/png;base64,{{ clipboard_data.image_png_base64 }}" alt="Clipboard Image">
                        <p style="font-size: 0.8em; color: #666;">(Image is rendered directly from server clipboard)</p>
                        <a href="/api/clipboard/download/png" class="btn clipboard-action-btn">Download as .png</a>
                    </div>
                {% elif clipboard_data.image_error %}
                    <p style="color:red;">Error accessing image clipboard: {{ clipboard_data.image_error }}</p>
                {% endif %}

                {% if not clipboard_data.text_plain and not clipboard_data.text_html and not clipboard_data.image_png_base64 and not clipboard_data.text_error and not clipboard_data.text_html_error and not clipboard_data.image_error and not clipboard_data.clipboard_warnings %}
                    <p>No clipboard content available.</p>
                {% endif %}

                {% if clipboard_data.clipboard_warnings %}
                    <p style="color:orange; font-size:0.9em;">Warnings: {{ clipboard_data.clipboard_warnings }}</p>
                {% endif %}

            {% else %}
                <p>Clipboard sharing is currently disabled on the server. Please enable it with `--share-clipboard` option.</p>
            {% endif %}
        </div>
    </div>

</div>

<script>
let curPath = '';
let fileFiles = [], dirFiles = [];
const connStatus      = document.getElementById('conn_status');
const curPathSpan     = document.getElementById('curpath');
const topBtn          = document.getElementById('topbtn');
const upBtn           = document.getElementById('upbtn');
const listing         = document.getElementById('listing');
const fileInput       = document.getElementById('fileInput');
const uploadFileBtn   = document.getElementById('uploadFileBtn');
const dirInput        = document.getElementById('dirInput');
const uploadDirBtn    = document.getElementById('uploadDirBtn');
const fileUploadProgress = document.getElementById('fileUploadProgress');
const dirUploadProgress  = document.getElementById('dirUploadProgress');
const clipboardContentDiv = document.getElementById('clipboard-content');
const realtimeClipboardToggle = document.getElementById('realtimeClipboardToggle');

let eventSource = null;
let isRealtimeEnabled = {{ 'true' if REALTIME_CLIPBOARD else 'false' }};

fileInput.onchange = e => {
    fileFiles = [...e.target.files];
    fileUploadProgress.innerText = '';
    fileUploadProgress.className = 'progress-span';
};
dirInput.onchange  = e => {
    dirFiles  = [...e.target.files];
    dirUploadProgress.innerText = '';
    dirUploadProgress.className = 'progress-span';
};

function fetchList(path='') {
    fetch('/api/list?path='+encodeURIComponent(path))
    .then(resp => {
        if (!resp.ok) {
            return resp.json().then(errorData => {
                const errorMessage = errorData.error || resp.statusText;
                if (resp.status === 403) {
                    alert('Permission denied to access this directory: ' + errorMessage);
                } else if (resp.status === 400) {
                    alert('Invalid directory path: ' + errorMessage);
                } else {
                    alert('Error fetching directory listing (' + resp.status + '): ' + errorMessage);
                }
                if (curPath && path !== curPath) {
                     const pathParts = curPath.split('/');
                     if (pathParts.length > 1) {
                         fetchList(pathParts.slice(0, -1).join('/'));
                     } else {
                         fetchList('');
                     }
                } else if (curPath && path === curPath) {
                    fetchList('');
                } else {
                    console.error('Failed to fetch list at root or cannot recover:', errorData);
                }
                return Promise.reject('Failed to fetch list: ' + errorMessage);
            }).catch(() => {
                alert('Error fetching directory listing: ' + resp.statusText + '. Please check server logs.');
                return Promise.reject('Failed to fetch list: Non-JSON error');
            });
        }
        return resp.json();
    })
    .then(data => {
        curPath = data.cwd || '';
        curPathSpan.innerText = 'Current Directory: /' + (curPath || '');

        topBtn.onclick = () => fetchList('');

        if (data.parent !== null) {
            upBtn.style.display = 'inline-block';
            upBtn.onclick = () => fetchList(data.parent);
        } else {
            upBtn.style.display = 'none';
        }

        listing.innerHTML = '';

        if (data.items.length === 0) {
            let li = document.createElement('li');
            li.innerText = 'This directory is empty.';
            li.style.color = '#777';
            listing.appendChild(li);
        }

        data.items.forEach(item => {
            let li = document.createElement('li');
            if(item.is_dir){
                li.innerHTML = '<span class="icon icon-folder">📁</span> ' + escapeHtml(item.name);
                li.className = 'folder';
                li.onclick = () => fetchList((curPath ? curPath + '/' : '') + item.name);
            }else{
                let a = document.createElement('a');
                a.href = '/api/download?path=' + encodeURIComponent((curPath ? curPath + '/' : '') + item.name);
                a.innerHTML = '<span class="icon icon-file">📄</span> ' + escapeHtml(item.name);
                a.setAttribute('download', item.name);
                li.appendChild(a);
            }
            listing.appendChild(li);
        });
    })
    .catch(error => {
        console.error('Error in fetchList (caught after response handling):', error);
    });
}
fetchList();

function uploadFiles(files, progressSpan, isDirectoryUpload = false) {
    if (files.length === 0) {
        alert(isDirectoryUpload ? 'Please select a directory to upload!' : 'Please select files to upload!');
        return;
    }

    let fd = new FormData();
    files.forEach(f => {
        const fileNameToUse = isDirectoryUpload && f.webkitRelativePath ? f.webkitRelativePath : f.name;
        fd.append('files[]', f, fileNameToUse);
    });
    fd.append('dir', curPath);

    progressSpan.innerText = '0%';
    progressSpan.className = 'progress-span';

    let xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

    xhr.upload.onprogress = e => {
        let percent = e.lengthComputable ? (e.loaded / e.total * 100) : 0;
        progressSpan.innerText = Math.round(percent) + '%';
    };

    xhr.onload = () => {
        if (xhr.status === 200) {
            progressSpan.innerText = 'Success!';
            progressSpan.classList.add('success');
            if (isDirectoryUpload) dirInput.value = '';
            else fileInput.value = '';
            if (isDirectoryUpload) dirFiles = [];
            else fileFiles = [];
            fetchList(curPath);
        } else {
            progressSpan.innerText = 'Failed!';
            progressSpan.classList.add('error');
            try {
                const response = JSON.parse(xhr.responseText);
                let errorMessage = response.error || 'Unknown error.';
                if (response.errors && response.errors.length > 0) {
                    errorMessage += "\nDetails: " + response.errors.join("\n");
                }
                alert('Upload failed: ' + errorMessage);
                console.error("Upload response error:", response);
            } catch (e) {
                alert('Upload failed: Server error or invalid response format.');
                console.error("Failed to parse upload error response:", e);
            }
        }
    };

    xhr.onerror = () => {
        progressSpan.innerText = 'Error!';
        progressSpan.classList.add('error');
        alert('Network error during upload. Please check your connection.');
    };

    xhr.send(fd);
}

uploadFileBtn.onclick = () => uploadFiles(fileFiles, fileUploadProgress, false);
uploadDirBtn.onclick = () => uploadFiles(dirFiles, dirUploadProgress, true);

function copyToClientClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => {
                alert('Content copied to your clipboard!');
            })
            .catch(err => {
                console.error('Could not copy content: ', err);
                alert('Failed to copy content to clipboard. Please copy manually or check browser permissions.');
            });
    } else {
        alert('Your browser does not support automatic clipboard writing. Please copy the content manually.');
    }
}

function updateClipboardContent(clipboardData) {
    let contentHtml = '';

    if (!{{ 'true' if SHARE_CLIPBOARD else 'false' }}) {
        clipboardContentDiv.innerHTML = '<p>Clipboard sharing is currently disabled on the server. Please enable it with `--share-clipboard` option.</p>';
        return;
    }

    let hasContent = false;

    if (clipboardData.text_plain) {
        hasContent = true;
        const escapedText = JSON.stringify(clipboardData.text_plain).slice(1, -1);
        contentHtml += `
            <div class="clipboard-content-item">
                <h5>Plain Text Content:</h5>
                <p>${escapeHtml(clipboardData.text_plain)}</p>
                <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('${escapedText}')">Copy Text to My Clipboard</button>
                <a href="/api/clipboard/download/text" class="btn clipboard-action-btn">Download as .txt</a>
            </div>
        `;
    } else if (clipboardData.text_error) {
        hasContent = true;
        contentHtml += `<p style="color:red;">Error accessing text clipboard: ${escapeHtml(clipboardData.text_error)}</p>`;
    }

    if (clipboardData.text_html) {
        hasContent = true;
        const escapedHtmlForJs = JSON.stringify(clipboardData.text_html).slice(1, -1);
        contentHtml += `
            <div class="clipboard-content-item">
                <h5>HTML Content:</h5>
                <div style="border: 1px dashed #ccc; padding: 5px; max-height: 200px; overflow-y: auto;">
                    ${clipboardData.text_html}
                </div>
                <p style="font-size: 0.8em; color: #666;">(Rendered directly. Download for source.)</p>
                <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('${escapedHtmlForJs}')">Copy HTML to My Clipboard</button>
                <a href="/api/clipboard/download/html" class="btn clipboard-action-btn">Download as .html</a>
            </div>
        `;
    } else if (clipboardData.text_html_error) {
        hasContent = true;
        contentHtml += `<p style="color:red;">Error accessing HTML clipboard: ${escapeHtml(clipboardData.text_html_error)}</p>`;
    }

    // Markdown is not a native Windows clipboard format, so this section is not applicable.
    // It would be handled as plain text if it's just text.

    if (clipboardData.image_png_base64) {
        hasContent = true;
        contentHtml += `
            <div class="clipboard-content-item">
                <h5>Image Content (PNG):</h5>
                <img src="data:image/png;base64,${clipboardData.image_png_base64}" alt="Clipboard Image">
                <p style="font-size: 0.8em; color: #666;">(Image is rendered directly from server clipboard)</p>
                <a href="/api/clipboard/download/png" class="btn clipboard-action-btn">Download as .png</a>
            </div>
        `;
    } else if (clipboardData.image_error) {
        hasContent = true;
        contentHtml += `<p style="color:red;">Error accessing image clipboard: ${escapeHtml(clipboardData.image_error)}</p>`;
    }

    if (!hasContent) {
        contentHtml += '<p>No clipboard content available.</p>';
    }
    if (clipboardData.clipboard_warnings) {
        contentHtml += `<p style="color:orange; font-size:0.9em;">Warnings: ${escapeHtml(clipboardData.clipboard_warnings)}</p>`;
    }
    clipboardContentDiv.innerHTML = contentHtml;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function updateRealtimeButtonState() {
    if (realtimeClipboardToggle) {
        if (isRealtimeEnabled) {
            realtimeClipboardToggle.innerText = 'Turn Realtime Off';
            realtimeClipboardToggle.classList.remove('toggle-off');
            realtimeClipboardToggle.classList.add('toggle-on');
        } else {
            realtimeClipboardToggle.innerText = 'Turn Realtime On';
            realtimeClipboardToggle.classList.remove('toggle-on');
            realtimeClipboardToggle.classList.add('toggle-off');
        }
    }
}

function connectRealtimeClipboard() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    if ({{ 'true' if REALTIME_CLIPBOARD and SHARE_CLIPBOARD else 'false' }}) {
        eventSource = new EventSource('/api/clipboard/stream');
        eventSource.onmessage = function(event) {
            const clipboardData = JSON.parse(event.data);
            updateClipboardContent(clipboardData);
            console.log("Realtime clipboard update received:", clipboardData);
        };
        eventSource.onerror = function(err) {
            console.error('EventSource failed:', err);
            eventSource.close();
            setTimeout(connectRealtimeClipboard, 3000);
        };
        console.log("Attempting to connect to realtime clipboard stream...");
    } else {
        console.log("Realtime clipboard disabled on server or by user.");
    }
}

if (realtimeClipboardToggle) {
    realtimeClipboardToggle.onclick = () => {
        isRealtimeEnabled = !isRealtimeEnabled;
        updateRealtimeButtonState();
        if (isRealtimeEnabled) {
            fetch('/api/clipboard/refresh')
                .then(response => response.json())
                .then(data => updateClipboardContent(data))
                .catch(error => console.error('Error fetching initial clipboard on realtime enable:', error));
            connectRealtimeClipboard();
        } else {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
                console.log("Realtime clipboard stream disconnected.");
            }
        }
    };
    updateRealtimeButtonState();
    if (isRealtimeEnabled) {
        connectRealtimeClipboard();
    } else {
        if ({{ 'true' if SHARE_CLIPBOARD else 'false' }}) {
             fetch('/api/clipboard/refresh')
                .then(response => response.json())
                .then(data => updateClipboardContent(data))
                .catch(error => console.error('Error fetching initial clipboard:', error));
        }
    }
} else {
    if ({{ 'true' if SHARE_CLIPBOARD else 'false' }}) {
         fetch('/api/clipboard/refresh')
            .then(response => response.json())
            .then(data => updateClipboardContent(data))
            .catch(error => console.error('Error fetching initial clipboard:', error));
    }
}

function checkServer() {
    fetch("/api/ping", { signal: AbortSignal.timeout(1500) })
    .then(r => {
        if (r.ok) {
            connStatus.style.display = 'none';
        } else {
            console.error("Ping failed: Server responded with status", r.status);
            connStatus.innerText = 'SERVER CONNECTION LOST (Server responded with an error)';
            connStatus.style.display = 'block';
        }
    })
    .catch(error => {
        console.error("Ping failed:", error);
        connStatus.innerText = 'SERVER CONNECTION LOST (Network error or server down)';
        connStatus.style.display = 'block';
    });
}

setInterval(checkServer, 2000);
checkServer();
</script>
</body>
</html>
"""

# --- Main execution block ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A simple Flask file server that shares files from a specified directory and optionally clipboard content.")
    parser.add_argument(
        '-d', '--dir',
        type=str,
        default=os.getcwd(),
        help="The directory to serve files from. Defaults to the current working directory."
    )
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=8000,
        help="The port number to run the server on. Defaults to 8000."
    )
    parser.add_argument(
        '-H', '--host',
        type=str,
        default='0.0.0.0',
        help="The host address to bind the server to. Use '0.0.0.0' for external access. Defaults to '0.0.0.0'."
    )
    parser.add_argument(
        '--share-clipboard',
        action='store_true',
        help="Enable sharing of the server's clipboard content (text, HTML, and image)."
    )
    parser.add_argument(
        '--realtime-clipboard',
        action='store_true',
        help="Enable real-time clipboard updates via Server-Sent Events (requires --share-clipboard)."
    )
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=1.0,
        help="The interval in seconds for polling clipboard content when real-time updates are enabled. Defaults to 1.0."
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help="Enable debug mode (DO NOT USE IN PRODUCTION)."
    )

    args = parser.parse_args()

    BASE_DIR = os.path.abspath(args.dir)
    SHARE_CLIPBOARD = args.share_clipboard
    REALTIME_CLIPBOARD = args.realtime_clipboard
    POLLING_INTERVAL = args.poll_interval

    if not os.path.isdir(BASE_DIR):
        print(f"Error: The specified directory '{args.dir}' does not exist or is not a valid directory.")
        exit(1)

    print(f"Serving files from: {BASE_DIR}")
    print(f"Server running on {args.host}:{args.port}")
    if SHARE_CLIPBOARD:
        print("Clipboard sharing is ENABLED (Text, HTML, and Images).")
        # Warn if pywin32 is not installed on Windows, as features will be limited
        if IS_WINDOWS and not (getattr(win32clipboard, 'OpenClipboard', None) and getattr(win32clipboard, 'GetClipboardData', None)):
            print("WARNING: pywin32 might not be fully functional. Image and HTML clipboard features may not work correctly.")

        if REALTIME_CLIPBOARD:
            print(f"Real-time clipboard updates are ENABLED with a polling interval of {POLLING_INTERVAL} seconds.")
            polling_thread = threading.Thread(target=clipboard_polling_thread, daemon=True)
            polling_thread.start()
        else:
            print("Real-time clipboard updates are DISABLED. Use --realtime-clipboard to enable.")
    else:
        print("Clipboard sharing is DISABLED. Use --share-clipboard to enable.")
        if REALTIME_CLIPBOARD:
            print("Warning: --realtime-clipboard has no effect when --share-clipboard is not enabled.")

    if args.debug:
        print("!!! DEBUG MODE IS ENABLED. DO NOT USE IN PRODUCTION. !!!")

    app.run(host=args.host, port=args.port, debug=args.debug)