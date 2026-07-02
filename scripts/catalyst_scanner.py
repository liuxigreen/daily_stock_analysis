#!/usr/bin/env python3
"""
每日催化剂扫描器 — 扫描新闻/政策/概念异动，映射到产业链受益标的。

数据源（全部免费，无需 API key）：
1. 东方财富首页 headlines（CDN 缓存，永不限流）
2. 东方财富概念板块 API（资金流向 + 涨幅异动）
3. 东方财富概念成分股 API
4. 财联社新闻（curl 抓取）

输出：docs/data/catalysts.json

用法：
  python3 catalyst_scanner.py                    # 正常运行
  python3 catalyst_scanner.py --dry-run          # 只输出不写文件
  python3 catalyst_scanner.py --verbose          # 详细日志
"""
import sys
import os
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA = REPO_DIR / "docs" / "data"

# ─── 产业链映射表 ───────────────────────────────────────────────
# 催化剂类型关键词 → 产业链路径
CONCEPT_CHAIN_MAP = {
    # AI / 半导体
    "光芯片": "AI算力 → 800G光模块 → 光芯片",
    "光模块": "AI算力 → 数据中心 → 养模块",
    "CPO概念": "AI算力 → 数据中心 → CPO共封装光学",
    "共封装光学": "AI算力 → 数据中心 → CPO共封装光学",
    "硅光概念": "AI算力 → 硅光方案",
    "AI芯片": "AI算力 → AI芯片",
    "人工智能": "AI算力 → 大模型 → AI应用",
    "算力": "AI算力 → GPU/ASIC → 算力基建",
    "数据中心": "AI算力 → 数据中心建设",
    "半导体": "芯片制造 → 半导体全产业链",
    "半导体设备": "芯片制造 → 半导体设备",
    "半导体材料": "芯片制造 → 半导体材料",
    "国产芯片": "国产替代 → 芯片自主可控",
    "存储芯片": "AI算力 → 存储需求 → 存储芯片",
    "先进封装": "芯片制造 → 先进封装",
    "光刻机": "芯片制造 → 光刻设备",

    # 新能源
    "电池化学品": "新能源车 → 动力电池 → 电池化学品",
    "固态电池": "新能源车 → 固态电池",
    "锂电池": "新能源车 → 动力电池 → 锂电池",
    "储能": "新能源 → 储能系统",
    "光伏": "新能源 → 光伏发电",
    "风电": "新能源 → 风电",
    "新能源汽车": "政策推动 → 新能源车 → 整车+零部件",

    # 消费 / 医药
    "创新药": "医药 → 创新药",
    "CXO": "医药 → CXO研发外包",
    "医疗器械": "医药 → 医疗器械",
    "减肥药": "医药 → GLP-1减肥药产业链",

    # 军工 / 航天
    "军工": "国防 → 军工全产业链",
    "航天航空": "国防 → 航天航空",
    "低空经济": "政策推动 → 无人机/eVTOL → 飞控系统",
    "商业航天": "政策推动 → 商业航天",

    # 消费电子 / 汽车
    "消费电子": "消费 → 消费电子",
    "汽车零部件": "智能汽车 → 汽车零部件",
    "无人驾驶": "智能汽车 → 自动驾驶",
    "人形机器人": "AI + 制造 → 人形机器人",
    "机器人": "AI + 制造 → 机器人产业链",

    # 材料 / 化工
    "新材料": "制造业 → 新材料",
    "碳纤维": "制造业 → 碳纤维复合材料",
    "玻璃基板": "面板/光伏 → 玻璃基板",

    # 金融 / 地产
    "券商": "资本市场 → 券商",
    "房地产": "政策 → 房地产",

    # 农业
    "农业种植": "粮食安全 → 农业",
    "养殖": "农业 → 养殖产业链",
}

# 政策关键词 → 催化剂类型
POLICY_KEYWORDS = {
    "国务院": "policy",
    "政治局": "policy",
    "工信部": "policy",
    "发改委": "policy",
    "央行": "policy",
    "银保监": "policy",
    "证监会": "policy",
    "财政部": "policy",
    "科技部": "policy",
    "大基金": "policy",
    "十四五": "policy",
    "十五五": "policy",
    "补贴": "policy",
    "减税": "policy",
}

INDUSTRY_KEYWORDS = {
    "量产": "industry",
    "出货": "industry",
    "订单": "industry",
    "供货": "industry",
    "突破": "industry",
    "发布": "industry",
    "上市": "industry",
    "收购": "industry",
    "并购": "industry",
    "合作": "industry",
    "招标": "industry",
    "装机": "industry",
}


def curl_get(url, timeout=10, referer=None):
    """用 curl 获取 URL 内容，比 urllib 更稳定。"""
    cmd = ["curl", "-s", "--max-time", str(timeout), url]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def log(msg, verbose=False):
    if verbose:
        print(f"  {msg}", file=sys.stderr)


# ─── 数据源 1: 东方财富首页 headlines ───────────────────────────
def scan_eastmoney_homepage(verbose=False):
    """抓取东方财富首页新闻标题。"""
    log("扫描东方财富首页...", verbose)
    html = curl_get("https://finance.eastmoney.com/", timeout=8)
    if not html:
        log("⚠️ 东方财富首页抓取失败", verbose)
        return []

    # 提取所有文章标题
    titles = re.findall(r'<a[^>]*title="([^"]{8,})"[^>]*>', html)
    # 去重
    seen = set()
    headlines = []
    for t in titles:
        t = t.strip()
        if t not in seen and len(t) > 8:
            seen.add(t)
            headlines.append(t)

    log(f"  获取 {len(headlines)} 条标题", verbose)
    return headlines


# ─── 数据源 2: 东方财富概念板块 ──────────────────────────────────
def scan_concept_sectors(verbose=False):
    """扫描概念板块异动（资金流入+涨幅异常）。"""
    log("扫描概念板块...", verbose)

    # 概念板块列表，按资金净流入排序
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=30&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:90+t:3+f:!50"
        "&fields=f12,f14,f3,f62,f184,f104,f105"
    )
    text = curl_get(url, timeout=8)
    if not text:
        log("⚠️ 概念板块 API 无响应", verbose)
        return []

    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
    except (json.JSONDecodeError, KeyError):
        log("⚠️ 概念板块 JSON 解析失败", verbose)
        return []

    concepts = []
    for item in diffs:
        code = item.get("f12", "")
        name = item.get("f14", "")
        change = item.get("f3", 0)
        net_inflow = item.get("f62", 0)  # 主力净流入（元）
        net_inflow_yi = net_inflow / 1e8 if net_inflow else 0

        if not name:
            continue

        concepts.append({
            "code": code,
            "name": name,
            "change_pct": round(change, 2) if change else 0,
            "net_inflow_yi": round(net_inflow_yi, 2),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
        })

    log(f"  获取 {len(concepts)} 个概念板块", verbose)
    return concepts


# ─── 数据源 3: 概念成分股 ──────────────────────────────────────
def get_concept_constituents(concept_code, concept_name, verbose=False):
    """获取某个概念板块的成分股。"""
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
        f"&fid=f62&fs=b:{concept_code}+f:!2"
        f"&fields=f12,f14,f3,f8,f62"
    )
    text = curl_get(url, timeout=8)
    if not text:
        return []

    try:
        data = json.loads(text)
        diffs = data.get("data", {}).get("diff", [])
    except (json.JSONDecodeError, KeyError):
        return []

    stocks = []
    for item in diffs:
        code = item.get("f12", "")
        name = item.get("f14", "")
        change = item.get("f3", 0)
        turnover = item.get("f8", 0)
        net_inflow = item.get("f62", 0)
        net_inflow_yi = net_inflow / 1e8 if net_inflow else 0

        if name:
            stocks.append({
                "code": code,
                "name": name,
                "change_pct": round(change, 2) if change else 0,
                "turnover": round(turnover, 2) if turnover else 0,
                "net_inflow_yi": round(net_inflow_yi, 2),
            })

    return stocks


# ─── 数据源 4: 财联社新闻 ──────────────────────────────────────
def scan_cls_news(verbose=False):
    """抓取财联社最新财经新闻。"""
    log("扫描财联社...", verbose)
    html = curl_get(
        "https://www.cls.cn/depth?id=1000",
        timeout=8,
        referer="https://www.cls.cn/"
    )
    if not html:
        log("⚠️ 财联社抓取失败", verbose)
        return []

    # 提取新闻标题
    titles = re.findall(r'"title"\s*:\s*"([^"]{8,})"', html)
    if not titles:
        titles = re.findall(r'<span[^>]*>([^<]{10,50})</span>', html)

    seen = set()
    headlines = []
    for t in titles:
        t = t.strip()
        if t not in seen and len(t) > 8:
            seen.add(t)
            headlines.append(t)

    log(f"  获取 {len(headlines)} 条财联社标题", verbose)
    return headlines


# ─── 催化剂分析 ────────────────────────────────────────────────
def classify_headline(headline):
    """判断标题属于什么类型。"""
    for kw, typ in POLICY_KEYWORDS.items():
        if kw in headline:
            return typ
    for kw, typ in INDUSTRY_KEYWORDS.items():
        if kw in headline:
            return typ
    return "general"


def match_concepts_to_chain(concepts, verbose=False):
    """将概念板块映射到产业链。"""
    results = []
    for c in concepts:
        name = c["name"]
        chain = CONCEPT_CHAIN_MAP.get(name)
        if chain:
            # 获取该概念的前5大成分股
            stocks = get_concept_constituents(c["code"], name, verbose)
            c["chain"] = chain
            c["top_constituents"] = stocks[:5]
            results.append(c)
    log(f"  产业链映射: {len(results)} 个概念", verbose)
    return results


def detect_anomalies(concepts, verbose=False):
    """检测概念板块异动。"""
    anomalies = []

    for c in concepts:
        reasons = []

        # 涨幅异动：涨幅 > 3% 且有资金流入
        if c["change_pct"] > 3 and c["net_inflow_yi"] > 1:
            reasons.append(f"涨幅{c['change_pct']:+.1f}%+主力流入{c['net_inflow_yi']:.1f}亿")

        # 资金悄悄进场：涨幅小但资金大量流入
        if 0 < c["change_pct"] < 2 and c["net_inflow_yi"] > 5:
            reasons.append(f"蓄势信号：涨{c['change_pct']:+.1f}%但主力流入{c['net_inflow_yi']:.1f}亿")

        # 涨停潮：板块内多只涨停
        if c.get("up_count", 0) > 10 and c["change_pct"] > 4:
            reasons.append(f"板块内{c['up_count']}只上涨，集体爆发")

        if reasons:
            anomalies.append({**c, "reasons": reasons})

    log(f"  检测到 {len(anomalies)} 个异动概念", verbose)
    return anomalies


def build_catalysts(headlines, cls_headlines, anomalies, verbose=False):
    """从新闻和异动中构建催化剂列表。"""
    catalysts = []
    now = datetime.now().isoformat()

    # 从异动概念构建催化剂
    for a in anomalies:
        chain = CONCEPT_CHAIN_MAP.get(a["name"], f"概念板块: {a['name']}")
        beneficiaries = []
        for s in a.get("top_constituents", []):
            beneficiaries.append({
                "code": s["code"],
                "name": s["name"],
                "reason": f"{a['name']}概念成分股，今日{s['change_pct']:+.1f}%",
            })

        # 判断紧急程度
        if a["change_pct"] > 5:
            urgency = "high"
        elif a["change_pct"] > 3:
            urgency = "medium"
        else:
            urgency = "low"

        catalysts.append({
            "title": f"{a['name']}板块异动：{'; '.join(a['reasons'])}",
            "source": "东方财富概念板块",
            "type": "industry",
            "affected_sectors": [a["name"]],
            "chain": chain,
            "beneficiary_stocks": beneficiaries,
            "urgency": urgency,
            "detected_at": now,
        })

    # 从新闻标题构建催化剂
    all_headlines = [(h, "东方财富") for h in headlines] + [(h, "财联社") for h in cls_headlines]
    for title, source in all_headlines:
        cat_type = classify_headline(title)
        if cat_type == "general":
            continue  # 跳过无意义的通用新闻

        # 匹配产业链
        affected = []
        chain = ""
        for keyword, ch in CONCEPT_CHAIN_MAP.items():
            if keyword in title:
                affected.append(keyword)
                chain = ch
                break

        if not affected:
            continue

        urgency = "high" if cat_type == "policy" else "medium"
        catalysts.append({
            "title": title,
            "source": source,
            "type": cat_type,
            "affected_sectors": affected,
            "chain": chain,
            "beneficiary_stocks": [],  # 新闻级别不映射具体标的
            "urgency": urgency,
            "detected_at": now,
        })

    log(f"  生成 {len(catalysts)} 条催化剂", verbose)
    return catalysts


# ─── 主流程 ────────────────────────────────────────────────────
def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print("🔍 催化剂扫描器启动", file=sys.stderr)

    # 1. 扫描数据源
    headlines = scan_eastmoney_homepage(verbose)
    cls_headlines = scan_cls_news(verbose)
    concepts = scan_concept_sectors(verbose)

    # 2. 检测异动
    anomalies = detect_anomalies(concepts, verbose)

    # 3. 映射产业链
    chain_concepts = match_concepts_to_chain(concepts, verbose)

    # 4. 构建催化剂
    catalysts = build_catalysts(headlines, cls_headlines, anomalies, verbose)

    # 5. 组装输出
    today = datetime.now().strftime("%Y-%m-%d")
    output = {
        "date": today,
        "catalysts": catalysts,
        "hot_concepts": [
            {
                "code": c["code"],
                "name": c["name"],
                "change_pct": c["change_pct"],
                "net_inflow": c["net_inflow_yi"],
                "chain": c.get("chain", ""),
                "constituents": c.get("top_constituents", [])[:5],
            }
            for c in chain_concepts
            if abs(c["change_pct"]) > 1 or abs(c["net_inflow_yi"]) > 1
        ],
        "top_headlines": headlines[:10],
        "stats": {
            "total_catalysts": len(catalysts),
            "high_urgency": sum(1 for c in catalysts if c["urgency"] == "high"),
            "concepts_scanned": len(concepts),
            "anomalies_detected": len(anomalies),
        },
    }

    # 6. 输出
    if dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        DOCS_DATA.mkdir(parents=True, exist_ok=True)
        out_path = DOCS_DATA / "catalysts.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"✅ 催化剂数据已写入 {out_path}", file=sys.stderr)
        print(f"   催化剂: {len(catalysts)} 条 (高优: {output['stats']['high_urgency']})", file=sys.stderr)
        print(f"   异动概念: {len(anomalies)} 个", file=sys.stderr)
        print(f"   产业链映射: {len(chain_concepts)} 个", file=sys.stderr)


if __name__ == "__main__":
    main()
