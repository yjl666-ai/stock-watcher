"""scraper_us.py — 美股财经新闻抓取"""
import requests, re, json
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_yahoo():
    items = []
    try:
        r = requests.get("https://finance.yahoo.com/news/rssindex", headers=HEADERS, timeout=15)
        import xml.etree.ElementTree as ET
        clean = re.sub(r"<!\[CDATA\[|\]\]>", "", r.text)
        root = ET.fromstring(clean)
        for item in list(root.iter("item"))[:20]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:200]
            if title and link and "Yahoo" not in title:
                items.append({"source": "Yahoo Finance", "title": title, "summary": desc, "link": link})
        print(f"  Yahoo Finance: {len(items)} 条")
    except Exception as e:
        print(f"  Yahoo Finance 失败: {e}")
    return items


def fetch_cnbc():
    items = []
    try:
        r = requests.get("https://www.cnbc.com/id/100003114/device/rss/rss.html", headers=HEADERS, timeout=15)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        for item in list(root.iter("item"))[:20]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:200]
            if title and link:
                items.append({"source": "CNBC", "title": title, "summary": desc, "link": link})
        print(f"  CNBC: {len(items)} 条")
    except Exception as e:
        print(f"  CNBC 失败: {e}")
    return items


def fetch_google():
    items = []
    try:
        url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB"
        r = requests.get(url, headers=HEADERS, timeout=15)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        for item in list(root.iter("item"))[:20]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:200]
            if title and link and "Google" not in title:
                items.append({"source": "Google News", "title": title, "summary": desc, "link": link})
        print(f"  Google News: {len(items)} 条")
    except Exception as e:
        print(f"  Google News 失败: {e}")
    return items


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


def fetch_news(limit=30):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from collections import Counter
    fetchers = [("Yahoo Finance", fetch_yahoo), ("CNBC", fetch_cnbc), ("Google News", fetch_google)]
    all_items = []
    print("📡 抓取美股新闻...")
    with ThreadPoolExecutor(max_workers=3) as ex:
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