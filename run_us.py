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

Return ONLY valid JSON (no other text):
{{
  "sentiment": "bullish" or "bearish" or "neutral",
  "sectors": ["Technology", "Healthcare", "Finance", "Energy", "Consumer", "Automotive", "Semiconductor", "Media", "Defense", "Retail", "Crypto", "Biotech"],
  "tickers": ["AAPL", "MSFT", "TSLA"],
  "impact": "one sentence explaining the impact logic"
}}

IMPORTANT RULES:
1. "sectors" must include 1-3 relevant sector names from the list above. ALWAYS include at least one sector.
2. "tickers" must include actual US ticker symbols (1-5 uppercase letters, NYSE/NASDAQ only) if the news mentions any specific publicly traded company. Use [] if no company is mentioned.
3. Return ONLY the JSON object, nothing else."""
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

    # ── 后备: 关键词板块检测（当 AI 返回空时） ──
    if len(heatmap) < 3:
        sector_kw = {
            "Technology": ["ai", "tech", "chip", "semiconductor", "nvidia", "intel", "amd", "software", "cloud", "quantum", "data", "robot", "cyber", "saas"],
            "Finance": ["bank", "finance", "fed", "interest", "treasury", "bond", "goldman", "jpmorgan", "morgan stanley", "crypto", "bitcoin", "insurance"],
            "Healthcare": ["health", "medical", "drug", "pharma", "biotech", "pfizer", "moderna", "vaccine", "hospital", "clinical"],
            "Energy": ["energy", "oil", "gas", "solar", "exxon", "renewable", "carbon", "shell", "petroleum"],
            "Consumer": ["consumer", "retail", "walmart", "nike", "amazon", "starbucks", "coca-cola", "restaurant", "food"],
            "Automotive": ["auto", "car", "ev", "electric vehicle", "tesla", "ford", "gm", "driverless", "autonomous"],
            "Defense": ["defense", "military", "lockheed", "boeing", "space", "aerospace", "weapon"],
            "Media": ["meta", "netflix", "disney", "streaming", "social media", "advertising", "entertainment"],
            "Semiconductor": ["semiconductor", "chip", "nvidia", "amd", "intel", "tsmc", "processor", "gpu"],
        }
        fb = Counter()
        for r in results:
            w = 1 if r["sentiment"] == "bullish" else (-1 if r["sentiment"] == "bearish" else 0)
            text = (r.get("title","") + " " + r.get("summary","")).lower()
            for sec, kws in sector_kw.items():
                if any(kw in text for kw in kws):
                    fb[sec] += w
                    break
        if fb:
            heatmap = sorted(fb.items(), key=lambda x: -x[1])[:8]

    # 股票
    tickers = Counter()
    for r in results:
        for t in r.get("tickers", []):
            tickers[t.upper()] += 1
    top_tickers = tickers.most_common(6)

    # ── 后备: 从新闻标题提取个股（当 AI 返回空时） ──
    if len(top_tickers) < 3:
        title_text = " ".join(r.get("title","") for r in results).lower()
        for kw, (ticker, _) in picks.KNOWN_US.items():
            if kw in title_text:
                cnt = title_text.count(kw)
                tickers[ticker] += cnt
        top_tickers = tickers.most_common(6)

    lines = [
        f"# 📊 美股市场观察 · {today}",
        "",
        f"**数据来源**: {src_lines}",
        "",
        "---",
        "",
        "## 📈 市场情绪",
        "",
        f"| 评分 | 方向 | 看涨 | 看跌 | 中性 |",
        f"|------|------|-----|-----|-----|",
        f"| {score}/100 | {label} | {len(bullish)} | {len(bearish)} | {len(neutral)} |",
        "",
        "---",
        "",
        "## 🔥 热门板块",
        "",
        "| 板块 | 热度 |",
        "|------|------|",
    ]
    max_h = max(abs(v) for _, v in heatmap) if heatmap else 1
    for name, w in heatmap:
        bar = "█" * max(1, int(abs(w) / max_h * 10))
        tag = "🟢" if w > 0 else "🔴"
        lines.append(f"| {tag} {name} | {bar} {w:+d} |")

    if top_tickers:
        lines.extend(["", "---", "", "## 💹 热门个股提及", ""])
        for t, c in top_tickers:
            lines.append(f"- **${t}** ({c} 次)")

    lines.extend(["", "---", ""])

    for label, items, emoji in [("🟢 看涨", bullish, "🟢"), ("🔴 看跌", bearish, "🔴"), ("⚪ 中性", neutral, "⚪")]:
        if not items: continue
        lines.append(f"## {label} ({len(items)})")
        for r in items:
            sectors = ", ".join(r.get("sectors", [])) or "—"
            lines.append(f"- **{r['title']}**")
            lines.append(f"  - 来源: [{r['source']}]({r['link']})")
            lines.append(f"  - 板块: {sectors}")
            lines.append(f"  - {r['impact']}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📡 抓取美股新闻...")
    print("=" * 60)
    items = scraper_us.fetch_news(limit=60)

    cnt = Counter(i["source"] for i in items)
    print(f"\n总计 {len(items)} 条，来源：")
    for s, n in cnt.most_common():
        print(f"  {s}: {n}")

    if not items:
        print("❌ 没抓到任何新闻"); sys.exit(1)

    print("\n" + "=" * 60)
    print("🤖 AI 分析中...")
    print("=" * 60)
    results = analyze_us(items[:60])

    report = gen_report_us(results)

    # ════ 选股评分 ════
    import picks
    picks_us = picks.score_stocks_us(results, items_raw=items)
    picks_report = picks.gen_picks_report(picks_us, {"total": len(items)})
    picks_path = Path(__file__).parent / "picks_us.md"
    picks_path.write_text(picks_report, encoding="utf-8")
    print(f"\n💡 美股选股: {picks_path} ({len(picks_us)} tickers)")

    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    name = f"us_report_{datetime.now():%Y%m%d_%H%M}.md"
    report_path = reports_dir / name
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 美股报告: {report_path}")

    # 存档到 GitHub（让历史不丢）
    try:
        import subprocess
        subprocess.run(["git", "add", str(report_path.relative_to(HERE)),
                        str(picks_path.relative_to(HERE))],
                       cwd=str(HERE), check=True, capture_output=True)
        msg = f"chore: 自动存档 {name}"
        result = subprocess.run(["git", "commit", "-m", msg],
                              cwd=str(HERE), capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(["git", "push", "origin", "main"],
                          cwd=str(HERE), capture_output=True, timeout=30)
            print(f"📦 已存档到 GitHub")
        else:
            print(f"⚠️  无变化或 commit 失败")
    except Exception as e:
        print(f"⚠️  存档失败: {e}")
    print("\n" + report[:2000] + ("..." if len(report) > 2000 else ""))