#!/usr/bin/env python3
"""
GitHub Actions 版选股脚本 — 不依赖 Hermes，独立运行。
从东方财富获取市场数据，输出候选列表供 AI 分析。
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"


def curl_get(url, timeout=10):
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def get_sector_flow():
    """获取板块资金流向 Top 15。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=15&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:90+t:2+f:!50"
        "&fields=f12,f14,f3,f62,f184"
    )
    text = curl_get(url)
    if not text:
        return []
    try:
        data = json.loads(text)
        return data.get("data", {}).get("diff", [])
    except Exception:
        return []


def get_top_gainers():
    """获取 A 股涨幅前 20。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
        "&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f12,f14,f3,f8,f62,f15,f16,f17"
    )
    text = curl_get(url)
    if not text:
        return []
    try:
        data = json.loads(text)
        return data.get("data", {}).get("diff", [])
    except Exception:
        return []


def get_concept_flow():
    """获取概念板块资金流向 Top 10。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=10&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:90+t:3+f:!50"
        "&fields=f12,f14,f3,f62"
    )
    text = curl_get(url)
    if not text:
        return []
    try:
        data = json.loads(text)
        return data.get("data", {}).get("diff", [])
    except Exception:
        return []


def main():
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    print(f"📊 采集市场数据 {date_str} {time_str}")

    sectors = get_sector_flow()
    gainers = get_top_gainers()
    concepts = get_concept_flow()

    # 组装输出
    output = {
        "date": date_str,
        "time": time_str,
        "sector_flow": [],
        "top_gainers": [],
        "concept_flow": [],
    }

    for s in sectors:
        output["sector_flow"].append({
            "code": s.get("f12", ""),
            "name": s.get("f14", ""),
            "change_pct": s.get("f3", 0),
            "net_inflow_yi": round(s.get("f62", 0) / 1e8, 2) if s.get("f62") else 0,
        })

    for g in gainers:
        output["top_gainers"].append({
            "code": g.get("f12", ""),
            "name": g.get("f14", ""),
            "change_pct": g.get("f3", 0),
            "turnover": g.get("f8", 0),
            "high": g.get("f15", 0),
            "low": g.get("f16", 0),
            "open": g.get("f17", 0),
        })

    for c in concepts:
        output["concept_flow"].append({
            "code": c.get("f12", ""),
            "name": c.get("f14", ""),
            "change_pct": c.get("f3", 0),
            "net_inflow_yi": round(c.get("f62", 0) / 1e8, 2) if c.get("f62") else 0,
        })

    # 写入文件
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
