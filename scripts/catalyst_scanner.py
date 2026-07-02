#!/usr/bin/env python3
"""
前瞻性催化剂扫描器 — 发现未来 1-4 周的市场风向。

核心理念：不看"今天什么热"，看"未来什么会热"。

数据源：
1. efinance — 板块资金流向 + 概念板块数据（替代被封的 curl）
2. 东方财富/财联社 — 新闻标题（curl 可用）
3. 前瞻性事件日历 — 未来已知的政策/会议/事件

产业链传导：当一个环节火了，找下一个还没启动的环节。

输出：docs/data/catalysts.json
"""
import sys
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA = REPO_DIR / "docs" / "data"

# ─── 产业链映射 ─────────────────────────────────────────────────
INDUSTRY_CHAINS = {
    "AI算力": {
        "keywords": ["光模块", "光芯片", "算力", "AI芯片", "数据中心", "液冷", "存储", "CPO", "硅光"],
        "chain": ["AI芯片", "光模块", "光芯片", "数据中心", "算力服务器", "液冷散热", "存储芯片"],
        "logic": "AI大模型训练需求爆发 → 算力基建先行 → 光互联 → 散热 → 存储",
    },
    "半导体国产替代": {
        "keywords": ["半导体", "芯片", "EDA", "光刻", "封装", "硅片", "设备", "材料"],
        "chain": ["半导体设备", "半导体材料", "EDA", "光刻胶", "先进封装", "硅片"],
        "logic": "大基金三期 → 设备国产化 → 材料配套 → 封测升级",
    },
    "人形机器人": {
        "keywords": ["机器人", "减速器", "伺服", "丝杠", "传感器", "灵巧"],
        "chain": ["减速器", "伺服电机", "传感器", "灵巧手", "丝杠", "轴承"],
        "logic": "Tesla Optimus + 宇树科技量产 → 核心零部件需求爆发",
    },
    "新能源车": {
        "keywords": ["电池", "锂电", "固态电池", "隔膜", "电解液", "铜箔"],
        "chain": ["动力电池", "固态电池", "电池化学品", "隔膜", "电解液", "铜箔"],
        "logic": "渗透率50%+ → 固态电池突破 → 电池材料升级",
    },
    "储能": {
        "keywords": ["储能", "PCS", "逆变器", "虚拟电厂"],
        "chain": ["储能系统", "PCS逆变器", "储能电池", "工商业储能", "虚拟电厂"],
        "logic": "电力市场化改革 → 工商业储能经济性改善 → 装机爆发",
    },
    "光伏风电": {
        "keywords": ["光伏", "风电", "硅料", "组件", "逆变器", "叶片", "海缆"],
        "chain": ["硅料", "电池片", "组件", "逆变器", "风电整机", "海缆", "铸件"],
        "logic": "产能出清 → 价格企稳 → 十五五新能源规划 → 装机旺季",
    },
    "军工航天": {
        "keywords": ["军工", "航天", "卫星", "航空", "雷达", "导弹"],
        "chain": ["航空发动机", "导弹", "卫星", "雷达", "军工电子"],
        "logic": "军费预算增长 → 装备采购放量 → 供应链弹性",
    },
    "智能汽车": {
        "keywords": ["智能驾驶", "无人驾驶", "激光雷达", "域控", "车载"],
        "chain": ["智能驾驶", "激光雷达", "域控制器", "车载芯片", "汽车电子"],
        "logic": "L3级自动驾驶政策落地 → 智驾渗透率提升 → 供应链放量",
    },
    "创新药": {
        "keywords": ["创新药", "CXO", "CDMO", "医药", "减肥药"],
        "chain": ["创新药", "CXO", "CDMO", "原料药"],
        "logic": "医保谈判常态化 → 创新药出海 → CXO订单回暖",
    },
    "低空经济": {
        "keywords": ["低空", "eVTOL", "无人机"],
        "chain": ["eVTOL整机", "飞控系统", "动力电池", "碳纤维", "通信导航"],
        "logic": "政策推动低空开放 → eVTOL适航认证 → 供应链受益",
    },
}


def curl_get(url, timeout=10, referer=None):
    cmd = ["curl", "-s", "--max-time", str(timeout)]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def log(msg, verbose=False):
    if verbose:
        print(f"  {msg}", file=sys.stderr)


# ─── 数据源 1: efinance 板块数据 ────────────────────────────────
def get_sector_data_efinance(verbose=False):
    """用 efinance 获取行业板块 + 概念板块资金流向。"""
    try:
        import efinance as ef
    except ImportError:
        log("⚠️ efinance 未安装，跳过板块数据", verbose)
        return [], []

    industries = []
    concepts = []

    try:
        # 行业板块资金流向
        log("efinance: 获取行业板块...", verbose)
        df_ind = ef.stock.get_realtime_quotes([])
        # efinance 板块数据需要通过 board 模块
    except Exception as e:
        log(f"⚠️ efinance 行业板块失败: {e}", verbose)

    # efinance 的板块接口
    try:
        from efinance.stock import get_belong_board
        log("efinance: 获取概念板块数据...", verbose)
    except ImportError:
        pass

    # 最可靠的方式：用 efinance 的东财接口
    try:
        import efinance as ef
        # 获取 A 股实时行情（包含市值）
        log("efinance: 获取全市场实时行情...", verbose)
        df = ef.stock.get_realtime_quotes()
        if df is not None and not df.empty:
            log(f"  获取 {len(df)} 只股票行情", verbose)
            return [], df  # 返回原始 DataFrame
    except Exception as e:
        log(f"⚠️ efinance 实时行情失败: {e}", verbose)

    return [], []


def get_sector_flow_efinance(verbose=False):
    """用 efinance 获取板块资金流向。"""
    try:
        import efinance as ef
        log("efinance: 获取板块资金流向...", verbose)
        # 东方财富板块资金流向
        df = ef.stock.get_belong_board("000001")
        log(f"  board data columns: {list(df.columns) if df is not None else 'None'}", verbose)
    except Exception:
        pass

    # 回退：用 curl 试试带 Referer 的请求
    log("curl: 尝试板块资金流向...", verbose)
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=30&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:90+t:2+f:!50"
        "&fields=f12,f14,f3,f62,f184,f104,f105"
    )
    text = curl_get(url, timeout=8, referer="https://quote.eastmoney.com/")
    if not text:
        log("⚠️ 板块资金流向 API 无响应", verbose)
        return []

    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
        sectors = []
        for item in diffs:
            name = item.get("f14", "")
            if not name:
                continue
            sectors.append({
                "code": item.get("f12", ""),
                "name": name,
                "change_pct": round(item.get("f3", 0) or 0, 2),
                "net_inflow_yi": round((item.get("f62", 0) or 0) / 1e8, 2),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
            })
        log(f"  获取 {len(sectors)} 个板块", verbose)
        return sectors
    except (json.JSONDecodeError, KeyError):
        return []


# ─── 数据源 2: efinance 个股数据 ────────────────────────────────
def get_all_stocks_efinance(verbose=False):
    """用 efinance 获取全市场 A 股实时行情（含市值）。"""
    try:
        import efinance as ef
        log("efinance: 获取全市场 A 股行情...", verbose)
        df = ef.stock.get_realtime_quotes()
        if df is None or df.empty:
            log("⚠️ efinance 返回空数据", verbose)
            return []

        stocks = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", ""))
            name = str(row.get("股票名称", ""))
            if not code or not name:
                continue

            # 市值
            cap = row.get("总市值", 0)
            try:
                cap_yi = round(float(cap) / 1e8, 0) if cap and float(cap) > 0 else 0
            except (ValueError, TypeError):
                cap_yi = 0

            # 涨跌幅
            try:
                change = round(float(row.get("涨跌幅", 0) or 0), 2)
            except (ValueError, TypeError):
                change = 0

            # 成交额
            try:
                amount = float(row.get("成交额", 0) or 0)
                amount_yi = round(amount / 1e8, 2)
            except (ValueError, TypeError):
                amount_yi = 0

            stocks.append({
                "code": code,
                "name": name,
                "change_pct": change,
                "market_cap_yi": cap_yi,
                "amount_yi": amount_yi,
            })

        log(f"  获取 {len(stocks)} 只 A 股", verbose)
        return stocks
    except ImportError:
        log("⚠️ efinance 未安装", verbose)
        return []
    except Exception as e:
        log(f"⚠️ efinance 失败: {e}", verbose)
        return []


def get_fund_flow_efinance(verbose=False):
    """用 efinance 获取个股资金流向 Top 30。"""
    try:
        import efinance as ef
        log("efinance: 获取个股资金流向...", verbose)
        # 东方财富个股资金流向
        df = ef.stock.get_latest_entrust()
        if df is not None and not df.empty:
            log(f"  资金流向: {len(df)} 条", verbose)
            return df
    except Exception:
        pass

    # 回退到 curl
    log("curl: 尝试个股资金流向...", verbose)
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=30&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f12,f14,f3,f8,f62,f20"
    )
    text = curl_get(url, timeout=8, referer="https://quote.eastmoney.com/")
    if not text:
        return []

    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
        stocks = []
        for item in diffs:
            code = item.get("f12", "")
            name = item.get("f14", "")
            if not code or not name:
                continue
            market_cap = item.get("f20", 0) or 0
            stocks.append({
                "code": code,
                "name": name,
                "change_pct": round(item.get("f3", 0) or 0, 2),
                "turnover": round(item.get("f8", 0) or 0, 2),
                "net_inflow_yi": round((item.get("f62", 0) or 0) / 1e8, 2),
                "market_cap_yi": round(market_cap / 1e8, 0) if market_cap else 0,
            })
        log(f"  获取 {len(stocks)} 只资金流向标的", verbose)
        return stocks
    except (json.JSONDecodeError, KeyError):
        return []


# ─── 数据源 3: 新闻 ────────────────────────────────────────────
def scan_headlines(verbose=False):
    """抓取东方财富 + 财联社新闻标题。"""
    log("扫描新闻...", verbose)
    headlines = []

    html = curl_get("https://finance.eastmoney.com/", timeout=8,
                     referer="https://finance.eastmoney.com/")
    if html:
        titles = re.findall(r'<a[^>]*title="([^"]{8,})"[^>]*>', html)
        seen = set()
        for t in titles:
            t = t.strip()
            if t not in seen and len(t) > 8:
                seen.add(t)
                headlines.append({"title": t, "source": "东方财富"})

    cls_html = curl_get(
        "https://www.cls.cn/depth?id=1000", timeout=8,
        referer="https://www.cls.cn/",
    )
    if cls_html:
        titles = re.findall(r'"title"\s*:\s*"([^"]{8,})"', cls_html)
        if not titles:
            titles = re.findall(r'<span[^>]*>([^<]{10,50})</span>', cls_html)
        seen = set()
        for t in titles:
            t = t.strip()
            if t not in seen and len(t) > 8:
                seen.add(t)
                headlines.append({"title": t, "source": "财联社"})

    log(f"  获取 {len(headlines)} 条新闻", verbose)
    return headlines


# ─── 蓄势信号检测 ───────────────────────────────────────────────
def detect_accumulation(stocks, sectors, verbose=False):
    """
    检测蓄势信号：资金在悄悄流入但价格还没动。

    个股层面：
    - 涨幅 < 2% 但成交额/市值比高 → 活跃但没涨 = 吸筹
    - 涨幅在 0-3% 之间，市值 50-500亿 → 蓄势区间

    板块层面：
    - 板块涨幅小但净流入大 → 机构在建仓
    """
    signals = []

    # 板块蓄势
    for s in sectors:
        reasons = []
        score = 0
        if 0 < s["change_pct"] < 2 and s["net_inflow_yi"] > 3:
            reasons.append(f"蓄势：涨{s['change_pct']:+.1f}%但主力流入{s['net_inflow_yi']:.1f}亿")
            score += 30
        if s["change_pct"] < 0 and s["net_inflow_yi"] > 5:
            reasons.append(f"逆市吸筹：跌{s['change_pct']:.1f}%但主力{s['net_inflow_yi']:.1f}亿")
            score += 40
        up = s.get("up_count", 0)
        down = s.get("down_count", 0)
        if up > down * 2 and 0 < s["change_pct"] < 3:
            reasons.append(f"板块{up}涨/{down}跌，集体蓄势")
            score += 20
        if reasons:
            signals.append({**s, "score": score, "reasons": reasons, "level": "sector"})

    # 个股蓄势（从全市场数据中筛选）
    for st in stocks:
        if st["market_cap_yi"] < 50 or st["market_cap_yi"] > 500:
            continue
        if st["change_pct"] < -3 or st["change_pct"] > 3:
            continue
        # 成交额/市值 > 3% 但涨幅小 → 活跃蓄势
        activity = st["amount_yi"] / max(st["market_cap_yi"], 1) * 100
        if activity > 3 and 0 < st["change_pct"] < 2:
            signals.append({
                "code": st["code"],
                "name": st["name"],
                "change_pct": st["change_pct"],
                "market_cap_yi": st["market_cap_yi"],
                "score": 20 + min(activity, 20),
                "reasons": [f"活跃蓄势：成交/市值{activity:.1f}%，涨{st['change_pct']:+.1f}%"],
                "level": "stock",
            })

    signals.sort(key=lambda x: x["score"], reverse=True)
    log(f"  检测到 {len(signals)} 个蓄势信号", verbose)
    return signals[:20]


# ─── 产业链传导 ─────────────────────────────────────────────────
def detect_chain_propagation(stocks, verbose=False):
    """
    产业链传导：从全市场数据中找产业链关键词匹配的标的，
    按产业链逻辑排列，找还没动的环节。
    """
    results = []
    for theme, info in INDUSTRY_CHAINS.items():
        matched = []
        for st in stocks:
            for kw in info["keywords"]:
                if kw in st["name"]:
                    matched.append(st)
                    break
        if matched:
            # 按涨跌幅排序：涨最多的 = 已启动，没涨的 = 待补涨
            matched.sort(key=lambda x: x["change_pct"], reverse=True)
            started = [s for s in matched if s["change_pct"] > 2]
            not_started = [s for s in matched if s["change_pct"] <= 2 and s["market_cap_yi"] >= 50]
            if started and not_started:
                results.append({
                    "theme": theme,
                    "logic": info["logic"],
                    "started": [{"code": s["code"], "name": s["name"], "change_pct": s["change_pct"]}
                                for s in started[:3]],
                    "next_opportunities": [{"code": s["code"], "name": s["name"],
                                            "market_cap_yi": s["market_cap_yi"], "change_pct": s["change_pct"]}
                                           for s in not_started[:5]],
                })
    results.sort(key=lambda x: len(x["started"]), reverse=True)
    log(f"  检测到 {len(results)} 个产业链传导机会", verbose)
    return results


# ─── 前瞻事件 ──────────────────────────────────────────────────
def get_forward_events():
    today = datetime.now()
    month = today.month
    year = today.year
    events = []
    if month in [3, 4]:
        events.append({"title": f"{year}年两会政策窗口", "affected": ["新能源", "半导体", "AI", "军工"]})
    if month in [4, 7, 10, 1]:
        q = (month - 1) // 3 + 1
        events.append({"title": f"Q{q}财报季", "affected": ["全行业"]})
    if month in [6, 12]:
        events.append({"title": "年中/年末经济工作会议", "affected": ["全行业"]})
    events.append({"title": "大基金三期投资节奏", "affected": ["半导体设备", "半导体材料", "先进封装"]})
    events.append({"title": "新能源装机旺季(Q3-Q4)", "affected": ["光伏", "风电", "储能"]})
    events.append({"title": "全球AI大模型迭代周期", "affected": ["AI芯片", "光模块", "算力"]})
    return events


# ─── 主流程 ────────────────────────────────────────────────────
def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print("🔍 前瞻性催化剂扫描器启动", file=sys.stderr)

    # 1. 获取数据
    sectors = get_sector_flow_efinance(verbose)
    all_stocks = get_all_stocks_efinance(verbose)
    fund_flow = get_fund_flow_efinance(verbose)
    headlines = scan_headlines(verbose)

    # 2. 检测蓄势信号
    accumulation = detect_accumulation(all_stocks, sectors, verbose)

    # 3. 产业链传导
    chain_props = detect_chain_propagation(all_stocks, verbose)

    # 4. 前瞻事件
    forward_events = get_forward_events()

    # 5. 新闻催化剂
    news_catalysts = []
    for h in headlines:
        title = h["title"]
        for theme, info in INDUSTRY_CHAINS.items():
            for kw in info["keywords"]:
                if kw in title:
                    news_catalysts.append({
                        "title": title,
                        "source": h["source"],
                        "theme": theme,
                        "logic": info["logic"],
                    })
                    break
            else:
                continue
            break

    # 6. 输出
    today = datetime.now().strftime("%Y-%m-%d")
    output = {
        "date": today,
        "catalysts": [
            {"title": f"蓄势信号：{'；'.join(s['reasons'])}", "type": "accumulation",
             "theme": s.get("name", ""), "urgency": "high" if s["score"] >= 40 else "medium"}
            for s in accumulation if s["score"] >= 20
        ] + [
            {"title": f"产业链传导：{p['theme']} — {', '.join(s['name'] for s in p['started'])}已启动",
             "type": "chain_propagation", "theme": p["theme"],
             "next": [s["name"] for s in p["next_opportunities"][:3]], "urgency": "medium"}
            for p in chain_props
        ] + [
            {"title": n["title"], "type": "news", "theme": n["theme"], "urgency": "medium"}
            for n in news_catalysts[:10]
        ],
        "accumulation_signals": accumulation,
        "chain_propagations": chain_props,
        "forward_events": forward_events,
        "sectors": sectors[:15],
        "fund_flow_top10": fund_flow[:10] if isinstance(fund_flow, list) else [],
        "top_headlines": [h["title"] for h in headlines[:10]],
        "stats": {
            "sectors_scanned": len(sectors),
            "stocks_scanned": len(all_stocks),
            "accumulation_signals": len([s for s in accumulation if s["score"] >= 20]),
            "chain_propagations": len(chain_props),
            "news_catalysts": len(news_catalysts),
        },
    }

    if dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        DOCS_DATA.mkdir(parents=True, exist_ok=True)
        with open(DOCS_DATA / "catalysts.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✅ 催化剂数据写入完成", file=sys.stderr)
        print(f"   板块: {len(sectors)} | 股票: {len(all_stocks)} | 蓄势: {output['stats']['accumulation_signals']} | 传导: {output['stats']['chain_propagations']}", file=sys.stderr)


if __name__ == "__main__":
    main()
