import sys
import os
import argparse
import shutil
from flask import (
    Flask, request, send_from_directory, render_template_string,
    jsonify, session, redirect, url_for
)
import werkzeug

parser = argparse.ArgumentParser()
parser.add_argument("base_dir", nargs="?", default=".")
parser.add_argument("--password", help="Set access password")
parser.add_argument("-p", "--port", type=int, default=8000)
args = parser.parse_args()

BASE_DIR = os.path.abspath(args.base_dir)
PASSWORD = args.password

app = Flask(__name__)
app.secret_key = os.urandom(16)

TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Flask File Browser</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    ul { list-style-type: none; padding-left: 0; }
    li { margin: 5px 0; }
    #progressWrapper { display: none; margin-top: 10px; }
    #progressBar { width: 100%%; height: 16px; }
    #statusText { margin-left: 10px; }
    #resultMessage { margin-top: 10px; color: green; }
    .file-actions button { margin-left: 8px; }
    #dropzone {
      border: 2px dashed #888; padding: 20px; text-align: center;
      color: #666; margin-top: 15px; background: #fafafa }
    #dropzone.dragover { border-color: #2a7; background: #e0ffe0; }
    .folder-actions button { margin-left: 8px; }
    #folderCreate { margin-top: 15px; }
  </style>
</head>
<body>
  <h2>Directory: {{ relpath or '.' }}</h2>
  <ul>
    {% if relpath %}
      <li><a href="{{ url_for('browse', req_path=parentpath) }}">[.. Up one level]</a></li>
    {% endif %}
    {% for name, is_dir in items %}
      <li>
        {% if is_dir %}
          <span class="folder-actions">
            📁 <a href="{{ url_for('browse', req_path=pathjoin(relpath, name)) }}">{{ name }}/</a>
            <button onclick="deleteFolder('{{ name }}')">Delete Folder</button>
          </span>
        {% else %}
          <span class="file-actions">
            📄 <a href="{{ url_for('download_file', path=pathjoin(relpath, name)) }}">{{ name }}</a>
            <button onclick="deleteFile('{{ name }}')">Delete</button>
            <button onclick="renameFilePrompt('{{ name }}')">Rename</button>
          </span>
        {% endif %}
      </li>
    {% endfor %}
  </ul>
  <hr>
  <h3>Upload files or folders</h3>
  <input type="file" id="fileInput" multiple webkitdirectory directory>
  <button onclick="uploadFile()">Upload</button>
  <div id="dropzone">Drag & drop files or folders here to upload</div>
  <div id="progressWrapper">
    <progress id="progressBar" value="0" max="100"></progress>
    <span id="statusText">0%</span>
  </div>
  <div id="resultMessage"></div>

  <div id="folderCreate">
    <h3>Create Folder</h3>
    <input type="text" id="newFolderName" placeholder="Folder name">
    <button onclick="createFolder()">Create</button>
    <div id="folderResult"></div>
  </div>
  <script>
    function uploadFile(files) {
      const fileInput = document.getElementById("fileInput");
      files = files || fileInput.files;
      if (!files || files.length === 0) {
        alert("Please select files or folders.");
        return;
      }
      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/upload/" + encodeURIComponent(destPath) : "/upload";
      const formData = new FormData();
      for (let i = 0; i < files.length; ++i) {
        formData.append("files", files[i], files[i].webkitRelativePath || files[i].name);
      }
      const xhr = new XMLHttpRequest();
      const progressWrapper = document.getElementById("progressWrapper");
      const progressBar = document.getElementById("progressBar");
      const statusText = document.getElementById("statusText");
      const resultMessage = document.getElementById("resultMessage");
      progressWrapper.style.display = "block";
      progressBar.value = 0;
      statusText.textContent = "0%";
      resultMessage.textContent = "";
      xhr.upload.addEventListener("progress", function(e) {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          progressBar.value = percent;
          statusText.textContent = percent + "%%";
        }
      });
      xhr.onload = function() {
        if (xhr.status === 200) {
          try {
            const res = JSON.parse(xhr.responseText);
            if (res.success) {
              resultMessage.textContent = "✅ Upload complete: " + res.filenames.length + " files/folders";
              setTimeout(()=>{location.reload()},600);
            } else {
              resultMessage.textContent = "❌ Upload failed: " + res.error;
            }
          } catch {
            resultMessage.textContent = "❌ Invalid server response.";
          }
        } else {
          resultMessage.textContent = "❌ Upload error: HTTP " + xhr.status;
        }
        fileInput.value = '';
      };
      xhr.open("POST", url);
      xhr.send(formData);
    }
    // Drag & Drop
    const dropzone = document.getElementById('dropzone');
    dropzone.addEventListener('dragover', function(e) { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', function(e) { dropzone.classList.remove('dragover'); });
    dropzone.addEventListener('drop', function(e) {
      e.preventDefault(); dropzone.classList.remove('dragover');
      uploadFile(e.dataTransfer.files);
    });
    // Delete file
    function deleteFile(name) {
      if (!confirm("Delete file: " + name + "?")) return;
      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/delete/" + encodeURIComponent(destPath) : "/delete";
      fetch(url, {
        method: "POST",
        headers: {'Content-Type':"application/json"},
        body: JSON.stringify({ filename: name })
      })
        .then(r=>r.json())
        .then(res=>{
          if(res.success) {
            alert("Deleted!");
            location.reload();
          } else {
            alert("Delete failed: "+res.error);
          }
        }).catch(()=>alert("Error deleting file"));
    }
    // Delete folder (recursive)
    function deleteFolder(name) {
      if (!confirm("Delete folder and all contents: " + name + "?")) return;
      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/delete_folder/" + encodeURIComponent(destPath) : "/delete_folder";
      fetch(url, {
        method: "POST",
        headers: {'Content-Type':"application/json"},
        body: JSON.stringify({ foldername: name })
      })
        .then(r=>r.json())
        .then(res=>{
          if(res.success) {
            alert("Folder deleted!");
            location.reload();
          } else {
            alert("Folder delete failed: "+res.error);
          }
        }).catch(()=>alert("Error deleting folder"));
    }
    // Rename
    function renameFilePrompt(oldName) {
      const newName = prompt("Enter new name:", oldName);
      if (!newName || newName === oldName) return;
      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/rename/" + encodeURIComponent(destPath) : "/rename";
      fetch(url, {
        method: "POST",
        headers: {'Content-Type':"application/json"},
        body: JSON.stringify({ old: oldName, new: newName })
      })
        .then(r=>r.json())
        .then(res=>{
          if(res.success) {
            alert("Renamed!");
            location.reload();
          } else {
            alert("Rename failed: "+res.error);
          }
        }).catch(()=>alert("Error renaming"));
    }
    // Create folder
    function createFolder() {
      const name = document.getElementById('newFolderName').value.trim();
      if(!name) return alert("Please enter a folder name");
      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/mkdir/" + encodeURIComponent(destPath) : "/mkdir";
      fetch(url, {
        method: "POST",
        headers: {'Content-Type':"application/json"},
        body: JSON.stringify({ foldername: name })
      })
        .then(r=>r.json())
        .then(res=>{
          document.getElementById('folderResult').textContent = res.success?"Folder created!":"Failed: "+res.error;
          if(res.success) setTimeout(()=>location.reload(),800);
        }).catch(()=>alert("Error creating folder"));
    }
  </script>
</body>
</html>
'''

def safe_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    if not final_path.startswith(base):
        raise ValueError("Directory traversal blocked")
    return final_path

def get_parent(path):
    return os.path.dirname(path.rstrip("/"))

@app.before_request
def require_login():
    if PASSWORD:
        if request.endpoint not in ('login', 'static') and not session.get("authed"):
            return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if not PASSWORD:
        return redirect(url_for("browse"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == PASSWORD:
            session["authed"] = True
            return redirect(url_for("browse"))
        else:
            return "<h3>Wrong password. <a href='/login'>Try again</a></h3>", 401
    return '''
      <form method="post">
        <h3>Password required</h3>
        <input type="password" name="password" autofocus required>
        <button type="submit">Login</button>
      </form>
    '''

@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
def browse(req_path):
    try:
        abs_path = safe_join(BASE_DIR, req_path)
        if os.path.isdir(abs_path):
            items = sorted(
                (name, os.path.isdir(os.path.join(abs_path, name)))
                for name in os.listdir(abs_path)
            )
            return render_template_string(
                TEMPLATE,
                relpath=req_path,
                items=items,
                parentpath=get_parent(req_path),
                pathjoin=os.path.join,
            )
        else:
            return download_file(req_path)
    except Exception as e:
        return f"<h3>Error: {e}</h3>"

@app.route("/download/<path:path>")
def download_file(path):
    try:
        abs_path = safe_join(BASE_DIR, path)
        return send_from_directory(
            os.path.dirname(abs_path),
            os.path.basename(abs_path),
            as_attachment=True
        )
    except Exception as e:
        return f"Download error: {e}"

# Multi-file/folder upload with folder structure
@app.route("/upload", methods=["POST"])
@app.route("/upload/<path:dest_path>", methods=["POST"])
def upload_file(dest_path=""):
    try:
        upload_folder = safe_join(BASE_DIR, dest_path)
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        files = request.files.getlist("files")
        if not files:
            file = request.files.get('file')
            if file:
                files = [file]
            else:
                return jsonify(success=False, error="No files"), 400
        filenames = []
        for f in files:
            if not f.filename:
                continue
            relpath = os.path.normpath(f.filename)
            if os.path.isabs(relpath) or relpath.startswith(".."):
                return jsonify(success=False, error="Invalid path in upload"), 400
            save_path = safe_join(upload_folder, relpath)
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            f.save(save_path)
            filenames.append(relpath)
        return jsonify(success=True, filenames=filenames)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route("/delete", methods=["POST"])
@app.route("/delete/<path:dest_path>", methods=["POST"])
def delete_file(dest_path=""):
    try:
        data = request.get_json()
        filename = data["filename"]
        abs_folder = safe_join(BASE_DIR, dest_path)
        abs_path = safe_join(abs_folder, filename)
        if not os.path.isfile(abs_path):
            return jsonify(success=False, error="File not found")
        os.remove(abs_path)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/delete_folder", methods=["POST"])
@app.route("/delete_folder/<path:dest_path>", methods=["POST"])
def delete_folder(dest_path=""):
    try:
        data = request.get_json()
        foldername = data["foldername"]
        abs_folder = safe_join(BASE_DIR, dest_path)
        abs_path = safe_join(abs_folder, foldername)
        if not os.path.isdir(abs_path):
            return jsonify(success=False, error="Folder not found")
        shutil.rmtree(abs_path)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/rename", methods=["POST"])
@app.route("/rename/<path:dest_path>", methods=["POST"])
def rename_file(dest_path=""):
    try:
        data = request.get_json()
        old = data["old"]
        new = data["new"]
        abs_folder = safe_join(BASE_DIR, dest_path)
        old_path = safe_join(abs_folder, old)
        new_path = safe_join(abs_folder, werkzeug.utils.secure_filename(new))
        if not os.path.exists(old_path):
            return jsonify(success=False, error="File/folder not found")
        os.rename(old_path, new_path)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/mkdir", methods=["POST"])
@app.route("/mkdir/<path:dest_path>", methods=["POST"])
def mkdir(dest_path=""):
    try:
        data = request.get_json()
        foldername = data["foldername"]
        abs_folder = safe_join(BASE_DIR, dest_path)
        new_path = safe_join(abs_folder, werkzeug.utils.secure_filename(foldername))
        if os.path.exists(new_path):
            return jsonify(success=False, error="Already exists")
        os.makedirs(new_path)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

if __name__ == "__main__":
    print(f"📂 Sharing: {BASE_DIR}")
    if PASSWORD:
        print("🔒 Password login enabled")
    app.run(host="0.0.0.0", port=args.port, debug=True)
