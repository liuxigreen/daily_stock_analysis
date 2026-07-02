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
        raw = r.stdout.strip()
        # 尝试提取第一个完整的 JSON 对象
        depth = 0
        end = 0
        for i, c in enumerate(raw):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        json_str = raw[:end] if end else raw
        resp = json.loads(json_str)
        if "choices" in resp and resp["choices"]:
            return resp["choices"][0]["message"]["content"]
        else:
            print(f"⚠️ API 响应异常: {raw[:300]}", file=sys.stderr)
            return None
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

    # 候选标的
    candidates_path = DOCS_DATA / "candidates.json"
    if candidates_path.exists():
        with open(candidates_path, encoding="utf-8") as f:
            data["candidates"] = json.load(f)

    return data


def build_prompt(data):
    """构建前瞻性 AI 分析 prompt。"""
    date = datetime.now().strftime("%Y-%m-%d")

    parts = [f"""你是A股前瞻性选股分析师。今天是 {date}。

核心目标：提前发现未来 1-4 周的市场风向，找到产业链中还没被市场发现的机会。
你不追已爆发的热点，而是找"下一个"会爆发的方向。

选股原则：
1. 市值 50-500亿优先（中盘弹性股），回避千亿以上蓝筹
2. 优先选有明确催化剂（政策/事件/产业链传导）的标的
3. 多维度分析：催化剂 + 产业链位置 + 资金面 + 技术面 + 估值
4. 找"蓄势待发"的，不追已涨停或涨幅>5%的
5. 产业链传导思维：A环节已涨 → 找B环节还没动的
\n"""]

    # 蓄势信号
    catalysts = data.get("catalysts", {})
    if catalysts.get("accumulation_signals"):
        parts.append("## 蓄势信号（资金在吸筹但价格没动）")
        for s in catalysts["accumulation_signals"][:8]:
            parts.append(f"- {s.get('name','')} 涨{s.get('change_pct',0):+.1f}% 评分{s.get('score',0)} | {'；'.join(s.get('reasons',[]))}")
        parts.append("")

    # 产业链传导
    if catalysts.get("chain_propagations"):
        parts.append("## 产业链传导机会（上游已启动，下游待补涨）")
        for p in catalysts["chain_propagations"][:5]:
            started = ", ".join(s["name"] for s in p.get("started", []))
            next_ops = ", ".join(s["name"] for s in p.get("next_opportunities", [])[:3])
            parts.append(f"- {p.get('theme','')}: {started} 已涨 → 关注 {next_ops}")
            parts.append(f"  逻辑: {p.get('logic','')}")
        parts.append("")

    # 候选标的
    candidates = data.get("candidates", {})
    if candidates.get("candidates"):
        parts.append("## 候选标的（已通过市值+蓄势筛选）")
        for c in candidates["candidates"][:15]:
            cap = c.get("market_cap_yi", 0)
            parts.append(f"- {c.get('code','')} {c.get('name','')} {cap:.0f}亿 [{c.get('source','')}] {c.get('reason','')[:60]}")
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
1. 选出 5-6 只未来 1-4 周值得关注的A股
2. 从候选标的中选择，也可补充你认为有价值的标的
3. 每只票必须给出多维度分析：
   - 催化剂：什么事件/政策/趋势会驱动它？
   - 产业链位置：在供应链哪个环节？先受益还是后受益？
   - 资金面：主力在进还是出？
   - 技术面：位置好不好？支撑在哪？
   - 估值：贵不贵？
4. 市值 50-500亿优先，说明为什么选这只而不是同板块大票
5. 给出：代码、名称、买入理由、买入区间、止损位、目标价
6. 不追涨停，不追涨幅>5%的，找蓄势待发的

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
      "market_cap": "160亿",
      "sector": "电池化学品",
      "reason": "电池化学品板块主力净流入15.3亿，蓄势形态",
      "catalyst": "十五五新能源规划出台在即",
      "chain_position": "电池化学品（上游材料）"
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
