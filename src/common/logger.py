# -*- coding: utf-8 -*-
"""
日志工具模块
提供统一的日志配置和管理
"""
import logging
import os
import sys
from datetime import datetime, timedelta


def setup_logger(name: str = "bid_collector", level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """初始化日志记录器"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def cleanup_old_logs(log_dir: str = "logs", keep_days: int = 30):
    """清理过期日志文件"""
    if not os.path.exists(log_dir):
        return
    cutoff = datetime.now() - timedelta(days=keep_days)
    for fname in os.listdir(log_dir):
        fpath = os.path.join(log_dir, fname)
        if os.path.isfile(fpath):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    os.remove(fpath)
            except Exception:
                pass
