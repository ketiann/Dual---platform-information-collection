# -*- coding: utf-8 -*-
"""
通用模块初始化
"""
from common.logger import setup_logger, cleanup_old_logs
from common.feishu_client import FeishuClient
from common.zhipu_client import ZhipuAIClient
from common.utils import (
    clean_text, parse_date, extract_date_after_keyword,
    parse_gjdw_project_name, parse_nfdw_project_name,
    make_unique_key, is_after_date,
)

__all__ = [
    "setup_logger", "cleanup_old_logs",
    "FeishuClient", "ZhipuAIClient",
    "clean_text", "parse_date", "extract_date_after_keyword",
    "parse_gjdw_project_name", "parse_nfdw_project_name",
    "make_unique_key", "is_after_date",
]
