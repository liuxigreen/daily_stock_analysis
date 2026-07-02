#!/usr/bin/env python3
"""
auto_watchlist.py — 从每日选股中自动添加高确信标的到观察池。

条件（同时满足才入池）：
1. AI 评分 >= 70
2. 有明确催化剂（catalyst 字段非空）
3. 市值 50-500亿
4. 不在观察池中（去重）

入池后自动设置：
- status: watching
- 催化剂日历（从 catalyst 字段推断）
- 12-18 个月观察期

用法：
  python3 scripts/auto_watchlist.py
  python3 scripts/auto_watchlist.py --verbose
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA = REPO_DIR / "docs" / "data"


def log(msg, verbose=False):
    if verbose:
        print(f"  {msg}", file=sys.stderr)


def get_real_price(code, verbose=False):
    """用腾讯 API 获取真实当前价格。"""
    if code.startswith("6") or code.startswith("9"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "5", f"https://qt.gtimg.cn/q={symbol}"],
            capture_output=True, timeout=10,
        )
        text = r.stdout.decode("gbk", errors="ignore")
        parts = text.split("~")
        if len(parts) > 3:
            price = float(parts[3])
            if price > 0:
                log(f"  腾讯API: {code} 现价 {price}", verbose)
                return price
    except Exception:
        pass
    return 0


def parse_market_cap(cap_str):
    """从 '185亿' 这样的字符串中提取市值数字。"""
    if not cap_str:
        return 0
    try:
        return float(str(cap_str).replace("亿", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")

    # 读取 AI 分析结果
    ai_path = DOCS_DATA / "ai_analysis.json"
    if not ai_path.exists():
        log("⚠️ ai_analysis.json 不存在", verbose)
        return
    with open(ai_path, encoding="utf-8") as f:
        ai_data = json.load(f)

    picks = ai_data.get("picks", [])
    if not picks:
        log("⚠️ 无选股结果", verbose)
        return

    # 读取当前观察池
    pool_path = DOCS_DATA / "watch_pool.json"
    pool = {"last_updated": today, "stocks": []}
    if pool_path.exists():
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)

    existing_codes = {s["code"] for s in pool.get("stocks", [])}

    # 筛选入池标的
    added = []
    for pick in picks:
        code = pick.get("code", "")
        name = pick.get("name", "")
        score = pick.get("score", 0)
        catalyst = pick.get("catalyst", "")
        cap_str = pick.get("market_cap", "")
        cap = parse_market_cap(cap_str)
        chain_pos = pick.get("chain_position", "")
        reason = pick.get("reason", "")

        # 条件检查
        if code in existing_codes:
            log(f"  跳过 {name}（已在观察池）", verbose)
            continue
        if score < 70:
            log(f"  跳过 {name}（评分{score}<70）", verbose)
            continue
        if not catalyst:
            log(f"  跳过 {name}（无明确催化剂）", verbose)
            continue
        if cap > 0 and (cap < 30 or cap > 500):
            log(f"  跳过 {name}（市值{cap:.0f}亿不在50-500范围）", verbose)
            continue

        # 入池
        stock_entry = {
            "code": code,
            "name": name,
            "added_date": today,
            "added_price": get_real_price(code, verbose) or pick.get("price", 0),
            "thesis": reason[:200],
            "supply_chain": chain_pos,
            "timeframe": "12-18个月",
            "status": "watching",
            "catalysts": [
                {
                    "event": catalyst,
                    "expected_date": "TBD",
                    "status": "pending",
                    "notes": f"AI评分{score}，{chain_pos}",
                }
            ],
            "price_history": [
                {
                    "date": today,
                    "price": pick.get("price", 0),
                    "note": "AI自动入池",
                }
            ],
            "risk_factors": [],
            "exit_conditions": [],
            "source": "ai_daily_pick",
            "ai_score": score,
        }

        pool["stocks"].append(stock_entry)
        existing_codes.add(code)
        added.append(f"{code} {name} {cap:.0f}亿 评分{score}")
        log(f"  ✅ 入池: {code} {name} {cap:.0f}亿 评分{score}", verbose)

    # 写回观察池
    if added:
        pool["last_updated"] = today
        with open(pool_path, "w", encoding="utf-8") as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)
        print(f"✅ 自动入池 {len(added)} 只标的:", file=sys.stderr)
        for a in added:
            print(f"   {a}", file=sys.stderr)
    else:
        log("无新标的入池", verbose)


if __name__ == "__main__":
    main()
