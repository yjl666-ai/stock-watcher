# stock-watcher 项目复盘

_2026-07-22 项目暂停开发时的总结 — 写给未来的 Hermes。下次接手先读一遍。_

---

## 一、项目做什么

美股 + 美股观察网站, 部署在 Render。
- 仓库: `yjl666-ai/stock-watcher` (独立仓库, 不是 safety-notice)
- Render URL: `https://stock-watcher-2dbs.onrender.com/`
- 路径: `C:\Users\12648\stock-watcher-new\`

---

## 二、关键文件

| 文件 | 作用 |
|---|---|
| `scraper_us.py` | 抓 6 个美股新闻源 (Yahoo / CNBC / Google News / Google Tech / Benzinga / Investing.com) |
| `run_us.py` | 抓取→AI分析→写报告→写选股, 触发整个流水线 |
| `news.py` | 通用模块: `call_qwen()` 调通义千问 API (支持环境变量 + 本地文件 fallback) |
| `picks.py` | 情绪评分 + 实时行情 (Yahoo Finance API) + 操作建议生成 |
| `web.py` | Flask 网站, 北京时间每日 9:00 自动刷新, 立即首次启动刷新 |
| `Procfile` | `web: python web.py` (冒号后必须有空格) |
| `requirements.txt` | flask, requests, markdown |
| `.gitignore` | 排除 reports/, picks_us.md, *.db 等运行时文件 |

---

## 三、踩过的坑 (防止重复犯错)

### 1. Procfile 缺空格
❌ `web: python web.py` (写成 `web:python web.py`)
✅ 冒号后必须有空格, 否则 Render build 失败, 但报错信息是模糊的 "Exited with status 1"

### 2. 漏 import Flask
❌ 直接用 `Flask(__name__)` 但只 `import markdown`
✅ 必须 `from flask import Flask` 单独导入, 否则 NameError

### 3. API Key 泄露
❌ 在 chat 里发 key, commit message 里有 key
✅ 统一 `os.environ.get("DASHSCOPE_API_KEY")`, 本地用 `~/.config/dashscope_key.txt`
✅ Render 上必须手动加环境变量 (没有 fallback 就会 RuntimeError)
🚨 任何 key 在 chat/commit 出现 = 立刻 rotate

### 4. Render 部署缓存
❌ 代码推到 GitHub 但 Render 没自动重新构建
✅ 点 "Manual Deploy" → "Clear build cache & deploy"
✅ 看 Logs 而不是只看 Status

### 5. 仓库污染 (2026-07-21 出过大事故)
❌ 在 safety-notice 仓库里新建 stock-watcher 子目录, 导致两个项目混在一起
✅ 现在 stock-watcher 在独立仓库 `yjl666-ai/stock-watcher`
✅ 任何新项目先建空仓库再 clone 下来

### 6. RSS XML 解析失败
❌ Benzinga RSS 含 `&nbsp;` 等未转义实体, ET.fromstring() 抛错
✅ 加正则预处理: `re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)[a-zA-Z]+;", "&amp;", text)`

### 7. etree._element_iterator 不能切片
❌ `root.iter("item")[:20]`
✅ `list(root.iter("item"))[:20]`

### 8. AI 提取 ticker 不准
❌ 用正则 `\b[A-Z]{1,5}\b` 会把 "SICAL", "MSUNG", "SMSN" 等当 ticker
✅ 只信 AI 提取的结果 + 内置公司名→ticker 映射 (40+)

### 9. 调度器首次启动没跑
❌ 只安排下次 9 点, 启动后页面 "正在生成..." 卡住
✅ 首次启动立即跑一次 (`_do_refresh` + `schedule_next`)

### 10. 北京时间显示问题
❌ `datetime.now()` 在 Render 服务器上是 UTC
✅ `datetime.now(TZ)` 其中 `TZ = timezone(timedelta(hours=8))`

### 11. 非美股 ticker 混进来
❌ `AIR.PA` (巴黎) `SMSN` (伦敦) 出现在美股推荐里
✅ `NON_US_SUFFIX = {'.PA','.L','.DE','.AS','.SW','.MI','.MC','.HK','.T','.KS'}`
✅ `_is_us_ticker()` 过滤后缀

### 12. BBAE 等站点爬不到
❌ BBAE 用 AWS WAF 挡 curl
✅ 改用 Yahoo Finance v8 API (公开免费) 查实时行情

### 13. 选股表 "—" 太多
❌ 观望股票显示 "—"
✅ 每只都给具体入场价/止损价 (即使是观望也给参考位)

### 14. Markdown 表格里 `<br>` 被吃
❌ 操作建议列 `<br>` 换行不生效
✅ 改为单行: "✅ 关注 · 📈强势 · 中位(60%位)"

---

## 四、当前状态 (2026-07-22)

### 工作流
```
scraper_us.py (6源抓新闻 60条)
    ↓
news.py (调通义千问 AI 分析)
    ↓
run_us.py (组合报告 + 选股)
    ↓
web.py (Flask 网站, 每日9点自动刷新, 显示给用户)
```

### 部署
- Render service: stock-watcher
- Branch: main
- Build: `pip install -r requirements.txt`
- Start: `web: python web.py`
- Env var: `DASHSCOPE_API_KEY=***`

### 限制
- Render 免费版 15 分钟无访问会休眠
- 每天 9:00 自动唤醒 + 跑流水线
- 节假日或凌晨没访问, 启动慢约 30 秒

---

## 五、下次接手的 TODO

如果用户回来, 可能的改进方向:
1. 加 A 股板块 (用户之前有过, 后来删了)
2. 技术指标加更多 (MACD, RSI, BOLL)
3. 选股推荐发邮件 / 微信通知 (代替用户每天访问)
4. AI 用更便宜的模型 (qwen-turbo 比 qwen-plus 便宜)
5. BAAE / 富途的免登录公开行情页面爬取 (代替 Yahoo)

---

## 六、一键验证脚本

每次改完代码必须跑:
```bash
python "C:\Users\12648\AppData\Local\Temp\hermes-verify.py" 2>&1
```
检查项:
- 所有 py 文件编译通过
- 关键函数/变量名都在
- 没 key 泄露
- 实时测试 `/health` 和 `/picks` 页面

---

_这份文档长期保留. 下次接手 stock-watcher 第一件事: 读这个._