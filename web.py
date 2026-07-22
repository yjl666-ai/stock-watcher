"""web.py — 美股观察网站"""
import markdown as md_lib
import subprocess, sys, os, re, threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from flask import Flask

HERE = Path(__file__).parent.resolve()
REPORTS_DIR = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# 北京时间
TZ = timezone(timedelta(hours=8))
def _bjnow():
    return datetime.now(TZ)

app = Flask(__name__)

CSS = """
*{box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:860px;margin:0 auto;padding:20px 18px;color:#1f2937;background:#f8fafc}
h1{font-size:22px;border-bottom:2px solid #e5e7eb;padding-bottom:8px;margin-top:0}
h2{font-size:17px;margin-top:24px;color:#374151}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
th,td{border:1px solid #e5e7eb;padding:7px 10px;text-align:left}
th{background:#f1f5f9;font-weight:600}
tr:nth-child(even){background:#fff}
blockquote{background:#fef3c7;border-left:4px solid #f59e0b;margin:0;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px;line-height:1.7}
pre{background:#1e293b;color:#e2e8f0;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px}
a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}
.nav{display:flex;gap:12px;align-items:center;margin-bottom:16px;font-size:13px;flex-wrap:wrap}
.nav a{color:#374151;padding:4px 10px;border-radius:6px;background:#f1f5f9;text-decoration:none}.nav a:hover{background:#e2e8f0}
.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600}
.badge-up{background:#fecaca;color:#991b1b}
.badge-down{background:#bbf7d0;color:#166534}
.footer{text-align:center;color:#9ca3af;font-size:11px;margin-top:32px;padding:16px 0;border-top:1px solid #e5e7eb}
.meta{font-size:12px;color:#9ca3af;margin-bottom:18px}
.err{text-align:center;padding:60px 20px;color:#9ca3af}
"""


def _format_time(name: str) -> str:
    """us_report_20260721_1737 → 2026-07-21 17:37"""
    try:
        ts = name.replace("us_report_", "")
        d = ts[:8]; t = ts[9:13] if len(ts) > 9 else "0000"
        return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:]}"
    except Exception:
        return name


@app.route("/")
def index():
    """美股报告首页"""
    files = sorted(REPORTS_DIR.glob("us_report_*.md"), reverse=True)
    path = files[0] if files else None
    if not path:
        return f'<html><head><meta charset=utf-8><style>{CSS}</style><meta http-equiv=refresh content=30></head><body><div class=err><h2>📭 正在生成首份报告...</h2><p>首次启动约需 90 秒，页面会自动刷新</p></div></body></html>'

    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables", "fenced_code"])
    update_time = _format_time(path.stem)
    next_refresh = _next_refresh_time()
    next_str = next_refresh.strftime("%H:%M") if next_refresh else "—"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>📊 美股每日观察</title>
<style>{CSS}</style>
</head>
<body>
<div class="nav">
  <a href="/">🏠 首页</a>
  <a href="/picks">💡 选股</a>
  <a href="/history">📋 历史</a>
  <a href="/refresh" style="color:#059669">🔄 刷新</a>
</div>
{html}
<div class="meta">📅 更新于 {update_time} · 下次自动刷新 {next_str}（每日北京时间 9:00）</div>
<div class="footer">数据来源：Yahoo Finance · CNBC · Google News | AI 分析：通义千问</div>
</body>
</html>"""


@app.route("/picks")
def picks():
    """美股选股页面"""
    path = HERE / "picks_us.md"
    if not path.exists():
        return f'<html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class=err><h2>📭 暂无选股数据</h2><p>刷新后会生成</p></div></body></html>'
    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables"])
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>💡 美股选股</title><style>{CSS}</style></head>
<body>
<div class="nav">
  <a href="/">🏠 首页</a>
  <a href="/picks">💡 选股</a>
  <a href="/history">📋 历史</a>
  <a href="/refresh" style="color:#059669">🔄 刷新</a>
</div>
{html}
</body></html>"""


@app.route("/history")
def history():
    files = sorted(REPORTS_DIR.glob("us_report_*.md"), reverse=True)
    items = ""
    for f in files[:30]:
        name = _format_time(f.stem)
        first = f.read_text(encoding="utf-8").split("\n")[0].replace("# ", "")
        items += f'<div style="padding:6px 0;border-bottom:1px solid #e5e7eb"><a href="/report/{f.stem}">{name}</a> <span style="color:#9ca3af;font-size:12px">— {first}</span></div>'
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>历史报告</title><style>{CSS}</style></head>
<body>
<div class="nav"><a href="/">🏠 首页</a></div>
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
<div class=nav><a href="/">🏠 首页</a> | <a href="/history">📋 历史</a></div>
{html}
</body></html>"""


# ════ 自动刷新 — 每日北京时间 9:00 ════

_last_refresh = None
_refresh_lock = threading.Lock()


def _next_refresh_time():
    """下次刷新时间：今天或明天的 9:00 北京时间"""
    now = _bjnow()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def _do_refresh():
    global _last_refresh
    with _refresh_lock:
        venv_python = str(HERE / ".venv" / "Scripts" / "python.exe")
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        try:
            subprocess.run(
                [venv_python, str(HERE / "run_us.py")],
                cwd=str(HERE), timeout=300,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
            )
            _last_refresh = _bjnow()
            print(f"[refresh] ✅ 完成 {_last_refresh}")
        except Exception as e:
            print(f"[refresh] ❌ {e}")


def _scheduler():
    """每日北京时间 9:00 跑一次"""
    def schedule_next():
        next_run = _next_refresh_time()
        delay = (next_run - _bjnow()).total_seconds()
        if delay < 0:
            delay = 0
        print(f"[scheduler] 下次刷新: {next_run} ({(delay)/60:.0f} 分钟后)")
        threading.Timer(delay, _run_and_reschedule).start()

    def _run_and_reschedule():
        _do_refresh()
        schedule_next()  # 安排下次

    schedule_next()


@app.route("/refresh")
def manual_refresh():
    threading.Thread(target=_do_refresh, daemon=True).start()
    return '<meta http-equiv="refresh" content="5;url=/"><p>🔄 正在刷新，5 秒后跳回...</p>'


@app.route("/health")
def health():
    return {"ok": True, "next_refresh": str(_next_refresh_time())}


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5001))
    print(f"\n📊 美股观察网站: http://localhost:{port}")
    print(f"   每日刷新: 北京时间 9:00")
    print(f"   手动刷新: http://localhost:{port}/refresh\n")
    threading.Thread(target=_scheduler, daemon=True).start()
    app.run(host=host, port=port, debug=False)