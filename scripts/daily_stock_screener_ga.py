#!/usr/bin/env python3
"""
市场数据采集脚本 — 从 efinance 获取板块+个股+概念数据。

输出：docs/data/screener_data.json
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
    """获取板块资金流向 Top 15。优先 efinance，回退 curl。"""
    # 尝试 efinance
    try:
        import efinance as ef
        # 东方财富行业板块资金流向
        df = ef.stock.get_belong_board("000001")
        if df is not None and not df.empty:
            sectors = []
            for _, row in df.iterrows():
                sectors.append({
                    "code": str(row.get("板块代码", row.get("股票代码", ""))),
                    "name": str(row.get("板块名称", row.get("股票名称", ""))),
                    "change_pct": round(float(row.get("涨跌幅", 0) or 0), 2),
                    "net_inflow_yi": round(float(row.get("主力净流入-净额", 0) or 0) / 1e8, 2),
                })
            if sectors:
                return sectors[:15]
    except Exception:
        pass

    # 回退 curl
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
    """获取 A 股涨幅前 20。优先 efinance，回退 curl。"""
    try:
        import efinance as ef
        df = ef.stock.get_realtime_quotes()
        if df is not None and not df.empty:
            # 按涨跌幅排序取前20
            df_sorted = df.sort_values("涨跌幅", ascending=False).head(20)
            gainers = []
            for _, row in df_sorted.iterrows():
                gainers.append({
                    "code": str(row.get("股票代码", "")),
                    "name": str(row.get("股票名称", "")),
                    "change_pct": round(float(row.get("涨跌幅", 0) or 0), 2),
                    "turnover": round(float(row.get("换手率", 0) or 0), 2),
                    "high": float(row.get("最高", 0) or 0),
                    "low": float(row.get("最低", 0) or 0),
                    "open": float(row.get("开盘", 0) or 0),
                })
            if gainers:
                return gainers
    except Exception:
        pass

    # 回退 curl
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
    """获取概念板块资金流向 Top 10。优先 efinance，回退 curl。"""
    try:
        import efinance as ef
        # 概念板块 — 尝试通过 board 接口
        # efinance 没有直接的概念板块 API，跳过
    except Exception:
        pass

    # curl
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

    output = {
        "date": date_str,
        "time": time_str,
        "sector_flow": [],
        "top_gainers": [],
        "concept_flow": [],
    }

    for s in sectors:
        output["sector_flow"].append({
            "code": s.get("code", s.get("f12", "")),
            "name": s.get("name", s.get("f14", "")),
            "change_pct": s.get("change_pct", s.get("f3", 0)),
            "net_inflow_yi": s.get("net_inflow_yi",
                round(s.get("f62", 0) / 1e8, 2) if s.get("f62") else 0),
        })

    for g in gainers:
        output["top_gainers"].append({
            "code": g.get("code", g.get("f12", "")),
            "name": g.get("name", g.get("f14", "")),
            "change_pct": g.get("change_pct", g.get("f3", 0)),
            "turnover": g.get("turnover", g.get("f8", 0)),
            "high": g.get("high", g.get("f15", 0)),
            "low": g.get("low", g.get("f16", 0)),
            "open": g.get("open", g.get("f17", 0)),
        })

    for c in concepts:
        output["concept_flow"].append({
            "code": c.get("code", c.get("f12", "")),
            "name": c.get("name", c.get("f14", "")),
            "change_pct": c.get("change_pct", c.get("f3", 0)),
            "net_inflow_yi": c.get("net_inflow_yi",
                round(c.get("f62", 0) / 1e8, 2) if c.get("f62") else 0),
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
