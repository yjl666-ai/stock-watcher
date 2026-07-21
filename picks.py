"""picks.py — 新闻情绪股票评分引擎（A股+美股）"""
import re, json, sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# ════ 配置 ════
SOURCE_WEIGHTS = {
    "华尔街见闻": 1.2, "东方财富快讯": 1.1, "东方财富": 1.0, "新浪财经": 0.9,
    "Yahoo Finance": 1.0, "CNBC": 1.1, "Google News": 0.9,
}

def _source_weight(source):
    for k, v in SOURCE_WEIGHTS.items():
        if k in source: return v
    return 1.0


# ════ AI ticker 提取 ════

def extract_us_tickers(items):
    """用 AI 从美股新闻标题批量提取公司→ticker"""
    import news
    titles = "\n".join(f"{i+1}. {it['title'][:100]}" for i, it in enumerate(items[:30]))
    prompt = f"""Extract publicly traded US companies from these headlines.
For each company found, provide the stock ticker symbol.

{titles}

Reply in JSON array only:
[{{"ticker": "AAPL", "company": "Apple"}}, {{"ticker": "TSLA", "company": "Tesla"}}, ...]
Only include real, verifiable US stock tickers. If a company isn't publicly traded, skip it."""

    try:
        text = news.call_qwen(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            tickers = json.loads(m.group())
            return {t["ticker"].upper(): t.get("company", "") for t in tickers}
    except Exception:
        pass
    return {}

def _recency_weight(date_str: str) -> float:
    """越新权重越高。1天前=1.0, 2天前=0.8, 3天前=0.5"""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        days = (datetime.now() - dt).days
        if days <= 0: return 1.0
        if days == 1: return 0.9
        if days == 2: return 0.7
        if days == 3: return 0.5
        return max(0.2, 1.0 - days * 0.1)
    except:
        return 1.0


# ════ A股评分 ════

def score_stocks_cn(analyzed_results):
    """
    analyzed_results: list of {sentiment, sectors, title, source, link}
    返回: [{code, name, score, mentions, sentiment_avg, reasons}]
    """
    stocks = {}
    for r in analyzed_results:
        source = r.get("source", "")
        sw = _source_weight(source)
        sentiment = 1 if r["sentiment"] == "看涨" else (-1 if r["sentiment"] == "看跌" else 0)

        # 从标题提取 6 位代码
        for code in re.findall(r'\b(\d{6})\b', r["title"]):
            if code.startswith("0"): continue
            if code not in stocks:
                stocks[code] = {"code": code, "name": "", "score": 0, "mentions": 0, "reasons": []}
            s = stocks[code]
            s["score"] += sentiment * sw
            s["mentions"] += 1
            s["reasons"].append({"title": r["title"][:60], "sentiment": r["sentiment"],
                                   "source": source.replace("🔥 ", "")})

    # 提取名称（从标题匹配）
    for r in analyzed_results:
        for code in stocks:
            if code in r["title"]:
                m = re.search(r'([\u4e00-\u9fa5]{2,6})[\(（]?' + code, r["title"])
                if m and not stocks[code]["name"]:
                    stocks[code]["name"] = m.group(1)

    ranked = sorted(stocks.values(), key=lambda x: -x["score"])
    return ranked[:15]


# ════ 美股评分 ════

def score_stocks_us(analyzed_results, items_raw=None):
    """
    analyzed_results: AI 分析结果
    items_raw: 原始新闻列表（用于 ticker 提取）
    """
    # 1. AI 批量提取 ticker
    ticker_map = {}
    if items_raw:
        ticker_map = extract_us_tickers(items_raw)

    stocks = {}
    for r in analyzed_results:
        source = r.get("source", "")
        sw = _source_weight(source)
        sentiment = 1 if r["sentiment"] == "bullish" else (-1 if r["sentiment"] == "bearish" else 0)
        title = r.get("title", "")

        # 2. 从标题精确正则匹配
        found = set()
        found.update(re.findall(r'\$([A-Z]{1,5})\b', title))
        found.update(re.findall(r'\(([A-Z]{1,5})\)', title))

        # 3. 用 AI ticker 做公司名→ticker 映射
        for company in ticker_map.values():
            if company and company.lower() in title.lower():
                for t, c in ticker_map.items():
                    if c == company:
                        found.add(t)

        # 噪音过滤
        noise = {"THE","A","AN","IS","IT","IN","ON","AT","TO","FOR","OF","AND","OR",
                 "BUT","NOT","NO","WE","US","BE","ITS","FROM","WITH","OVER","MORE",
                 "JUST","AFTER","BACK","DOWN","EVEN","FIRST","HAS","LIKE","MAY","NEW",
                 "NEXT","ONLY","OVER","RISE","THAN","THAT","THEM","THEN","THIS","WAS","WERE"}
        found = {t for t in found if t not in noise and len(t) >= 1}

        for ticker in found:
            ticker = ticker.upper()
            if ticker not in stocks:
                stocks[ticker] = {"ticker": ticker, "name": "", "score": 0, "mentions": 0, "reasons": []}
            s = stocks[ticker]
            s["score"] += sentiment * sw
            s["mentions"] += 1
            s["reasons"].append({"title": title[:80], "sentiment": r["sentiment"],
                                   "source": source.replace("🔥 ", "")})

    ranked = sorted(stocks.values(), key=lambda x: -x["score"])
    return ranked[:15]


# ════ 综合报告 ════

def _gen_reason(ticker, reasons):
    """AI 生成选股理由（一句话）"""
    if not reasons:
        return "新闻提及"
    import news
    titles = "\n".join(f"[{r['sentiment']}] {r['title'][:80]}" for r in reasons[:5])
    prompt = f"""Based on these news mentions for {ticker}, write ONE concise sentence (under 40 words) explaining why this stock deserves attention. Focus on the key catalyst or risk. Reply with just the sentence, no extra text.

{titles}"""
    try:
        return news.call_qwen(prompt).strip().strip('"').strip("'")
    except:
        return "—"


def gen_picks_report_cn(scored, results_summary):
    """A股选股 Markdown"""
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 💡 A股选股参考 · {dt}",
        "",
        f"**扫描新闻**: {results_summary.get('total', 0)} 条 | **发现股票**: {len(scored)} 只",
        "",
        "> ⚠️ 本报告基于新闻情绪量化评分，不构成投资建议。决策请结合个人风险承受能力。",
        "",
        "---",
        "",
        "## 🏆 综合推荐",
        "",
        "| # | 股票/代码 | 情绪分 | 提及 | 选股理由 |",
        "|---|---|---|---|---|",
    ]
    for i, s in enumerate(scored[:10]):
        name = s.get("name") or s.get("code", "?")
        code = s.get("code", "")
        reasons = s.get("reasons", [])
        emoji = "🟢" if s["score"] > 1 else ("🔴" if s["score"] < 0 else "⚪")
        reason = _gen_reason(f"{name}({code})", reasons)
        lines.append(f"| {i+1} | {emoji} {name}<br><small>{code}</small> | {s['score']:+.1f} | {s['mentions']} | {reason[:80]} |")

    risks = [s for s in scored if s["score"] < -1]
    if risks:
        lines.extend(["", "## ⚠️ 风险提示", ""])
        for s in risks[:5]:
            lines.append(f"- **{s.get('name') or s.get('code')}** 情绪 {s['score']:.0f}，{s['mentions']} 次负面提及")

    lines.extend(["", "---", "", "📡 数据来源：新闻情绪分析 · 仅供参考"])

    return "\n".join(lines)


def gen_picks_report_us(scored, results_summary):
    """美股选股 Markdown"""
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 💡 US Stock Picks · {dt}",
        "",
        f"**News scanned**: {results_summary.get('total',0)} articles | **Tickers found**: {len(scored)}",
        "",
        "> ⚠️ Sentiment-based scoring only. NOT investment advice.",
        "",
        "---",
        "",
        "## 🏆 Top Picks",
        "",
        "| # | Ticker | Sentiment | Mentions | Why |",
        "|---|---|---|---|---|",
    ]
    for i, s in enumerate(scored[:10]):
        reasons = s.get("reasons", [])
        emoji = "🟢" if s["score"] > 1 else ("🔴" if s["score"] < 0 else "⚪")
        reason = _gen_reason(f"${s['ticker']}", reasons)
        lines.append(f"| {i+1} | {emoji} ${s['ticker']} | {s['score']:+.1f} | {s['mentions']} | {reason[:80]} |")

    risks = [s for s in scored if s["score"] < -1]
    if risks:
        lines.extend(["", "## ⚠️ Risk Alerts", ""])
        for s in risks[:5]:
            lines.append(f"- **${s['ticker']}** score {s['score']:.0f}, {s['mentions']} bearish mentions")

    lines.extend(["", "---", "", "📡 Data: Sentiment analysis from Yahoo Finance · CNBC · Google News"])

    return "\n".join(lines)


# ════ 跑分入口 ════

if __name__ == "__main__":
    import news
    import scraper as sc
    import scraper_us as sc_us

    print("\n" + "="*50)
    print("💡 A股选股评分")
    print("="*50)

    # A股
    items_cn = sc.fetch_news(limit=30)
    if items_cn:
        results_cn = news.analyze_news(items_cn)
        picks_cn = score_stocks_cn(results_cn)
        print(f"\n发现 {len(picks_cn)} 只股票")
        for p in picks_cn[:5]:
            print(f"  {p.get('name') or p['code']} {p['score']:+.1f} ({p['mentions']}次)")

    print("\n" + "="*50)
    print("💡 US Stock Picks")
    print("="*50)

    # 美股
    items_us = sc_us.fetch_news(limit=30)
    if items_us:
        import run_us
        results_us = run_us.analyze_us(items_us)
        picks_us = score_stocks_us(results_us)
        print(f"\n发现 {len(picks_us)} 个 tickers")
        for p in picks_us[:5]:
            print(f"  ${p['ticker']} {p['score']:+.1f} ({p['mentions']}x)")