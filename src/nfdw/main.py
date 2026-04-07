# -*- coding: utf-8 -*-
"""
NFDW信息采集工具 - 主入口
负责：采集调度、数据存储、通知推送
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.logger import setup_logger, cleanup_old_logs
from common.feishu_client import FeishuClient
from common.utils import is_after_date
from nfdw.collector import NFDWCollector
from config.settings import NFDW_CONFIG, FEISHU_BITABLE, GENERAL


def run_nfdw_task(headless: bool = True) -> dict:
    """
    执行NFDW采集任务
    返回: {"success": bool, "new_count": int, "total_count": int, "error": str}
    """
    logger = setup_logger("nfdw", GENERAL["log_level"])
    logger.info("=" * 60)
    logger.info("NFDW信息采集任务启动")
    logger.info("=" * 60)

    execute_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    feishu = FeishuClient()

    try:
        # 1. 获取已有数据（去重用）
        logger.info("获取飞书表格已有数据...")
        existing_keys = feishu.get_existing_keys("nfdw")
        logger.info(f"已有数据 {len(existing_keys)} 条")

        # 2. 执行采集
        logger.info("开始数据采集...")
        collector = NFDWCollector(headless=headless, logger=logger)
        new_records = collector.run(existing_keys=existing_keys)

        # 3. 写入飞书表格
        new_count = 0
        if new_records:
            logger.info(f"写入 {len(new_records)} 条新数据到飞书表格...")
            result = feishu.append_records("nfdw", new_records)
            new_count = result.get("created", 0)
            logger.info(f"成功写入 {new_count} 条数据")
        else:
            logger.info("没有新增数据")

        # 4. 获取总数据量
        total_count = feishu.get_total_count("nfdw")
        logger.info(f"表格总数据量: {total_count} 条")

        # 5. 发送成功通知
        table_url = FEISHU_BITABLE["nfdw"]["url"]
        feishu.send_success_notification(
            task_name="NFDW信息采集",
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
                task_name="NFDW信息采集",
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
    result = run_nfdw_task()
    print(f"\n执行结果: {'成功' if result['success'] else '失败'}")
    print(f"新增数据: {result['new_count']} 条")
    print(f"总数据量: {result['total_count']} 条")
    if result["error"]:
        print(f"错误信息: {result['error']}")
