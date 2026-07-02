#!/usr/bin/env python3
"""
候选股票池生成器 — 从催化剂 + 蓄势信号 + 产业链传导中筛选标的。

选择逻辑（按优先级）：
1. 蓄势信号中的中盘股（50-500亿）
2. 产业链传导中"下一环节"标的
3. 资金流入但涨幅小的蓄势标的
4. 有明确催化剂的标的

市值偏好：50-500亿优先，500-1500亿可选，>2000亿排除

输出：docs/data/candidates.json
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA = REPO_DIR / "docs" / "data"


def curl_get(url, timeout=10):
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def log(msg, verbose=False):
    if verbose:
        print(f"  {msg}", file=sys.stderr)


def cap_weight(cap_yi):
    """50-500亿最优。"""
    if cap_yi < 30:
        return 0.2
    elif cap_yi < 50:
        return 0.5
    elif cap_yi <= 200:
        return 1.0
    elif cap_yi <= 500:
        return 0.9
    elif cap_yi <= 1000:
        return 0.5
    elif cap_yi <= 2000:
        return 0.2
    else:
        return 0.05


def read_catalysts(verbose=False):
    path = DOCS_DATA / "catalysts.json"
    if not path.exists():
        log("⚠️ catalysts.json 不存在", verbose)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_all_stocks_efinance(verbose=False):
    """用 efinance 获取全市场 A 股实时行情。"""
    try:
        import efinance as ef
        log("efinance: 获取全市场行情...", verbose)
        df = ef.stock.get_realtime_quotes()
        if df is None or df.empty:
            return []

        stocks = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", ""))
            name = str(row.get("股票名称", ""))
            if not code or not name:
                continue
            try:
                cap = float(row.get("总市值", 0) or 0)
                cap_yi = round(cap / 1e8, 0) if cap > 0 else 0
            except (ValueError, TypeError):
                cap_yi = 0
            try:
                change = round(float(row.get("涨跌幅", 0) or 0), 2)
            except (ValueError, TypeError):
                change = 0
            try:
                amount = float(row.get("成交额", 0) or 0)
                amount_yi = round(amount / 1e8, 2)
            except (ValueError, TypeError):
                amount_yi = 0

            stocks.append({
                "code": code, "name": name,
                "change_pct": change,
                "market_cap_yi": cap_yi,
                "amount_yi": amount_yi,
            })
        log(f"  获取 {len(stocks)} 只 A 股", verbose)
        return stocks
    except ImportError:
        log("⚠️ efinance 未安装", verbose)
        return []
    except Exception as e:
        log(f"⚠️ efinance 失败: {e}", verbose)
        return []


def get_fund_flow(verbose=False):
    """获取个股资金流入 Top 40。"""
    log("获取资金流向...", verbose)
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=40&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f12,f14,f3,f8,f62,f20"
    )
    text = curl_get(url, timeout=8)
    if not text:
        return []
    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
        stocks = []
        for item in diffs:
            code = item.get("f12", "")
            name = item.get("f14", "")
            if not code or not name:
                continue
            mc = item.get("f20", 0) or 0
            stocks.append({
                "code": code, "name": name,
                "change_pct": round(item.get("f3", 0) or 0, 2),
                "turnover": round(item.get("f8", 0) or 0, 2),
                "net_inflow_yi": round((item.get("f62", 0) or 0) / 1e8, 2),
                "market_cap_yi": round(mc / 1e8, 0) if mc else 0,
            })
        log(f"  获取 {len(stocks)} 只资金流向标的", verbose)
        return stocks
    except Exception:
        return []


def select_candidates(catalysts_data, all_stocks, fund_flow, verbose=False):
    """核心选择逻辑：催化剂驱动，市值过滤。"""
    selected = {}
    stats = {"accumulation": 0, "chain": 0, "flow": 0, "catalyst": 0}

    # 构建全市场股票索引（code -> stock info）
    stock_map = {s["code"]: s for s in all_stocks}

    # 用 fund_flow 补充市值信息
    for s in fund_flow:
        if s["code"] in stock_map:
            stock_map[s["code"]].update({"net_inflow_yi": s["net_inflow_yi"]})

    # --- 规则 1: 蓄势信号中的个股 ---
    for sig in catalysts_data.get("accumulation_signals", []):
        if sig.get("level") != "stock":
            continue
        code = sig["code"]
        if code in selected:
            continue
        st = stock_map.get(code, sig)
        cap = st.get("market_cap_yi", 0)
        if cap < 30 or cap > 2000:
            continue
        selected[code] = {
            "code": code, "name": sig["name"],
            "source": "accumulation",
            "reason": f"蓄势信号：{'；'.join(sig.get('reasons', []))}",
            "market_cap_yi": cap,
            "score": 70 + cap_weight(cap) * 30,
        }
        stats["accumulation"] += 1

    # --- 规则 2: 产业链传导中的"下一环节"标的 ---
    for prop in catalysts_data.get("chain_propagations", []):
        for opp in prop.get("next_opportunities", []):
            code = opp["code"]
            if code in selected:
                continue
            cap = opp.get("market_cap_yi", 0)
            if cap < 30 or cap > 2000:
                continue
            selected[code] = {
                "code": code, "name": opp["name"],
                "source": "chain",
                "reason": f"产业链传导({prop['theme']}): 待补涨，{prop['logic'][:60]}",
                "market_cap_yi": cap,
                "score": 60 + cap_weight(cap) * 30,
            }
            stats["chain"] += 1

    # --- 规则 3: 资金流入蓄势标的 ---
    for s in fund_flow:
        code = s["code"]
        if code in selected:
            continue
        cap = s["market_cap_yi"]
        if cap < 50 or cap > 1500:
            continue
        if s["change_pct"] >= 2 or s["change_pct"] <= -3:
            continue
        flow_ratio = s["net_inflow_yi"] / max(cap, 1) * 100
        if flow_ratio < 0.05:
            continue
        selected[code] = {
            "code": code, "name": s["name"],
            "source": "flow",
            "reason": f"资金蓄势：涨{s['change_pct']:+.1f}%，主力{s['net_inflow_yi']:+.1f}亿，{cap:.0f}亿",
            "market_cap_yi": cap,
            "score": 50 + cap_weight(cap) * 20 + min(flow_ratio * 10, 20),
        }
        stats["flow"] += 1

    # --- 规则 4: 全市场蓄势个股（efinance 数据） ---
    for st in all_stocks:
        code = st["code"]
        if code in selected:
            continue
        cap = st["market_cap_yi"]
        if cap < 50 or cap > 500:
            continue
        if st["change_pct"] < -2 or st["change_pct"] > 3:
            continue
        activity = st["amount_yi"] / max(cap, 1) * 100
        if activity < 3:
            continue
        selected[code] = {
            "code": code, "name": st["name"],
            "source": "screening",
            "reason": f"中盘蓄势：{cap:.0f}亿，涨{st['change_pct']:+.1f}%，活跃度{activity:.1f}%",
            "market_cap_yi": cap,
            "score": 40 + cap_weight(cap) * 20 + min(activity, 15),
        }
        stats["catalyst"] += 1

    # 排序 + 截断
    candidates = list(selected.values())
    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = candidates[:15]

    log(f"  蓄势: {stats['accumulation']} | 传导: {stats['chain']} | 资金: {stats['flow']} | 筛选: {stats['catalyst']}", verbose)
    log(f"  合计: {len(candidates)} 只", verbose)
    return candidates


def write_outputs(candidates, verbose=False):
    today = datetime.now().strftime("%Y-%m-%d")
    output = {
        "date": today,
        "candidates": candidates,
        "stats": {
            "total": len(candidates),
            "by_source": {},
            "avg_market_cap": 0,
        },
    }
    total_cap = 0
    for c in candidates:
        src = c["source"]
        output["stats"]["by_source"][src] = output["stats"]["by_source"].get(src, 0) + 1
        total_cap += c.get("market_cap_yi", 0)
    if candidates:
        output["stats"]["avg_market_cap"] = round(total_cap / len(candidates))

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    with open(DOCS_DATA / "candidates.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    codes = ",".join(c["code"] for c in candidates)
    with open(DOCS_DATA / "candidate_codes.txt", "w", encoding="utf-8") as f:
        f.write(codes + "\n")
    log(f"  候选: {codes}", verbose)


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    print("🎯 候选股票池生成器启动（催化剂驱动）", file=sys.stderr)

    catalysts_data = read_catalysts(verbose)
    all_stocks = get_all_stocks_efinance(verbose)
    fund_flow = get_fund_flow(verbose)

    if not all_stocks and not fund_flow:
        print("⚠️ 无数据可用", file=sys.stderr)
        sys.exit(1)

    candidates = select_candidates(catalysts_data, all_stocks, fund_flow, verbose)

    if not candidates:
        print("⚠️ 未生成候选", file=sys.stderr)
        write_outputs([], verbose)
        sys.exit(0)

    write_outputs(candidates, verbose)
    print(f"✅ 候选池: {len(candidates)} 只", file=sys.stderr)
    for c in candidates:
        cap = c.get("market_cap_yi", 0)
        print(f"   {c['code']} {c['name']} [{c['source']}] {cap:.0f}亿 | {c['reason'][:50]}", file=sys.stderr)


if __name__ == "__main__":
    main()
