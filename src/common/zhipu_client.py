# -*- coding: utf-8 -*-
"""
智谱AI客户端模块
用于对公告内容进行智能解析和分析
"""
import json
import requests
from typing import Optional

from config.settings import ZHIPU_AI


class ZhipuAIClient:
    """智谱AI API客户端"""

    def __init__(self):
        self.api_key = ZHIPU_AI["api_key"]
        self.base_url = ZHIPU_AI["base_url"]
        self.model = ZHIPU_AI["model"]

    def chat(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
        """
        调用智谱AI对话接口
        messages: [{"role": "user", "content": "..."}]
        返回: 模型回复文本
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        data = resp.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        else:
            raise Exception(f"智谱AI调用失败: {data.get('error', data)}")

    def extract_fields_from_content(self, content: str, field_names: list[str]) -> dict:
        """
        使用大模型从公告全文中提取指定字段
        field_names: 需要提取的字段名称列表
        返回: {字段名: 提取值}
        """
        prompt = f"""请从以下公告内容中提取指定字段信息。请严格按照JSON格式返回结果。

需要提取的字段：
{json.dumps(field_names, ensure_ascii=False)}

提取规则：
1. 项目编号：查找"编号："、"项目编号："等关键词后面的内容
2. 创建时间/发布时间：查找"发布时间"、"发布日期"等关键词后面的日期
3. 文件获取截止时间：查找"获取结束时间"、"截止时间"、"文件获取截止时间"等关键词后面的日期
4. 所有日期统一格式为：YYYY-MM-DD HH:MM:SS，如果只有日期则补 00:00:00
5. 如果某个字段找不到，对应值设为空字符串""

公告内容：
{content[:3000]}

请直接返回JSON格式结果，不要添加其他说明文字。"""

        try:
            result = self.chat([{"role": "user", "content": prompt}])
            # 尝试解析JSON
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def parse_project_name(self, project_name: str, platform: str) -> dict:
        """
        解析项目名称，提取单位和项目简称
        GJDW格式：【单位】项目简称
        NFDW格式：单位|项目简称
        """
        if platform == "gjdw":
            prompt = f"""请从以下项目名称中提取"单位"和"项目简称"。
格式通常为：【单位】项目简称

项目名称：{project_name}

请严格按JSON格式返回：{{"单位": "...", "项目简称": "..."}}，不要添加其他说明。"""
        else:
            prompt = f"""请从以下项目名称中提取"单位"和"项目简称"。
格式通常为：单位|项目简称

项目名称：{project_name}

请严格按JSON格式返回：{{"单位": "...", "项目简称": "..."}}，不要添加其他说明。"""

        try:
            result = self.chat([{"role": "user", "content": prompt}])
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(result)
        except Exception:
            return {"单位": "", "项目简称": project_name}
