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
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
API_KEY = os.environ.get("ROUTER_API_KEY", "")
API_URL = "https://9router.opspilot.me/v1/chat/completions"
MODEL = "edgen"


def validate_picks(picks):
    """校验每个 pick 的 code 与名称是否匹配，跳过幻觉代码。"""
    valid = []
    for pick in picks:
        code = pick.get("code", "")
        name = pick.get("name", "")
        if not code:
            continue
        # 确定前缀
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
            if len(parts) > 2:
                real_name = parts[1]
                if real_name and name and real_name != name:
                    print(f"  ⚠️ 跳过 {name}({code})：代码实际对应{real_name}，AI 幻觉错误代码", file=sys.stderr)
                    continue
        except Exception:
            pass  # 无法校验时放行
        valid.append(pick)
    return valid


def _try_repair_json(text):
    """H1: 尝试从 LLM 文本中提取 JSON，支持 json_repair 和正则回退。"""
    # 预处理：全角冒号/逗号/引号→半角（LLM 输出常见问题）
    text = text.replace("\uff1a", ":").replace("\uff0c", ",").replace("\u201c", '"').replace("\u201d", '"')
    # 尝试用 json_repair
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        result = json.loads(repaired)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    # 尝试用正则提取 ```json ... ``` 块
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取最后一个完整的 JSON 对象
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1
    return None


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

    # H6: 添加 3 次重试，每次间隔 2 秒
    max_retries = 3
    for attempt in range(max_retries):
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
            if attempt < max_retries - 1:
                print(f"⚠️ LLM 调用失败(尝试 {attempt + 1}/{max_retries}): {e}，2秒后重试", file=sys.stderr)
                time.sleep(2)
            else:
                print(f"❌ LLM 调用失败(已重试 {max_retries} 次): {e}", file=sys.stderr)
                return None


def load_data():
    """加载市场数据和催化剂数据。"""
    data = {}
    files = {
        "screener": "screener_data.json",
        "catalysts": "catalysts.json",
        "watchpool": "watch_pool_report.json",
        "candidates": "candidates.json",
    }
    for key, filename in files.items():
        path = DOCS_DATA / filename
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data[key] = json.load(f)
            except json.JSONDecodeError as e:
                print(f"⚠️ {filename} JSON解析失败: {e}", file=sys.stderr)
    return data


def get_market_environment():
    """获取市场环境：上证指数近5日涨跌。"""
    try:
        import efinance as ef
        df = ef.stock.get_quote_history("000001", klt=101)  # 日线
        if df is not None and not df.empty:
            # 取最近5个交易日
            recent = df.tail(5)
            cols = set(recent.columns)
            close_col = next((c for c in ["收盘", "close", "收盘价"] if c in cols), None)
            if close_col and len(recent) >= 2:
                closes = recent[close_col].astype(float).tolist()
                start_price = closes[0]
                end_price = closes[-1]
                change_pct = (end_price - start_price) / start_price * 100 if start_price > 0 else 0
                # 判断市场阶段：用MA5和MA20的关系
                all_closes = df[close_col].astype(float).tolist()
                if len(all_closes) >= 20:
                    ma5 = sum(all_closes[-5:]) / 5
                    ma20 = sum(all_closes[-20:]) / 20
                    if ma5 > ma20:
                        phase = "牛市（MA5>MA20）"
                    elif ma5 < ma20:
                        phase = "熊市（MA5<MA20）"
                    else:
                        phase = "震荡（MA5≈MA20）"
                else:
                    phase = "数据不足"
                start_str = f"{start_price:.2f}"
                end_str = f"{end_price:.2f}"
                sign = "+" if change_pct >= 0 else ""
                return f"## 市场环境\n上证指数近5日：{start_str} → {end_str}（{sign}{change_pct:.1f}%）\n当前阶段：{phase}\n"
    except Exception:
        pass
    return ""


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
6. 流动性过滤：日均成交额<1亿的不选（无法有效进出）
7. 板块分散：6只票至少覆盖2个以上不同板块，避免集中风险
8. 不得推荐ST、*ST、退市风险警示、退市整理期、名称含'退'的标的
\n"""]

    # 前瞻事件（新增）
    catalysts = data.get("catalysts", {})
    if catalysts.get("forward_events"):
        parts.append("## 未来催化事件（已知即将发生）")
        for e in catalysts["forward_events"]:
            parts.append(f"- {e.get('title','')}: 影响 {', '.join(e.get('affected',[]))}")
        parts.append("")

    # 今日重要新闻（新增）
    if catalysts.get("top_headlines"):
        parts.append("## 今日重要新闻")
        for h in catalysts["top_headlines"][:8]:
            parts.append(f"- {h}")
        parts.append("")

    # 蓄势信号
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
            pe = c.get("pe", "")
            pb = c.get("pb", "")
            pe_str = f" PE:{pe}" if pe else ""
            pb_str = f" PB:{pb}" if pb else ""
            parts.append(f"- {c.get('code','')} {c.get('name','')} {cap:.0f}亿{pe_str}{pb_str} [{c.get('source','')}] {c.get('reason','')[:60]}")
        parts.append("")

    # 市场环境
    market_env = get_market_environment()
    if market_env:
        parts.append(market_env)

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

    # 观察池（增强版）
    watchpool = data.get("watchpool", {})
    if watchpool.get("stocks"):
        parts.append("## 观察池动态（已有持仓/观察标的，避免重复推荐）")
        for w in watchpool["stocks"]:
            parts.append(f"- {w.get('name','')} {w.get('code','')} 现价{w.get('current_price',0)} 盈亏{w.get('pnl_pct',0):+.1f}%")
            if w.get("thesis"):
                parts.append(f"  逻辑: {w.get('thesis','')[:80]}")
            if w.get("catalyst_alerts"):
                for a in w["catalyst_alerts"][:1]:
                    parts.append(f"  催化: {a.get('event','')} ({a.get('expected_date','TBD')})")
        parts.append("")

    # 复盘反馈（新增 — 让 AI 从失败中学习）
    feedback_path = DOCS_DATA / "feedback.txt"
    if feedback_path.exists():
        try:
            with open(feedback_path, encoding="utf-8") as f:
                feedback = f.read(1000)
            if feedback.strip():
                parts.append("## 复盘反馈（近期失败案例，务必规避）")
                parts.append(feedback)
                parts.append("")
        except Exception:
            pass

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
   - 风险：核心风险是什么？什么条件下必须止损？
4. 市值 50-500亿优先，说明为什么选这只而不是同板块大票
5. 给出：代码、名称、买入理由、买入区间、止损位、目标价、持仓周期
6. 不追涨停，不追涨幅>5%的，找蓄势待发的
7. 不要重复推荐观察池已有的标的
8. 6只票至少覆盖2个以上不同板块，避免集中风险
9. 不得推荐ST、*ST、退市风险警示、退市整理期、名称含'退'的标的
10. 【关键】股票代码必须与上方「候选标的」列表中的代码完全一致。如需补充列表外标的，代码必须准确无误——深南电路=002916、通富微电=002156、长电科技=600584，切勿混淆。价格字段必须使用上方提供的实时价格。
11. 每只票给出风险回报比（目标收益/止损空间），以及建议仓位占总资金比例（单票不超过20%）

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
      "chain_position": "电池化学品（上游材料）",
      "risk": "产能过剩导致价格战",
      "timeframe": "波段(3-4周)"
    }
  ]
}
```
score 评分标准：80-100强催化剂+低估值+蓄势充分，60-79明确催化剂+合理估值，40-59有潜力但不确定，0-39风险大于收益""")

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
        # 预处理：全角冒号→半角（LLM 输出常见问题）
        _normalized = result.replace("\uff1a", ":").replace("\uff0c", ",").replace("\u201c", '"').replace("\u201d", '"')
        # 尝试从 markdown code block 中提取
        if "```json" in _normalized:
            json_str = _normalized.split("```json")[1].split("```")[0].strip()
        elif "```" in _normalized:
            json_str = _normalized.split("```")[1].split("```")[0].strip()
        else:
            json_str = _normalized.strip()
        analysis = json.loads(json_str)
    except json.JSONDecodeError:
        # H1: JSON 解析失败时，尝试用 json_repair 或正则修复
        analysis = _try_repair_json(_normalized)
        if analysis is None:
            # 如果所有修复都失败，保存原始文本
            analysis = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "raw_text": result,
                "picks": [],
            }

    # 添加元数据
    analysis["generated_at"] = datetime.now().isoformat()
    analysis["model"] = MODEL

    # C2: 校验 picks 中的代码与名称一致性，跳过幻觉代码
    raw_picks = analysis.get("picks", [])
    if raw_picks:
        analysis["picks"] = validate_picks(raw_picks)

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
