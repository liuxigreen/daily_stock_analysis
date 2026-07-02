#!/usr/bin/env python3
"""
picks.json 生成器 — 从 AI 分析结果 + 催化剂数据组装最终 picks.json。

输入：docs/data/ai_analysis.json + docs/data/catalysts.json
输出：docs/data/picks.json + docs/data/history.json
"""
import json
import os
from datetime import datetime
from pathlib import Path

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"


def main():
    date = datetime.now().strftime("%Y-%m-%d")

    # 加载 AI 分析结果
    analysis_path = DOCS_DATA / "ai_analysis.json"
    if not analysis_path.exists():
        print("⚠️ ai_analysis.json 不存在，跳过", flush=True)
        return

    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)

    # 加载催化剂数据
    catalysts = {}
    catalyst_path = DOCS_DATA / "catalysts.json"
    if catalyst_path.exists():
        with open(catalyst_path, encoding="utf-8") as f:
            catalysts = json.load(f)

    # 组装 market_context
    main_theme = analysis.get("main_theme", "")
    hot_concepts = catalysts.get("hot_concepts", [])
    # 如果 hot_concepts 为空，从 accumulation_signals 中提取
    if not hot_concepts:
        acc = catalysts.get("accumulation_signals", [])
        hot_concepts = [{"name": s.get("name", "")} for s in acc if s.get("score", 0) >= 20]
    accumulating = "、".join([c.get("name", "") for c in hot_concepts[:3]]) if hot_concepts else ""

    picks_data = {
        "date": date,
        "market_context": {
            "main_line": main_theme,
            "accumulating": accumulating,
            "overheated": "",
            "sentiment": "neutral",
            "policy": "",
        },
        "picks": analysis.get("picks", []),
    }

    # 写入 picks.json
    picks_path = DOCS_DATA / "picks.json"
    with open(picks_path, "w", encoding="utf-8") as f:
        json.dump(picks_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 写入 picks.json ({len(picks_data['picks'])} 只)")

    # 更新 history.json
    history_path = DOCS_DATA / "history.json"
    history = {"records": []}
    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)

    records = history.get("records", [])
    # 去重
    today_record = None
    for r in records:
        if r.get("date") == date:
            today_record = r
            break

    picks_summary = []
    for p in picks_data["picks"]:
        picks_summary.append({
            "code": p.get("code", ""),
            "name": p.get("name", ""),
            "return": p.get("change_pct", 0),
            "status": "持有中",
        })

    new_record = {
        "date": date,
        "total_count": len(picks_data["picks"]),
        "win_count": 0,
        "avg_return": 0,
        "review": main_theme,
        "picks": picks_summary,
    }

    if today_record:
        today_record.update(new_record)
    else:
        records.insert(0, new_record)

    history["records"] = records[:90]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"✅ 更新 history.json ({len(records)} 条记录)")


if __name__ == "__main__":
    main()
