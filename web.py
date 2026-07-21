"""web.py — 股市观察报告网站"""
import markdown as md_lib
import subprocess, sys, os, re, threading
from pathlib import Path
from datetime import datetime, timedelta, timezone

# 北京时间
TZ = timezone(timedelta(hours=8))

def _bjnow():
    return datetime.now(TZ)
from flask import Flask

HERE = Path(__file__).parent.resolve()
REPORTS_DIR = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

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
.nav{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-bottom:16px;font-size:13px}
.nav a{color:#6b7280;padding:4px 10px;border-radius:6px;background:#f1f5f9}.nav a:hover{background:#e2e8f0}
.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600}
.badge-up{background:#fecaca;color:#991b1b}
.badge-down{background:#bbf7d0;color:#166534}
.footer{text-align:center;color:#9ca3af;font-size:11px;margin-top:32px;padding:16px 0;border-top:1px solid #e5e7eb}
.meta{font-size:12px;color:#9ca3af;margin-bottom:18px}
"""

def latest_report():
    files = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    return files[0] if files else None

def _format_time(name: str) -> str:
    """report_20260721_1008 → 2026-07-21 10:08"""
    try:
        ts = name.replace("report_", "")
        d = ts[:8]; t = ts[9:13] if len(ts) > 9 else "0000"
        y, m, day = d[:4], d[4:6], d[6:8]
        h, mi = t[:2], t[2:]
        return f"{y}-{m}-{day} {h}:{mi}"
    except Exception:
        return name

@app.route("/")
def index():
    path = latest_report()
    if not path:
        return f"<html><head><meta charset=utf-8><style>{CSS}</style><meta http-equiv=refresh content=30></head><body><div class=err><h2>📭 正在生成首份报告...</h2><p>首次启动约需 90 秒，页面会自动刷新</p></div></body></html>"

    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables", "fenced_code"])

    # 给涨跌幅加颜色
    html = re.sub(r'>([+]\d+\.\d+%)<', r'><span class="badge badge-up">\1</span><', html)
    html = re.sub(r'>(-\d+\.\d+%)<', r'><span class="badge badge-down">\1</span><', html)

    name = path.stem.replace("report_", "")
    update_time = _format_time(path.stem)

    # 下次自动刷新时间
    next_refresh = _next_refresh_time()
    next_str = next_refresh.strftime("%H:%M") if next_refresh else "—"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>📊 股市每日观察</title>
<style>{CSS}</style>
</head>
<body>
<div class="nav">
  <a href="/">🇨🇳 A股</a>
  <a href="/us">🇺🇸 美股</a>
  <a href="/picks" style="color:#d97706">💡 选股</a>
  <a href="/history">📋 历史</a>
  <a href="/refresh" style="color:#059669">🔄 刷新</a>
</div>
{html}
<div class="meta">📅 更新于 {update_time} · 下次自动刷新 {next_str} · 间隔 6 小时</div>
<div class="footer">数据来源：人民网财经 · 东方财富 · 新浪财经 | AI 分析：通义千问</div>
</body>
</html>"""

@app.route("/history")
def history():
    files = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    items = ""
    for f in files[:30]:
        name = _format_time(f.stem)
        first = f.read_text(encoding="utf-8").split("\n")[0].replace("# ", "")
        items += f'<div style="padding:6px 0;border-bottom:1px solid #e5e7eb"><a href="/report/{f.stem}">{name}</a> <span style="color:#9ca3af;font-size:12px">— {first}</span></div>'
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

# ════ 自动刷新 ════

REFRESH_INTERVAL = int(os.environ.get("REFRESH_HOURS", "6"))  # 默认 6 小时
_last_refresh = None   # type: datetime | None
_refresh_lock = threading.Lock()

def _next_refresh_time():
    global _last_refresh
    if _last_refresh:
        return _last_refresh + timedelta(hours=REFRESH_INTERVAL)
    return None

def _do_refresh():
    """后台跑 run.py + run_us.py 生成报告和选股"""
    global _last_refresh
    with _refresh_lock:
        venv_python = str(HERE.parent / ".venv" / "Scripts" / "python.exe")
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        for script in ["run.py", "run_us.py"]:
            try:
                subprocess.run(
                    [venv_python, str(HERE / script)],
                    cwd=str(HERE), timeout=300,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    capture_output=True,
                )
            except Exception as e:
                print(f"[refresh:{script}] ❌ {e}")
        _last_refresh = _bjnow()
        print(f"[refresh] ✅ 完成 {_last_refresh}")

def _scheduler():
    """定时调度：每 REFRESH_INTERVAL 小时跑一次"""
    # 等 30 秒让服务启动完毕
    threading.Timer(30, _do_refresh).start()
    # 之后每 N 小时调度
    def loop():
        _do_refresh()
        threading.Timer(REFRESH_INTERVAL * 3600, loop).start()
    threading.Timer(30 + REFRESH_INTERVAL * 3600, loop).start()

@app.route("/refresh")
def manual_refresh():
    """手动触发刷新"""
    threading.Thread(target=_do_refresh, daemon=True).start()
    return '<meta http-equiv="refresh" content="5;url=/"><p>🔄 正在刷新，5 秒后跳回...</p>'

@app.route("/us")
def us_index():
    """美股报告首页"""
    files = sorted(REPORTS_DIR.glob("us_report_*.md"), reverse=True)
    path = files[0] if files else None
    if not path:
        return f"<html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class=err><h2>📭 暂无美股报告</h2><p>正在生成中...</p></div></body></html>"

    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables", "fenced_code"])
    name = path.stem.replace("us_report_", "")
    update_time = _format_time("us_" + name)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>📊 US Market Watch</title>
<style>{CSS}</style>
</head>
<body>
<div class="nav">
  <a href="/">🇨🇳 A股</a>
  <a href="/us">🇺🇸 美股</a>
  <a href="/picks" style="color:#d97706">💡 A股选股</a>
  <a href="/picks/us" style="color:#d97706">💡 美股选股</a>
  <a href="/history">📋 历史</a>
</div>
{html}
<div class="meta">📅 更新于 {update_time} · 数据来源: Yahoo Finance · CNBC · Google News | AI: 通义千问</div>
</body></html>"""

@app.route("/picks")
def picks_cn():
    """A股选股页面"""
    path = HERE / "picks_cn.md"
    if not path.exists():
        return f"<html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class=err><h2>📭 暂无选股数据</h2></div></body></html>"
    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables"])
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>💡 A股选股</title><style>{CSS}</style></head>
<body>
<div class=nav>
  <a href="/">🇨🇳 A股</a><a href="/us">🇺🇸 美股</a>
  <a href="/picks">💡 A股选股</a><a href="/picks/us">💡 美股选股</a>
  <a href="/history">📋 历史</a>
</div>
{html}
</body></html>"""

@app.route("/picks/us")
def picks_us():
    """美股选股页面"""
    path = HERE / "picks_us.md"
    if not path.exists():
        return f"<html><head><meta charset=utf-8><style>{CSS}</style></head><body><div class=err><h2>📭 No picks data yet</h2></div></body></html>"
    raw = path.read_text(encoding="utf-8")
    html = md_lib.markdown(raw, extensions=["tables"])
    return f"""<!DOCTYPE html>
<html lang=zh-CN>
<head><meta charset=utf-8><title>💡 美股选股参考</title><style>{CSS}</style></head>
<body>
<div class=nav>
  <a href="/">🇨🇳 A股</a><a href="/us">🇺🇸 美股</a>
  <a href="/picks">💡 A股选股</a><a href="/picks/us">💡 美股选股</a>
  <a href="/history">📋 历史</a>
</div>
{html}
</body></html>"""

@app.route("/health")
def health():
    return {"ok": True, "next_refresh": str(_next_refresh_time())}

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5001))
    print(f"\n📊 股市观察网站: http://localhost:{port}")
    print(f"   自动刷新: 每 {REFRESH_INTERVAL} 小时")
    print(f"   手动刷新: http://localhost:{port}/refresh\n")
    # 启动后台调度
    threading.Thread(target=_scheduler, daemon=True).start()
    app.run(host=host, port=port, debug=False)