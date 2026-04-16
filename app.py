from flask import Flask, request, send_file, Response
import os
import tempfile
import subprocess

app = Flask(__name__)

HTML = """
<!doctype html>
<title>SEO Schema Generator</title>
<h2>SEO Schema Generator</h2>
<p>Upload your Excel input file (.xlsx). You'll receive an output .xlsx.</p>
<form method="POST" action="/run" enctype="multipart/form-data">
  <input type="file" name="file" accept=".xlsx" required>
  <button type="submit">Generate</button>
</form>
"""


@app.route("/", methods=["GET"])
def home():
    return HTML


@app.route("/run", methods=["POST"])
def run():
    if "file" not in request.files:
        return Response("Missing file", status=400)

    file = request.files["file"]
    if not file.filename:
        return Response("Empty filename", status=400)

    tmp_dir = tempfile.mkdtemp()
    input_path = os.path.join(tmp_dir, "input.xlsx")
    output_path = os.path.join(tmp_dir, "seo_output.xlsx")
    file.save(input_path)

    result = subprocess.run(
        ["python", "seo_automation.py", input_path, "--xlsx", output_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_text = result.stderr.strip() or result.stdout.strip() or "Unknown processing error"
        return Response(f"Processing failed:\n{error_text}", status=500)

    if not os.path.exists(output_path):
        return Response("Processing failed: output file was not created.", status=500)

    return send_file(output_path, as_attachment=True, download_name="seo_output.xlsx")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
