"""run_us.py — 一键跑：美股新闻 + AI 分析 + 出报告"""
import sys, re, json
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))

import scraper_us
import news  # 复用 call_qwen()

# ════ 美股专用分析 ════

def analyze_us(news_list):
    """AI 分析每条新闻对美股的影响"""
    results = []
    for n in news_list:
        prompt = f"""Analyze this financial news impact on US stock market (NYSE, NASDAQ).

Title: {n['title']}
Summary: {n['summary']}

Reply in JSON only:
{{
  "sentiment": "bullish" or "bearish" or "neutral",
  "sectors": ["affected sector1", "sector2"],
  "tickers": ["AAPL", "TSLA"],
  "impact": "one sentence explaining the impact logic"
}}"""
        try:
            text = news.call_qwen(prompt)
            m = re.search(r'\{.*?\}', text, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
            else:
                parsed = {"sentiment": "neutral", "sectors": [], "tickers": [], "impact": text[:80]}
        except Exception as e:
            parsed = {"sentiment": "neutral", "sectors": [], "tickers": [], "impact": f"error: {e}"}
        parsed["title"] = n["title"]
        parsed["link"] = n["link"]
        parsed["source"] = n["source"]
        parsed["summary"] = n.get("summary", "")
        results.append(parsed)
        s = parsed["sentiment"]
        emoji = "🟢" if s == "bullish" else ("🔴" if s == "bearish" else "⚪")
        print(f"  {emoji} {n['title'][:50]}...")
    return results


def gen_report_us(results):
    """生成美股 Markdown 报告"""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    bullish = [r for r in results if r["sentiment"] == "bullish"]
    bearish = [r for r in results if r["sentiment"] == "bearish"]
    neutral = [r for r in results if r["sentiment"] == "neutral"]
    total = len(results) or 1

    # 情绪评分
    score = round((len(bullish) - len(bearish)) / total * 50 + 50)
    if score >= 65: label = "BULLISH 📈"
    elif score <= 35: label = "BEARISH 📉"
    else: label = "NEUTRAL ➡️"

    # 源分布
    src_cnt = Counter(r["source"] for r in results)
    src_lines = " · ".join(f"{s} {n}" for s, n in src_cnt.most_common())

    # 板块热度
    hot = Counter()
    for r in results:
        w = 1 if r["sentiment"] == "bullish" else (-1 if r["sentiment"] == "bearish" else 0)
        for s in r.get("sectors", []):
            hot[s] += w
    heatmap = sorted(hot.items(), key=lambda x: -x[1])[:8]

    # 股票
    tickers = Counter()
    for r in results:
        for t in r.get("tickers", []):
            tickers[t.upper()] += 1
    top_tickers = tickers.most_common(6)

    lines = [
        f"# 📊 US Market Watch · {today}",
        "",
        f"**Sources**: {src_lines}",
        "",
        "---",
        "",
        "## 📈 Market Sentiment",
        "",
        f"| Score | Direction | Bullish | Bearish | Neutral |",
        f"|-------|-----------|---------|---------|---------|",
        f"| {score}/100 | {label} | {len(bullish)} | {len(bearish)} | {len(neutral)} |",
        "",
        "---",
        "",
        "## 🔥 Hot Sectors",
        "",
        "| Sector | Heat |",
        "|--------|------|",
    ]
    max_h = max(abs(v) for _, v in heatmap) if heatmap else 1
    for name, w in heatmap:
        bar = "█" * max(1, int(abs(w) / max_h * 10))
        tag = "🟢" if w > 0 else "🔴"
        lines.append(f"| {tag} {name} | {bar} {w:+d} |")

    if top_tickers:
        lines.extend(["", "---", "", "## 💹 Top Tickers Mentioned", ""])
        for t, c in top_tickers:
            lines.append(f"- **${t}** ({c} mentions)")

    lines.extend(["", "---", ""])

    for label, items, emoji in [("🟢 Bullish", bullish, "🟢"), ("🔴 Bearish", bearish, "🔴"), ("⚪ Neutral", neutral, "⚪")]:
        if not items: continue
        lines.append(f"## {label} ({len(items)})")
        for r in items:
            sectors = ", ".join(r.get("sectors", [])) or "—"
            tickers = ", ".join(f"${t}" for t in r.get("tickers", [])) or "—"
            lines.append(f"- **{r['title']}**")
            lines.append(f"  - Source: [{r['source']}]({r['link']})")
            lines.append(f"  - Sectors: {sectors}  |  Tickers: {tickers}")
            lines.append(f"  - {r['impact']}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📡 抓取美股新闻...")
    print("=" * 60)
    items = scraper_us.fetch_news(limit=30)

    cnt = Counter(i["source"] for i in items)
    print(f"\n总计 {len(items)} 条，来源：")
    for s, n in cnt.most_common():
        print(f"  {s}: {n}")

    if not items:
        print("❌ 没抓到任何新闻"); sys.exit(1)

    print("\n" + "=" * 60)
    print("🤖 AI 分析中...")
    print("=" * 60)
    results = analyze_us(items[:30])

    report = gen_report_us(results)

    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    name = f"us_report_{datetime.now():%Y%m%d_%H%M}.md"
    report_path = reports_dir / name
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 美股报告: {report_path}")
    print("\n" + report[:2000] + ("..." if len(report) > 2000 else ""))