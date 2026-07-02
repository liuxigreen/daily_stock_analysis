#!/usr/bin/env python3
"""
AI 分析师 — 用 DeepSeek (via 9Router) 分析市场数据，选出 5-6 只标的。

环境变量：
  ROUTER_API_KEY - 9Router API key

输入：docs/data/screener_data.json + docs/data/catalysts.json
输出：docs/data/ai_analysis.json
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
API_KEY = os.environ.get("ROUTER_API_KEY", "")
API_URL = "https://9router.opspilot.me/v1/chat/completions"
MODEL = "edgen"


def call_llm(prompt, max_tokens=4000):
    """调用 DeepSeek via 9Router。"""
    if not API_KEY:
        print("⚠️ ROUTER_API_KEY 未设置，跳过 AI 分析", file=sys.stderr)
        return None

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    })

    cmd = [
        "curl", "-s", "--max-time", "60",
        "-X", "POST", API_URL,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {API_KEY}",
        "-d", payload,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        resp = json.loads(r.stdout)
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}", file=sys.stderr)
        return None


def load_data():
    """加载市场数据和催化剂数据。"""
    data = {}

    # 选股数据
    screener_path = DOCS_DATA / "screener_data.json"
    if screener_path.exists():
        with open(screener_path, encoding="utf-8") as f:
            data["screener"] = json.load(f)

    # 催化剂数据
    catalyst_path = DOCS_DATA / "catalysts.json"
    if catalyst_path.exists():
        with open(catalyst_path, encoding="utf-8") as f:
            data["catalysts"] = json.load(f)

    # 观察池
    watch_path = DOCS_DATA / "watch_pool_report.json"
    if watch_path.exists():
        with open(watch_path, encoding="utf-8") as f:
            data["watchpool"] = json.load(f)

    return data


def build_prompt(data):
    """构建 AI 分析 prompt。"""
    date = datetime.now().strftime("%Y-%m-%d")

    parts = [f"你是A股选股分析师。今天是 {date}。根据以下数据选出 5-6 只明日值得关注的A股。\n"]

    # 催化剂
    catalysts = data.get("catalysts", {})
    if catalysts.get("catalysts"):
        parts.append("## 今日催化剂")
        for c in catalysts["catalysts"][:5]:
            parts.append(f"- [{c.get('urgency','')}] {c.get('title','')}")
            if c.get("chain"):
                parts.append(f"  产业链: {c['chain']}")
            for s in c.get("beneficiary_stocks", [])[:3]:
                parts.append(f"  受益: {s.get('code','')} {s.get('name','')} - {s.get('reason','')}")
        parts.append("")

    # 热点概念
    if catalysts.get("hot_concepts"):
        parts.append("## 异动概念板块")
        for c in catalysts["hot_concepts"][:5]:
            parts.append(f"- {c.get('name','')} {c.get('change_pct',0):+.1f}% 主力{c.get('net_inflow',0):.1f}亿 → {c.get('chain','')}")
            for s in c.get("constituents", [])[:3]:
                parts.append(f"  {s.get('code','')} {s.get('name','')} {s.get('change_pct',0):+.1f}%")
        parts.append("")

    # 板块资金流
    screener = data.get("screener", {})
    if screener.get("sector_flow"):
        parts.append("## 板块资金流向 Top 10")
        for s in screener["sector_flow"][:10]:
            parts.append(f"- {s.get('name','')} {s.get('change_pct',0):+.1f}% 主力{s.get('net_inflow_yi',0):.1f}亿")
        parts.append("")

    # 涨幅榜
    if screener.get("top_gainers"):
        parts.append("## 今日涨幅前10")
        for g in screener["top_gainers"][:10]:
            parts.append(f"- {g.get('code','')} {g.get('name','')} {g.get('change_pct',0):+.1f}% 换手{g.get('turnover',0):.1f}%")
        parts.append("")

    # 观察池
    watchpool = data.get("watchpool", {})
    if watchpool.get("stocks"):
        parts.append("## 观察池动态")
        for w in watchpool["stocks"]:
            parts.append(f"- {w.get('name','')} {w.get('code','')} 现价{w.get('current_price',0)} 盈亏{w.get('pnl_pct',0):+.1f}%")
        parts.append("")

    # 选股指令
    parts.append("""## 选股要求
1. 选出 5-6 只明日值得关注的A股
2. 优先选择有明确催化剂的标的
3. 给出：代码、名称、买入理由（一句话）、买入区间、止损位、目标价
4. 考虑板块轮动和资金流向
5. 不追涨停，找蓄势待发的

输出 JSON 格式：
```json
{
  "date": "日期",
  "main_theme": "今日主线",
  "picks": [
    {
      "code": "000792",
      "name": "盐湖股份",
      "price": 30.49,
      "change_pct": 1.0,
      "score": 40,
      "target": 33.5,
      "stop_loss": 28.5,
      "buy_range": "29.8-30.8",
      "expected_return": "+10%",
      "highlight": "",
      "market_cap": "",
      "sector": "电池化学品",
      "reason": "电池化学品板块主力净流入15.3亿，蓄势形态"
    }
  ]
}
```""")

    return "\n".join(parts)


def main():
    if not API_KEY:
        print("❌ ROUTER_API_KEY 未设置", file=sys.stderr)
        sys.exit(1)

    print("🤖 AI 分析师启动", file=sys.stderr)

    data = load_data()
    prompt = build_prompt(data)

    print(f"📡 调用 DeepSeek 分析...", file=sys.stderr)
    result = call_llm(prompt)

    if not result:
        print("❌ AI 分析失败", file=sys.stderr)
        sys.exit(1)

    # 提取 JSON
    try:
        # 尝试从 markdown code block 中提取
        if "```json" in result:
            json_str = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            json_str = result.split("```")[1].split("```")[0].strip()
        else:
            json_str = result.strip()

        analysis = json.loads(json_str)
    except json.JSONDecodeError:
        # 如果 JSON 解析失败，保存原始文本
        analysis = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "raw_text": result,
            "picks": [],
        }

    # 添加元数据
    analysis["generated_at"] = datetime.now().isoformat()
    analysis["model"] = MODEL

    # 写入文件
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DATA / "ai_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    picks = analysis.get("picks", [])
    print(f"✅ AI 分析完成", file=sys.stderr)
    print(f"   选出: {len(picks)} 只", file=sys.stderr)
    for p in picks:
        print(f"   {p.get('code','')} {p.get('name','')} {p.get('buy_range','')}", file=sys.stderr)


if __name__ == "__main__":
    main()
