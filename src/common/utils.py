# -*- coding: utf-8 -*-
"""
通用工具模块
提供日期解析、文本清洗、数据去重等通用功能
"""
import re
from datetime import datetime
from typing import Optional


def clean_text(text: str) -> str:
    """清洗文本：去除多余空格、换行、HTML标签"""
    if not text:
        return ""
    # 去除HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 去除多余空白
    text = re.sub(r"\s+", " ", text)
    # 去除首尾空白
    text = text.strip()
    return text


def clean_text_preserve_format(text: str) -> str:
    """
    清洗文本但保留格式：去除HTML标签，保留段落分隔
    - 去除HTML标签
    - 将多个连续换行合并为最多2个换行（保留段落分隔）
    - 将多个连续空格合并为1个空格
    - 去除每行首尾空白
    - 保留有意义的换行
    """
    if not text:
        return ""
    # 去除HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 将多个连续换行合并为最多2个换行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 将 \r\n 统一为 \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 去除每行首尾空白，同时将行内多个连续空格合并为1个
    lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.split("\n")]
    text = "\n".join(lines)
    # 去除首尾空白
    text = text.strip()
    return text


def parse_date(date_str: str) -> Optional[str]:
    """
    解析日期字符串，统一为 YYYY-MM-DD HH:MM:SS 格式
    支持多种日期格式
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # 常见日期格式模式
    patterns = [
        # 2026-03-31 23:30:00
        (r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})", "%Y-%m-%d %H:%M:%S"),
        # 2026-03-31 23:30
        (r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})", "%Y-%m-%d %H:%M"),
        # 2026年03月31日 23:30:00
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2}):(\d{1,2})", None),
        # 2026年03月31日 23时30分
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时(\d{1,2})分", None),
        # 2026年03月31日 23时30分00秒
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时(\d{1,2})分(\d{1,2})秒", None),
        # 2026年03月31日
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", None),
        # 2026-03-31
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "%Y-%m-%d"),
        # 2026/03/31 23:30:00
        (r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})", None),
        # 2026/03/31
        (r"(\d{4})/(\d{1,2})/(\d{1,2})", None),
    ]

    for pattern, fmt in patterns:
        match = re.search(pattern, date_str)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 6:
                    dt = datetime(int(groups[0]), int(groups[1]), int(groups[2]),
                                  int(groups[3]), int(groups[4]), int(groups[5]))
                elif len(groups) == 5:
                    dt = datetime(int(groups[0]), int(groups[1]), int(groups[2]),
                                  int(groups[3]), int(groups[4]))
                elif len(groups) == 3:
                    dt = datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                else:
                    continue
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, IndexError):
                continue

    return None


def extract_date_after_keyword(text: str, keywords: list[str]) -> Optional[str]:
    """
    从文本中提取关键词后的日期
    keywords: 关键词列表，如 ["获取结束时间：", "截止时间："]
    支持格式：YYYY-MM-DD HH:MM:SS, YYYY年MM月DD日 HH:MM 等
    """
    if not text:
        return None

    for keyword in keywords:
        idx = text.find(keyword)
        if idx != -1:
            after_text = text[idx + len(keyword):].strip()
            # 提取日期部分（最多取80个字符）
            date_part = after_text[:80]
            date_str = parse_date(date_part)
            if date_str:
                return date_str

    return None


def parse_gjdw_project_name(project_name: str) -> dict:
    """
    解析GJDW项目名称
    格式：【单位】项目简称
    """
    unit = ""
    short_name = project_name

    # 尝试匹配【单位】项目简称 格式
    match = re.match(r"【(.+?)】(.+)", project_name)
    if match:
        unit = match.group(1).strip()
        short_name = match.group(2).strip()

    return {"单位": unit, "项目简称": short_name}


def parse_nfdw_project_name(project_name: str) -> dict:
    """
    解析NFDW项目名称
    格式1：单位|项目简称
    格式2：单位公司...项目简称（无分隔符，通过"公司"关键词识别）
    """
    unit = ""
    short_name = project_name

    # 尝试匹配 单位|项目简称 格式
    if "|" in project_name:
        parts = project_name.split("|", 1)
        unit = parts[0].strip()
        short_name = parts[1].strip()
    else:
        # 无分隔符时，用正则匹配第一个"公司"结尾的词组作为单位
        match = re.match(r"^(.+?公司).+$", project_name)
        if match:
            unit = match.group(1).strip()
            short_name = project_name[len(unit):].strip()

    return {"单位": unit, "项目简称": short_name}


def make_unique_key(project_code: str, visit_url: str) -> str:
    """生成去重唯一键"""
    return f"{project_code or ''}|{visit_url or ''}"


def is_after_date(date_str: str, ref_date_str: str = "2026-03-18") -> bool:
    """判断日期是否在参考日期之后"""
    if not date_str:
        return False
    try:
        date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
        return date >= ref_date
    except ValueError:
        return False
