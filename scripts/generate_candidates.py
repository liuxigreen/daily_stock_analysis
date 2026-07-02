#!/usr/bin/env python3
"""
generate_candidates.py — 从催化剂数据 + 资金流向生成候选股票池。

数据源：
1. docs/data/catalysts.json（来自 catalyst_scanner.py）— 今日催化剂受益标的
2. 东方财富个股资金流向 API — 按主力净流入排序 Top 20

选择逻辑：
- 催化剂 urgency=high 的受益标的 → 自动入选
- 催化剂 urgency=medium 的受益标的 + 在资金流入 Top 20 内 → 入选
- 资金流入 Top 10 中涨幅 < 3%（蓄势/吸筹）→ 入选
- 去重、最多 15 只

输出：
- docs/data/candidates.json — 结构化候选列表
- /tmp/candidate_codes.txt — 逗号分隔代码列表（供 main.py --stocks 使用）

用法：
  python3 scripts/generate_candidates.py
  python3 scripts/generate_candidates.py --verbose
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA = REPO_DIR / "docs" / "data"

# ─── Eastmoney API 地址 ────────────────────────────────────────────
# 个股资金流向（按主力净流入降序，全市场 A 股 + 创业板 + 科创板 + 北交所）
FUND_FLOW_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get?"
    "pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
    "&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    "&fields=f12,f14,f3,f8,f62"
)

# 概念板块成分股（按主力净流入排序）
CONSTITUENTS_URL_TEMPLATE = (
    "https://push2.eastmoney.com/api/qt/clist/get?"
    "pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
    "&fid=f62&fs=b:{concept_code}+f:!2"
    "&fields=f12,f14,f3,f8,f62"
)


def log(msg, verbose=False):
    if verbose:
        print(f"  {msg}", file=sys.stderr)


def curl_get(url, timeout=10):
    """用 curl 获取 URL 内容。"""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def fetch_fund_flow_top20(verbose=False):
    """获取全市场个股按主力净流入排序 Top 20。"""
    log("请求个股资金流向 Top 20...", verbose)
    text = curl_get(FUND_FLOW_URL, timeout=8)
    if not text:
        log("⚠️ 资金流向 API 无响应", verbose)
        return []

    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
    except (json.JSONDecodeError, KeyError):
        log("⚠️ 资金流向 JSON 解析失败", verbose)
        return []

    stocks = []
    for item in diffs:
        code = item.get("f12", "")
        name = item.get("f14", "")
        change = item.get("f3", 0)
        net_inflow = item.get("f62", 0)
        net_inflow_yi = net_inflow / 1e8 if net_inflow else 0

        if not code or not name:
            continue

        stocks.append({
            "code": code,
            "name": name,
            "change_pct": round(change, 2) if change else 0,
            "net_inflow_yi": round(net_inflow_yi, 2),
            "rank": len(stocks) + 1,  # 1-based rank
        })

    log(f"  获取 {len(stocks)} 只资金流入标的", verbose)
    return stocks


def read_catalysts(verbose=False):
    """读取 docs/data/catalysts.json，返回催化剂列表和 beneficiary 索引。"""
    path = DOCS_DATA / "catalysts.json"
    if not path.exists():
        log(f"⚠️ catalysts.json 不存在: {path}", verbose)
        return [], {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        log("⚠️ catalysts.json 解析失败", verbose)
        return [], {}

    catalysts = data.get("catalysts", [])

    # 构建 beneficiary 索引: code -> {name, reasons[], sources[]}
    beneficiaries = {}  # code -> {name, reasons, urgency, from_catalyst}
    for cat in catalysts:
        urgency = cat.get("urgency", "low")
        title = cat.get("title", "未知催化剂")
        for stock in cat.get("beneficiary_stocks", []):
            code = stock.get("code", "")
            name = stock.get("name", "")
            reason = stock.get("reason", "")
            if not code:
                continue
            if code not in beneficiaries:
                beneficiaries[code] = {
                    "code": code,
                    "name": name,
                    "reasons": [],
                    "urgency": urgency,
                    "from_catalyst": True,
                }
            # 如果同一只股票出现在多个催化剂中，取最高 urgency
            urgency_priority = {"low": 0, "medium": 1, "high": 2}
            existing = beneficiaries[code]
            existing["reasons"].append(f"[{urgency}] {title}: {reason}")
            if urgency_priority.get(urgency, 0) > urgency_priority.get(existing["urgency"], 0):
                existing["urgency"] = urgency

    log(f"  催化剂受益标的: {len(beneficiaries)} 只 (来自 {len(catalysts)} 条催化剂)", verbose)
    return catalysts, beneficiaries


def read_screener_data(verbose=False):
    """读取 docs/data/screener_data.json，提取涨幅榜数据作为参考。"""
    path = DOCS_DATA / "screener_data.json"
    if not path.exists():
        log(f"⚠️ screener_data.json 不存在: {path}", verbose)
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        log("⚠️ screener_data.json 解析失败", verbose)
        return {}

    return data


def select_candidates(beneficiaries, fund_flow_top20, verbose=False):
    """
    核心选择逻辑。

    规则：
    1. 催化剂 urgency=high → 自动入选
    2. 催化剂 urgency=medium + 在资金流入 Top 20 → 入选
    3. 资金流入 Top 10 + 涨幅 < 3% → 入选（吸筹/蓄势）
    4. 去重、最多 15 只
    """
    # 资金流入 Top 20 的 code 集合（用于快速查找）
    flow_codes = {s["code"]: s for s in fund_flow_top20}
    # 资金流入 Top 10 的 code 集合
    flow_top10_codes = {s["code"]: s for s in fund_flow_top20 if s["rank"] <= 10}

    selected = {}  # code -> candidate dict
    auto_included = 0
    medium_matched = 0
    accumulation = 0

    # --- 规则 1: 催化剂 urgency=high 自动入选 ---
    for code, info in beneficiaries.items():
        if info["urgency"] == "high":
            reason_str = " | ".join(info["reasons"])
            selected[code] = {
                "code": code,
                "name": info["name"],
                "source": "catalyst",
                "reason": f"催化剂高优: {reason_str[:200]}",
            }
            auto_included += 1

    # --- 规则 2: 催化剂 urgency=medium + 在资金流入 Top 20 ---
    for code, info in beneficiaries.items():
        if code in selected:
            continue
        if info["urgency"] == "medium" and code in flow_codes:
            flow_stock = flow_codes[code]
            reason_str = " | ".join(info["reasons"])
            selected[code] = {
                "code": code,
                "name": info["name"],
                "source": "both",
                "reason": (
                    f"催化剂中优先 (催化剂{info['urgency']}) + "
                    f"资金流入第{flow_stock['rank']}名 ({flow_stock['net_inflow_yi']}亿)"
                ),
            }
            medium_matched += 1

    # --- 规则 3: 资金流入 Top 10 + 涨幅 < 3% (蓄势吸筹) ---
    for code, flow_stock in flow_top10_codes.items():
        if code in selected:
            # 如果已从 catalyst 入选，升级 source 为 both（如果还没标记 both）
            if selected[code]["source"] == "catalyst" and code in flow_codes:
                selected[code]["source"] = "both"
                selected[code]["reason"] += (
                    f" | 同时资金流入第{flow_stock['rank']}名 ({flow_stock['net_inflow_yi']}亿)"
                )
            continue
        if flow_stock["change_pct"] < 3:
            selected[code] = {
                "code": code,
                "name": flow_stock["name"],
                "source": "flow",
                "reason": (
                    f"资金流入第{flow_stock['rank']}名 ({flow_stock['net_inflow_yi']}亿)，"
                    f"涨幅{flow_stock['change_pct']:+.1f}% < 3%，蓄势吸筹"
                ),
            }
            accumulation += 1

    # --- 规则 4: 去重已完成（用 dict 天然去重），现在限制数量 ---
    log(f"  规则1(高优催化剂): {auto_included} 只", verbose)
    log(f"  规则2(中优+资金流入): {medium_matched} 只", verbose)
    log(f"  规则3(吸筹蓄势): {accumulation} 只", verbose)
    log(f"  初步合计: {len(selected)} 只", verbose)

    candidates = list(selected.values())

    # 如果超过 15 只，按优先级截断
    if len(candidates) > 15:
        # 优先级: both > catalyst > flow
        def priority_key(c):
            source_order = {"both": 0, "catalyst": 1, "flow": 2}
            return source_order.get(c["source"], 99)
        candidates.sort(key=priority_key)
        candidates = candidates[:15]
        log(f"  超过15只上限，截断后: {len(candidates)} 只", verbose)

    return candidates


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("🎯 生成候选股票池", file=sys.stderr)

    # 1. 读取催化剂数据
    catalysts_data, beneficiaries = read_catalysts(verbose)
    if not beneficiaries:
        log("⚠️ 没有催化剂受益标的，将仅依赖资金流向数据", verbose)

    # 2. 读取筛选器数据（辅助参考，主要用 API）
    screener = read_screener_data(verbose)

    # 3. 从 Eastmoney 获取个股资金流向 Top 20
    fund_flow_top20 = fetch_fund_flow_top20(verbose)
    if not fund_flow_top20:
        print("⚠️ 资金流向数据获取失败，无法生成候选池", file=sys.stderr)
        sys.exit(1)

    # 4. 执行选择逻辑
    candidates = select_candidates(beneficiaries, fund_flow_top20, verbose)

    if not candidates:
        print("⚠️ 未生成任何候选标的", file=sys.stderr)
        # 输出空文件
        write_outputs([], verbose)
        sys.exit(0)

    # 5. 输出
    write_outputs(candidates, verbose)

    print(f"✅ 候选池: {len(candidates)} 只股票", file=sys.stderr)
    for c in candidates:
        print(f"   {c['code']} {c['name']} [{c['source']}] {c['reason'][:80]}", file=sys.stderr)


def write_outputs(candidates, verbose=False):
    """写入 candidates.json 和 /tmp/candidate_codes.txt。"""
    today = datetime.now().strftime("%Y-%m-%d")

    # --- candidates.json ---
    output = {
        "date": today,
        "candidates": candidates,
        "stats": {
            "total": len(candidates),
            "by_source": {},
        },
    }
    for c in candidates:
        src = c["source"]
        output["stats"]["by_source"][src] = output["stats"]["by_source"].get(src, 0) + 1

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DATA / "candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"  写入 {out_path}", verbose)

    # --- /tmp/candidate_codes.txt ---
    codes = [c["code"] for c in candidates]
    codes_str = ",".join(codes)
    tmp_path = Path("/tmp/candidate_codes.txt")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(codes_str + "\n")
        log(f"  写入 {tmp_path}: {codes_str}", verbose)
    except (OSError, FileNotFoundError):
        # Android/Termux 无 /tmp，回退到 docs/data/
        tmp_path = DOCS_DATA / "candidate_codes.txt"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(codes_str + "\n")
        log(f"  写入 {tmp_path} (fallback): {codes_str}", verbose)
    print(f"    {tmp_path}: {codes_str}", file=sys.stderr)


if __name__ == "__main__":
    main()
