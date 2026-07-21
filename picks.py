"""picks.py — 新闻情绪股票评分引擎（A股+美股）"""
import re, json, sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

SOURCE_WEIGHTS = {
    "华尔街见闻": 1.2, "东方财富快讯": 1.1, "东方财富": 1.0, "新浪财经": 0.9,
    "Yahoo Finance": 1.0, "CNBC": 1.1, "Google News": 0.9,
}

def _source_weight(source):
    for k, v in SOURCE_WEIGHTS.items():
        if k in source: return v
    return 1.0

# ════ AI ticker 提取 ════

KNOWN_US = {
    "apple": ("AAPL","Apple"), "amazon": ("AMZN","Amazon"), "tesla": ("TSLA","Tesla"),
    "nvidia": ("NVDA","NVIDIA"), "microsoft": ("MSFT","Microsoft"), "google": ("GOOGL","Google"),
    "meta": ("META","Meta"), "netflix": ("NFLX","Netflix"), "intel": ("INTC","Intel"),
    "amd": ("AMD","AMD"), "coca-cola": ("KO","Coca-Cola"), "coca cola": ("KO","Coca-Cola"),
    "walmart": ("WMT","Walmart"), "exxon": ("XOM","Exxon"), "jpmorgan": ("JPM","JPMorgan"),
    "bank of america": ("BAC","BofA"), "goldman": ("GS","Goldman Sachs"),
    "morgan stanley": ("MS","Morgan Stanley"), "berkshire": ("BRK.B","Berkshire"),
    "nike": ("NKE","Nike"), "starbucks": ("SBUX","Starbucks"), "disney": ("DIS","Disney"),
    "pfizer": ("PFE","Pfizer"), "moderna": ("MRNA","Moderna"), "uber": ("UBER","Uber"),
    "salesforce": ("CRM","Salesforce"), "ibm": ("IBM","IBM"), "oracle": ("ORCL","Oracle"),
    "general motors": ("GM","GM"), "ford": ("F","Ford"), "boeing": ("BA","Boeing"),
    "palantir": ("PLTR","Palantir"), "trump media": ("DJT","Trump Media"),
    "samsung": ("SSNLF","Samsung"), "alibaba": ("BABA","Alibaba"),
    "jd.com": ("JD","JD.com"), "venture global": ("VG","Venture Global"),
}

def extract_us_tickers(items):
    import news
    titles = "\n".join(f"{i+1}. {it['title'][:100]}" for i, it in enumerate(items[:30]))
    prompt = f"从以下英文财经新闻标题中提取被提及的美股上市公司及股票代码。\n\n{titles}\n\n只返回JSON：[{{\"ticker\":\"AAPL\",\"company\":\"Apple\"}}, ...]"

    result = {}
    for it in items:
        t = it["title"].lower()
        for kw, (ticker, name) in KNOWN_US.items():
            if kw in t:
                result[ticker] = name
    try:
        text = news.call_qwen(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            for t in json.loads(m.group()):
                result[t["ticker"].upper()] = t.get("company","")
    except: pass
    return result

# ════ AI A股公司提取 ════

def extract_cn_stocks(items):
    import news
    titles = "\n".join(f"{i+1}. {it['title'][:100]}" for i, it in enumerate(items[:30]))
    prompt = f"从以下财经新闻标题中提取被提及的A股上市公司及股票代码。\n\n{titles}\n\n只返回JSON：[{{\"code\":\"600519\",\"name\":\"贵州茅台\"}}, ...]"
    try:
        text = news.call_qwen(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            return {t["code"]: t.get("name","") for t in json.loads(m.group())}
    except: pass
    return {}

# ════ A股评分 ════

def score_stocks_cn(analyzed_results, items_raw=None):
    cn_map = extract_cn_stocks(items_raw) if items_raw else {}
    stocks = {}
    for r in analyzed_results:
        sw = _source_weight(r.get("source",""))
        sentiment = 1 if r["sentiment"] == "看涨" else (-1 if r["sentiment"] == "看跌" else 0)
        found = set()
        for code in re.findall(r'\b(\d{6})\b', r["title"]):
            if not code.startswith("0"): found.add(code)
        for code, name in cn_map.items():
            if name and name in r["title"]: found.add(code)
        for code in found:
            if code not in stocks:
                stocks[code] = {"code": code, "name": cn_map.get(code,""), "score": 0, "mentions": 0, "reasons": []}
            stocks[code]["score"] += sentiment * sw
            stocks[code]["mentions"] += 1
            stocks[code]["reasons"].append({"title": r["title"][:60], "sentiment": r["sentiment"], "source": r["source"].replace("🔥 ","")})
    for r in analyzed_results:
        for code in stocks:
            if code in r["title"]:
                m = re.search(r'([\u4e00-\u9fa5]{2,6})[\(（]?' + code, r["title"])
                if m and not stocks[code]["name"]:
                    stocks[code]["name"] = m.group(1)
    return sorted(stocks.values(), key=lambda x: -x["score"])[:15]

# ════ 美股评分 ════

def score_stocks_us(analyzed_results, items_raw=None):
    ticker_map = extract_us_tickers(items_raw) if items_raw else {}
    stocks = {}
    NOISE = {"THE","A","AN","IS","IT","IN","ON","AT","TO","FOR","OF","AND","OR","BUT","NOT","NO","WE","US","BE","ITS","FROM","WITH","OVER","MORE","JUST","AFTER","BACK","DOWN","EVEN","FIRST","HAS","LIKE","MAY","NEW","NEXT","ONLY","RISE","THAN","THAT","THEM","THEN","THIS","WAS","WERE"}
    for r in analyzed_results:
        sw = _source_weight(r.get("source",""))
        sentiment = 1 if r["sentiment"] == "bullish" else (-1 if r["sentiment"] == "bearish" else 0)
        title = r.get("title","")
        found = set(re.findall(r'\$([A-Z]{1,5})\b', title))
        found.update(re.findall(r'\(([A-Z]{1,5})\)', title))
        for company in ticker_map.values():
            if company and company.lower() in title.lower():
                for t, c in ticker_map.items():
                    if c == company: found.add(t)
        found = {t for t in found if t not in NOISE and len(t) >= 1}
        for ticker in found:
            ticker = ticker.upper()
            if ticker not in stocks:
                stocks[ticker] = {"ticker": ticker, "name": ticker_map.get(ticker,""), "score": 0, "mentions": 0, "reasons": []}
            stocks[ticker]["score"] += sentiment * sw
            stocks[ticker]["mentions"] += 1
            stocks[ticker]["reasons"].append({"title": title[:80], "sentiment": r["sentiment"], "source": r["source"].replace("🔥 ","")})
    return sorted(stocks.values(), key=lambda x: -x["score"])[:15]

# ════ 报告生成 ════

def _gen_reason_cn(label, reasons):
    if not reasons: return "新闻提及"
    import news
    titles = "\n".join(f"[{r['sentiment']}] {r['title'][:80]}" for r in reasons[:5])
    prompt = f"根据关于{label}的以下新闻，写一句中文选股理由（30字以内），聚焦关键催化剂或风险。只回复一句话。\n\n{titles}"
    try: return news.call_qwen(prompt).strip().strip('"').strip("'")
    except: return "—"

def gen_picks_report_cn(scored, summary):
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 💡 A股选股参考 · {dt}", "", f"**扫描新闻**: {summary.get('total',0)} 条 | **发现股票**: {len(scored)} 只", "", "> ⚠️ 本报告基于新闻情绪量化评分，不构成投资建议。", "", "---", "", "## 🏆 综合推荐", "", "| # | 股票/代码 | 情绪分 | 提及 | 选股理由 |", "|---|---|---|---|---|"]
    for i, s in enumerate(scored[:10]):
        name = s.get("name") or s.get("code","?")
        code = s.get("code","")
        emoji = "🟢" if s["score"] > 1 else ("🔴" if s["score"] < 0 else "⚪")
        reason = _gen_reason_cn(f"{name}({code})", s.get("reasons",[]))
        lines.append(f"| {i+1} | {emoji} {name}<br><small>{code}</small> | {s['score']:+.1f} | {s['mentions']} | {reason[:80]} |")
    risks = [s for s in scored if s["score"] < -1]
    if risks:
        lines.extend(["", "## ⚠️ 风险提示", ""])
        for s in risks[:5]:
            lines.append(f"- **{s.get('name') or s.get('code')}** 情绪 {s['score']:.0f}，{s['mentions']} 次负面提及")
    lines.extend(["", "---", "", "📡 数据来源：新闻情绪分析 · 仅供参考"])
    return "\n".join(lines)

def gen_picks_report_us(scored, summary):
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 💡 美股选股参考 · {dt}", "", f"**扫描新闻**: {summary.get('total',0)} 篇 | **发现股票**: {len(scored)} 只", "", "> ⚠️ 基于新闻情绪量化评分，不构成投资建议。", "", "---", "", "## 🏆 综合推荐", "", "| # | 股票 | 情绪分 | 提及 | 选股理由 |", "|---|---|---|---|---|"]
    for i, s in enumerate(scored[:10]):
        emoji = "🟢" if s["score"] > 1 else ("🔴" if s["score"] < 0 else "⚪")
        reason = _gen_reason_cn(f"${s['ticker']}", s.get("reasons",[]))
        lines.append(f"| {i+1} | {emoji} ${s['ticker']} | {s['score']:+.1f} | {s['mentions']} | {reason[:80]} |")
    risks = [s for s in scored if s["score"] < -1]
    if risks:
        lines.extend(["", "## ⚠️ 风险提示", ""])
        for s in risks[:5]:
            lines.append(f"- **${s['ticker']}** 情绪 {s['score']:.0f}，{s['mentions']} 次负面提及")
    lines.extend(["", "---", "", "📡 数据来源：Yahoo Finance · CNBC · Google News | 仅供参考"])
    return "\n".join(lines)

# ════ 独立测试 ════

if __name__ == "__main__":
    import news, scraper as sc, scraper_us as sc_us
    print("\n💡 A股选股"); items_cn = sc.fetch_news(limit=30)
    if items_cn:
        results_cn = news.analyze_news(items_cn); picks_cn = score_stocks_cn(results_cn, items_raw=items_cn)
        print(f"发现 {len(picks_cn)} 只"); [print(f"  {p.get('name') or p['code']} {p['score']:+.1f}") for p in picks_cn[:5]]
    print("\n💡 美股选股"); items_us = sc_us.fetch_news(limit=30)
    if items_us:
        import run_us; results_us = run_us.analyze_us(items_us); picks_us = score_stocks_us(results_us, items_raw=items_us)
        print(f"发现 {len(picks_us)} tickers"); [print(f"  ${p['ticker']} {p['score']:+.1f}") for p in picks_us[:5]]
