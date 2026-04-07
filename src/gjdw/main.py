# -*- coding: utf-8 -*-
"""
GJDW信息采集工具 - 主入口
负责：采集调度、数据存储、通知推送
"""
import sys
import os
import time
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.logger import setup_logger, cleanup_old_logs
from common.feishu_client import FeishuClient
from common.utils import is_after_date
from gjdw.collector import GJDWCollector
from config.settings import GJDW_CONFIG, FEISHU_BITABLE, GENERAL


def run_gjdw_task(headless: bool = True) -> dict:
    """
    执行GJDW采集任务
    返回: {"success": bool, "new_count": int, "total_count": int, "error": str}
    """
    logger = setup_logger("gjdw", GENERAL["log_level"])
    logger.info("=" * 60)
    logger.info("GJDW信息采集任务启动")
    logger.info("=" * 60)

    execute_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    feishu = FeishuClient()

    try:
        # 1. 获取已有数据（去重用）
        logger.info("获取飞书表格已有数据...")
        existing_keys = feishu.get_existing_keys("gjdw")
        logger.info(f"已有数据 {len(existing_keys)} 条")

        # 2. 执行采集
        logger.info("开始数据采集...")
        collector = GJDWCollector(headless=headless, logger=logger)
        new_records = collector.run(existing_keys=existing_keys)

        # 3. 写入飞书表格
        new_count = 0
        if new_records:
            logger.info(f"写入 {len(new_records)} 条新数据到飞书表格...")
            result = feishu.append_records("gjdw", new_records)
            new_count = result.get("created", 0)
            logger.info(f"成功写入 {new_count} 条数据")
        else:
            logger.info("没有新增数据")

        # 4. 获取总数据量
        total_count = feishu.get_total_count("gjdw")
        logger.info(f"表格总数据量: {total_count} 条")

        # 5. 发送成功通知
        table_url = FEISHU_BITABLE["gjdw"]["url"]
        feishu.send_success_notification(
            task_name="GJDW信息采集",
            execute_time=execute_time,
            new_count=new_count,
            total_count=total_count,
            table_url=table_url,
        )
        logger.info("成功通知已发送")

        return {
            "success": True,
            "new_count": new_count,
            "total_count": total_count,
            "error": "",
        }

    except Exception as e:
        logger.error(f"任务执行失败: {e}", exc_info=True)

        # 发送失败通知
        try:
            feishu.send_failure_notification(
                task_name="GJDW信息采集",
                execute_time=execute_time,
                error_msg=str(e)[:500],
            )
        except Exception:
            logger.error("发送失败通知也失败了")

        return {
            "success": False,
            "new_count": 0,
            "total_count": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GJDW信息采集工具")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()

    result = run_gjdw_task(headless=not args.no_headless)
    print(f"\n执行结果: {'成功' if result['success'] else '失败'}")
    print(f"新增数据: {result['new_count']} 条")
    print(f"总数据量: {result['total_count']} 条")
    if result["error"]:
        print(f"错误信息: {result['error']}")
