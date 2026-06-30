#!/usr/bin/env python3
"""
推送每日选股数据到 GitHub repo。
供 cron job 在每日选股分析完成后调用。

用法:
  python3 push_picks.py picks/2026-06-30.json

环境变量:
  GITHUB_PAT - GitHub Personal Access Token (有 repo 权限)
"""
import sys, os, json, subprocess, tempfile, shutil
from pathlib import Path

REPO_DIR = os.path.expanduser("~/workspace/daily_stock_analysis")
BRANCH = "main"
GIT_USER = "22 sf Bot"
GIT_EMAIL = "bot@liuxigreen.github.io"

def run(cmd, cwd=REPO_DIR):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"⚠️  {cmd[0]} exit {r.returncode}: {r.stderr[:200]}")
    return r

def push_picks(pick_file):
    pick_path = Path(pick_file).resolve()
    if not pick_path.exists():
        print(f"❌ 文件不存在: {pick_file}")
        sys.exit(1)

    # 读取选股数据
    with open(pick_path) as f:
        data = json.load(f)
    date = data.get("date", "unknown")

    # 复制到 repo 的 picks/ 目录
    target = Path(REPO_DIR) / "picks" / f"{date}.json"
    shutil.copy2(pick_path, target)
    print(f"✅ 复制到: {target}")

    # Git 提交
    os.chdir(REPO_DIR)
    run(["git", "config", "user.name", GIT_USER])
    run(["git", "config", "user.email", GIT_EMAIL])

    msg = f"chore: 每日选股数据 {date}"
    run(["git", "add", f"picks/{date}.json"])
    r = run(["git", "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        print("ℹ️  没有新变更，跳过提交")
        return

    run(["git", "commit", "-m", msg])
    run(["git", "push", "origin", BRANCH])
    print(f"✅ 已推送 picks/{date}.json 到 GitHub")
    print(f"🌐 网站: https://liuxigreen.github.io/daily_stock_analysis/")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 push_picks.py <选股JSON路径>")
        sys.exit(1)
    push_picks(sys.argv[1])