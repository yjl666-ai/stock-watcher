"""picks.py — 美股新闻情绪选股评分引擎 + 实时行情"""
import re, json, sys, requests as _req
from pathlib import Path
from datetime import datetime
from collections import Counter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

SOURCE_WEIGHTS = {
    "Yahoo Finance": 1.0, "CNBC": 1.1, "Google News": 0.9,
}

def _source_weight(source):
    for k, v in SOURCE_WEIGHTS.items():
        if k in source: return v
    return 1.0

# ════ 美股公司→ticker 内置映射 ════

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
    "airbus": ("EADSY","Airbus"), "nebius": ("NBIS","Nebius"),
    "spotify": ("SPOT","Spotify"), "snap": ("SNAP","Snap"),
    "crowdstrike": ("CRWD","CrowdStrike"), "lockheed": ("LMT","Lockheed"),
    "iren": ("IREN","IREN Ltd"),
}

NON_US_SUFFIX = {'.PA','.L','.DE','.AS','.SW','.MI','.MC','.HK','.T','.KS'}

def _is_us_ticker(t):
    for s in NON_US_SUFFIX:
        if t.upper().endswith(s): return False
    return len(t) <= 5 and not t[0].isdigit()


def extract_us_tickers(items):
    import news
    result = {}
    for it in items:
        t = it["title"].lower()
        for kw, (ticker, name) in KNOWN_US.items():
            if kw in t:
                result[ticker] = name
    titles = "\n".join(f"{i+1}. {it['title'][:100]}" for i, it in enumerate(items[:30]))
    prompt = f"从以下英文财经新闻标题中提取被提及的美股上市公司及股票代码。\n\n{titles}\n\n只返回JSON：[{{\"ticker\":\"AAPL\",\"company\":\"Apple\"}}, ...]"
    try:
        text = news.call_qwen(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            for t in json.loads(m.group()):
                result[t["ticker"].upper()] = t.get("company","")
    except: pass
    return result


def score_stocks_us(analyzed_results, items_raw=None):
    ticker_map = extract_us_tickers(items_raw) if items_raw else {}
    stocks = {}
    NOISE = {"THE","A","AN","IS","IT","IN","ON","AT","TO","FOR","OF","AND","OR",
             "BUT","NOT","NO","WE","US","BE","ITS","FROM","WITH","OVER","MORE",
             "JUST","AFTER","BACK","DOWN","EVEN","FIRST","HAS","LIKE","MAY","NEW",
             "NEXT","ONLY","RISE","THAN","THAT","THEM","THEN","THIS","WAS","WERE"}
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
        found = {t for t in found if t not in NOISE and len(t) >= 1 and _is_us_ticker(t)}
        for ticker in found:
            ticker = ticker.upper()
            if ticker not in stocks:
                stocks[ticker] = {"ticker": ticker, "name": ticker_map.get(ticker,""),
                                  "score": 0, "mentions": 0, "reasons": []}
            stocks[ticker]["score"] += sentiment * sw
            stocks[ticker]["mentions"] += 1
            stocks[ticker]["reasons"].append({"title": title[:80], "sentiment": r["sentiment"],
                                              "source": r["source"].replace("🔥 ","")})
    return sorted(stocks.values(), key=lambda x: -x["score"])[:15]

# ════ Yahoo Finance 实时行情 ════

def fetch_quote(ticker):
    """查实时行情，返回 {price, chg_day, chg_5d, chg_20d, pct_52w, advice}"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
        d = _req.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8).json()["chart"]["result"][0]
        m = d["meta"]
        closes = [c for c in d["indicators"]["quote"][0]["close"] if c is not None]
        price = m["regularMarketPrice"]
        prev = closes[-2] if len(closes) >= 2 else price
        chg_day = round((price - prev) / prev * 100, 2)
        ma5 = sum(closes[-5:])/5 if len(closes)>=5 else price
        ma20 = sum(closes[-20:])/20 if len(closes)>=20 else price
        chg_5d = round((closes[-1]/closes[-6]-1)*100, 2) if len(closes)>=6 else 0
        chg_20d = round((closes[-1]/closes[-21]-1)*100, 2) if len(closes)>=21 else 0
        hi, lo = m.get("fiftyTwoWeekHigh",price), m.get("fiftyTwoWeekLow",price)
        pct_52 = round((price - lo) / (hi - lo) * 100) if hi != lo else 50
        return {
            "price": price, "chg_day": chg_day, "chg_5d": chg_5d,
            "chg_20d": chg_20d, "pct_52w": pct_52, "ma5": ma5, "ma20": ma20,
        }
    except: return None


def _gen_advice(ticker, score, q):
    """根据情绪+技术面生成中文建议"""
    if not q: return "暂无行情"
    p, d5, d20 = q["price"], q["chg_5d"], q["chg_20d"]
    p52 = q["pct_52w"]
    trend = "强势" if d5 > 3 else ("弱势" if d5 < -5 else "震荡")
    position = "高位" if p52 > 80 else ("低位" if p52 < 20 else "中位")
    
    lines = []
    lines.append(f"💰 \${p:.2f} | 今日 {q['chg_day']:+.2f}% | 5日 {d5:+.2f}%")
    lines.append(f"📊 {trend} · {position}(52周{p52}%位)")
    
    if score >= 1.5 and d5 > -3 and p52 < 80:
        lines.append("✅ 建议关注：情绪+技术双支撑")
    elif score >= 1 and p52 < 30:
        lines.append("🟡 低位待反转，观望等信号")
    elif p52 > 85:
        lines.append("⚠️ 高位追涨风险大，等回调")
    elif d5 < -5:
        lines.append("🔴 短期急跌，等止跌再考虑")
    elif score < 0:
        lines.append("❌ 情绪偏空，暂不建议")
    else:
        lines.append("⚪ 中性观望")
    
    return "<br>".join(lines)


def _gen_reason_cn(label, reasons):
    if not reasons: return "新闻提及"
    import news
    titles = "\n".join(f"[{r['sentiment']}] {r['title'][:80]}" for r in reasons[:5])
    prompt = f"根据关于{label}的以下新闻，写一句中文选股理由（30字以内），聚焦关键催化剂或风险。只回复一句话。\n\n{titles}"
    try: return news.call_qwen(prompt).strip().strip('"').strip("'")
    except: return "—"


def gen_picks_report(scored, summary):
    """美股选股 Markdown（含实时行情+操作建议）"""
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 批量查行情
    quotes = {}
    for s in scored[:10]:
        quotes[s["ticker"]] = fetch_quote(s["ticker"])
    
    lines = [f"# 💡 美股选股参考 · {dt}", "",
             f"**扫描新闻**: {summary.get('total',0)} 篇 | **发现股票**: {len(scored)} 只",
             "", "> ⚠️ 基于新闻情绪+实时行情量化评分，不构成投资建议。", "",
             "---", "", "## 🏆 综合推荐", "",
             "| # | 股票 | 情绪分 | 实时行情 | 选股理由 | 操作建议 |",
             "|---|---|---|---|---|---|"]
    
    for i, s in enumerate(scored[:10]):
        emoji = "🟢" if s["score"] > 1 else ("🔴" if s["score"] < 0 else "⚪")
        name = s.get("name", "")
        display = f"{name} ${s['ticker']}" if name else f"${s['ticker']}"
        reason = _gen_reason_cn(display, s.get("reasons",[]))
        q = quotes.get(s["ticker"])
        if q:
            quote_str = f"\${q['price']:.2f}<br><small>{q['chg_day']:+.2f}% / 5日{q['chg_5d']:+.2f}%</small>"
        else:
            quote_str = "—"
        advice = _gen_advice(s["ticker"], s["score"], q) if q else "—"
        lines.append(f"| {i+1} | {emoji} {display} | {s['score']:+.1f} | {quote_str} | {reason[:60]} | {advice} |")

    risks = [s for s in scored if s["score"] < -1]
    if risks:
        lines.extend(["", "## ⚠️ 风险提示", ""])
        for s in risks[:5]:
            lines.append(f"- **{s.get('name') or s['ticker']}** 情绪 {s['score']:.0f}，{s['mentions']} 次负面提及")

    lines.extend(["", "---", "", "📡 实时行情：Yahoo Finance | 新闻：Yahoo Finance · CNBC · Google News | AI：通义千问"])
    return "\n".join(lines)


if __name__ == "__main__":
    import scraper_us, run_us
    items = scraper_us.fetch_news(limit=30)
    if items:
        results = run_us.analyze_us(items)
        picks = score_stocks_us(results, items_raw=items)
        print(f"发现 {len(picks)} 只")
        for p in picks[:5]:
            print(f"  ${p['ticker']:6s}  {p['score']:+.1f}  ({p['mentions']}x)")