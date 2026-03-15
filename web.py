from flask import Flask, request, redirect
import subprocess, threading, os, time

app = Flask(__name__)

LOG_FILE = "run.log"
process = None

# ================= RUN CKR SCRIPT =================
def run_script(uid, region):
    global process
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        process = subprocess.Popen(
            ["python", "ckr.py"],
            stdin=subprocess.PIPE,
            stdout=f,
            stderr=f,
            text=True
        )

        process.stdin.write(uid + "\n")
        process.stdin.write(region + "\n")
        process.stdin.write("y\n")
        process.stdin.flush()

        time.sleep(2)
        process.stdin.write("\n")
        process.stdin.flush()

        process.wait()
        process = None


# ================= STATUS SUMMARY =================
def get_clean_summary():
    if not os.path.exists(LOG_FILE):
        return ""

    lines = open(LOG_FILE, encoding="utf-8", errors="ignore").read().splitlines()

    keys = [
        "PLAYER INFORMATION",
        "FINAL RESULTS",
        "Likes Before",
        "Likes After",
        "Likes Added",
        "Successfully",
        "Operation Completed",
        "Success Rate"
    ]

    keep = [l for l in lines if any(k in l for k in keys)]
    return "\n".join(keep[-25:])


# ================= DASHBOARD =================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uid = request.form.get("uid")
        region = request.form.get("region")

        threading.Thread(
            target=run_script,
            args=(uid, region),
            daemon=True
        ).start()

        return redirect("/status")

    return """<!doctype html>
<html lang="en">
<head>
<title>CKRPRO Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
*{box-sizing:border-box}
body{
    margin:0;
    min-height:100vh;
    background:linear-gradient(135deg,#0f1220,#090b14);
    font-family:Segoe UI,Roboto,Arial;
    color:#eaeaf0;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:16px;
}
.card{
    width:100%;
    max-width:420px;
    background:rgba(22,26,51,.95);
    backdrop-filter:blur(10px);
    border-radius:22px;
    padding:22px;
    box-shadow:0 25px 60px rgba(0,0,0,.55);
}
.logo{text-align:center;font-size:26px;font-weight:800}
.logo span{color:#4f7cff}
.sub{text-align:center;font-size:12px;color:#9aa3c7;margin-bottom:18px}
label{font-size:12px;color:#aab;display:block;margin-top:10px}
input,select{
    width:100%;
    padding:13px 14px;
    border-radius:14px;
    border:none;
    background:#0f1220;
    color:#fff;
    margin-top:6px;
}
button{
    width:100%;
    padding:14px;
    border-radius:16px;
    border:none;
    cursor:pointer;
    font-weight:700;
    margin-top:16px;
}
button.start{
    background:linear-gradient(135deg,#4f7cff,#6f8cff);
    color:white;
}
.links{display:flex;justify-content:center;gap:12px;margin-top:18px}
.links a{
    font-size:13px;
    color:#cdd6ff;
    text-decoration:none;
    padding:6px 12px;
    border-radius:12px;
    background:#0f1220;
}
.footer{text-align:center;font-size:11px;color:#889;margin-top:18px}
</style>
</head>
<body>
<div class="card">
<div class="logo">CKR<span>PRO</span></div>
<div class="sub">Free Fire Auto Liker Dashboard</div>

<form method="post">
<label>Target UID</label>
<input name="uid" inputmode="numeric" pattern="[0-9]+" required>

<label>Region</label>
<select name="region">
<option>BD</option>
<option>IND</option>
<option>BR</option>
<option>US</option>
<option>SAC</option>
</select>

<button class="start"> START</button>
</form>

<div class="links">
<a href="https://youtube.com/@ckrunknown" target="_blank">YouTube</a>
<a href="https://instagram.com/ckrunknown7" target="_blank">Instagram</a>
<a href="https://tiktok.com/@ckrunknown" target="_blank">TikTok</a>
</div>

<div class="footer">
© CKRPRO | <a href="/status" style="color:#8fb3ff">View Status</a>
</div>
</div>
</body>
</html>"""


# ================= STATUS PAGE =================
@app.route("/status")
def status():
    summary = get_clean_summary()
    return f"""
<!doctype html>
<html>
<head>
<meta http-equiv="refresh" content="3">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1220;color:#eaeaf0;font-family:Arial;padding:12px}}
.box{{max-width:520px;margin:20px auto;padding:16px;border-radius:14px;background:#161a33}}
pre{{white-space:pre-wrap;background:#0f1220;padding:12px;border-radius:10px}}
a{{display:block;text-align:center;color:#8fb3ff;text-decoration:none;margin-top:10px}}
</style>
</head>
<body>
<div class="box">
<h3>Status</h3>
<pre>{summary if summary else "Running... please wait"}</pre>
<a href="/">⬅ Back</a>
</div>
</body>
</html>
"""


# ================= STOP =================
@app.route("/stop", methods=["POST"])
def stop():
    global process
    if process:
        try:
            process.terminate()
        except:
            pass
        process = None
    return redirect("/")


# ================= START SERVER =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)