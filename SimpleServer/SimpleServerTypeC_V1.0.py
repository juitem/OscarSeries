import os
from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string

app = Flask(__name__)
BASE_DIR = os.getcwd()

def safe_path(rel_path):
    abs_path = os.path.abspath(os.path.join(BASE_DIR, rel_path))
    if not abs_path.startswith(BASE_DIR):
        abort(403)
    return abs_path

@app.route('/')
def index():
    return render_template_string(TEMPLATE)

@app.route('/api/list', methods=['GET'])
def api_list_dir():
    rel = request.args.get('path', '')
    abs_dir = safe_path(rel)
    if not os.path.isdir(abs_dir):
        return jsonify(error="Not a directory"), 400
    dirs, files = [], []
    for name in sorted(os.listdir(abs_dir)):
        full = os.path.join(abs_dir, name)
        item = {'name': name, 'is_dir': os.path.isdir(full)}
        (dirs if item['is_dir'] else files).append(item)
    parent = os.path.dirname(rel) if rel else None
    if parent == "": parent = None
    return jsonify({'cwd': rel, 'items': dirs + files, 'parent': parent})

@app.route('/api/upload', methods=['POST'])
def api_upload():
    rel = request.form.get('dir', '')
    abs_dir = safe_path(rel)
    if not os.path.isdir(abs_dir):
        return jsonify(error="Invalid target dir"), 400
    files = request.files.getlist('files[]')
    for f in files:
        # webkitRelativePath 지원 (폴더 업로드), 없으면 f.filename
        save_path = os.path.join(abs_dir, f.filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        f.save(save_path)
    return jsonify(success=True)

@app.route('/api/download', methods=['GET'])
def api_download():
    rel = request.args.get('path', '')
    abs_file = safe_path(rel)
    if not os.path.isfile(abs_file):
        abort(404)
    dirn = os.path.dirname(abs_file)
    fname = os.path.basename(abs_file)
    return send_from_directory(dirn, fname, as_attachment=True)

@app.route('/api/ping')
def ping():
    return jsonify(ok=True)

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Simple File Server Type-C</title>
<style>
body {
    font-family: 'Segoe UI', 'Arial', sans-serif; margin:0; background:#f8fafc;
}
#conn_status {
    display:none; background:#d32f2f; color:#fff;
    padding:10px;text-align:center;font-weight:bold;position:fixed;top:0;left:0;right:0;z-index:999;
}
#container {
    max-width: 900px; margin: 72px auto 0 auto; background: #fff;
    border-radius:12px; box-shadow:0 2px 12px #aaa3;
    padding:32px 32px 32px 32px;
}
h2 { margin-bottom:15px; color:#08488d;}
#pathbar {
    margin-bottom:20px; display:flex; align-items: center;
    gap: 10px;
}
#topbtn, #upbtn {
    border: none; background:#def; color:#0561a9;
    font-size:15px; border-radius:5px; padding:4px 12px;
    cursor: pointer; transition:.15s;
}
#topbtn:hover, #upbtn:hover { background: #cbeafd;}
#curpath { font-weight:500; color:#0a2754;}
ul#listing {
    border:1px solid #e4eaf2; border-radius:8px; padding:0 12px; background:#fafdff;
    margin:0 0 8px 0; min-height:40px;
}
li {
    display:flex; align-items:center; gap:12px;
    border-bottom:1px solid #edf1f6; height:36px; font-size:16px;
}
li.folder { font-weight:bold; color:#1461b0; cursor:pointer;}
li:last-child { border-bottom:none;}
li a {text-decoration:none; color:#384c66; transition:.1s;}
li a:hover {color:#217cee;}
.section { margin: 32px 0 0 0;}
.form-row { display:flex; align-items:center; gap:10px; margin-top:4px;}
input[type="file"] {
    border: 1px solid #c3d0e5; border-radius:6px; background:#fcfdff; font-size:15px;
}
button[type="button"], .btn {
    border:none; color:#fff; background:#407bcd; border-radius:5px;
    padding:7px 16px; font-size:15px; cursor:pointer; transition: .13s;
}
button[type="button"]:hover, .btn:hover { background:#265fa3;}
.progress-span { height:18px; display:inline-block; color:#16622f; min-width:52px; margin-left:8px;}
@media (max-width:650px) {
    #container { padding:12px; }
    h2 { font-size:19px;}
    li { font-size:14px;}
    .section { margin:18px 0 0 0;}
}
</style>
</head>
<body>
<div id="conn_status">SERVER CONNECTION LOST</div>
<div id="container">
    <h2>SimpleShare - Type C v1.0</h2>
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
            <button id="uploadFileBtn" type="button" class="btn">Upload</button>
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

fileInput.onchange = e => { fileFiles = [...e.target.files]; };
dirInput.onchange  = e => { dirFiles  = [...e.target.files]; };

function fetchList(path='') {
    fetch('/api/list?path='+encodeURIComponent(path))
    .then(resp=>resp.json())
    .then(data => {
        curPath = data.cwd || '';
        curPathSpan.innerText = 'Current Directory: /' + (curPath || '');
        // Top : always BASE_DIR("")
        topBtn.onclick = () => fetchList('');
        // Up : parent exists
        if (data.parent) {
            upBtn.style.display = 'inline-block';
            upBtn.onclick = () => fetchList(data.parent);
        } else {
            upBtn.style.display = 'none';
        }
        // Forder first. driven by server
        listing.innerHTML = '';
        data.items.forEach(item => {
            let li = document.createElement('li');
            if(item.is_dir){
                li.innerText = '📁 ' + item.name;
                li.className = 'folder';
                li.onclick = () => fetchList((curPath ? curPath + '/' : '') + item.name);
            }else{
                let a = document.createElement('a');
                a.href = '/api/download?path=' + encodeURIComponent((curPath ? curPath + '/' : '') + item.name);
                a.innerText = '📄 ' + item.name;
                a.setAttribute('download', item.name);
                li.appendChild(a);
            }
            listing.appendChild(li);
        });
    });
}
fetchList();

uploadFileBtn.onclick = () => {
    if (fileFiles.length === 0) { alert('Select files to upload!'); return; }
    let fd = new FormData();
    fileFiles.forEach(f => fd.append('files[]', f, f.name));
    fd.append('dir', curPath);
    fileUploadProgress.innerText = '';
    let xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.upload.onprogress = e => {
        let percent = e.lengthComputable ? (e.loaded / e.total * 100) : 0;
        fileUploadProgress.innerText = Math.round(percent) + '%';
    };
    xhr.onload = () => {
        if(xhr.status === 200){
            fileUploadProgress.innerText = 'Success!';
            fileInput.value = '';
            fileFiles = [];
            fetchList(curPath);
        }else{
            fileUploadProgress.innerText = 'Failed!';
        }
    };
    xhr.onerror = () => fileUploadProgress.innerText = 'Error!';
    xhr.send(fd);
};

uploadDirBtn.onclick = () => {
    if(dirFiles.length === 0) { alert('Select a directory!'); return;}
    let fd = new FormData();
    dirFiles.forEach(f => {
        // 구조 보존(webkitRelativePath 활용)
        if(f.webkitRelativePath) fd.append('files[]', f, f.webkitRelativePath);
        else fd.append('files[]', f, f.name);
    });
    fd.append('dir', curPath);
    dirUploadProgress.innerText = '';
    let xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.upload.onprogress = e => {
        let percent = e.lengthComputable ? (e.loaded / e.total * 100) : 0;
        dirUploadProgress.innerText = Math.round(percent) + '%';
    };
    xhr.onload = () => {
        if(xhr.status === 200){
            dirUploadProgress.innerText = 'Success!';
            dirInput.value = '';
            dirFiles = [];
            fetchList(curPath);
        }else{
            dirUploadProgress.innerText = 'Failed!';
        }
    };
    xhr.onerror = () => dirUploadProgress.innerText = 'Error!';
    xhr.send(fd);
};

// Check Server Connection
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
    app.run(port=8000, debug=True)
