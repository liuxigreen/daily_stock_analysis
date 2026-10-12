#!/usr/bin/env python3
"""
市场数据采集脚本 — 从新浪/腾讯获取板块+个股+概念数据。

数据源：market_source（新浪+腾讯），替代挂掉的 eastmoney/efinance。
输出：docs/data/screener_data.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_source as ms

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"


def get_sector_flow():
    """行业板块资金流/涨幅 Top 15（新浪）。"""
    return ms.get_sector_flow()


def get_top_gainers():
    """A 股涨幅前 20（新浪）。"""
    return ms.get_top_gainers(20)


def get_concept_flow():
    """概念板块（新浪行业板块作为近似，取涨幅前 10）。"""
    return ms.get_sector_flow()[:10]


def main():
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    print(f"📊 采集市场数据 {date_str} {time_str}")

    sectors = get_sector_flow()
    gainers = get_top_gainers()
    concepts = get_concept_flow()

    output = {
        "date": date_str,
        "time": time_str,
        "sector_flow": [],
        "top_gainers": [],
        "concept_flow": [],
    }

    for s in sectors[:15]:
        output["sector_flow"].append({
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "change_pct": s.get("change_pct", 0),
            "net_inflow_yi": s.get("amount_yi", 0),
            "leader": s.get("leader", ""),
        })

    for g in gainers[:20]:
        output["top_gainers"].append({
            "code": g.get("code", ""),
            "name": g.get("name", ""),
            "change_pct": g.get("change_pct", 0),
            "turnover": g.get("turnover", 0),
            "high": g.get("high", 0),
            "low": g.get("low", 0),
            "open": g.get("open", 0),
        })

    for c in concepts:
        output["concept_flow"].append({
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "change_pct": c.get("change_pct", 0),
            "net_inflow_yi": c.get("amount_yi", 0),
        })

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DATA / "screener_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 写入 {out_path}")
    print(f"   板块: {len(output['sector_flow'])} 个")
    print(f"   涨幅榜: {len(output['top_gainers'])} 只")
    print(f"   概念: {len(output['concept_flow'])} 个")


if __name__ == "__main__":
    main()
