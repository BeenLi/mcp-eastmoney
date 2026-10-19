"""Eastmoney HTTP client — wraps push2delay.eastmoney.com (free, no API key).

行情/日周月K线/指数优先走腾讯 qt.gtimg.cn（支持批量、限流宽松），失败再退回东财；
分钟K线、资金流、搜索只有东财源。
"""
from __future__ import annotations

import json
import re

import httpx
from typing import Any

# Free public endpoints — no API key required
QUOTE_HOST = "https://push2delay.eastmoney.com"
KLINE_HOST = "https://push2his.eastmoney.com"
SEARCH_HOST = "https://searchadapter.eastmoney.com"
# 天天基金（东财旗下）盘中净值估算，JSONP 格式
FUND_GZ_HOST = "https://fundgz.1234567.com.cn"
# 东财 F10 历史净值（官方公布净值，含 ETF/QDII），需 fundf10 的 Referer
FUND_API_HOST = "https://api.fund.eastmoney.com"

# 腾讯行情：一次请求可查多个代码，GBK 编码，字段用 ~ 分隔
TX_QUOTE_HOST = "https://qt.gtimg.cn"
TX_KLINE_HOST = "https://web.ifzq.gtimg.cn"

# 常用指数的 secid（市场.代码）。指数代码与个股撞号，不能用 market_prefix 推断：
# 000001 是上证指数也是平安银行，前者在沪市(1)，后者在深市(0)。
INDEX_SECIDS = {
    "000001": "1.000001",  # 上证指数
    "000016": "1.000016",  # 上证50
    "000300": "1.000300",  # 沪深300
    "000905": "1.000905",  # 中证500
    "000852": "1.000852",  # 中证1000
    "000688": "1.000688",  # 科创50
    "000922": "1.000922",  # 中证红利
    "399001": "0.399001",  # 深证成指
    "399006": "0.399006",  # 创业板指
    "HSI": "100.HSI",      # 恒生指数
    "NDX": "100.NDX",      # 纳斯达克100
    "SPX": "100.SPX",      # 标普500
}
# 同一批指数在腾讯的代码
INDEX_TX = {
    "000001": "sh000001", "000016": "sh000016", "000300": "sh000300", "000905": "sh000905",
    "000852": "sh000852", "000688": "sh000688", "000922": "sh000922",
    "399001": "sz399001", "399006": "sz399006",
    "HSI": "hkHSI", "NDX": "us.NDX", "SPX": "us.INX",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# ---- helpers ----------------------------------------------------------------

def market_prefix(code: str) -> str:
    """Return 0 (深市) or 1 (沪市) prefix for a 6-digit A-share code."""
    code = code.strip()
    if code.startswith(("60", "68", "11", "13", "5")):
        return "1"  # 沪市 主板/科创/转债/ETF
    return "0"  # 深市 主板/创业板/北交所


def tx_symbol(code: str) -> str:
    """6-digit A-share/fund code -> Tencent symbol (sh600519 / sz159941 / bj830799)."""
    code = code.strip()
    if code.startswith(("8", "4", "92")):
        return f"bj{code}"
    return ("sh" if market_prefix(code) == "1" else "sz") + code


def _price_digits(s: str) -> int:
    """Decimal places as quoted: '4.236' -> 3, '1329.00' -> 2."""
    return len(s.split(".")[1]) if "." in s else 0


def _safe(v: Any, default: float = 0.0) -> float:
    """Eastmoney returns '-' for halted stocks; coerce safely."""
    try:
        f = float(v)
        return default if f != f else f  # NaN check
    except (TypeError, ValueError):
        return default


def _fmt_money(v: float) -> str:
    """Format CNY amount: 亿 / 万 / raw."""
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


# ---- HTTP client ------------------------------------------------------------

class EastmoneyClient:
    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(timeout=timeout, headers=HEADERS)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str) -> dict:
        r = await self._client.get(url)
        r.raise_for_status()
        return r.json()

    async def _tx_quotes(self, symbols: list[str]) -> dict[str, list[str]]:
        """Batch quote from Tencent. Returns {symbol: fields}; unknown symbols are omitted."""
        r = await self._client.get(f"{TX_QUOTE_HOST}/q={','.join(symbols)}")
        r.raise_for_status()
        out = {}
        for m in re.finditer(r'v_([\w.]+)="([^"]*)"', r.content.decode("gbk", "replace")):
            f = m.group(2).split("~")
            if len(f) > 38:
                out[m.group(1)] = f
        return out

    @staticmethod
    def _tx_parse_quote(f: list[str]) -> dict:
        digits = _price_digits(f[3])
        return {
            "code": f[2],
            "name": f[1],
            "price": round(_safe(f[3]), digits),
            "change": _safe(f[31]),
            "change_pct": _safe(f[32]),
            "open": _safe(f[5]),
            "high": _safe(f[33]),
            "low": _safe(f[34]),
            "prev_close": _safe(f[4]),
            "volume": int(_safe(f[6])),            # 手
            "amount": _fmt_money(_safe(f[37]) * 1e4),  # 腾讯单位是万元
            "turnover_rate": _safe(f[38]),
            "pe": _safe(f[39]) or None,  # ETF/LOF 无市盈率
            "time": f[30],
        }

    # ---- 1. 实时行情 ----
    async def get_quote(self, code: str) -> dict:
        """Real-time quote for a single stock/ETF. Tencent first, Eastmoney fallback."""
        try:
            q = await self._tx_quotes([tx_symbol(code)])
            if q:
                return self._tx_parse_quote(next(iter(q.values())))
        except httpx.HTTPError:
            pass
        return await self._em_get_quote(code)

    async def get_quotes(self, codes: list[str]) -> list[dict]:
        """Batch quotes in one Tencent request (A-shares / ETF / LOF)."""
        syms = {tx_symbol(c): c for c in codes}
        q = await self._tx_quotes(list(syms))
        return [self._tx_parse_quote(q[s]) if s in q else {"code": c, "error": f"未找到 {c}"}
                for s, c in syms.items()]

    async def _em_get_quote(self, code: str) -> dict:
        m = market_prefix(code)
        url = (
            f"{QUOTE_HOST}/api/qt/stock/get?secid={m}.{code}"
            "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f62,f162,f168,f169,f170,f50,f71,f59,f152"
        )
        d = (await self._get(url)).get("data") or {}
        if not d:
            return {"error": f"未找到股票 {code}"}
        # 价格字段是整数，按 f59（价格小数位）缩放；f152 恒为 2，不能用
        digits = int(_safe(d.get("f59"), 2))  # 股票 2 位，ETF/LOF 3 位
        scale = 10 ** digits or 100
        cur = _safe(d.get("f43")) / scale
        prev = _safe(d.get("f60")) / scale
        change = cur - prev
        pct = (change / prev * 100) if prev else 0.0
        return {
            "code": d.get("f57"),
            "name": d.get("f58"),
            "price": round(cur, digits),
            "change": round(change, 2),
            "change_pct": round(pct, 2),
            "open": round(_safe(d.get("f46")) / scale, digits),
            "high": round(_safe(d.get("f44")) / scale, digits),
            "low": round(_safe(d.get("f45")) / scale, digits),
            "prev_close": round(prev, digits),
            "volume": int(_safe(d.get("f47"))),
            "amount": _fmt_money(_safe(d.get("f48"))),
            "turnover_rate": round(_safe(d.get("f168")) / 100, 2),
            "pe": round(_safe(d.get("f162")) / 100, 2),  # f162=动态市盈率（f169 是涨跌额）
        }

    # ---- 2. 主力资金排行 ----
    async def main_fund_rank(self, limit: int = 20, market: str = "all") -> list[dict]:
        """Top stocks by main net inflow."""
        fs_map = {
            "all": "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:1+t:8",
            "sh": "m:0+t:6,m:0+t:13,m:0+t:80",
            "sz": "m:1+t:2,m:1+t:23,m:1+t:8",
            "cyb": "m:0+t:80",
            "kcb": "m:1+t:23",
        }
        fs = fs_map.get(market, fs_map["all"])
        url = (
            f"{QUOTE_HOST}/api/qt/clist/get?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f62&fs={fs}&fields=f12,f14,f2,f3,f62,f184,f66,f70,f76,f78"
        )
        diff = (await self._get(url)).get("data", {}).get("diff", []) or []
        out = []
        for r in diff:
            out.append({
                "code": r.get("f12"),
                "name": r.get("f14"),
                "price": _safe(r.get("f2")),
                "change_pct": _safe(r.get("f3")),
                "main_net_inflow": _fmt_money(_safe(r.get("f62"))),
                "main_net_pct": _safe(r.get("f184")),
                "super_large_net": _fmt_money(_safe(r.get("f66"))),
                "large_net": _fmt_money(_safe(r.get("f70"))),
                "medium_net": _fmt_money(_safe(r.get("f76"))),
                "small_net": _fmt_money(_safe(r.get("f78"))),
            })
        return out

    # ---- 3. 板块资金流 ----
    async def sector_fund_flow(self, kind: str = "industry", limit: int = 20) -> list[dict]:
        """Sector-level fund flow ranking. kind: industry / concept."""
        fs = "m:90+t:2" if kind == "industry" else "m:90+t:3"
        url = (
            f"{QUOTE_HOST}/api/qt/clist/get?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f62&fs={fs}&fields=f12,f14,f2,f3,f62,f184,f128,f136"
        )
        diff = (await self._get(url)).get("data", {}).get("diff", []) or []
        out = []
        for r in diff:
            out.append({
                "code": r.get("f12"),
                "name": r.get("f14"),
                "change_pct": _safe(r.get("f3")),
                "main_net_inflow": _fmt_money(_safe(r.get("f62"))),
                "main_net_pct": _safe(r.get("f184")),
                "leading_stock": r.get("f128") or "-",
                "leading_change_pct": _safe(r.get("f136")),
            })
        return out

    # ---- 4. K线 ----
    async def get_kline(self, code: str, period: str = "daily", limit: int = 30,
                        secid: str | None = None) -> dict:
        """Historical K-line. period: daily / weekly / monthly / 5min / 15min / 30min / 60min."""
        klt_map = {
            "daily": 101, "weekly": 102, "monthly": 103,
            "5min": 5, "15min": 15, "30min": 30, "60min": 60,
        }
        tx_period = {"daily": "day", "weekly": "week", "monthly": "month"}.get(period)
        if tx_period and not (secid and secid not in INDEX_SECIDS.values()):
            try:
                return await self._tx_kline(code, tx_period, period, limit, secid)
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                pass
        klt = klt_map.get(period, 101)
        secid = secid or f"{market_prefix(code)}.{code}"
        url = (
            f"{KLINE_HOST}/api/qt/stock/kline/get?secid={secid}"
            f"&klt={klt}&fqt=1&end=20500101&lmt={limit}"
            "&fields1=f1,f2,f3,f4,f5,f6"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        )
        data = (await self._get(url)).get("data") or {}
        klines = data.get("klines") or []
        rows = []
        for line in klines:
            p = line.split(",")
            if len(p) < 8:
                continue
            rows.append({
                "date": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]),
                "volume": int(p[5]), "amount": _fmt_money(float(p[6])),
                "amplitude": float(p[7]) if len(p) > 7 else 0.0,
                "change_pct": float(p[8]) if len(p) > 8 else 0.0,
                "change": float(p[9]) if len(p) > 9 else 0.0,
                "turnover": float(p[10]) if len(p) > 10 else 0.0,
            })
        return {
            "code": data.get("code"),
            "name": data.get("name"),
            "period": period,
            "klines": rows,
        }

    async def _tx_kline(self, code: str, tx_period: str, period: str, limit: int,
                        secid: str | None) -> dict:
        idx = {v: k for k, v in INDEX_SECIDS.items()}.get(secid) if secid else None
        sym = INDEX_TX[idx] if idx else tx_symbol(code)
        url = f"{TX_KLINE_HOST}/appstock/app/fqkline/get?param={sym},{tx_period},,,{limit},qfq"
        r = await self._client.get(url)
        r.raise_for_status()
        d = r.json()["data"][sym]
        raw = d.get("qfq" + tx_period) or d.get(tx_period) or []
        if not raw:
            raise ValueError("empty kline")
        rows, prev = [], None
        for p in raw:
            o, c, h, l = float(p[1]), float(p[2]), float(p[3]), float(p[4])
            rows.append({
                "date": p[0], "open": o, "close": c, "high": h, "low": l,
                "volume": int(float(p[5])),
                "change_pct": round((c / prev - 1) * 100, 2) if prev else 0.0,
                "change": round(c - prev, 3) if prev else 0.0,
            })
            prev = c
        qt = (d.get("qt") or {}).get(sym) or []
        return {"code": code, "name": qt[1] if len(qt) > 1 else None,
                "period": period, "source": "tencent", "klines": rows}

    # ---- 5. 股票搜索 ----
    async def search(self, keyword: str, limit: int = 10) -> list[dict]:
        """Search A-share stocks by name / code / pinyin."""
        url = (
            f"{SEARCH_HOST}/api/suggest/get?input={keyword}&type=14"
            f"&token=D43BF722C8E33BDC906FB84D85E326E8&count={limit}"
        )
        r = await self._client.get(url)
        # Response is JSONP-ish but with cb empty it's plain JSON
        try:
            text = r.text.strip()
            if text.startswith("("):
                text = text[1:-1]
            import json
            d = json.loads(text)
        except Exception:
            return []
        items = d.get("QuotationCodeTable", {}).get("Data", []) or []
        out = []
        for it in items:
            if it.get("Classify") != "AStock":
                continue
            out.append({
                "code": it.get("Code"),
                "name": it.get("Name"),
                "pinyin": it.get("PinYin"),
                "market": it.get("SecurityTypeName"),
            })
        return out

    # ---- 6. 指数行情 ----
    async def get_index(self, code: str, period: str = "daily", limit: int = 30) -> dict:
        """Index quote + K-line. code: 000300 / 399006 / HSI, or an explicit secid like 1.000300."""
        code = code.strip().upper()
        secid = code if "." in code else INDEX_SECIDS.get(code)
        if not secid:
            return {"error": f"未知指数 {code}，可直接传 secid（如 1.000300）", "known": list(INDEX_SECIDS)}
        idx = {v: k for k, v in INDEX_SECIDS.items()}.get(secid)
        if idx:
            try:
                q = await self._tx_quotes([INDEX_TX[idx]])
                f = q[INDEX_TX[idx]]
                cur, prev = _safe(f[3]), _safe(f[4])
                amount = _fmt_money(_safe(f[37]) * 1e4) if INDEX_TX[idx][:2] in ("sh", "sz") else None
                return self._index_result(secid, f[1], cur, prev, _safe(f[33]), _safe(f[34]), amount,
                                          period, await self.get_kline(code, period, limit, secid=secid))
            except (httpx.HTTPError, KeyError):
                pass
        url = (
            f"{QUOTE_HOST}/api/qt/stock/get?secid={secid}"
            "&fields=f43,f44,f45,f46,f48,f57,f58,f59,f60,f152"
        )
        d = (await self._get(url)).get("data") or {}
        if not d:
            return {"error": f"未找到指数 {secid}"}
        scale = 10 ** int(_safe(d.get("f59"), 2))
        cur, prev = _safe(d.get("f43")) / scale, _safe(d.get("f60")) / scale
        return self._index_result(secid, d.get("f58"), cur, prev, _safe(d.get("f44")) / scale,
                                  _safe(d.get("f45")) / scale, _fmt_money(_safe(d.get("f48"))),
                                  period, await self.get_kline(code, period, limit, secid=secid))

    @staticmethod
    def _index_result(secid, name, cur, prev, high, low, amount, period, kline) -> dict:
        closes = [r["close"] for r in kline["klines"]]
        return {
            "secid": secid,
            "name": name,
            "price": round(cur, 2),
            "change_pct": round((cur - prev) / prev * 100, 2) if prev else 0.0,
            "high": round(high, 2),
            "low": round(low, 2),
            "amount": amount,
            "period": period,
            "period_change_pct": round((closes[-1] / closes[0] - 1) * 100, 2) if len(closes) > 1 else None,
            "period_high": max(closes) if closes else None,
            "period_low": min(closes) if closes else None,
            "klines": kline["klines"],
        }

    # ---- 7. 场内基金溢价率 ----
    async def fund_premium(self, code: str) -> dict:
        """ETF/LOF premium = 场内成交价 / 基金净值 - 1.

        场内价来自腾讯行情（失败退回东财）；净值来自天天基金：dwjz 是上一交易日公布的官方净值，
        gsz 是盘中按持仓估算的实时净值（对跨境/QDII 基金估算误差较大）。
        """
        quote = await self.get_quote(code)
        if "error" in quote:
            return quote
        gz: dict = {}
        try:
            r = await self._client.get(f"{FUND_GZ_HOST}/js/{code}.js")
            m = re.search(r"jsonpgz\((.*)\)", r.text)
            gz = json.loads(m.group(1)) if m and m.group(1).strip() else {}
        except (httpx.HTTPError, ValueError):
            pass
        if not gz:
            # fundgz 对 ETF 返回 404 页（2026-10 实测对所有基金都 404），退回 F10 历史净值接口取官方净值
            r = await self._client.get(
                f"{FUND_API_HOST}/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=1",
                headers={"Referer": "https://fundf10.eastmoney.com/"},
            )
            rows = ((r.json().get("Data") or {}).get("LSJZList")) or []
            if not rows:
                return {"code": code, "name": quote["name"], "price": quote["price"],
                        "error": "取不到该基金的净值"}
            gz = {"dwjz": rows[0].get("DWJZ"), "jzrq": rows[0].get("FSRQ")}
        price, nav, est = quote["price"], _safe(gz.get("dwjz")), _safe(gz.get("gsz"))
        return {
            "code": code,
            "name": gz.get("name") or quote["name"],
            "price": price,
            "change_pct": quote["change_pct"],
            "nav": nav,
            "nav_date": gz.get("jzrq"),
            "premium_vs_nav_pct": round((price / nav - 1) * 100, 2) if nav else None,
            "est_nav": est or None,
            "est_time": gz.get("gztime"),
            "premium_vs_est_pct": round((price / est - 1) * 100, 2) if est else None,
        }
