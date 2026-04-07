# -*- coding: utf-8 -*-
"""
双平台信息采集工具 - 项目入口
GJDW（国家电网）+ NFDW（南方电网）

用法:
    python main.py --once          # 立即执行一次全部采集
    python main.py --once --gjdw   # 仅执行GJDW采集
    python main.py --once --nfdw   # 仅执行NFDW采集
    python main.py --schedule      # 启动定时调度模式
"""
import sys
import os

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.chdir(project_root)

from src.scheduler import TaskScheduler


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="双平台信息采集工具（GJDW + NFDW）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --once              立即执行一次全部采集
  python main.py --once --gjdw       仅执行GJDW采集
  python main.py --once --nfdw       仅执行NFDW采集
  python main.py --schedule          启动定时调度模式（每日08:30采集，09:00通知）
        """,
    )
    parser.add_argument("--once", action="store_true", help="立即执行一次采集（默认行为）")
    parser.add_argument("--schedule", action="store_true", help="启动定时调度模式")
    parser.add_argument("--gjdw", action="store_true", help="仅执行GJDW采集")
    parser.add_argument("--nfdw", action="store_true", help="仅执行NFDW采集")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口（调试用）")

    args = parser.parse_args()

    scheduler = TaskScheduler()

    if args.schedule:
        scheduler.run_scheduled()
    else:
        # 默认执行一次
        if args.gjdw:
            scheduler._run_gjdw_task()
        elif args.nfdw:
            scheduler._run_nfdw_task()
        else:
            scheduler.run_once()


if __name__ == "__main__":
    main()
