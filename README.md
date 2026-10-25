# mcp-eastmoney

> 🇨🇳 让 Claude / Cursor / Codex 等 MCP 客户端直接查询 A 股、ETF/LOF、指数行情和场内基金溢价率，免 API Key

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP](https://img.shields.io/badge/MCP-Server-purple.svg)](https://modelcontextprotocol.io)

[English](#english) | [中文](#中文)

<p align="center">
  <img src="assets/demo.png" alt="Claude × mcp-eastmoney 演示" width="780">
  <br>
  <sub>👆 在 Claude Desktop 中直接用自然语言查询 A 股行情和主力资金</sub>
</p>

> 本仓库 fork 自 [27dream/mcp-eastmoney](https://github.com/27dream/mcp-eastmoney)，在其基础上增加了腾讯行情源、批量查询、指数走势和溢价率工具，并修复了几处数据解析问题，详见[与上游的差异](#与上游的差异)。

---

## 中文

### ✨ 特性

- 🆓 **免费、免 Key**：只调用腾讯和东方财富网页行情用的公开接口
- 🔀 **双数据源**：行情、日/周/月 K 线、指数优先走腾讯（支持批量、限流宽松），失败自动退回东财
- 📈 **指数走势**：上证、沪深300、中证500/1000、中证红利、创业板指、科创50、恒生、纳指100、标普500
- 💰 **场内基金溢价率**：ETF/LOF 场内价相对官方净值的溢价/折价
- 🧮 **技术指标**：MA / MACD / KDJ 本地计算，不依赖 numpy/pandas
- 🌏 **北向资金、涨停池、港股/美股**：来自上游 v0.2.0
- 🔌 **标准 MCP 协议**：兼容 Claude Desktop / Claude Code / Cursor / Cline 等客户端

### 🛠️ 提供的 Tools（13 个）

| Tool | 说明 | 数据源 | 示例 |
|------|------|--------|------|
| `get_stock_quote` | 单只股票/ETF/LOF 实时行情（价格、涨跌、成交、换手率、PE） | 腾讯 → 东财 | `get_stock_quote(code="510300")` |
| `get_quotes` | 批量行情，一次请求最多 60 个代码 | 腾讯 | `get_quotes(codes=["600519","510300","159941"])` |
| `get_index` | 指数快照 + K 线走势 + 区间涨跌/高低点 | 腾讯 → 东财 | `get_index(code="000300", limit=20)` |
| `get_fund_premium` | 场内基金溢价率 = 场内价 ÷ 净值 − 1 | 腾讯 + 东财 F10 | `get_fund_premium(code="513100")` |
| `get_kline` | 历史 K 线（日/周/月，前复权；5/15/30/60 分钟） | 日线：腾讯 → 东财 → 新浪；周/月：腾讯 → 东财；分钟：东财 → 新浪 | `get_kline(code="600519", period="weekly")` |
| `search_stock` | 按名称/拼音/代码搜索 | 东财 | `search_stock(keyword="宁德")` |
| `main_fund_rank` | 主力资金净流入排行 | 东财 | `main_fund_rank(market="all", limit=10)` |
| `sector_fund_flow` | 行业/概念板块资金流 + 领涨股 | 东财 | `sector_fund_flow(kind="industry")` |
| `technical_indicators` | K 线 + MA5/10/20/30/60、MACD、KDJ | 同 `get_kline` | `technical_indicators(code="510300", limit=120)` |
| `north_bound_flow` | 北向/南向资金每日买入、卖出、净额 ⚠️ 数字已无参考价值，见数据说明 | 东财 | `north_bound_flow(days=5)` |
| `limit_up_pool` | 涨停池：连板数、封板时间、封板资金、炸板次数 | 东财 | `limit_up_pool(date="20261024")` |
| `hk_us_quote` | 港股/美股实时行情 | 东财 | `hk_us_quote(code="00700", market="hk")` |
| `hk_us_kline` | 港股/美股 K 线 | 东财 | `hk_us_kline(code="AAPL", market="us")` |

`get_index` 的 `code` 可用：`000001` 上证指数、`000016` 上证50、`000300` 沪深300、`000905` 中证500、`000852` 中证1000、`000688` 科创50、`000922` 中证红利、`399001` 深证成指、`399006` 创业板指、`HSI` 恒生、`NDX` 纳指100、`SPX` 标普500，也可直接传东财 secid（如 `1.000300`）。

### 🚀 快速开始

需要先安装 [uv](https://docs.astral.sh/uv/)：`curl -LsSf https://astral.sh/uv/install.sh | sh`

**方式一：直接从 GitHub 运行**

```bash
uvx --from git+https://github.com/BeenLi/mcp-eastmoney mcp-eastmoney
```

> ⚠️ 这个包没有发布到 PyPI，`uvx mcp-eastmoney` / `pip install mcp-eastmoney` 找不到它，请用上面的 git 地址安装。依赖里锁定了 `mcp<2`：mcp 2.x 去掉了本项目用的装饰器接口，装到 2.x 会启动即崩溃。

**方式二：克隆到本地（便于自己修改）**

```bash
git clone https://github.com/BeenLi/mcp-eastmoney ~/Developer/selfhosted/mcp-eastmoney
cd ~/Developer/selfhosted/mcp-eastmoney
uv sync
uv run python tests/test_mcp_protocol.py   # 应列出 13 个工具
```

### 🔌 接入 Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows），在 `mcpServers` 里加入下面其中一种：

```json
{
  "mcpServers": {
    "eastmoney": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/BeenLi/mcp-eastmoney", "mcp-eastmoney"]
    }
  }
}
```

本地克隆版：

```json
{
  "mcpServers": {
    "eastmoney": {
      "command": "/Users/<你>/.local/bin/uv",
      "args": ["--directory", "/Users/<你>/Developer/selfhosted/mcp-eastmoney", "run", "mcp-eastmoney"]
    }
  }
}
```

Claude Desktop 找不到 `uv` / `uvx` 时，把 `command` 换成 `which uv` 输出的完整路径。改完按 ⌘Q 完全退出再打开。需要走代理时可以加 `"env": {"HTTPS_PROXY": "http://127.0.0.1:7897"}`。

Claude Code 用户：`claude mcp add eastmoney -- uvx --from git+https://github.com/BeenLi/mcp-eastmoney mcp-eastmoney`

### 💬 使用示例

> 沪深300、创业板指最近 20 个交易日走势如何？
>
> 513100、159941、510300 现在溢价率多少？
>
> 帮我批量看一下这几只 ETF 的行情：510300、510500、159915、513100

### 🔍 它是怎么工作的

MCP 服务器只是一层"翻译"：客户端通过 stdin/stdout 发 JSON-RPC 请求，服务器把它转成对行情网站的 HTTP 请求，再把返回的数字整理成中文字段。

| 接口 | 用途 | 格式要点 |
|------|------|----------|
| `qt.gtimg.cn/q=sh510300,sz159941,...` | 腾讯实时行情 | 一次可查几十个代码；GBK 编码，字段用 `~` 分隔；成交额单位是万元 |
| `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 腾讯日/周/月 K 线（前复权） | |
| `push2delay.eastmoney.com/api/qt/stock/get` | 东财单只快照（延时约 15 分钟） | `secid=市场.代码`；价格是整数，按 `f59` 的小数位缩放 |
| `push2his.eastmoney.com/api/qt/stock/kline/get` | 东财 K 线（含分钟线） | `klt=101/102/103` 日/周/月，`fqt=1` 前复权 |
| `push2delay.eastmoney.com/api/qt/clist/get` | 东财主力资金、板块排行 | `fid=f62` 按主力净流入排序 |
| `push2delay.eastmoney.com/api/qt/kamt.kline/get` | 东财北向/南向资金 | |
| `push2ex.eastmoney.com/getTopicZTPool` | 东财涨停池 | |
| `money.finance.sina.com.cn/.../getKLineData` | 新浪 K 线（A 股兜底） | 不复权；成交量单位是股 |
| `api.fund.eastmoney.com/f10/lsjz` | 东财 F10 历史净值 | 需 `fundf10.eastmoney.com` 的 Referer |

几个容易踩的细节：

- **为什么腾讯优先**：东财快照一次只能查一个代码，查 7 只基金就要发十几个请求，短时间连发容易被封 IP；腾讯一个请求就能把几十个代码全拿回来。
- **secid 的市场前缀**：`1.` 沪市、`0.` 深市、`100.` 海外指数。指数代码会和个股撞号，`000001` 既是上证指数（`1.000001`）也是平安银行（`0.000001`），所以指数用单独的映射表，不按代码开头猜市场。
- **价格小数位**：东财用整数传价格，`f59` 表示小数位（股票 2 位、ETF/LOF 3 位）。`f152` 恒为 2，用它会把 ETF 价格放大 10 倍。
- **溢价率的口径**：这里用的是"场内价 ÷ 上一交易日官方净值 − 1"。QDII 基金（如纳指 ETF）净值 T+2 才公布，算出的溢价率会偏高一些。券商软件显示的盘中溢价率用的是交易所每 15 秒发布的 IOPV（参考净值），本工具暂不提供。天天基金的盘中估值接口（`fundgz.1234567.com.cn`）在 2026-10 实测已对所有基金返回 404，代码保留了它作为首选，取不到时自动退回 F10 官方净值。

### 与上游的差异

- 新增 `get_quotes`、`get_index`、`get_fund_premium` 三个工具
- 合并上游 v0.2.0 的 5 个工具（北向资金、涨停池、技术指标、港股/美股行情和 K 线）和新浪 K 线兜底；`limit_up_pool` 补上了 `date` 参数
- 行情、日/周/月 K 线、指数改为腾讯优先、东财备用
- 依赖锁定 `mcp>=1.0.0,<2`（mcp 2.x 去掉了 `Server.list_tools()` 装饰器接口），并加入 `uv.lock`
- 修复：价格小数位改用 `f59`；`pe` 改读 `f162`（动态市盈率，原来读的 `f169` 是涨跌额）；ETF/LOF 无市盈率时返回空值而不是 0

### ⚠️ 数据说明

- 数据来自腾讯、东方财富的公开接口，东财为延时行情，仅供研究参考，不构成任何投资建议
- 资金流、北向资金、涨停池、搜索、港股/美股只有东财源；东财限流时这几个工具会报错，其余工具不受影响
- `north_bound_flow`：2024 年 8 月起沪深交易所不再实时披露北向资金买卖额，接口返回的数字（实测买入 840 万、卖出 0）已不能用来判断外资动向，仅为兼容上游保留
- 请合理控制请求频率，查多个代码时优先用 `get_quotes`

### 📜 License

MIT

---

## English

**mcp-eastmoney** is an [MCP](https://modelcontextprotocol.io) server that gives AI assistants China A-share, ETF/LOF and index market data, plus exchange-traded fund premium/discount, using free public endpoints from Tencent and Eastmoney. No API key required.

This is a fork of [27dream/mcp-eastmoney](https://github.com/27dream/mcp-eastmoney) (including upstream v0.2.0) that adds a Tencent data source (batch quotes, lenient rate limits) with Eastmoney fallback, index and fund-premium tools, and several parsing fixes.

### 🛠️ Tools

| Tool | Description |
|------|-------------|
| `get_stock_quote` | Quote for one stock / ETF / LOF (Tencent → Eastmoney) |
| `get_quotes` | Batch quotes, up to 60 codes in one request (Tencent) |
| `get_index` | Index snapshot + K-line trend (CSI 300, SSE, ChiNext, CSI Dividend, HSI, NDX, SPX…) |
| `get_fund_premium` | ETF/LOF premium = exchange price ÷ official NAV − 1 |
| `get_kline` | Daily/weekly/monthly (Tencent → Eastmoney, daily also Sina) or 5/15/30/60-min (Eastmoney → Sina) K-lines |
| `search_stock` | Search by name / pinyin / code (Eastmoney) |
| `main_fund_rank` | Main capital net inflow ranking (Eastmoney) |
| `sector_fund_flow` | Industry / concept sector capital flow (Eastmoney) |
| `technical_indicators` | K-line plus MA / MACD / KDJ, computed locally |
| `north_bound_flow` | Stock Connect north/south-bound daily flow (Eastmoney). Exchanges stopped real-time disclosure in Aug 2024, so the figures are not meaningful |
| `limit_up_pool` | Limit-up stock pool with board count and seal time (Eastmoney) |
| `hk_us_quote` / `hk_us_kline` | Hong Kong / US stock quote and K-line (Eastmoney) |

### 🚀 Quick Start

```bash
uvx --from git+https://github.com/BeenLi/mcp-eastmoney mcp-eastmoney
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "eastmoney": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/BeenLi/mcp-eastmoney", "mcp-eastmoney"]
    }
  }
}
```

The package is not published on PyPI, so `uvx mcp-eastmoney` / `pip install mcp-eastmoney` will not find it; install from the git URL above. Dependencies pin `mcp<2` because mcp 2.x removed the decorator API this server uses.

### ⚠️ Disclaimer

Data comes from public Tencent and Eastmoney endpoints (Eastmoney quotes are delayed ~15 min) and is provided as-is. **Not financial advice.**

### 📜 License

MIT
