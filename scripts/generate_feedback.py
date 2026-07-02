#!/usr/bin/env python3
"""读取历史失败案例，生成复盘反馈简报，供选股分析参考"""
import json, sys, os
from datetime import datetime, timedelta

HISTORY_PATH = os.path.expanduser("~/workspace/daily_stock_analysis/docs/data/history.json")
LOOKBACK_DAYS = 60  # 从历史第一天算起

def load_history():
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"records": []}

def analyze():
    data = load_history()
    records = data.get("records", [])
    if not records:
        print("# 📋 复盘反馈\n\n暂无历史数据，继续按标准流程执行。")
        return

    # 聚合所有picks
    all_picks = []
    for r in records:
        for p in r.get("picks", []):
            all_picks.append({
                "name": p.get("name", p.get("code", "?")),
                "code": p.get("code", ""),
                "return": float(p.get("return", 0)),
                "date": r.get("date", ""),
                "review": r.get("review", ""),
                "total_count": r.get("total_count", 0),
                "win_count": r.get("win_count", 0)
            })

    failures = [p for p in all_picks if p["return"] < 0]
    wins = [p for p in all_picks if p["return"] >= 0]
    total = len(all_picks)

    avg_ret = sum(p["return"] for p in all_picks) / total if total else 0
    win_rate = len(wins) / total * 100 if total else 0
    avg_win = sum(p["return"] for p in wins) / len(wins) if wins else 0
    avg_loss = sum(p["return"] for p in failures) / len(failures) if failures else 0

    # 近7天 vs 前7天对比
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)
    recent = [p for p in all_picks if p["date"] >= cutoff.strftime("%Y-%m-%d")]
    recent_failures = [p for p in recent if p["return"] < 0]

    print("# 📋 复盘反馈（注入分析器）")
    print(f"\n统计周期：最近 {LOOKBACK_DAYS} 天，共 {len(records)} 个交易日，{total} 次推荐")
    print(f"整体胜率：{win_rate:.0f}% | 平均收益：{avg_ret:+.2f}%")
    print(f"平均盈利：{avg_win:+.2f}% | 平均亏损：{avg_loss:.2f}%")

    if recent_failures:
        print(f"\n## ❌ 近期失败案例（{len(recent_failures)} 次）")
        print("以下为最近失败的推荐，分析时借鉴原因，避免重复踩坑：")
        for f in sorted(recent_failures, key=lambda x: x["return"])[:10]:
            print(f"\n- {f['name']}（{f['code']}）{f['return']:+.2f}% | {f['date']}")
            if f["review"]:
                print(f"  复盘：{f['review']}")

    # 提取失败模式
    if failures:
        print("\n## 🔍 失败模式总结")
        # 识别失败集中度
        super_losses = [f for f in failures if f["return"] < -5]
        if super_losses:
            codes = [f["code"] for f in super_losses]
            print(f"- 大幅回撤（>-5%）共 {len(super_losses)} 次，集中在：{', '.join(codes[:5])}")
            print(f"- 平均亏损：{sum(f['return'] for f in super_losses)/len(super_losses):.2f}%")
            print(f"- 警示：-5% 以上的回撤说明止损线可能过宽，或选入的票波动率超出预期")
        # 推荐数量 vs 胜率
        high_count_days = [r for r in records if r.get("total_count", 0) >= 7]
        if high_count_days:
            high_win = sum(r.get("win_count", 0) for r in high_count_days)
            high_total = sum(r.get("total_count", 0) for r in high_count_days)
            print(f"- 当日推荐≥7只时，胜率 {high_win/high_total*100:.0f}%（{high_win}/{high_total}）")
            print(f"- 建议：减少推荐数量，聚焦最高质量的前5只")

    # 板块表现
    print("\n## 📊 板块表现")
    print("（由选股引擎自动判断，当前无板块级失败数据）")

    print(f"\n## 💡 本次选股建议")
    print("- 优先选择有明确催化剂（新闻/政策/业绩）的标的")
    print("- 评分 >30 且 试盘量 >1.5x 优先")
    print(f"- 近期平均亏损 {avg_loss:.2f}%，止损线收缩至 -6~-7%")

if __name__ == "__main__":
    analyze()