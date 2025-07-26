import os
from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string
from werkzeug.utils import secure_filename
import functools
import logging
import argparse
import pyperclip # We rely on pyperclip for clipboard operations
import json # Used for custom Jinja2 filter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
BASE_DIR = None
SHARE_CLIPBOARD = False 

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

# --- Clipboard Handling Functions (Simplified for text only) ---
def get_clipboard_content():
    """
    Retrieves plain text clipboard content using pyperclip.
    Returns a dictionary with 'text_plain' if content is found.
    """
    detected_content = {}
    try:
        text_content = pyperclip.paste()
        if text_content:
            detected_content['text_plain'] = text_content
            app.logger.info("Clipboard content: Plain text (from pyperclip) detected.")
        else:
            app.logger.info("Clipboard is empty or contains no plain text.")
    except pyperclip.PyperclipException as e:
        app.logger.error(f"Error pasting text from clipboard with pyperclip: {e}")
        # Log the error but don't re-raise, to allow the server to continue
        detected_content['error'] = f"Clipboard access failed: {e}"
        
    return detected_content


@app.route('/')
def index():
    # Initialize clipboard_data as an empty dictionary.
    # get_clipboard_content() now returns a single dictionary, so no unpacking needed.
    clipboard_data = {} 
    
    if SHARE_CLIPBOARD:
        # CORRECTED LINE for ValueError: not enough values to unpack
        clipboard_data = get_clipboard_content() 
    
    return render_template_string(TEMPLATE, clipboard_data=clipboard_data)

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

# This endpoint is modified to only handle plain text download
@app.route('/api/clipboard/download/<file_type>', methods=['GET'])
def api_clipboard_download(file_type):
    """
    Provides clipboard content as a downloadable file (text only).
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
    else:
        # If any other file_type is requested or text_plain is not available
        abort(404, description=f"Clipboard content not available in requested format: {file_type}. Only plain text is supported.")

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
<title>Simple File Server Type-C (Text Clipboard)</title>
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
li {
    display:flex; align-items:center; gap:12px;
    border-bottom:1px solid #edf1f6; height:36px; font-size:16px;
    padding-left: 5px; 
}
li.folder { font-weight:bold; color:#1461b0; cursor:pointer;}
li:last-child { border-bottom:none;}
li a {
    text-decoration:none; color:#384c66; transition:.1s ease-in-out;
    display: flex; align-items: center; gap: 12px;
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
#clipboard-content img { /* This style remains but images won't be displayed from server clipboard in this version */
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
    <h2>ShareNow - Type C v1.4 (Text Clipboard Only)</h2>
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
                {# Removed image_png_base64 and text_html sections as we're text-only now #}
                
                {% if clipboard_data.text_plain %}
                    <div class="clipboard-content-item">
                        <h5>Plain Text Content:</h5>
                        <p>{{ clipboard_data.text_plain | e }}</p> 
                        <button type="button" class="btn clipboard-action-btn" onclick="copyToClientClipboard('{{ clipboard_data.text_plain | js_string }}')">Copy Text to My Clipboard</button>
                        <a href="/api/clipboard/download/text" class="btn clipboard-action-btn">Download as .txt</a>
                    </div>
                {% elif clipboard_data.error %}
                    <p style="color:red;">Error accessing clipboard: {{ clipboard_data.error }}</p>
                {% else %}
                    <p>No plain text clipboard content available.</p>
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
const uploadDirBtn    = document.getElementById('uploadDirBtn'); // Corrected ID here: 'uploadDirBtn'
const fileUploadProgress = document.getElementById('fileUploadProgress');
const dirUploadProgress  = document.getElementById('dirUploadProgress');

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
                li.innerHTML = '📁 ' + item.name; 
                li.className = 'folder';
                li.onclick = () => fetchList((curPath ? curPath + '/' : '') + item.name);
            }else{
                let a = document.createElement('a');
                a.href = '/api/download?path=' + encodeURIComponent((curPath ? curPath + '/' : '') + item.name);
                a.innerHTML = '📄 ' + item.name; 
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

function checkServer() {
    fetch("/api/ping").then(r=>{
        if(r.ok) {
            connStatus.style.display = 'none'; 
        } else {
            connStatus.style.display = 'block'; 
        }
    }).catch(()=>{
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
        default='0.0.0.0', # Changed default host to '0.0.0.0' for external access
        help="The host address to bind the server to. Use '0.0.0.0' for external access. Defaults to '0.0.0.0'."
    )
    parser.add_argument(
        '--share-clipboard', 
        action='store_true', 
        help="Enable sharing of the server's clipboard content (text only)."
    )
    parser.add_argument(
        '--debug', 
        action='store_true', 
        help="Enable debug mode (DO NOT USE IN PRODUCTION)."
    )

    args = parser.parse_args()

    BASE_DIR = os.path.abspath(args.dir)
    SHARE_CLIPBOARD = args.share_clipboard 

    if not os.path.isdir(BASE_DIR):
        print(f"Error: The specified directory '{args.dir}' does not exist or is not a valid directory.")
        exit(1)

    print(f"Serving files from: {BASE_DIR}")
    print(f"Server running on {args.host}:{args.port}")
    if SHARE_CLIPBOARD:
        print("Clipboard sharing is ENABLED (Text only).")
    else:
        print("Clipboard sharing is DISABLED.")
    
    if args.debug:
        print("!!! DEBUG MODE IS ENABLED. DO NOT USE IN PRODUCTION. !!!")

    app.run(host=args.host, port=args.port, debug=args.debug)