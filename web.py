"""web.py — 股市观察报告网站"""
import markdown as md_lib
from pathlib import Path
from flask import Flask

HERE = Path(__file__).parent.resolve()
REPORTS_DIR = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

CSS = """
*{box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:860px;margin:0 auto;padding:20px 18px;color:#1f2937;background:#f8fafc}
h1{font-size:24px;border-bottom:2px solid #e5e7eb;padding-bottom:10px}
h2{font-size:18px;margin-top:28px;color:#374151}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #e5e7eb;padding:8px 12px;text-align:left;font-size:14px}
th{background:#f1f5f9;font-weight:600}
tr:nth-child(even){background:#fff}
blockquote{background:#fef3c7;border-left:4px solid #f59e0b;margin:0;padding:12px 16px;border-radius:0 8px 8px 0;font-size:14px;line-height:1.7}
pre{background:#1e293b;color:#e2e8f0;padding:14px;border-radius:8px;overflow-x:auto;font-size:13px}
a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}
.nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;font-size:14px}
.nav a{color:#6b7280}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600}
.badge-up{background:#fecaca;color:#991b1b}
.badge-down{background:#bbf7d0;color:#166534}
.footer{text-align:center;color:#9ca3af;font-size:12px;margin-top:40px;padding:20px 0;border-top:1px solid #e5e7eb}
.err{text-align:center;padding:60px 20px;color:#9ca3af}
.refresh{font-size:12px;color:#9ca3af}
"""

def latest_report():
    """返回最新一份报告"""
    files = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    return files[0] if files else None

@app.route("/")
def index():
    path = latest_report()
    if not path:
        return f"<html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class=err><h2>📭 暂无报告</h2><p>请先运行 run.py 生成报告</p></div></body></html>"

    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables", "fenced_code"])

    # 增强样式：给涨跌幅加颜色
    import re
    html = re.sub(r'([+-]\d+\.\d+%)', r'<span class="badge badge-up">\1</span>', html)
    html = re.sub(r'(-\d+\.\d+%)', r'<span class="badge badge-down">\1</span>', html)

    name = path.stem.replace("report_", "")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 股市每日观察</title>
<style>{CSS}</style>
</head>
<body>
<div class="nav">
  <div>📊 <strong>股市每日观察</strong> · {name}</div>
  <div>
    <a href="/history">📋 历史</a> &nbsp;
    <span class="refresh">刷新时间未知</span>
  </div>
</div>
{html}
<div class="footer">数据来源：人民网财经 · 东方财富 · 新浪财经 &nbsp;|&nbsp; AI 分析：通义千问</div>
</body>
</html>"""

@app.route("/history")
def history():
    files = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    items = ""
    for f in files[:30]:
        name = f.stem.replace("report_", "")
        # 提取首行
        first = f.read_text(encoding="utf-8").split("\n")[0].replace("# ", "")
        items += f'<div style="padding:8px 0;border-bottom:1px solid #e5e7eb"><a href="/report/{f.stem}">{name}</a> <span style="color:#9ca3af">— {first}</span></div>'
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>历史报告</title><style>{CSS}</style></head>
<body>
<div class=nav><a href="/">← 返回首页</a></div>
<h1>📋 历史报告</h1>
{items or '<p style=color:#9ca3af>暂无</p>'}
</body></html>"""

@app.route("/report/<name>")
def view_report(name):
    path = REPORTS_DIR / f"{name}.md"
    if not path.exists():
        return "<h2>404</h2>", 404
    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables", "fenced_code"])
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>{name}</title><style>{CSS}</style></head>
<body>
<div class=nav><a href="/">← 返回首页</a> | <a href="/history">📋 历史</a></div>
{html}
</body></html>"""

@app.route("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5001))
    print(f"\n📊 股市观察网站: http://localhost:{port}")
    print(f"   历史记录: http://localhost:{port}/history\n")
    app.run(host=host, port=port, debug=False)