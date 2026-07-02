#!/usr/bin/env python3
"""
watcher.py — 观察池监控脚本

功能：
1. 读取 watch_pool.json，获取观察池股票列表
2. 通过腾讯财经 API 获取当前实时价格
3. 检查催化剂进展（对比 expected_date 与当前日期）
4. 更新 price_history，记录当日价格
5. 生成 watch_pool_report.json 供网站展示
6. 更新 catalyst_calendar.json

用法：
    python scripts/watcher.py
    python scripts/watcher.py --dry-run    # 仅输出报告，不写回文件
    python scripts/watcher.py --verbose    # 详细日志
"""

import json
import os
import re
import sys
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests 未安装，请执行: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA_DIR = BASE_DIR / "docs" / "data"
WATCH_POOL_PATH = DOCS_DATA_DIR / "watch_pool.json"
CATALYST_CALENDAR_PATH = DOCS_DATA_DIR / "catalyst_calendar.json"
REPORT_OUTPUT_PATH = DOCS_DATA_DIR / "watch_pool_report.json"

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("watcher")


# ---------------------------------------------------------------------------
# 腾讯财经 API
# ---------------------------------------------------------------------------
TENCENT_API = "http://qt.gtimg.cn/q"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]


def stock_code_to_symbol(code: str) -> str:
    """将6位纯数字代码转为 sh/sz/bj 前缀格式（腾讯/新浪通用）"""
    code = code.strip().split(".")[0] if "." in code else code.strip()
    if code.startswith(("6", "5", "90")):
        return f"sh{code}"
    return f"sz{code}"


def fetch_tencent_price(stock_code: str) -> Optional[Dict[str, Any]]:
    """
    从腾讯财经 API 获取单只股票的实时行情。

    返回 dict:
        name: 股票名称
        price: 最新价
        change_pct: 涨跌幅 (%)
        change_amount: 涨跌额
        pre_close: 昨收
        open_price: 今开
        high: 最高
        low: 最低
        volume: 成交量（手）
        amount: 成交额（万元）
        timestamp: 行情时间
    """
    symbol = stock_code_to_symbol(stock_code)
    url = f"{TENCENT_API}={symbol}"
    headers = {
        "Referer": "http://finance.qq.com",
        "User-Agent": USER_AGENTS[0],
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
    except requests.RequestException as e:
        logger.warning(f"[腾讯API] {stock_code} 网络异常: {e}")
        return None

    content = resp.text.strip()
    if '=""' in content or not content:
        logger.warning(f"[腾讯API] {stock_code} 返回空数据")
        return None

    # 提取引号内的数据
    data_start = content.find('"')
    data_end = content.rfind('"')
    if data_start == -1 or data_end == -1:
        logger.warning(f"[腾讯API] {stock_code} 数据格式异常")
        return None

    data_str = content[data_start + 1 : data_end]
    fields = data_str.split("~")

    if len(fields) < 45:
        logger.warning(f"[腾讯API] {stock_code} 字段数不足: {len(fields)}")
        return None

    def safe_float(val: str) -> Optional[float]:
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None

    result = {
        "name": fields[1],
        "price": safe_float(fields[3]),
        "pre_close": safe_float(fields[4]),
        "open_price": safe_float(fields[5]),
        "change_amount": safe_float(fields[31]) if len(fields) > 31 else None,
        "change_pct": safe_float(fields[32]) if len(fields) > 32 else None,
        "high": safe_float(fields[33]) if len(fields) > 33 else None,
        "low": safe_float(fields[34]) if len(fields) > 34 else None,
        "volume": safe_float(fields[36]) if len(fields) > 36 else None,
        "amount": safe_float(fields[37]) if len(fields) > 37 else None,
        "timestamp": fields[30] if len(fields) > 30 else "",
    }

    if result["price"] is None or result["price"] <= 0:
        logger.warning(f"[腾讯API] {stock_code} 价格无效: {result['price']}")
        return None

    logger.info(
        f"[腾讯API] {stock_code} {result['name']}: "
        f"价格={result['price']}, 涨跌={result['change_pct']}%"
    )
    return result


# ---------------------------------------------------------------------------
# 催化剂日期检查
# ---------------------------------------------------------------------------
def parse_catalyst_date(expected_date: str) -> Optional[date]:
    """
    解析催化剂预期日期，支持以下格式：
    - "2026-09"    → 取当月最后一天
    - "2026-H1"    → 取 2026-06-30
    - "2026-H2"    → 取 2026-12-31
    - "2026-Q1"    → 取 2026-03-31
    - "2026-Q2"    → 取 2026-06-30
    - "2026-Q3"    → 取 2026-09-30
    - "2026-Q4"    → 取 2026-12-31
    - "2026-09-15" → 直接解析
    """
    expected_date = expected_date.strip()

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", expected_date)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # YYYY-MM (取当月最后一天)
    m = re.match(r"^(\d{4})-(\d{2})$", expected_date)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if mo == 12:
            return date(y + 1, 1, 1)
        return date(y, mo + 1, 1)

    # YYYY-H1 / YYYY-H2
    m = re.match(r"^(\d{4})-H([12])$", expected_date)
    if m:
        y = int(m.group(1))
        half = int(m.group(2))
        return date(y, 6, 30) if half == 1 else date(y, 12, 31)

    # YYYY-Q1~Q4
    m = re.match(r"^(\d{4})-Q([1-4])$", expected_date)
    if m:
        y = int(m.group(1))
        q = int(m.group(2))
        quarter_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        mo, day = quarter_ends[q]
        return date(y, mo, day)

    # YYYY (取年底)
    m = re.match(r"^(\d{4})$", expected_date)
    if m:
        return date(int(m.group(1)), 12, 31)

    logger.warning(f"无法解析催化剂日期: {expected_date}")
    return None


def check_catalyst_status(expected_date: str, today: date) -> str:
    """
    根据预期日期和当前日期判断催化剂状态：
    - "due_soon"  : 距离到期 <= 60 天
    - "upcoming"  : 距离到期 > 60 天
    - "overdue"   : 已过期
    """
    deadline = parse_catalyst_date(expected_date)
    if deadline is None:
        return "unknown"

    delta = (deadline - today).days
    if delta < 0:
        return "overdue"
    if delta <= 60:
        return "due_soon"
    return "upcoming"


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def generate_report(
    pool_data: Dict[str, Any],
    price_cache: Dict[str, Dict[str, Any]],
    today_str: str,
) -> Dict[str, Any]:
    """生成 watch_pool_report.json 内容"""
    stocks = pool_data.get("stocks", [])
    report_stocks = []
    status_counts: Dict[str, int] = {"watching": 0, "buying": 0, "holding": 0, "exited": 0}
    total_pnl_pct = 0.0
    pnl_count = 0

    for stock in stocks:
        code = stock["code"]
        status = stock.get("status", "watching")
        status_counts[status] = status_counts.get(status, 0) + 1

        added_price = stock.get("added_price", 0)
        current_price = 0.0
        change_pct_today = 0.0
        data_source = "unknown"

        quote = price_cache.get(code)
        if quote and quote.get("price"):
            current_price = quote["price"]
            change_pct_today = quote.get("change_pct", 0) or 0
            data_source = "tencent"

        # 计算相对买入价的盈亏
        pnl_pct = 0.0
        if added_price > 0 and current_price > 0:
            pnl_pct = (current_price - added_price) / added_price * 100
            total_pnl_pct += pnl_pct
            pnl_count += 1

        # 催化剂信息
        catalysts = stock.get("catalysts", [])
        catalyst_alerts = []
        today_date = date.fromisoformat(today_str)
        for cat in catalysts:
            if cat.get("status") == "confirmed" or cat.get("status") == "failed":
                continue
            auto_status = check_catalyst_status(cat["expected_date"], today_date)
            catalyst_alerts.append({
                "event": cat["event"],
                "expected_date": cat["expected_date"],
                "auto_status": auto_status,
                "user_status": cat.get("status", "pending"),
            })

        # 最新价格历史
        price_history = stock.get("price_history", [])
        latest_history = price_history[-1] if price_history else None

        report_stocks.append({
            "code": code,
            "name": stock.get("name", ""),
            "status": status,
            "thesis": stock.get("thesis", ""),
            "supply_chain": stock.get("supply_chain", ""),
            "timeframe": stock.get("timeframe", ""),
            "added_date": stock.get("added_date", ""),
            "added_price": added_price,
            "current_price": current_price,
            "change_pct_today": change_pct_today,
            "pnl_pct": round(pnl_pct, 2),
            "data_source": data_source,
            "catalyst_alerts": catalyst_alerts,
            "risk_factors": stock.get("risk_factors", []),
            "exit_conditions": stock.get("exit_conditions", []),
            "latest_price_note": latest_history.get("note", "") if latest_history else "",
        })

    avg_pnl = round(total_pnl_pct / pnl_count, 2) if pnl_count > 0 else 0.0
    pnl_sign = "+" if avg_pnl >= 0 else ""

    report = {
        "date": today_str,
        "summary": {
            "total": len(stocks),
            "watching": status_counts.get("watching", 0),
            "buying": status_counts.get("buying", 0),
            "holding": status_counts.get("holding", 0),
            "exited": status_counts.get("exited", 0),
            "total_pnl": f"{pnl_sign}{avg_pnl}%",
            "avg_pnl_pct": avg_pnl,
        },
        "stocks": report_stocks,
    }
    return report


# ---------------------------------------------------------------------------
# 更新 watch_pool.json 的 price_history
# ---------------------------------------------------------------------------
def update_price_history(
    pool_data: Dict[str, Any],
    price_cache: Dict[str, Dict[str, Any]],
    today_str: str,
) -> bool:
    """将今日价格追加到每只股票的 price_history（跳过已有今日记录的情况）"""
    updated = False
    for stock in pool_data.get("stocks", []):
        code = stock["code"]
        history = stock.get("price_history", [])

        # 避免重复追加
        if history and history[-1].get("date") == today_str:
            continue

        quote = price_cache.get(code)
        if quote and quote.get("price"):
            history.append({
                "date": today_str,
                "price": quote["price"],
                "note": "",
            })
            stock["price_history"] = history
            updated = True

    return updated


# ---------------------------------------------------------------------------
# 更新催化剂日历
# ---------------------------------------------------------------------------
def update_catalyst_calendar(
    pool_data: Dict[str, Any],
    calendar_path: Path,
    today_str: str,
) -> Dict[str, Any]:
    """根据 watch_pool 的催化剂信息重新生成 catalyst_calendar.json"""
    today_date = date.fromisoformat(today_str)
    upcoming = []

    for stock in pool_data.get("stocks", []):
        for cat in stock.get("catalysts", []):
            auto_status = check_catalyst_status(cat["expected_date"], today_date)
            importance = "high"
            if cat["expected_date"].endswith("-H2") or cat["expected_date"].endswith("-H1"):
                importance = "medium"

            upcoming.append({
                "date": cat["expected_date"],
                "stock_code": stock["code"],
                "stock_name": stock.get("name", ""),
                "event": cat["event"],
                "importance": importance,
                "status": cat.get("status", "pending"),
                "auto_status": auto_status,
            })

    # 按日期排序（先到期的排前面）
    upcoming.sort(key=lambda x: x["date"])

    calendar_data = {
        "last_updated": today_str,
        "upcoming": upcoming,
    }
    return calendar_data


# ---------------------------------------------------------------------------
# IO 工具
# ---------------------------------------------------------------------------
def load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"文件不存在: {path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {path}: {e}")
        return {}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    logger.info(f"已写入: {path}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="观察池监控 — 更新价格 & 检查催化剂")
    parser.add_argument("--dry-run", action="store_true", help="仅输出报告，不写回文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    today_str = date.today().isoformat()
    logger.info(f"===== 观察池监控 {today_str} =====")

    # 1. 读取 watch_pool.json
    pool_data = load_json(WATCH_POOL_PATH)
    if not pool_data or not pool_data.get("stocks"):
        logger.warning("观察池为空或文件不存在，跳过")
        return

    stocks = pool_data["stocks"]
    logger.info(f"观察池共 {len(stocks)} 只股票")

    # 2. 获取实时价格
    price_cache: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        code = stock["code"]
        logger.info(f"获取 {stock.get('name', '')} ({code}) 实时价格...")
        quote = fetch_tencent_price(code)
        if quote:
            price_cache[code] = quote
        else:
            logger.warning(f"{code} 价格获取失败，使用历史价格")

    # 3. 检查催化剂
    today_date = date.fromisoformat(today_str)
    logger.info("--- 催化剂检查 ---")
    for stock in stocks:
        for cat in stock.get("catalysts", []):
            auto_status = check_catalyst_status(cat["expected_date"], today_date)
            deadline = parse_catalyst_date(cat["expected_date"])
            days_left = (deadline - today_date).days if deadline else None
            status_emoji = {
                "overdue": "🔴",
                "due_soon": "🟡",
                "upcoming": "🟢",
                "unknown": "⚪",
            }.get(auto_status, "⚪")
            days_str = f"{days_left}天" if days_left is not None else "未知"
            logger.info(
                f"  {status_emoji} {stock['name']} | {cat['event']} | "
                f"预期: {cat['expected_date']} | 状态: {auto_status} | 剩余: {days_str}"
            )

    # 4. 更新 price_history
    pool_updated = update_price_history(pool_data, price_cache, today_str)
    pool_data["last_updated"] = datetime.now().isoformat(timespec="seconds")

    # 5. 生成报告
    report = generate_report(pool_data, price_cache, today_str)

    # 6. 更新催化剂日历
    calendar_data = update_catalyst_calendar(pool_data, CATALYST_CALENDAR_PATH, today_str)

    # --- 输出 ---
    print("\n" + "=" * 60)
    print(f"📋 观察池报告 {today_str}")
    print("=" * 60)
    print(f"总计: {report['summary']['total']} 只")
    print(f"状态: 观察 {report['summary']['watching']} | "
          f"买入 {report['summary']['buying']} | "
          f"持有 {report['summary']['holding']} | "
          f"退出 {report['summary']['exited']}")
    print(f"平均盈亏: {report['summary']['total_pnl']}")
    print("-" * 60)

    for s in report["stocks"]:
        pnl_emoji = "📈" if s["pnl_pct"] >= 0 else "📉"
        print(f"{pnl_emoji} {s['name']} ({s['code']})")
        print(f"   买入价: {s['added_price']} → 现价: {s['current_price']}")
        print(f"   今日涨跌: {s['change_pct_today']:+.2f}% | 盈亏: {s['pnl_pct']:+.2f}%")
        if s["catalyst_alerts"]:
            for ca in s["catalyst_alerts"]:
                icon = {"overdue": "🔴", "due_soon": "🟡", "upcoming": "🟢"}.get(ca["auto_status"], "⚪")
                print(f"   {icon} 催化剂: {ca['event']} ({ca['expected_date']}) [{ca['auto_status']}]")
        print()

    # --- 写文件 ---
    if args.dry_run:
        print("\n[DRY RUN] 不写入文件")
        print(f"\n--- report ---\n{json.dumps(report, ensure_ascii=False, indent=2)}")
    else:
        save_json(REPORT_OUTPUT_PATH, report)
        if pool_updated:
            save_json(WATCH_POOL_PATH, pool_data)
        save_json(CATALYST_CALENDAR_PATH, calendar_data)
        logger.info("所有文件已更新完成")

    logger.info("===== 监控完成 =====")


if __name__ == "__main__":
    main()
