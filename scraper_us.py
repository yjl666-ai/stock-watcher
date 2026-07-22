"""scraper_us.py — 美股财经新闻抓取（6源）"""
import requests, re, json
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _parse_rss_items(url, source_name, limit=40):
    """通用 RSS 解析"""
    import xml.etree.ElementTree as ET
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        # 修复非法 XML 实体（如 Benzinga 的 &nbsp;）
        clean = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)[a-zA-Z]+;", "&amp;", r.text)
        clean = re.sub(r"<!\[CDATA\[|\]\]>", "", clean)
        root = ET.fromstring(clean)
        for item in list(root.iter("item"))[:limit]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:200]
            # 过滤掉源站自身的标题
            skip = {"Yahoo", "CNBC", "Google", "Benzinga", "Investing"}
            if title and link and not any(s in title for s in skip):
                items.append({"source": source_name, "title": title, "summary": desc, "link": link})
    except Exception as e:
        print(f"  {source_name} 失败: {e}")
    return items


def fetch_yahoo(): return _parse_rss_items("https://finance.yahoo.com/news/rssindex", "Yahoo Finance", limit=40)
def fetch_cnbc(): return _parse_rss_items("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", limit=40)
def fetch_google(): return _parse_rss_items("https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB", "Google News", limit=40)
def fetch_google_tech(): return _parse_rss_items("https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB", "Google Tech", limit=30)
def fetch_benzinga(): return _parse_rss_items("https://www.benzinga.com/feed", "Benzinga", limit=40)
def fetch_investing(): return _parse_rss_items("https://www.investing.com/rss/news.rss", "Investing.com", limit=30)


def deduplicate(items, threshold=0.65):
    from difflib import SequenceMatcher
    def _sim(a, b):
        return SequenceMatcher(None, re.sub(r"[^a-zA-Z0-9]", "", a.lower()),
                               re.sub(r"[^a-zA-Z0-9]", "", b.lower())).ratio()
    merged, used = [], [False] * len(items)
    for i, item in enumerate(items):
        if used[i]: continue
        group = [item]
        for j in range(i+1, len(items)):
            if used[j] or items[j]["source"] == item["source"]: continue
            if _sim(item["title"], items[j]["title"]) > threshold:
                group.append(items[j]); used[j] = True
        used[i] = True
        if len(group) > 1:
            group[0]["source"] = f"🔥 {' · '.join(g['source'] for g in group)}"
        merged.append(group[0])
    return merged


def fetch_news(limit=60):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from collections import Counter
    fetchers = [
        ("Yahoo Finance", fetch_yahoo),
        ("CNBC", fetch_cnbc),
        ("Google News", fetch_google),
        ("Google Tech", fetch_google_tech),
        ("Benzinga", fetch_benzinga),
        ("Investing.com", fetch_investing),
    ]
    all_items = []
    print(f"📡 抓取美股新闻（{len(fetchers)} 个源）...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(f): name for name, f in fetchers}
        for f in as_completed(futures):
            try: all_items.extend(f.result())
            except Exception as e: print(f"  [异常] {e}")
    deduped = deduplicate(all_items)
    hot = sum(1 for it in deduped if it["source"].startswith("🔥"))
    source_items = {}
    for it in deduped:
        src = it["source"].replace("🔥 ", "")
        source_items.setdefault(src, []).append(it)
    result, sources, idx = [], list(source_items.keys()), [0] * len(source_items)
    while len(result) < limit:
        added = False
        for i, src in enumerate(sources):
            if idx[i] < len(source_items[src]):
                result.append(source_items[src][idx[i]]); idx[i] += 1; added = True
        if not added: break
    print(f"  去重前 {len(all_items)} → 去重后 {len(deduped)} ({hot} 交叉)")
    for s, n in Counter(it["source"] for it in result).most_common():
        print(f"    {s}: {n}")
    return result[:limit]


if __name__ == "__main__":
    items = fetch_news(20)
    print(f"\n总计 {len(items)} 条")
    for i in items[:5]:
        print(f"  [{i['source']}] {i['title'][:60]}")