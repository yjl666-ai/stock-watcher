# stock-watcher 项目交接文档

> 写给 Codex：这是我和袁嘉乐协作开发的美股观察网站，部署在 Render。代码、配置、文件位置都在这里，可以接着改。

---

## 1. 项目一句话

**每日北京时间 9:00 自动抓取美股新闻（6 源 60 条）→ AI（通义千问）分析情绪 → 生成报告 + 选股 → 网站展示给用户。**

支持：
- 美股大盘情绪评分 + 热门板块热度 + 个股提及
- 选股推荐表（含公司名、情绪分、实时行情、选股理由、操作建议）
- 10 只股票逐只深度分析（指标表 + 入场价 + 止损价）
- 股票名点击跳转 BBAE 详情页
- 历史报告存档

---

## 2. 关键位置

### 线上

| 项目 | URL |
|------|-----|
| **网站** | https://stock-watcher-2dbs.onrender.com/ |
| 报告首页（美股市场观察） | `/` |
| 美股选股（综合推荐 + 10只深度分析） | `/picks` |
| 历史报告 | `/history` |
| 手动刷新触发 | `/refresh` |
| 健康检查 | `/health` |

### GitHub

| 项目 | URL |
|------|-----|
| 仓库 | https://github.com/yjl666-ai/stock-watcher |
| 分支 | main |
| SSH URL | `git@github.com:yjl666-ai/stock-watcher.git` |

### Render

| 项目 | 值 |
|------|-----|
| Service 名 | stock-watcher |
| URL | https://dashboard.render.com/ |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `web: python web.py`（注意冒号后空格）|
| 环境变量 | `DASHSCOPE_API_KEY`=阿里云百炼 API Key |
| 自动唤醒 | 每日北京时间 9:00 跑一次流水线 |

### 本地代码

| 路径 | 作用 |
|------|------|
| `C:\Users\12648\stock-watcher-new\` | **本地工作目录（推荐）** |
| `C:\Users\12648\.config\dashscope_key.txt` | 本地 DashScope API Key |
| `C:\Users\12648\AppData\Local\Hermes\` | Hermes 桌面 App 数据 |

> ⚠️ 注意：`C:\Users\12648\safety-notice-review\stock-watcher\` 是**旧副本**，不是工作目录。直接去 `stock-watcher-new`。

---

## 3. 文件清单

| 文件 | 行数 | 作用 |
|------|------|------|
| `web.py` | ~200 | Flask 网站 + 北京时间 9 点调度器 |
| `scraper_us.py` | ~120 | 抓 6 个美股新闻源（Yahoo/CNBC/Google News/Google Tech/Benzinga/Investing.com） |
| `news.py` | ~430 | AI 分析模块（情绪、板块、理由生成）。**通用模块，可复用** |
| `run_us.py` | ~165 | 美股流水线：抓→分析→生成报告+选股→存档 |
| `picks.py` | ~260 | 选股评分引擎 + Yahoo Finance 实时行情 + 深度分析生成 |
| `Procfile` | 1 行 | `web: python web.py` |
| `requirements.txt` | 3 项 | flask, requests, markdown |
| `.gitignore` | 12 行 | 排除临时文件，`reports/` 整体排除但 `us_report_*.md` 豁免 |
| `PROJECT-NOTES.md` | ~150 行 | **项目复盘 + 14 个踩坑教训，必读** |

---

## 4. 关键设计

### 工作流（每日 9:00 自动跑）

```
[9:00 触发]
web.py → _do_refresh()
   ↓
subprocess.run("python run_us.py")
   ↓
run_us.py:
  scraper_us.fetch_news(limit=60)  # 抓 60 条
  news.analyze_us(items)             # AI 逐条分析情绪
  run_us.gen_report_us(results)      # 生成大盘报告
  picks.score_stocks_us(...)         # 选股评分
  picks.fetch_quote(ticker)          # Yahoo Finance 实时行情（10只）
  picks.gen_picks_report(...)        # 生成选股报告
  ↓
写文件:
  reports/us_report_YYYYMMDD_HHMM.md
  picks_us.md
  ↓
git commit + push 到 GitHub（自动存档）
```

### 评分算法

**情绪分**：
```
score = Σ(看涨+1 / 看跌-1 / 中性0) × 来源权重
来源权重: 华尔街见闻 1.2 / 东方财富快讯 1.1 / CNBC 1.1 / Yahoo 1.0 / Google 0.9
```

**市场情绪评分**：
```
score = (看涨数 - 看跌数) / 总数 × 50 + 50
≥65 → BULLISH / ≤35 → BEARISH / 36-64 → NEUTRAL
```

**操作建议**：基于 `情绪分 + 5日涨跌 + 52周位置` 三维度判定
- 强支撑 → 📈 做多（回调到 -3% 买入）
- 低估 + 震荡 → 🟡 等反转
- 52周 >85% → ⚠️ 高位不追
- 5日 < -5% → 🔴 急跌观望
- 情绪 < -0.5 → 📉 偏空
- 其他 → ⚪ 观望（给突破/跌破参考价）

### API Key 加载优先级

```python
os.environ["DASHSCOPE_API_KEY"]  # 1. 环境变量（Render 用）
~/.config/dashscope_key.txt      # 2. 本地文件（本地用）
```

---

## 5. 6 个新闻源（含 RSS 地址）

| 源 | RSS URL | 备注 |
|----|---------|------|
| Yahoo Finance | `https://finance.yahoo.com/news/rssindex` | |
| CNBC | `https://www.cnbc.com/id/100003114/device/rss/rss.html` | |
| Google News | `https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB` | |
| Google Tech | `https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB` | |
| Benzinga | `https://www.benzinga.com/feed` | XML 实体需预处理 |
| Investing.com | `https://www.investing.com/rss/news.rss` | |

---

## 6. 美股公司映射（`picks.py: KNOWN_US`）

40+ 公司名 → ticker 映射，用于从新闻标题提取股票：

```python
"apple": ("AAPL","Apple"), "tesla": ("TSLA","Tesla"),
"nvidia": ("NVDA","NVIDIA"), "microsoft": ("MSFT","Microsoft"),
"google": ("GOOGL","Google"), "meta": ("META","Meta"),
"netflix": ("NFLX","Netflix"), "goldman": ("GS","Goldman Sachs"),
"jpmorgan": ("JPM","JPMorgan"), "nike": ("NKE","Nike"),
"intel": ("INTC","Intel"), "amd": ("AMD","AMD"),
"coca-cola": ("KO","Coca-Cola"), "disney": ("DIS","Disney"),
"boeing": ("BA","Boeing"), "palantir": ("PLTR","Palantir"),
"trump media": ("DJT","Trump Media"), "alibaba": ("BABA","Alibaba"),
"nebius": ("NBIS","Nebius"), "spotify": ("SPOT","Spotify"),
"snap": ("SNAP","Snap"), "crowdstrike": ("CRWD","CrowdStrike"),
"lockheed": ("LMT","Lockheed"), "iren": ("IREN","IREN Ltd"),
# ... 共 40+ 个
```

**添加新公司**：在 `KNOWN_US` 里加一行 `"公司名": ("TICKER","公司全名")` 即可。

---

## 7. 已知问题和限制

### Render 免费实例限制

- 15 分钟无访问 → 容器休眠
- **休眠后重启，reports/ 目录丢失**（容器是临时的）
- 历史报告只有 GitHub 上有 commit（`reports/us_report_*.md`）

### API Key 配额

- 通义千问 qwen-plus 有免费额度（100 万 tokens）
- 每天跑一次，AI 调用约 30 次，每次 500-2000 tokens
- 估算：每天 ~30000 tokens，免费额度足够

### 选股 ticker 提取限制

- AI 提取的 ticker 准确率 ~80%
- 内置 40+ 知名公司映射兜底
- 非美股 ticker 自动过滤（`.PA`, `.L`, `.DE` 等欧股代码）

### BBAE 集成

- BBAE 网站本身爬不到（AWS WAF 屏蔽）
- 但用户手动点击股票名可跳转 BBAE 详情页
- 跳转 URL: `https://trading.bbae.com/zh-CN/mymarket?symbol={TICKER}`

---

## 8. 踩过的坑（必看）

完整记录在 `PROJECT-NOTES.md`，以下是 Top 10：

1. **Procfile 缺空格** → `web:python web.py`（错误）vs `web: python web.py`（对）
2. **漏 import Flask** → 重写 web.py 时漏了 `from flask import Flask`
3. **API Key 泄露** → 任何 key 在 chat/commit 出现必须立刻 rotate
4. **Render 不自动部署** → 需 "Clear build cache & deploy"
5. **仓库污染** → A 项目仓库里塞 B 项目会乱套，独立仓库
6. **Benzinga RSS XML 实体** → `&nbsp;` 等需用正则预处理
7. **etree.iter 不能切片** → `list(root.iter("item"))[:20]`
8. **AI ticker 提取噪音** → 单词 "JUST" "AFTER" 会被当 ticker，加噪音黑名单
9. **首次启动没跑刷新** → 调度器首次需立即跑一次
10. **非美股 ticker 混入** → `.PA` `.L` `.DE` 等欧股代码需过滤

---

## 9. 怎么本地运行

```bash
cd C:\Users\12648\stock-watcher-new

# 方式 1: 跑一次流水线（生成报告）
.venv\Scripts\python.exe run_us.py
# （如果没 .venv，用系统 python 也行）
C:\Users\12648\safety-notice-review\.venv\Scripts\python.exe run_us.py

# 方式 2: 启动网站
.venv\Scripts\python.exe web.py
# 浏览器打开 http://localhost:5001
```

---

## 10. 怎么部署新代码到 Render

```bash
cd C:\Users\12648\stock-watcher-new
git add .
git commit -m "描述你改了什么"
git push origin main
# 等 Render 自动构建（~2 分钟）
# 或者去 Render Dashboard 点 "Manual Deploy" → "Clear build cache & deploy"
```

---

## 11. 下一步可改进的方向

| 方向 | 难度 | 价值 |
|------|:---:|:---:|
| 加 RSI/MACD/BOLL 等更多技术指标 | ⭐⭐ | 中 |
| 加邮件/微信通知 | ⭐⭐⭐ | 高（不用每天主动访问）|
| 加更多新闻源（如 SeekingAlpha、MarketWatch） | ⭐⭐ | 中 |
| 加行业板块筛选 | ⭐⭐⭐ | 中 |
| 选股结果导出 CSV/PDF | ⭐ | 中 |
| A 股模块（之前有过，被用户删了） | ⭐⭐⭐ | 看用户 |
| 本地 Docker 部署 | ⭐⭐ | 中 |

---

## 12. 联系

- 用户：袁嘉乐，GitHub `@yjl666-ai`，邮箱 `yuanjiale2026@163.com`
- 协作模式：用户给方向，AI 实现，用户每行代码都要读懂
- 不用过 ML 研究路线，做应用层

---

> 这份文档给你（Codex）看的。接手时先读 `PROJECT-NOTES.md`（踩坑记录），再看这份（项目全景），再动代码。