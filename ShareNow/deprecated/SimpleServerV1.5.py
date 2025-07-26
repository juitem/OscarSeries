# Revert To V1.2 for temporal
import sys
import os
from flask import Flask, request, send_from_directory, render_template_string, jsonify
import werkzeug

# 📁 Determine base directory: from CLI argument or current directory
if len(sys.argv) > 1:
    BASE_DIR = os.path.abspath(sys.argv[1])
else:
    BASE_DIR = os.path.abspath(".")

app = Flask(__name__)
app.secret_key = 'secret-key'

# 🖼 HTML template with upload progress and auto-refresh
TEMPLATE = '''
<!DOCTYPE html>
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
  </style>
</head>
<body>
  <h2>Directory listing: {{ relpath or '.' }}</h2>
  <ul>
    {% if relpath %}
      <li><a href="{{ url_for('browse', req_path=parentpath) }}">[.. Go up]</a></li>
    {% endif %}
    {% for name, is_dir in items %}
      {% if is_dir %}
        <li>📁 <a href="{{ url_for('browse', req_path=pathjoin(relpath, name)) }}">{{ name }}/</a></li>
      {% else %}
        <li>📄 <a href="{{ url_for('download_file', path=pathjoin(relpath, name)) }}">{{ name }}</a></li>
      {% endif %}
    {% endfor %}
  </ul>

  <hr>
  <h3>Upload a File</h3>
  <input type="file" id="fileInput">
  <button onclick="uploadFile()">Upload</button>

  <div id="progressWrapper">
    <progress id="progressBar" value="0" max="100"></progress>
    <span id="statusText">0%</span>
  </div>

  <div id="resultMessage"></div>

  <script>
    function uploadFile() {
      const fileInput = document.getElementById("fileInput");
      const file = fileInput.files[0];
      if (!file) {
        alert("Please select a file.");
        return;
      }

      const destPath = "{{ relpath or '' }}";
      const url = destPath ? "/upload/" + encodeURIComponent(destPath) : "/upload";

      const formData = new FormData();
      formData.append("file", file);

      const xhr = new XMLHttpRequest();
      const progressWrapper = document.getElementById("progressWrapper");
      const progressBar = document.getElementById("progressBar");
      const statusText = document.getElementById("statusText");
      const resultMessage = document.getElementById("resultMessage");

      // Reset UI
      progressWrapper.style.display = "block";
      progressBar.value = 0;
      statusText.textContent = "0%";
      resultMessage.textContent = "";

      // Track upload progress
      xhr.upload.addEventListener("progress", function(e) {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          progressBar.value = percent;
          statusText.textContent = percent + "%";
        }
      });

      // After upload complete
      xhr.onload = function() {
        if (xhr.status === 200) {
          try {
            const res = JSON.parse(xhr.responseText);
            if (res.success) {
              resultMessage.textContent = "✅ Upload complete: " + res.filename;
              fileInput.value = '';

              // 🔄 Refresh page to update file list after 0.7 seconds
              setTimeout(() => {
                location.reload();
              }, 700);
            } else {
              resultMessage.textContent = "❌ Upload failed: " + res.error;
            }
          } catch {
            resultMessage.textContent = "❌ Invalid server response.";
          }
        } else {
          resultMessage.textContent = "❌ Upload error: HTTP " + xhr.status;
        }
      };

      xhr.open("POST", url);
      xhr.send(formData);
    }
  </script>
</body>
</html>
'''

# 🛡 Securely join paths
def safe_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    if not final_path.startswith(base):
        raise ValueError("Blocked path traversal attempt")
    return final_path

# Return parent path
def get_parent(path):
    return os.path.dirname(path.rstrip("/"))

# 📁 Browse folders or download file
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

# 📄 Download file on click
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
        return f"<h3>Download failed: {e}</h3>"

# 📤 Handle file upload with overwrite support
@app.route("/upload", methods=["POST"])
@app.route("/upload/<path:dest_path>", methods=["POST"])
def upload_file(dest_path=""):
    try:
        upload_folder = safe_join(BASE_DIR, dest_path)

        # Auto-create upload folder if not exists
        os.makedirs(upload_folder, exist_ok=True)

        if 'file' not in request.files:
            return jsonify(success=False, error="No file part"), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify(success=False, error="No selected file"), 400

        filename = werkzeug.utils.secure_filename(file.filename)
        save_path = os.path.join(upload_folder, filename)

        # Save file (overwrite allowed)
        file.save(save_path)

        return jsonify(success=True, filename=filename)

    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

# 🚀 Run Flask server
if __name__ == "__main__":
    print(f"📂 Sharing directory: {BASE_DIR}")
    app.run(host="0.0.0.0", port=8000, debug=True)
