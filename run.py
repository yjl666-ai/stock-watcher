"""run.py — 一键跑：抓新闻 + AI 分析 + 出报告"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import scraper
import news
from datetime import datetime

print("\n" + "="*60)
print("📡 抓取财经新闻（多源）...")
print("="*60)
items = scraper.fetch_news(limit=40)

from collections import Counter
cnt = Counter(i["source"] for i in items)
print(f"\n总计 {len(items)} 条，来源：")
for s, n in cnt.most_common():
    print(f"  {s}: {n}")

if not items:
    print("❌ 没抓到任何新闻")
    sys.exit(1)

print("\n" + "="*60)
print("🤖 AI 分析每条新闻...")
print("="*60)
results = news.analyze_news(items)

print("\n" + "="*60)
print("💡 生成选股评分...")
print("="*60)
import picks
picks_cn = picks.score_stocks_cn(results)
picks_report = picks.gen_picks_report_cn(picks_cn, {"total": len(items)})
picks_path = Path(__file__).parent / "picks_cn.md"
picks_path.write_text(picks_report, encoding="utf-8")
print(f"  选股报告: {picks_path} ({len(picks_cn)} 只)")

print("\n" + "="*60)
print("📝 生成 Markdown 报告...")
print("="*60)
report = news.generate_report(results)

# 保存到 reports/ 目录（用于历史对比）
reports_dir = Path(__file__).parent / "reports"
reports_dir.mkdir(exist_ok=True)
report_path = reports_dir / f"report_{datetime.now():%Y%m%d_%H%M}.md"
report_path.write_text(report, encoding="utf-8")
# 同时保存一份到根目录方便直接看
(Path(__file__).parent / f"report_{datetime.now():%Y%m%d_%H%M}.md").write_text(report, encoding="utf-8")
print(f"\n✅ 报告已生成: {report_path}")
print("\n" + report[:2000] + ("..." if len(report) > 2000 else ""))