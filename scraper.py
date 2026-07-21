"""scraper.py — 多源财经新闻抓取 + 去重合并"""
import requests
import re
import json
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def fetch_eastmoney():
    """东方财富公告"""
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {"cb": "jQuery", "sr": "-1", "page_size": 30, "page_index": 1,
              "ann_type": "A", "client_source": "web", "stock_list": "", "f_node": "0", "s_node": "0"}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = json.loads(re.sub(r"^jQuery\(|\)\s*$", "", r.text))
        items = []
        for item in data.get("data", {}).get("list", [])[:20]:
            title, code = item.get("title", ""), item.get("art_code", "")
            if title and code:
                items.append({"source": "东方财富", "title": title, "summary": "",
                              "link": f"https://data.eastmoney.com/notices/detail/{code}.html"})
        print(f"  东方财富: {len(items)} 条")
        return items
    except Exception as e:
        print(f"  东方财富 失败: {e}"); return []


def fetch_cls():
    """财联社电报 — 国内最快财经快讯"""
    url = "https://www.cls.cn/api/telegraph/list"
    params = {"app": "CailianpressWeb", "os": "web", "sv": "8.4.6",
              "rn": 30, "refresh_type": 1, "hasFirstVipArticle": 0}
    headers = {**HEADERS, "Referer": "https://www.cls.cn/telegraph"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = []
        for item in data.get("data", {}).get("roll_data", [])[:30]:
            title = item.get("title", "") or item.get("brief", "")
            cid = item.get("id", "")
            if title:
                items.append({"source": "财联社", "title": title,
                              "summary": item.get("brief", "")[:200],
                              "link": f"https://www.cls.cn/detail/{cid}"})
        print(f"  财联社: {len(items)} 条")
        return items
    except Exception as e:
        # 备用：直接解析 JSON 字符串（可能不是 dict 格式）
        try:
            raw = r.text if 'r' in dir() else ""
            data = json.loads(raw)
            items = []
            roll = data.get("data", {}).get("roll_data", [])
            for item in roll[:30]:
                title = item.get("title", "") or item.get("brief", "")
                cid = item.get("id", "")
                if title:
                    items.append({"source": "财联社", "title": title,
                                  "summary": item.get("brief", "")[:200],
                                  "link": f"https://www.cls.cn/detail/{cid}"})
            print(f"  财联社(备用): {len(items)} 条")
            return items
        except:
            pass
        print(f"  财联社 失败: {e}"); return []


def fetch_sina():
    """新浪财经 — 备用 lid 参数"""
    for lid in ["2516", "2509", "2512"]:
        url = "https://feed.mix.sina.com.cn/api/roll/get"
        params = {"pageid": "153", "lid": lid, "k": "", "num": "20", "page": "1"}
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            data = r.json()
            items = []
            for item in data.get("result", {}).get("data", [])[:20]:
                title = item.get("title", "")
                if title:
                    items.append({"source": "新浪财经", "title": title,
                                  "summary": re.sub(r"<[^>]+>", "", item.get("intro", ""))[:200],
                                  "link": item.get("url", "")})
            if items:
                print(f"  新浪财经(lid={lid}): {len(items)} 条")
                return items
        except Exception:
            continue
    print(f"  新浪财经: 0 条"); return []


def fetch_people():
    """人民网财经 RSS"""
    import xml.etree.ElementTree as ET
    url = "http://www.people.com.cn/rss/finance.xml"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            items.append({"source": "人民网财经",
                          "title": item.findtext("title", "").strip(),
                          "summary": re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:200],
                          "link": item.findtext("link", "").strip()})
        print(f"  人民网财经: {len(items)} 条")
        return items[:20]
    except Exception as e:
        print(f"  人民网财经 失败: {e}"); return []


# ════════════════════════════════════════════
#  去重：多源报道同一事件 → 合并标记
# ════════════════════════════════════════════

def _similar(a: str, b: str) -> float:
    """标题相似度 (0~1)"""
    # 去掉标点对比实质内容
    clean = lambda s: re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", s)
    return SequenceMatcher(None, clean(a), clean(b)).ratio()


def deduplicate(items, threshold=0.7):
    """跨源去重：多站同时报同一事件 → 合并标记 🔥"""
    merged = []
    used = [False] * len(items)
    for i, item in enumerate(items):
        if used[i]: continue
        group = [item]
        for j in range(i + 1, len(items)):
            if used[j]: continue
            # 只跨源合并，同源不合并
            if items[j]["source"] == item["source"]:
                continue
            if _similar(item["title"], items[j]["title"]) > threshold:
                group.append(items[j])
                used[j] = True
        used[i] = True
        if len(group) > 1:
            sources = " · ".join(g["source"] for g in group)
            group[0]["source"] = f"🔥 {sources}"
        merged.append(group[0])
    return merged


def fetch_news(limit=40):
    """并发抓取 + 去重"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    fetchers = [
        ("东方财富", fetch_eastmoney),
        ("新浪财经", fetch_sina),
        ("人民网财经", fetch_people),
    ]
    all_items = []
    print("📡 抓取财经新闻...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(f): name for name, f in fetchers}
        for f in as_completed(futures):
            try:
                all_items.extend(f.result())
            except Exception as e:
                print(f"  [异常] {e}")

    before = len(all_items)
    deduped = deduplicate(all_items)
    hot = sum(1 for it in deduped if it["source"].startswith("🔥"))
    print(f"\n  去重前 {before} → 去重后 {len(deduped)} ({hot} 条多源重点)")
    return deduped[:limit]


if __name__ == "__main__":
    items = fetch_news(limit=40)
    from collections import Counter
    cnt = Counter(i["source"] for i in items)
    print(f"\n总计 {len(items)} 条:")
    for s, n in cnt.most_common():
        print(f"  {s}: {n}")