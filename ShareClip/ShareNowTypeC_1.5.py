import os
from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string
from werkzeug.utils import secure_filename
import functools
import logging
import argparse
import pyperclip # For text clipboard access
from PIL import Image # For image processing
import io # For handling in-memory binary data
import base64 # For embedding images in HTML
import pyclip # A more robust clipboard library for various types# Import json for JavaScript string escaping
import json 
# You might also consider 'from urllib.parse import quote' for URL encoding, 
# but for JS strings, 'json.dumps' is generally sufficient and safer.


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
BASE_DIR = None
SHARE_CLIPBOARD = False # New global variable for clipboard sharing

# --- Custom Jinja2 Filter for JavaScript String Escaping ---
# This filter is needed because Jinja2's default 'tojson' might not be enough
# or the original template used a custom filter from another context.
def js_string(value):
    """
    Escapes a string for safe inclusion in JavaScript within an HTML attribute.
    Uses json.dumps to handle quotes, newlines, etc.
    """
    # json.dumps adds quotes, so we need to slice them off, then optionally
    # handle cases where it might break HTML attributes (though less common for simple data).
    # For a robust solution in HTML attributes, also consider HTML escaping the output of json.dumps.
    # However, for direct JS injection within a script tag, json.dumps is perfect.
    # In your case, it's used within an onclick attribute, so a combination might be safer.
    # For now, let's just use json.dumps and remove the outer quotes.
    return json.dumps(value)[1:-1] # Removes the outer quotes added by json.dumps

# Register the custom filter with Jinja2 environment
app.jinja_env.filters['js_string'] = js_string



# Configuration for allowed extensions (optional, but good for security)
# You can customize this list based on what file types you expect
ALLOWED_EXTENSIONS = {'tar','gz','zip','txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'mp3', 'mp4', 'py', 'html', 'css', 'js', 'json', 'xml', 'csv', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

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
    # Normalize the path to remove redundant separators and resolve '..' components
    normalized_path = os.path.normpath(rel_path)
    # Join BASE_DIR with the normalized relative path
    abs_path = os.path.abspath(os.path.join(BASE_DIR, normalized_path))
    
    # Critical security check: Ensure the absolute path starts with BASE_DIR
    # This prevents accessing files outside the designated directory.
    if not abs_path.startswith(BASE_DIR):
        app.logger.warning(f"Attempted directory traversal detected: {rel_path} -> {abs_path}")
        abort(403, description="Access denied: Path outside base directory.")
    
    return abs_path

# --- Clipboard Handling Functions ---
def get_clipboard_content():
    """
    Retrieves clipboard content, attempting various types (image, HTML text, plain text).
    Returns a dictionary with detected types and their content, e.g.,
    {'image_png_base64': '...', 'text_plain': '...', 'text_html': '...'}
    """
    detected_content = {}
    
    try:
        # pyclip.paste(raw=True) returns a dictionary of all MIME type data available in the clipboard.
        # Example: {'image/png': b'...', 'text/plain': b'...', 'text/html': b'...'}
        raw_clipboard_data = pyclip.paste(raw=True)
        app.logger.info(f"Raw clipboard data types available: {list(raw_clipboard_data.keys())}")

        # 1. Process image data (higher priority)
        if 'image/png' in raw_clipboard_data:
            img_bytes = raw_clipboard_data['image/png']
            try:
                # Validate if it's a valid PNG using PIL
                img = Image.open(io.BytesIO(img_bytes))
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG') 
                base64_img = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                detected_content['image_png_base64'] = base64_img
                app.logger.info("Clipboard content: PNG Image detected and processed.")
            except Exception as e:
                app.logger.warning(f"Failed to process 'image/png' from clipboard: {e}")

        elif 'image/jpeg' in raw_clipboard_data: # Also try JPEG
            img_bytes = raw_clipboard_data['image/jpeg']
            try:
                img = Image.open(io.BytesIO(img_bytes))
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG') # Convert to PNG for consistency
                base64_img = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                detected_content['image_png_base64'] = base64_img
                app.logger.info("Clipboard content: JPEG Image detected and processed (converted to PNG).")
            except Exception as e:
                app.logger.warning(f"Failed to process 'image/jpeg' from clipboard: {e}")
        
        # 2. Process HTML text
        if 'text/html' in raw_clipboard_data:
            html_bytes = raw_clipboard_data['text/html']
            try:
                html_text = html_bytes.decode('utf-8')
                detected_content['text_html'] = html_text
                app.logger.info("Clipboard content: HTML text detected and processed.")
            except UnicodeDecodeError:
                app.logger.warning("Clipboard content: 'text/html' could not be decoded as UTF-8.")

        # 3. Process plain text (most common)
        if 'text/plain' in raw_clipboard_data:
            plain_bytes = raw_clipboard_data['text/plain']
            try:
                plain_text = plain_bytes.decode('utf-8')
                detected_content['text_plain'] = plain_text
                app.logger.info("Clipboard content: Plain text detected and processed.")
            except UnicodeDecodeError:
                app.logger.warning("Clipboard content: 'text/plain' could not be decoded as UTF-8.")
        
        # If pyclip did not return any data at all
        if not detected_content and not raw_clipboard_data:
            app.logger.info("pyclip.paste(raw=True) returned no data. Falling back to pyperclip for plain text.")

    except Exception as e:
        app.logger.warning(f"Error accessing clipboard with pyclip.paste(raw=True): {e}. Falling back to pyperclip for plain text.")
        
    # Attempt pyperclip if nothing was detected by pyclip or an error occurred
    if not detected_content:
        try:
            text_content = pyperclip.paste()
            if text_content:
                detected_content['text_plain'] = text_content
                app.logger.info("Clipboard content: Text (from pyperclip) detected as fallback.")
        except pyperclip.PyperclipException as e:
            app.logger.error(f"Error pasting text from clipboard with pyperclip: {e}")
        
    return detected_content


# You can uncomment and use this basic authentication decorator if needed.
# For production, consider Flask-HTTPAuth or a more robust authentication system.
# from flask_httpauth import HTTPBasicAuth
# auth = HTTPBasicAuth()

# @auth.verify_password
# def verify_password(username, password):
#     # In a real application, retrieve credentials from a secure store (e.g., database, environment variables)
#     # and use hashed passwords (e.g., bcrypt).
#     users = {"admin": "pass"} # !!! DANGER: Hardcoded password, not for production !!!
#     if username in users and users[username] == password:
#         return username
#     return None

# def login_required(f):
#     @functools.wraps(f)
#     def decorated_function(*args, **kwargs):
#         if not auth.current_user():
#             return auth.authenticate_header()
#         return f(*args, **kwargs)
#     return decorated_function


@app.route('/')
# @login_required # Uncomment to enable authentication for the main page
def index():
    # return render_template_string(TEMPLATE)
    # clipboard_data 변수를 항상 초기화하고 전달하도록 수정
    clipboard_data_to_pass = {'type': None, 'content': None} 
    
    if SHARE_CLIPBOARD:
        clip_type, clip_content = get_clipboard_content()
        clipboard_data_to_pass['type'] = clip_type
        clipboard_data_to_pass['content'] = clip_content
    
    # 항상 clipboard_data_to_pass를 템플릿으로 전달
    return render_template_string(TEMPLATE, clipboard_data=clipboard_data_to_pass)

@app.route('/api/list', methods=['GET'])
# @login_required # Uncomment to enable authentication for API list
def api_list_dir():
    """
    Lists the contents of a directory.
    """
    rel = request.args.get('path', '')
    abs_dir = safe_path(rel)
    
    if not os.path.isdir(abs_dir):
        app.logger.info(f"Requested path is not a directory or does not exist: {abs_dir}")
        return jsonify(error="Not a directory or does not exist", path=rel), 400
    
    # Check if the directory is readable
    if not os.access(abs_dir, os.R_OK):
        app.logger.warning(f"Permission denied to read directory: {abs_dir}")
        return jsonify(error="Permission denied: Cannot read directory"), 403

    dirs, files = [], []
    try:
        # Sort items case-insensitively for better UX
        for name in sorted(os.listdir(abs_dir), key=lambda x: x.lower()):
            full = os.path.join(abs_dir, name)
            # Optionally skip hidden files/directories (those starting with '.')
            # if not name.startswith('.'):
            item = {'name': name, 'is_dir': os.path.isdir(full)}
            (dirs if item['is_dir'] else files).append(item)
    except OSError as e:
        app.logger.error(f"Server error listing directory {abs_dir}: {e}")
        return jsonify(error="Server error: Could not list directory contents"), 500
    
    parent = os.path.dirname(rel) if rel else None
    if parent == "": parent = None # Ensure parent is None for the root directory itself
    
    return jsonify({'cwd': rel, 'items': dirs + files, 'parent': parent})

@app.route('/api/upload', methods=['POST'])
# @login_required # Uncomment to enable authentication for upload
def api_upload():
    """
    Handles file and directory uploads.
    """
    rel = request.form.get('dir', '')
    abs_dir = safe_path(rel)
    
    if not os.path.isdir(abs_dir):
        app.logger.info(f"Upload target is not a directory or does not exist: {abs_dir}")
        return jsonify(error="Invalid target directory or does not exist"), 400
    
    # Ensure directory is writable before processing files
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
        # Check if a filename is provided.
        # For directory uploads, f.filename can contain paths like "subdir/file.txt"
        if f.filename == '':
            errors.append(f"Skipping file with no filename (empty filename).")
            continue
            
        # Werkzeug's secure_filename cleans the filename to prevent path traversal attempts
        # and ensure it's safe for the underlying OS.
        # It removes path components (like / or \) and invalid characters.
        # For directory uploads, the client-side sends webkitRelativePath as f.filename,
        # so we need to rebuild the directory structure based on that.
        
        # Determine the full path relative to the target directory.
        # f.filename already contains the webkitRelativePath for directory uploads
        # (e.g., "myfolder/mysubfolder/file.txt").
        # secure_filename will flatten this, so we need to manually join it to keep structure.
        
        # First, sanitize each component of the path given by f.filename
        path_components = f.filename.split(os.path.sep)
        sanitized_components = [secure_filename(comp) for comp in path_components if comp]
        
        # Reconstruct the safe relative path.
        # If any component was empty after sanitization (e.g., "."), skip it.
        if not sanitized_components:
            errors.append(f"Skipping file due to invalid or empty path after sanitization: {f.filename}")
            continue
            
        # Rejoin components to form the relative path within the target upload directory
        # This preserves the directory structure from webkitdirectory uploads
        final_relative_path = os.path.join(*sanitized_components)
        
        # Construct the absolute path where the file will be saved
        final_save_path = os.path.join(abs_dir, final_relative_path)

        # Allow all extensions, for now
        # Check for allowed file extension (optional, but recommended)
        # if '.' in final_save_path and not allowed_file(final_save_path):
        #      errors.append(f"File '{f.filename}' has an disallowed extension. Skipping.")
        #      app.logger.warning(f"Upload attempt with disallowed extension: {final_save_path}")
        #      continue

        try:
            # Ensure the directory structure exists for nested uploads (e.g., for 'myfolder/mysubfolder/file.txt')
            os.makedirs(os.path.dirname(final_save_path), exist_ok=True)
            f.save(final_save_path)
            uploaded_count += 1
            app.logger.info(f"Successfully uploaded: {final_save_path}")
        except Exception as e:
            errors.append(f"Failed to upload {f.filename}: {e}")
            app.logger.error(f"Error saving file {final_save_path}: {e}")

    if errors:
        # If there were any errors, return a 500 status but also indicate partial success.
        status_code = 500 if uploaded_count == 0 else 200 # If some uploaded, it's technically success with warnings
        return jsonify(success=False, uploaded_count=uploaded_count, errors=errors, message="Some files failed to upload."), status_code
    
    return jsonify(success=True, uploaded_count=uploaded_count)

@app.route('/api/download', methods=['GET'])
# @login_required # Uncomment to enable authentication for download
def api_download():
    """
    Handles file downloads.
    """
    rel = request.args.get('path', '')
    abs_file = safe_path(rel)
    
    if not os.path.isfile(abs_file):
        app.logger.info(f"Requested path for download is not a file or does not exist: {abs_file}")
        abort(404, description="File not found or is a directory.")
    
    # Check read permissions before sending the file
    if not os.access(abs_file, os.R_OK):
        app.logger.warning(f"Permission denied to read file: {abs_file}")
        abort(403, description="Permission denied: Cannot read file.")

    dirn = os.path.dirname(abs_file)
    fname = os.path.basename(abs_file)
    
    # send_from_directory is secure when `directory` (dirn) is properly controlled,
    # and `filename` (fname) does not contain path separators.
    # Our `safe_path` ensures `abs_file` is within `BASE_DIR`, and then `os.path.dirname/basename`
    # correctly separates the directory and filename, making `send_from_directory` safe here.
    return send_from_directory(dirn, fname, as_attachment=True, mimetype='application/octet-stream')

@app.route('/api/clipboard/download/<file_type>', methods=['GET'])
def api_clipboard_download(file_type):
    """
    Provides clipboard content as a downloadable file.
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
    elif file_type == 'image_png' and 'image_png_base64' in clipboard_data:
        try:
            img_bytes = base64.b64decode(clipboard_data['image_png_base64'])
            return app.response_class(
                img_bytes,
                mimetype='image/png',
                headers={'Content-Disposition': 'attachment;filename=clipboard_image.png'}
            )
        except Exception as e:
            app.logger.error(f"Error decoding base64 image for download: {e}")
            abort(500, description="Error processing clipboard image.")
    else:
        abort(404, description=f"Clipboard content not available in requested format: {file_type}.")

@app.route('/api/ping')
def ping():
    """
    Simple endpoint to check server health.
    """
    return jsonify(ok=True)


TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ShareNow Type-C (with Clipboard)</title>
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
    gap: 10px; flex-wrap: wrap; /* Allow wrapping on small screens */
}
#topbtn, #upbtn {
    border: none; background:#def; color:#0561a9;
    font-size:15px; border-radius:5px; padding:4px 12px;
    cursor: pointer; transition:.15s ease-in-out;
}
#topbtn:hover, #upbtn:hover { background: #cbeafd;}
#curpath {
    font-weight:500; color:#0a2754;
    flex-grow: 1; /* Allow it to take available space */
    word-break: break-all; /* Break long paths */
}
ul#listing {
    border:1px solid #e4eaf2; border-radius:8px; padding:0 12px; background:#fafdff;
    margin:0 0 8px 0; min-height:40px; list-style: none; /* Remove default list style */
}
li {
    display:flex; align-items:center; gap:12px;
    border-bottom:1px solid #edf1f6; height:36px; font-size:16px;
    padding-left: 5px; /* Add some padding for alignment */
}
li.folder { font-weight:bold; color:#1461b0; cursor:pointer;}
li:last-child { border-bottom:none;}
li a {
    text-decoration:none; color:#384c66; transition:.1s ease-in-out;
    display: flex; align-items: center; gap: 12px;
    flex-grow: 1; /* Make anchor fill space for better click target */
}
li a:hover {color:#217cee;}
.section { margin: 32px 0 0 0; padding-top: 15px; border-top: 1px dashed #e4eaf2;}
.section:first-of-type { border-top: none; padding-top: 0; margin-top: 0;}
.form-row { display:flex; align-items:center; gap:10px; margin-top:8px; flex-wrap: wrap;}
input[type="file"] {
    border: 1px solid #c3d0e5; border-radius:6px; background:#fcfdff; font-size:15px;
    padding: 6px; /* Add padding for better appearance */
    flex-grow: 1; /* Allow input to fill available space */
    min-width: 180px; /* Ensure it doesn't get too small */
}
button[type="button"], .btn {
    border:none; color:#fff; background:#407bcd; border-radius:5px;
    padding:7px 16px; font-size:15px; cursor:pointer; transition: .13s ease-in-out;
    white-space: nowrap; /* Prevent button text from wrapping */
}
button[type="button"]:hover, .btn:hover { background:#265fa3;}
.progress-span {
    height:18px; display:inline-block; color:#16622f; min-width:52px; margin-left:8px;
    font-size: 14px; /* Adjust font size */
}
/* New styles for better feedback */
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
#clipboard-content {
    background: #ffffff;
    border: 1px solid #d0e0f0;
    border-radius: 5px;
    padding: 10px;
    margin-top: 10px;
    min-height: 40px;
    overflow-x: auto; /* For long text or wide images */
    word-break: break-all; /* Ensure long text breaks */
}
#clipboard-content img {
    max-width: 100%; /* Ensure images fit within the container */
    height: auto;
    display: block; /* Remove extra space below image */
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
    <h2>ShareNow - Type C + ClipBoard v1.5</h2>
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
        <h4>Shared Clipboard Content (from Server)</h4>
        <div id="clipboard-content">
            {% if clipboard_data %} 
                {% if clipboard_data.image_png_base64 %}
                    <div class="clipboard-content-item">
                        <h5>Image Content:</h5>
                        <img src="data:image/png;base64,{{ clipboard_data.image_png_base64 }}" alt="Clipboard Image">
                        <a href="/api/clipboard/download/image_png" class="btn clipboard-action-btn">Download as .png</a>
                    </div>
                {% endif %}
                
                {% if clipboard_data.text_html %}
                    <div class="clipboard-content-item">
                        <h5>HTML Content:</h5>
                        <div style="border:1px solid #ddd; padding:10px; background:#f9f9f9; max-height:200px; overflow-y:auto;">
                            {{ clipboard_data.text_html | safe }} 
                        </div>
                        <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('{{ clipboard_data.text_html | js_string }}')">Copy HTML to My Clipboard</button>
                        <a href="/api/clipboard/download/html" class="btn clipboard-action-btn">Download as .html</a>
                    </div>
                {% endif %}

                {% if clipboard_data.text_plain %}
                    <div class="clipboard-content-item">
                        <h5>Plain Text Content:</h5>
                        <p>{{ clipboard_data.text_plain | e }}</p> 
                        <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('{{ clipboard_data.text_plain | js_string }}')">Copy Text to My Clipboard</button>
                        <a href="/api/clipboard/download/text" class="btn clipboard-action-btn">Download as .txt</a>
                    </div>
                {% endif %}

                {% if not clipboard_data.image_png_base64 and not clipboard_data.text_html and not clipboard_data.text_plain %}
                    <p>No recognizable clipboard content available.</p>
                {% endif %}

            {% else %}
                <p>Clipboard sharing is currently disabled or no content is available.</p> 
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

// Clear inputs and reset progress messages when selecting new files
fileInput.onchange = e => { 
    fileFiles = [...e.target.files]; 
    fileUploadProgress.innerText = ''; 
    fileUploadProgress.className = 'progress-span'; // Reset class
};
dirInput.onchange  = e => { 
    dirFiles  = [...e.target.files]; 
    dirUploadProgress.innerText = ''; 
    dirUploadProgress.className = 'progress-span'; // Reset class
};

function fetchList(path='') {
    fetch('/api/list?path='+encodeURIComponent(path))
    .then(resp => {
        if (!resp.ok) { // Handle HTTP errors like 400, 403, 404, 500
            // Attempt to parse JSON error message from server
            return resp.json().then(errorData => {
                const errorMessage = errorData.error || resp.statusText;
                if (resp.status === 403) {
                    alert('Permission denied to access this directory: ' + errorMessage);
                } else if (resp.status === 400) {
                    alert('Invalid directory path: ' + errorMessage);
                } else {
                    alert('Error fetching directory listing (' + resp.status + '): ' + errorMessage);
                }
                // If current path exists, try to navigate back on error, otherwise go to root
                if (curPath && path !== curPath) { // Avoid infinite loop if currentPath itself is problematic
                     // A simple way to go up a level in the client-side
                     const pathParts = curPath.split('/');
                     if (pathParts.length > 1) {
                         fetchList(pathParts.slice(0, -1).join('/'));
                     } else { // Already at a top level below root
                         fetchList('');
                     }
                } else if (curPath && path === curPath) { // If the current path is problematic, try root
                    fetchList('');
                } else { // Already at root, just alert
                    console.error('Failed to fetch list at root or cannot recover:', errorData);
                }
                return Promise.reject('Failed to fetch list: ' + errorMessage); // Stop processing
            }).catch(() => {
                // Fallback for non-JSON or unreadable error responses
                alert('Error fetching directory listing: ' + resp.statusText + '. Please check server logs.');
                return Promise.reject('Failed to fetch list: Non-JSON error');
            });
        }
        return resp.json();
    })
    .then(data => {
        curPath = data.cwd || '';
        curPathSpan.innerText = 'Current Directory: /' + (curPath || '');
        
        // Top button: always navigate to the base directory (empty path)
        topBtn.onclick = () => fetchList('');
        
        // Up button: show if a parent directory exists (data.parent is not null)
        if (data.parent !== null) { 
            upBtn.style.display = 'inline-block';
            upBtn.onclick = () => fetchList(data.parent);
        } else {
            upBtn.style.display = 'none';
        }
        
        listing.innerHTML = ''; // Clear current listing
        
        // Display message if the directory is empty
        if (data.items.length === 0) {
            let li = document.createElement('li');
            li.innerText = 'This directory is empty.';
            li.style.color = '#777';
            listing.appendChild(li);
        }

        // Populate the file/folder listing
        data.items.forEach(item => {
            let li = document.createElement('li');
            if(item.is_dir){
                li.innerHTML = '📁 ' + item.name; // Use innerHTML to parse emoji
                li.className = 'folder';
                // Construct the path for navigating into a subdirectory
                li.onclick = () => fetchList((curPath ? curPath + '/' : '') + item.name);
            }else{
                let a = document.createElement('a');
                // Construct the download URL
                a.href = '/api/download?path=' + encodeURIComponent((curPath ? curPath + '/' : '') + item.name);
                a.innerHTML = '📄 ' + item.name; // Use innerHTML for emoji
                a.setAttribute('download', item.name); // Suggests filename for download
                li.appendChild(a);
            }
            listing.appendChild(li);
        });
    })
    .catch(error => {
        console.error('Error in fetchList (caught after response handling):', error);
        // The user should have already been alerted by the .then(resp => ...) block
    });
}
fetchList(); // Initial call to list the root directory

/**
 * Handles the upload process for files or directories.
 * @param {File[]} files - An array of File objects to upload.
 * @param {HTMLElement} progressSpan - The DOM element to display upload progress.
 * @param {boolean} isDirectoryUpload - True if it's a directory upload (uses webkitRelativePath).
 */
function uploadFiles(files, progressSpan, isDirectoryUpload = false) {
    if (files.length === 0) {
        alert(isDirectoryUpload ? 'Please select a directory to upload!' : 'Please select files to upload!');
        return;
    }
    
    let fd = new FormData();
    files.forEach(f => {
        // For directory uploads, f.webkitRelativePath contains the full path including subdirs
        // For single files, f.name is sufficient.
        // The server-side will use this `filename` argument to reconstruct the path.
        const fileNameToUse = isDirectoryUpload && f.webkitRelativePath ? f.webkitRelativePath : f.name;
        fd.append('files[]', f, fileNameToUse);
    });
    fd.append('dir', curPath); // Send the current directory as the target upload location
    
    progressSpan.innerText = '0%';
    progressSpan.className = 'progress-span'; // Reset class for new upload
    
    let xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    
    // Update progress bar
    xhr.upload.onprogress = e => {
        let percent = e.lengthComputable ? (e.loaded / e.total * 100) : 0;
        progressSpan.innerText = Math.round(percent) + '%';
    };
    
    // Handle upload completion (success or failure)
    xhr.onload = () => {
        if (xhr.status === 200) {
            progressSpan.innerText = 'Success!';
            progressSpan.classList.add('success');
            // Clear input after successful upload
            if (isDirectoryUpload) dirInput.value = '';
            else fileInput.value = '';
            // Reset files array
            if (isDirectoryUpload) dirFiles = [];
            else fileFiles = [];
            fetchList(curPath); // Refresh listing to show new files
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
    
    // Handle network errors during upload
    xhr.onerror = () => {
        progressSpan.innerText = 'Error!';
        progressSpan.classList.add('error');
        alert('Network error during upload. Please check your connection.');
    };
    
    xhr.send(fd); // Send the FormData
}

// Attach event listeners to upload buttons
uploadFileBtn.onclick = () => uploadFiles(fileFiles, fileUploadProgress, false);
uploadDirBtn.onclick = () => uploadFiles(dirFiles, dirUploadProgress, true);

// Function to copy text to client's clipboard
function copyToClientClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => {
                alert('Text copied to your clipboard!');
            })
            .catch(err => {
                console.error('Could not copy text: ', err);
                alert('Failed to copy text to clipboard. Please copy manually or check browser permissions.');
            });
    } else {
        alert('Your browser does not support automatic clipboard writing. Please copy the text manually.');
    }
}

// Check Server Connection periodically
function checkServer() {
    fetch("/api/ping").then(r=>{
        if(r.ok) {
            connStatus.style.display = 'none'; // Server is responsive
        } else {
            connStatus.style.display = 'block'; // Server is not responsive (HTTP error)
        }
    }).catch(()=>{
        connStatus.style.display = 'block'; // Network error (server unreachable)
    });
}
setInterval(checkServer, 5000); // Check every 5 seconds
checkServer(); // Initial check on page load
</script>
</body>
</html>
"""
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A simple Flask file server that shares files from a specified directory.")
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
        help="The host address to bind the server to. Use '0.0.0.0' for external access. Defaults to '127.0.0.1'."
    )
    parser.add_argument(
        '--share-clipboard', # New argument for clipboard sharing
        action='store_true', 
        help="Enable sharing of the server's clipboard content (text and image)."
    )
    parser.add_argument(
        '--debug', 
        action='store_true', # When --debug is present, it's True
        help="Enable debug mode (DO NOT USE IN PRODUCTION)."
    )

    args = parser.parse_args()

    # Set BASE_DIR from the parsed argument
    # Normalize and make absolute to ensure consistency
    BASE_DIR = os.path.abspath(args.dir)
#    global SHARE_CLIPBOARD # Declare SHARE_CLIPBOARD as global to modify it
    SHARE_CLIPBOARD = args.share_clipboard

    # Validate if the provided directory exists and is a directory
    if not os.path.isdir(BASE_DIR):
        print(f"Error: The specified directory '{args.dir}' does not exist or is not a valid directory.")
        exit(1) # Exit the program if the directory is invalid

    print(f"Serving files from: {BASE_DIR}")
    print(f"Server running on {args.host}:{args.port}")
    if SHARE_CLIPBOARD:
        print("Clipboard sharing is ENABLED.")
    else:
        print("Clipboard sharing is DISABLED.")
    
    if args.debug:
        print("!!! DEBUG MODE IS ENABLED. DO NOT USE IN PRODUCTION. !!!")

    app.run(host=args.host, port=args.port, debug=args.debug)