import os
import time
from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string, Response, stream_with_context
from werkzeug.utils import secure_filename
import logging
import argparse
import pyperclip
import json
import base64
import subprocess
from io import BytesIO
from PIL import Image
import threading
import queue

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
BASE_DIR = None
SHARE_CLIPBOARD = False
REALTIME_CLIPBOARD = False
POLLING_INTERVAL = 1 # Default polling interval in seconds

# Queue for inter-thread communication (clipboard updates)
clipboard_queue = queue.Queue()
last_clipboard_content = {} # Store last sent clipboard content to avoid redundant updates

# --- Custom Jinja2 Filter for JavaScript String Escaping ---
def js_string(value):
    """
    Escapes a string for safe inclusion in JavaScript within an HTML attribute.
    Uses json.dumps to handle quotes, newlines, etc.
    """
    return json.dumps(value)[1:-1]

# Register the custom filter with Jinja2 environment
app.jinja_env.filters['js_string'] = js_string


# Configuration for allowed extensions (optional, but good for security)
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'mp3', 'mp4', 'py', 'html', 'css', 'js', 'json', 'xml', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

def allowed_file(filename):
    """
    Checks if a file's extension is in the allowed list.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_path(rel_path):
    """
    Ensures that the requested path is within the BASE_DIR to prevent directory traversal attacks.
    """
    normalized_path = os.path.normpath(rel_path)
    abs_path = os.path.abspath(os.path.join(BASE_DIR, normalized_path))

    if not abs_path.startswith(BASE_DIR):
        app.logger.warning(f"Attempted directory traversal detected: {rel_path} -> {abs_path}")
        abort(403, description="Access denied: Path outside base directory.")

    return abs_path

# --- Clipboard Handling Functions (Now supports text, HTML, Markdown, and various image types converted to PNG/SVG) ---
def get_clipboard_content():
    """
    Retrieves plain text, HTML, Markdown, and various image types from the clipboard.
    Image types are converted to PNG and returned as base64.
    Returns a dictionary with 'text_plain', 'text_html', 'text_markdown', 'image_png_base64', 'image_svg_base64' if content is found.
    Includes error keys if clipboard access fails for a specific type or conversion fails.
    """
    detected_content = {}

    # 1. Try to get plain text content using pyperclip
    try:
        text_content = pyperclip.paste()
        if text_content:
            detected_content['text_plain'] = text_content
            # app.logger.info("Clipboard content: Plain text (from pyperclip) detected.") # Log only on change
    except pyperclip.PyperclipException as e:
        app.logger.error(f"Error pasting text from clipboard with pyperclip: {e}")
        detected_content['text_error'] = f"Text clipboard access failed: {e}"

    # 2. Try to get HTML content using wl-paste (Wayland specific)
    if os.getenv('WAYLAND_DISPLAY') or os.getenv('XDG_SESSION_TYPE') == 'wayland':
        try:
            html_content_raw = subprocess.check_output(['wl-paste', '--type', 'text/html'], timeout=2)
            if html_content_raw:
                detected_content['text_html'] = html_content_raw.decode('utf-8', errors='ignore')
                # app.logger.info("Clipboard content: HTML detected.")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            app.logger.debug(f"wl-paste --type text/html failed: {e}")
            if isinstance(e, FileNotFoundError):
                detected_content['text_html_error'] = "wl-paste not found. Is 'wl-clipboard' installed?"
        except Exception as e:
            app.logger.warning(f"Unexpected error during wl-paste for text/html: {e}")
            detected_content['text_html_error'] = f"Unexpected error getting HTML: {e}"

        # 3. Try to get Markdown content using wl-paste
        try:
            markdown_content_raw = subprocess.check_output(['wl-paste', '--type', 'text/markdown'], timeout=2)
            if markdown_content_raw:
                detected_content['text_markdown'] = markdown_content_raw.decode('utf-8', errors='ignore')
                # app.logger.info("Clipboard content: Markdown detected.")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            app.logger.debug(f"wl-paste --type text/markdown failed: {e}")
        except Exception as e:
            app.logger.warning(f"Unexpected error during wl-paste for text/markdown: {e}")
            detected_content['text_markdown_error'] = f"Unexpected error getting Markdown: {e}"

    # 4. Try to get image content using wl-paste (Wayland specific)
    IMAGE_MIME_TYPES = ['image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'image/tiff', 'image/webp']
    image_data_found = False
    image_access_errors = []

    if os.getenv('WAYLAND_DISPLAY') or os.getenv('XDG_SESSION_TYPE') == 'wayland':
        try:
            svg_data_raw = subprocess.check_output(['wl-paste', '--type', 'image/svg+xml'], timeout=2)
            if svg_data_raw:
                detected_content['image_svg_base64'] = base64.b64encode(svg_data_raw).decode('utf-8')
                # app.logger.info("Clipboard content: SVG image detected.")
                image_data_found = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            app.logger.debug(f"wl-paste --type image/svg+xml failed: {e}")
            if isinstance(e, FileNotFoundError):
                image_access_errors.append(f"wl-paste not found. Is 'wl-clipboard' installed?")
            else:
                image_access_errors.append(f"Image clipboard access failed for SVG: {e}")
        except Exception as e:
            app.logger.warning(f"Unexpected error during wl-paste for image/svg+xml: {e}")
            image_access_errors.append(f"Unexpected error for SVG: {e}")

        if not detected_content.get('image_png_base64') and not detected_content.get('image_svg_base64'):
            for mime_type in IMAGE_MIME_TYPES:
                try:
                    raw_image_data = subprocess.check_output(['wl-paste', '--type', mime_type], timeout=2)
                    if raw_image_data:
                        image_stream = BytesIO(raw_image_data)
                        try:
                            img = Image.open(image_stream)

                            if img.mode == 'RGBA' or (img.mode == 'P' and 'transparency' in img.info):
                                output_buffer = BytesIO()
                                img.save(output_buffer, format='PNG', optimize=True)
                            elif img.mode == 'P':
                                output_buffer = BytesIO()
                                img.convert('RGB').save(output_buffer, format='PNG', optimize=True)
                            else:
                                output_buffer = BytesIO()
                                img.save(output_buffer, format='PNG', optimize=True)

                            image_png_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                            detected_content['image_png_base64'] = image_png_base64
                            # app.logger.info(f"Clipboard content: Image ({mime_type} converted to PNG) detected.")
                            image_data_found = True
                            break
                        except Exception as img_conv_e:
                            app.logger.warning(f"Failed to open or convert {mime_type} clipboard data to PNG: {img_conv_e}")
                            image_access_errors.append(f"Conversion failed for {mime_type}: {img_conv_e}")

                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                    app.logger.debug(f"wl-paste --type {mime_type} failed: {e}")
                    if isinstance(e, FileNotFoundError):
                        image_access_errors.append(f"wl-paste not found for {mime_type}. Is 'wl-clipboard' installed?")
                        break
                    elif isinstance(e, subprocess.TimeoutExpired):
                        image_access_errors.append(f"wl-paste for {mime_type} timed out. Clipboard might be empty or locked.")
                    else:
                        image_access_errors.append(f"Image clipboard access failed for {mime_type}: {e}")
                except Exception as e:
                    app.logger.warning(f"Unexpected error during wl-paste for {mime_type}: {e}")
                    image_access_errors.append(f"Unexpected error for {mime_type}: {e}")

        if not image_data_found and not detected_content.get('image_png_base64') and not detected_content.get('image_svg_base64') and image_access_errors:
             detected_content['image_error'] = "No convertible image found or errors occurred: " + "; ".join(set(image_access_errors))
        elif not image_data_found and not detected_content.get('image_png_base64') and not detected_content.get('image_svg_base64'):
             detected_content['image_error'] = "No image found in clipboard. Make sure 'wl-clipboard' and 'Pillow' are installed."
    else:
        # app.logger.info("Wayland session not detected or wl-paste not available, skipping image clipboard check.")
        detected_content['image_error'] = "Not a Wayland session. Image clipboard not supported via wl-paste."

    return detected_content

# --- Background thread for clipboard polling ---
def clipboard_polling_thread():
    global last_clipboard_content
    while True:
        if REALTIME_CLIPBOARD:
            current_clipboard_content = get_clipboard_content()
            if current_clipboard_content != last_clipboard_content:
                app.logger.info("Clipboard content changed, pushing update to clients.")
                clipboard_queue.put(current_clipboard_content)
                last_clipboard_content = current_clipboard_content
        time.sleep(POLLING_INTERVAL) # Use the global POLLING_INTERVAL

@app.route('/')
def index():
    clipboard_data = {}

    if SHARE_CLIPBOARD:
        clipboard_data = get_clipboard_content()
        global last_clipboard_content # Initialize last_clipboard_content on first load
        last_clipboard_content = clipboard_data

    return render_template_string(TEMPLATE,
                                  clipboard_data=clipboard_data,
                                  SHARE_CLIPBOARD=SHARE_CLIPBOARD,
                                  REALTIME_CLIPBOARD=REALTIME_CLIPBOARD)

@app.route('/api/list', methods=['GET'])
def api_list_dir():
    """
    Lists the contents of a directory.
    """
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
    """
    Handles file and directory uploads.
    """
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
             # Allow for test
            #  continue

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
    """
    Handles file downloads.
    """
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
    """
    Provides clipboard content as a downloadable file (text or PNG image).
    """
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
    elif file_type == 'markdown' and 'text_markdown' in clipboard_data:
        return app.response_class(
            clipboard_data['text_markdown'],
            mimetype='text/markdown',
            headers={'Content-Disposition': 'attachment;filename=clipboard_markdown.md'}
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
    elif file_type == 'svg' and 'image_svg_base64' in clipboard_data:
        try:
            image_binary_data = base64.b64decode(clipboard_data['image_svg_base64'])
            return app.response_class(
                image_binary_data,
                mimetype='image/svg+xml',
                headers={'Content-Disposition': 'attachment;filename=clipboard_image.svg'}
            )
        except Exception as e:
            app.logger.error(f"Error decoding base64 SVG for download: {e}")
            abort(500, description="Error processing SVG for download.")
    else:
        abort(404, description=f"Clipboard content not available in requested format: {file_type}. Supported: plain text, HTML, Markdown, PNG, SVG.")

@app.route('/api/clipboard/refresh', methods=['GET'])
def api_clipboard_refresh():
    """
    API endpoint to refresh clipboard data and return it as JSON.
    This is now primarily used for initial load or manual refresh if realtime is off.
    """
    if not SHARE_CLIPBOARD:
        return jsonify(error="Clipboard sharing is not enabled."), 403

    current_clipboard_content = get_clipboard_content()
    global last_clipboard_content
    last_clipboard_content = current_clipboard_content # Update last content for polling thread
    return jsonify(current_clipboard_content)

@app.route('/api/clipboard/stream')
def clipboard_stream():
    """
    SSE endpoint for real-time clipboard updates.
    """
    if not SHARE_CLIPBOARD or not REALTIME_CLIPBOARD:
        return Response("Clipboard sharing or realtime updates not enabled.", status=403)

    def generate():
        while True:
            try:
                # Wait for new clipboard content from the polling thread
                clipboard_data = clipboard_queue.get(timeout=POLLING_INTERVAL + 1) # Timeout slightly longer than polling interval
                # Format data as an SSE event
                yield f"data: {json.dumps(clipboard_data)}\n\n"
            except queue.Empty:
                # Send a comment to keep the connection alive if no data
                yield ":keepalive\n\n"
            except Exception as e:
                app.logger.error(f"Error in SSE stream: {e}")
                break # Break loop on error to close connection

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/ping')
def ping():
    """
    Simple endpoint to check server health.
    """
    return jsonify(ok=True)


# --- Main HTML Template ---
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
/* Icon styles added */
.icon {
    display: inline-block;
    width: 20px; /* Adjust icon size for emojis */
    height: 20px;
    vertical-align: middle;
    margin-right: 5px; /* Spacing from text */
    font-size: 1.2em; /* Make emoji slightly larger than text */
    line-height: 1; /* Ensure proper vertical alignment */
}
/* No background-image needed for emojis, just set font size and color if desired */
.icon-folder {
    /* Emojis usually handle their own color, but you can hint */
    /* color: #FFD700; */ /* Gold for example, but might not apply to all emojis */
}
.icon-file {
    /* color: #384c66; */ /* Example: blue-grey for files */
}
/* Adjust existing list item styles */
li {
    display: flex; /* Use Flexbox to align icon and text */
    align-items: center;
    gap: 0px; /* Adjust spacing between icon and text */
    border-bottom: 1px solid #edf1f6; height:36px; font-size:16px;
    padding-left: 5px;
}
li.folder { font-weight:bold; color:#1461b0; cursor:pointer;}
li:last-child { border-bottom:none;}
li a {
    text-decoration:none; color:#384c66; transition:.1s ease-in-out;
    display: flex; align-items: center; gap: 0px; /* Adjust spacing between icon and text inside link */
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

/* Clipboard specific styles */
#clipboard-section {
    background: #e6f0ff; /* Light blue background for clipboard section */
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
    overflow-x: auto; /* For long text */
    word-break: break-all; /* Ensure long text breaks */
}
#clipboard-content img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 5px 0;
    border: 1px solid #eee;
}
.clipboard-action-btn {
    background: #28a745; /* Green for clipboard actions */
    margin-left: 5px;
}
.clipboard-action-btn:hover {
    background: #218838;
}
/* New style for toggle button states */
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
    <h2>ShareNow+ v1.22 (Text, HTML, Image Clipboard)</h2>
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
            {# Initial clipboard content rendered by Flask #}
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

                {% if clipboard_data.image_png_base64 %}
                    <div class="clipboard-content-item">
                        <h5>Image Content (PNG):</h5>
                        <img src="data:image/png;base64,{{ clipboard_data.image_png_base64 }}" alt="Clipboard Image">
                        <p style="font-size: 0.8em; color: #666;">(Image is rendered directly from server clipboard)</p>
                        <a href="/api/clipboard/download/png" class="btn clipboard-action-btn">Download as .png</a>
                    </div>
                {% elif clipboard_data.image_svg_base64 %}
                    <div class="clipboard-content-item">
                        <h5>Image Content (SVG):</h5>
                        <img src="data:image/svg+xml;base64,{{ clipboard_data.image_svg_base64 }}" alt="Clipboard SVG Image">
                        <p style="font-size: 0.8em; color: #666;">(SVG rendered directly. Note: SVG is not converted to PNG.)</p>
                        <a href="/api/clipboard/download/svg" class="btn clipboard-action-btn">Download as .svg</a>
                    </div>
                {% elif clipboard_data.image_error %}
                    <p style="color:red;">Error accessing image clipboard: {{ clipboard_data.image_error }}</p>
                {% endif %}

                {% if not clipboard_data.text_plain and not clipboard_data.text_html and not clipboard_data.text_markdown and not clipboard_data.image_png_base64 and not clipboard_data.image_svg_base64 and not clipboard_data.text_error and not clipboard_data.text_html_error and not clipboard_data.text_markdown_error and not clipboard_data.image_error %}
                    <p>No clipboard content available.</p>
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
const uploadDirBtn    = document.getElementById('dirInput'); // Corrected typo: uploadDirBtn
const fileUploadProgress = document.getElementById('fileUploadProgress');
const dirUploadProgress  = document.getElementById('dirUploadProgress');
const clipboardContentDiv = document.getElementById('clipboard-content');
const realtimeClipboardToggle = document.getElementById('realtimeClipboardToggle'); // New toggle button

let eventSource = null; // Variable to hold the SSE EventSource object
let isRealtimeEnabled = {{ 'true' if REALTIME_CLIPBOARD else 'false' }}; // Initial state from server

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
                li.innerHTML = '<span class="icon icon-folder">📁</span> ' + item.name; /* Use folder emoji */
                li.className = 'folder';
                li.onclick = () => fetchList((curPath ? curPath + '/' : '') + item.name);
            }else{
                let a = document.createElement('a');
                a.href = '/api/download?path=' + encodeURIComponent((curPath ? curPath + '/' : '') + item.name);
                a.innerHTML = '<span class="icon icon-file">📄</span> ' + item.name; /* Use file emoji */
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

// Function to update only the clipboard content section
function updateClipboardContent(clipboardData) {
    let contentHtml = '';

    // Check if clipboard sharing is enabled on the server
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

    if (clipboardData.text_markdown) {
        hasContent = true;
        contentHtml += `
            <div class="clipboard-content-item">
                <h5>Markdown Content:</h5>
                <pre style="background:#f0f0f0; padding:10px; border-radius:5px; max-height: 200px; overflow-y: auto;">${escapeHtml(clipboardData.text_markdown)}</pre>
                <p style="font-size: 0.8em; color: #666;">(Raw Markdown. Server could convert to HTML if 'markdown' library is installed.)</p>
                <a href="/api/clipboard/download/markdown" class="btn clipboard-action-btn">Download as .md</a>
            </div>
        `;
    } else if (clipboardData.text_markdown_error) {
        hasContent = true;
        contentHtml += `<p style="color:red;">Error accessing Markdown clipboard: ${escapeHtml(clipboardData.text_markdown_error)}</p>`;
    }


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
    } else if (clipboardData.image_svg_base64) {
        hasContent = true;
        contentHtml += `
            <div class="clipboard-content-item">
                <h5>Image Content (SVG):</h5>
                <img src="data:image/svg+xml;base64,${clipboardData.image_svg_base64}" alt="Clipboard SVG Image">
                <p style="font-size: 0.8em; color: #666;">(SVG rendered directly. Note: SVG is not converted to PNG.)</p>
                <a href="/api/clipboard/download/svg" class="btn clipboard-action-btn">Download as .svg</a>
            </div>
        `;
    } else if (clipboardData.image_error) {
        hasContent = true;
        contentHtml += `<p style="color:red;">Error accessing image clipboard: ${escapeHtml(clipboardData.image_error)}</p>`;
    }

    if (!hasContent) {
        contentHtml += '<p>No clipboard content available.</p>';
    }
    clipboardContentDiv.innerHTML = contentHtml;
}

// Utility function to escape HTML for display within <p> tags, etc.
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


// --- Realtime Clipboard Toggle ---
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
        eventSource.close(); // Close existing connection if any
        eventSource = null;
    }
    if ({{ 'true' if REALTIME_CLIPBOARD and SHARE_CLIPBOARD else 'false' }}) { // Only connect if both server-side flags are true
        eventSource = new EventSource('/api/clipboard/stream');
        eventSource.onmessage = function(event) {
            const clipboardData = JSON.parse(event.data);
            updateClipboardContent(clipboardData);
            console.log("Realtime clipboard update received:", clipboardData);
        };
        eventSource.onerror = function(err) {
            console.error('EventSource failed:', err);
            eventSource.close(); // Attempt to reconnect on error
            // Optionally, try to reconnect after a delay
            setTimeout(connectRealtimeClipboard, 3000);
        };
        console.log("Attempting to connect to realtime clipboard stream...");
    } else {
        console.log("Realtime clipboard disabled on server or by user.");
    }
}

if (realtimeClipboardToggle) {
    realtimeClipboardToggle.onclick = () => {
        isRealtimeEnabled = !isRealtimeEnabled; // Toggle state
        updateRealtimeButtonState();
        if (isRealtimeEnabled) {
            // When turning ON, fetch current content immediately and then connect SSE
            fetch('/api/clipboard/refresh')
                .then(response => response.json())
                .then(data => updateClipboardContent(data))
                .catch(error => console.error('Error fetching initial clipboard on realtime enable:', error));
            connectRealtimeClipboard();
        } else {
            // When turning OFF, close SSE connection
            if (eventSource) {
                eventSource.close();
                eventSource = null;
                console.log("Realtime clipboard stream disconnected.");
            }
        }
        // NOTE: This client-side toggle only affects THIS client's behavior.
        // It does NOT change the server's --realtime-clipboard argument.
    };
    updateRealtimeButtonState(); // Set initial button state
    if (isRealtimeEnabled) { // Connect SSE on page load if initially enabled
        connectRealtimeClipboard();
    } else {
        // If realtime is off, ensure current content is loaded (manual refresh on page load)
        fetch('/api/clipboard/refresh')
            .then(response => response.json())
            .then(data => updateClipboardContent(data))
            .catch(error => console.error('Error fetching initial clipboard:', error));
    }
} else {
    // If realtime toggle button is not even rendered (SHARE_CLIPBOARD is false)
    // or if SHARE_CLIPBOARD is true but REALTIME_CLIPBOARD is false from server start,
    // we still need to fetch initial content.
    if ({{ 'true' if SHARE_CLIPBOARD else 'false' }}) {
         fetch('/api/clipboard/refresh')
            .then(response => response.json())
            .then(data => updateClipboardContent(data))
            .catch(error => console.error('Error fetching initial clipboard:', error));
    }
}


// --- Server Connection Status Check ---
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A file server that shares files from a specified directory and optionally clipboard content. by Juitem JoonWoo Kim. juitem@gmail.com")
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
        help="Enable sharing of the server's clipboard content (text and image)."
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
        print("Clipboard sharing is ENABLED (Text, HTML, Markdown, and Images).")
        if REALTIME_CLIPBOARD:
            print(f"Real-time clipboard updates are ENABLED with a polling interval of {POLLING_INTERVAL} seconds.")
            # Start the clipboard polling thread if realtime is enabled
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

    # When running with Flask's default development server (which uses Werkzeug's reloader),
    # the main script is run twice. This can cause the polling thread to start twice.
    # For production, use a proper WSGI server like Gunicorn/Waitress.
    # For development, you might see duplicate log messages from the polling thread.
    app.run(host=args.host, port=args.port, debug=args.debug)