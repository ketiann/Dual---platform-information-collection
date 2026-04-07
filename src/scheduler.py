# -*- coding: utf-8 -*-
"""
定时任务调度器
支持：每日定时执行GJDW和NFDW采集任务，定时推送通知
"""
import sys
import os
import time
import signal
import threading
from datetime import datetime, timedelta

# 添加src目录和项目根目录到路径
_src_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_src_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from common.logger import setup_logger, cleanup_old_logs
from config.settings import SCHEDULE, GENERAL


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.logger = setup_logger("scheduler", GENERAL["log_level"])
        self._running = True
        self._gjdw_result = None
        self._nfdw_result = None
        self._gjdw_notified = False
        self._nfdw_notified = False

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """处理终止信号"""
        self.logger.info("接收到终止信号，正在停止调度器...")
        self._running = False

    def _should_run_crawl(self) -> bool:
        """判断是否到了采集执行时间"""
        now = datetime.now()
        target = now.replace(
            hour=SCHEDULE["crawl_hour"],
            minute=SCHEDULE["crawl_minute"],
            second=0,
            microsecond=0,
        )
        # 允许5分钟内的执行窗口
        return target <= now <= target + timedelta(minutes=5)

    def _should_run_notify(self) -> bool:
        """判断是否到了通知推送时间"""
        now = datetime.now()
        target = now.replace(
            hour=SCHEDULE["notify_hour"],
            minute=SCHEDULE["notify_minute"],
            second=0,
            microsecond=0,
        )
        # 允许5分钟内的执行窗口
        return target <= now <= target + timedelta(minutes=5)

    def _run_gjdw_task(self):
        """执行GJDW采集任务"""
        try:
            from gjdw.main import run_gjdw_task
            self._gjdw_result = run_gjdw_task(headless=True)
            self._gjdw_notified = False
        except Exception as e:
            self.logger.error(f"GJDW任务执行异常: {e}", exc_info=True)
            self._gjdw_result = {"success": False, "error": str(e)}
            self._gjdw_notified = False

    def _run_nfdw_task(self):
        """执行NFDW采集任务"""
        try:
            from nfdw.main import run_nfdw_task
            self._nfdw_result = run_nfdw_task(headless=True)
            self._nfdw_notified = False
        except Exception as e:
            self.logger.error(f"NFDW任务执行异常: {e}", exc_info=True)
            self._nfdw_result = {"success": False, "error": str(e)}
            self._nfdw_notified = False

    def run_once(self):
        """立即执行一次采集（手动模式）"""
        self.logger.info("手动执行模式 - 立即开始采集")
        self._run_gjdw_task()
        self._run_nfdw_task()
        self._print_summary()

    def run_scheduled(self):
        """启动定时调度（守护模式）"""
        self.logger.info("=" * 60)
        self.logger.info("定时任务调度器启动")
        self.logger.info(f"GJDW采集时间: 每日 {SCHEDULE['crawl_hour']:02d}:{SCHEDULE['crawl_minute']:02d}")
        self.logger.info(f"NFDW采集时间: 每日 {SCHEDULE['crawl_hour']:02d}:{SCHEDULE['crawl_minute']:02d}")
        self.logger.info(f"通知推送时间: 每日 {SCHEDULE['notify_hour']:02d}:{SCHEDULE['notify_minute']:02d}")
        self.logger.info("=" * 60)

        last_crawl_date = None
        check_interval = 60  # 每60秒检查一次

        while self._running:
            try:
                now = datetime.now()
                current_date = now.strftime("%Y-%m-%d")

                # 每日采集
                if self._should_run_crawl() and last_crawl_date != current_date:
                    self.logger.info(f"到达采集时间，开始执行任务 ({now})")

                    # 并行执行两个采集任务
                    gjdw_thread = threading.Thread(target=self._run_gjdw_task, name="GJDW")
                    nfdw_thread = threading.Thread(target=self._run_nfdw_task, name="NFDW")

                    gjdw_thread.start()
                    nfdw_thread.start()

                    gjdw_thread.join(timeout=600)  # 10分钟超时
                    nfdw_thread.join(timeout=600)

                    last_crawl_date = current_date
                    self.logger.info("今日采集任务执行完毕")

                # 每60秒检查一次
                time.sleep(check_interval)

            except KeyboardInterrupt:
                self.logger.info("接收到中断信号，停止调度器")
                break
            except Exception as e:
                self.logger.error(f"调度器异常: {e}", exc_info=True)
                time.sleep(check_interval)

        self.logger.info("调度器已停止")

    def _print_summary(self):
        """打印执行摘要"""
        self.logger.info("=" * 60)
        self.logger.info("执行摘要")

        if self._gjdw_result:
            r = self._gjdw_result
            status = "✅ 成功" if r["success"] else "❌ 失败"
            self.logger.info(f"GJDW: {status} | 新增 {r.get('new_count', 0)} 条 | 总计 {r.get('total_count', 0)} 条")

        if self._nfdw_result:
            r = self._nfdw_result
            status = "✅ 成功" if r["success"] else "❌ 失败"
            self.logger.info(f"NFDW: {status} | 新增 {r.get('new_count', 0)} 条 | 总计 {r.get('total_count', 0)} 条")

        self.logger.info("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="双平台信息采集调度器")
    parser.add_argument("--once", action="store_true", help="立即执行一次采集")
    parser.add_argument("--gjdw", action="store_true", help="仅执行GJDW采集")
    parser.add_argument("--nfdw", action="store_true", help="仅执行NFDW采集")
    args = parser.parse_args()

    scheduler = TaskScheduler()

    if args.once:
        if args.gjdw:
            scheduler._run_gjdw_task()
        elif args.nfdw:
            scheduler._run_nfdw_task()
        else:
            scheduler.run_once()
    else:
        scheduler.run_scheduled()
