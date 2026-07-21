"""news.py — 抓财经新闻 + AI 总结影响（无第三方 RSS 依赖）"""
import requests
import re
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ════ 股票行情 ════

def extract_stocks(results):
    """从 AI 结果中提取股票代码 → 查实时行情"""
    import re as _re, requests as _req
    quotes = []
    seen = set()

    for r in results:
        # 提取标题中 6 位代码
        for code in _re.findall(r'\b(\d{6})\b', r["title"]):
            if code in seen or code.startswith("0"):
                continue
            seen.add(code)
            exchange = "sh" if code.startswith(("6", "9")) else "sz"
            try:
                resp = _req.get(
                    f"http://hq.sinajs.cn/list={exchange}{code}",
                    headers={"Referer": "https://finance.sina.com.cn"},
                    timeout=4,
                )
                resp.encoding = "gbk"
                parts = resp.text.split('"')[1].split(",")
                if len(parts) > 3 and parts[3]:
                    price = float(parts[3])
                    prev = float(parts[2]) if parts[2] else price
                    chg = round((price - prev) / prev * 100, 2) if prev else 0
                    emoji = "🔴" if chg > 0 else ("🟢" if chg < 0 else "⚪")
                    quotes.append({
                        "name": parts[0],
                        "code": code,
                        "price": price,
                        "change": chg,
                        "emoji": emoji,
                        "title": r["title"][:40],
                    })
            except Exception:
                pass
        if len(quotes) >= 6:
            break
    return quotes


# ════ 历史对比 ════

def compare_with_yesterday(results):
    """对比昨天报告"""
    today = datetime.now()
    yesterday = today.strftime("%Y%m%d")
    today_str = today.strftime("%Y-%m-%d")

    # 找最近的旧报告
    reports_dir = Path(__file__).parent / "reports"
    old_files = sorted(reports_dir.glob("report_*.md"), reverse=True)
    if not old_files:
        return None

    prev = old_files[0]
    prev_text = prev.read_text(encoding="utf-8")

    # 提取旧报告的核心数据
    import re as _re
    prev_score = _re.search(r'(\d+)/100', prev_text)
    prev_score = int(prev_score.group(1)) if prev_score else None
    prev_date = _re.search(r'\d{4}-\d{2}-\d{2}', prev_text)
    prev_date = prev_date.group(0) if prev_date else "?"

    # 当前报告分数
    bullish = [r for r in results if r["sentiment"] == "看涨"]
    bearish = [r for r in results if r["sentiment"] == "看跌"]
    neutral = [r for r in results if r["sentiment"] == "中性"]
    total = len(results) or 1
    curr_score = round((len(bullish) - len(bearish)) / total * 50 + 50)

    # 提取旧板块热度
    prev_sectors = set()
    for m in _re.finditer(r'[🟢🔴🔥⚪]\s+(\S+)', prev_text):
        prev_sectors.add(m.group(1))

    # 当前板块
    from collections import Counter
    curr_sector_count = Counter()
    for r in results:
        for s in r.get("sectors", []):
            curr_sector_count[s] += 1
    curr_sectors = set(s for s, _ in curr_sector_count.most_common(5))

    new_sectors = curr_sectors - prev_sectors
    fading = prev_sectors - curr_sectors

    score_diff = curr_score - prev_score if prev_score else 0
    arrow = "↑" if score_diff > 0 else ("↓" if score_diff < 0 else "→")

    return {
        "prev_date": prev_date,
        "prev_score": prev_score,
        "curr_score": curr_score,
        "score_diff": score_diff,
        "arrow": arrow,
        "new_sectors": new_sectors,
        "fading_sectors": fading,
    }

# ── RSS 源（公开地址） ──
# 优先用 feedburner/google feeds 代理，绕过部分站点反爬
SOURCES = {
    # 财经主流
    "人民网财经": "http://www.people.com.cn/rss/finance.xml",
    "新华网财经": "http://www.news.cn/rss/finance.xml",
    "中国证券网": "https://www.cnstock.com/rss",
    "上海证券报": "https://paper.cnstock.com/rss",
    # 科技/创投
    "36氪": "https://www.36kr.com/feed",
    "钛媒体": "https://www.tmtpost.com/rss",
    "IT之家": "https://www.ithome.com/rss/",
    # 综合
    "联合早报": "https://www.zaobao.com/rss/finance.xml",
    "BBC中文": "https://www.bbc.com/zhongwen/simp/index.xml",
}


def fetch_rss(url, limit=15):
    """解析 RSS XML（用 stdlib，不用 feedparser）"""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "")
            # 去掉 HTML 标签
            desc_clean = re.sub(r"<[^>]+>", "", desc).strip()[:200]
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "summary": desc_clean,
                })
            if len(items) >= limit:
                break
        return items
    except Exception as e:
        print(f"  [抓取失败] {url}: {e}")
        return []


def fetch_news(limit=40):
    """从多个 RSS 源并发抓新闻"""
    def _fetch_one(source_url):
        source, url = source_url
        print(f"  抓 [{source}]...")
        items = fetch_rss(url, limit=30)
        for it in items:
            it["source"] = source
        return items

    all_items = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_fetch_one, (s, u)) for s, u in SOURCES.items()]
        for f in as_completed(futures):
            try:
                all_items.extend(f.result())
            except Exception as e:
                print(f"  [异常] {e}")
    return all_items[:limit]


def call_qwen(prompt):
    """调通义千问 qwen-plus"""
    api_key = Path.home().joinpath(".config", "dashscope_key.txt").read_text(encoding="utf-8").strip()
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    r = requests.post(url, headers=headers, json=data, timeout=30)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def analyze_news(news_list):
    """AI 分析每条新闻对股市的影响"""
    results = []
    for n in news_list:
        prompt = f"""分析以下财经新闻对 A 股 / 港股 / 美股 的影响。

标题: {n['title']}
摘要: {n['summary']}

请用 JSON 格式回答（只输出 JSON，不要其他内容）:
{{
  "sentiment": "看涨" 或 "看跌" 或 "中性",
  "sectors": ["受影响板块1", "板块2"],
  "impact": "一句话说明影响逻辑"
}}"""
        try:
            text = call_qwen(prompt)
            m = re.search(r'\{.*?\}', text, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
            else:
                parsed = {"sentiment": "中性", "sectors": [], "impact": text[:80]}
        except Exception as e:
            parsed = {"sentiment": "中性", "sectors": [], "impact": f"分析失败: {e}"}
        parsed["title"] = n["title"]
        parsed["link"] = n["link"]
        parsed["source"] = n["source"]
        results.append(parsed)
        print(f"  [{parsed['sentiment']}] {n['title'][:40]}...")
    return results


def generate_summary(results):
    """AI 写大盘摘要 + 情绪评分"""
    bullish = [r for r in results if r["sentiment"] == "看涨"]
    bearish = [r for r in results if r["sentiment"] == "看跌"]
    neutral = [r for r in results if r["sentiment"] == "中性"]
    total = len(results) or 1
    score = round((len(bullish) - len(bearish)) / total * 50 + 50)  # 0-100

    # 情绪标签
    if score >= 65: emoji, label = "😀", "偏多"
    elif score <= 35: emoji, label = "😟", "偏空"
    else: emoji, label = "😐", "中性"

    # 提取高频板块（不考虑情绪，纯出现次数）
    from collections import Counter
    all_sectors = []
    for r in results:
        all_sectors.extend(r.get("sectors", []))
    top_keywords = [w for w, _ in Counter(all_sectors).most_common(5)]

    # 选 5 条最有代表性的给 AI 总结
    sample = bullish[:3] + bearish[:2]
    titles = "\n".join(f"- [{r['sentiment']}] {r['title']}" for r in sample)
    prompt = f"""根据以下今日财经新闻摘要，写一段 3 句话的大盘综述（中文，150 字以内）。
涵盖：整体方向、主要驱动力、主要风险。不要提具体建议。

情绪: 看涨 {len(bullish)} / 看跌 {len(bearish)} / 中性 {len(neutral)}
高频词: {', '.join(top_keywords)}
代表新闻:
{titles}"""

    try:
        text = call_qwen(prompt)
    except Exception:
        text = "AI 摘要生成失败"

    return {
        "score": score,
        "emoji": emoji,
        "label": label,
        "keywords": top_keywords,
        "text": text.strip(),
    }


def generate_heatmap(results):
    """板块热度图：出现次数 × 情绪权重"""
    from collections import Counter
    raw = Counter()  # 纯出现次数
    weighted = Counter()  # 情绪加权

    for r in results:
        sentiment = r["sentiment"]
        w = 1 if sentiment == "看涨" else (-1 if sentiment == "看跌" else 0)
        for s in r.get("sectors", []):
            raw[s] += 1
            weighted[s] += w

    # 按加权热度排序
    ranked = sorted(weighted.items(), key=lambda x: (-x[1], -raw[x[0]]))[:10]
    max_cnt = max(raw.values()) if raw else 1

    lines = []
    for name, w in ranked:
        cnt = raw[name]
        bar_len = max(1, int(cnt / max_cnt * 12))
        bar = "█" * bar_len
        if w >= 3: tag = "🔥"
        elif w > 0: tag = "🟢"
        elif w < 0: tag = "🔴"
        else: tag = "⚪"
        sign = "+" if w > 0 else ""
        lines.append((tag, name, bar, f"{sign}{w}", cnt))
    return lines


def generate_report(results):
    """生成 Markdown 报告"""
    from collections import Counter
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    bullish = [r for r in results if r["sentiment"] == "看涨"]
    bearish = [r for r in results if r["sentiment"] == "看跌"]
    neutral = [r for r in results if r["sentiment"] == "中性"]

    source_counts = Counter(r["source"] for r in results)
    source_lines = " · ".join(f"{s} {n}" for s, n in source_counts.most_common())

    # 情绪摘要
    summary = generate_summary(results)

    # 板块热度
    heatmap = generate_heatmap(results)

    # 股票行情
    stocks = extract_stocks(results)

    # 历史对比
    comp = compare_with_yesterday(results)

    lines = [
        f"# 📊 股市每日观察 · {today}",
        "",
        f"**来源**: {source_lines}",
        "",
        "---",
        "",
        "## 📈 大盘情绪",
        "",
        f"| 情绪评分 | 方向 | 看涨 | 看跌 | 中性 |",
        f"|---------|------|-----|-----|-----|",
        f"| {summary['score']}/100 {summary['emoji']} | {summary['label']} | {len(bullish)} | {len(bearish)} | {len(neutral)} |",
        "",
        f"> {summary['text']}",
        "",
    ]

    # 历史对比
    if comp and comp["prev_score"] is not None:
        new_s = "、".join(comp["new_sectors"]) if comp["new_sectors"] else "—"
        fade_s = "、".join(comp["fading_sectors"]) if comp["fading_sectors"] else "—"
        score_diff = comp["score_diff"]
        sign = "+" if score_diff > 0 else ""
        lines.extend([
            "",
            "📅 **vs 昨日**（{prev}）: 情绪 {prev_s}{arrow}{curr_s} | 新增热点: {new} | 消退: {fade}".format(
                prev=comp["prev_date"],
                prev_s=comp["prev_score"],
                arrow=comp["arrow"],
                curr_s=comp["curr_score"],
                new=new_s,
                fade=fade_s,
            ),
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 🔥 板块热度",
        "",
        "| 板块 | 热度 |",
        "|------|------|",
    ])
    for tag, name, bar, weight_str, cnt in heatmap:
        lines.append(f"| {tag} {name} | {bar} {weight_str}（{cnt}条） |")

    lines.extend([
        "",
        "---",
        "",
    ])

    # 股票行情
    if stocks:
        lines.extend([
            "## 📈 热门股票今日表现",
            "",
            "| 股票 | 代码 | 现价 | 涨跌幅 | 关联新闻 |",
            "|------|------|------|--------|----------|",
        ])
        for s in stocks:
            sign = "+" if s["change"] > 0 else ""
            lines.append(
                f"| {s['emoji']} {s['name']} | {s['code']} | {s['price']:.2f} | {sign}{s['change']}% | {s['title']} |"
            )
        lines.extend(["", "---", ""])

    for label, items in [("🟢 看涨", bullish), ("🔴 看跌", bearish), ("⚪ 中性", neutral)]:
        if not items:
            continue
        lines.append(f"## {label} ({len(items)})")
        for r in items:
            sectors = "、".join(r["sectors"]) if r["sectors"] else "—"
            lines.append(f"- **{r['title']}**")
            lines.append(f"  - 来源: [{r['source']}]({r['link']})")
            lines.append(f"  - 影响板块: {sectors}")
            lines.append(f"  - 逻辑: {r['impact']}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("📡 抓取财经新闻...")
    news = fetch_news(limit=20)
    print(f"  抓到 {len(news)} 条")

    print("🤖 AI 分析中...")
    results = analyze_news(news)

    report = generate_report(results)

    report_path = Path(__file__).parent / f"report_{datetime.now():%Y%m%d_%H%M}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 报告已生成: {report_path}")
    print("\n" + report[:1500] + ("..." if len(report) > 1500 else ""))