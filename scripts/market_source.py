#!/usr/bin/env python3
"""
统一行情数据源 — 替代挂掉的 eastmoney/efinance。

背景：eastmoney push2 节点 2026-10 起持续 502，efinance 底层也调它，故整体失效。
本模块改用 新浪(vip.stock.finance.sina.com.cn) + 腾讯(qt.gtimg.cn)，两者实测稳定。

对外接口（与旧 efinance 用法兼容）：
  get_all_stocks()      -> [{code,name,change_pct,market_cap_yi,amount_yi,pe,pb,price,turnover}]
  get_top_gainers(n)    -> 同上，按涨幅降序前 n
  get_sector_flow()     -> [{code,name,change_pct,net_inflow_yi}]
  get_index_history(sym)-> [(date, close), ...]  指数近 N 日日线
"""
import json
import subprocess
import time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# 新浪节点代码：hs_a = 全部A股；sh_a/sz_a 可细分
SINA_NODES = ["hs_a"]


def _curl(url, timeout=15, referer=None, decode="utf-8"):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-A", UA]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
        if r.returncode != 0:
            return ""
        return r.stdout.decode(decode, errors="replace")
    except Exception:
        return ""


def _curl_json(url, timeout=15, referer=None):
    text = _curl(url, timeout=timeout, referer=referer)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def get_all_stocks(max_pages=60, verbose=False):
    """全市场 A 股实时行情（新浪分页）。每页100只，60页≈6000只，覆盖全市场。"""
    stocks = []
    for node in SINA_NODES:
        for page in range(1, max_pages + 1):
            url = (
                "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node={node}"
            )
            data = _curl_json(url, timeout=20)
            if not data or not isinstance(data, list):
                break
            for x in data:
                code = str(x.get("code", "")).strip()
                name = str(x.get("name", "")).strip()
                if not code or not name:
                    continue
                mktcap = _to_float(x.get("mktcap", 0))  # 万元
                amount = _to_float(x.get("amount", 0))   # 元
                stocks.append({
                    "code": code,
                    "name": name,
                    "price": _to_float(x.get("trade", 0)),
                    "change_pct": round(_to_float(x.get("changepercent", 0)), 2),
                    "market_cap_yi": round(mktcap / 1e4, 0) if mktcap else 0,  # 万元→亿元
                    "amount_yi": round(amount / 1e8, 2) if amount else 0,
                    "turnover": round(_to_float(x.get("turnoverratio", 0)), 2),
                    "pe": round(_to_float(x.get("per", 0)), 2) or None,
                    "pb": round(_to_float(x.get("pb", 0)), 2) or None,
                })
            if len(data) < 100:
                break
            time.sleep(0.15)  # 温和限速
    if verbose:
        print(f"  [market_source] 新浪获取 {len(stocks)} 只 A 股")
    return stocks


def get_top_gainers(n=20, verbose=False):
    """涨幅榜前 n（新浪单次请求）。"""
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"Market_Center.getHQNodeData?page=1&num={n}&sort=changepercent&asc=0&node=hs_a"
    )
    data = _curl_json(url, timeout=20)
    if not data or not isinstance(data, list):
        return []
    out = []
    for x in data:
        mktcap = _to_float(x.get("mktcap", 0))
        out.append({
            "code": str(x.get("code", "")),
            "name": str(x.get("name", "")),
            "price": _to_float(x.get("trade", 0)),
            "change_pct": round(_to_float(x.get("changepercent", 0)), 2),
            "turnover": round(_to_float(x.get("turnoverratio", 0)), 2),
            "amount_yi": round(_to_float(x.get("amount", 0)) / 1e8, 2),
            "market_cap_yi": round(mktcap / 1e4, 0) if mktcap else 0,
            "high": _to_float(x.get("high", 0)),
            "low": _to_float(x.get("low", 0)),
            "open": _to_float(x.get("open", 0)),
        })
    if verbose:
        print(f"  [market_source] 涨幅榜 {len(out)} 只")
    return out


def get_sector_flow(verbose=False):
    """行业板块资金流/涨幅（新浪行业板块列表）。返回按涨跌幅降序。"""
    text = _curl("https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php",
                 timeout=15, decode="gbk")
    if not text:
        return []
    # 格式: var S_Finance_bankuai_sinaindustry = {"new_blhy":"new_blhy,玻璃行业,19,均价,涨跌,涨跌幅,成交量,成交额,领涨股代码,现价,涨跌额,涨跌幅,领涨股名", ...}
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
    except Exception:
        return []
    out = []
    for code, val in obj.items():
        f = val.split(",")
        if len(f) < 6:
            continue
        try:
            out.append({
                "code": code,
                "name": f[1],
                "stock_count": int(f[2]) if f[2].isdigit() else 0,
                "change_pct": round(float(f[5]), 2),
                "amount_yi": round(float(f[7]) / 1e8, 2) if len(f) > 7 and f[7] else 0,
                "leader": f[12] if len(f) > 12 else "",
            })
        except (ValueError, IndexError):
            continue
    out.sort(key=lambda x: x["change_pct"], reverse=True)
    if verbose:
        print(f"  [market_source] 行业板块 {len(out)} 个")
    return out


def get_index_daily(symbol="sh000001", days=30, verbose=False):
    """指数日线（新浪）。symbol 如 sh000001(上证)/sz399001(深证)。返回 [(date, close)]。"""
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
    )
    data = _curl_json(url, timeout=20)
    if not data or not isinstance(data, list):
        return []
    return [(x.get("day", ""), _to_float(x.get("close", 0))) for x in data]


if __name__ == "__main__":
    print("=== 自测 market_source ===")
    g = get_top_gainers(3, verbose=True)
    for x in g:
        print("  ", x["code"], x["name"], x["change_pct"], "%")
    s = get_sector_flow(verbose=True)
    for x in s[:3]:
        print("  ", x["name"], x["change_pct"], "%")
    h = get_index_daily("sh000001", 5)
    print("  指数近5日:", h)
