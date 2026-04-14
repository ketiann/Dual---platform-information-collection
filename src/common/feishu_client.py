# -*- coding: utf-8 -*-
"""
飞书API客户端模块
支持：多维表格写入、机器人消息通知
"""
import json
import re
import time
from typing import Optional

import requests

from config.settings import FEISHU, FEISHU_BITABLE


class FeishuClient:
    """飞书API客户端"""

    def __init__(self):
        self.app_id = FEISHU["app_id"]
        self.app_secret = FEISHU["app_secret"]
        self.encrypt_key = FEISHU["encrypt_key"]
        self.verification_token = FEISHU["verification_token"]
        self._tenant_access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self.base_url = "https://open.feishu.cn/open-apis"
        # 通知方式：优先使用webhook（如已配置），否则使用API
        self.webhook_url = FEISHU.get("webhook_url", "")

    # ==================== Token管理 ====================

    def _get_tenant_access_token(self) -> str:
        """获取或刷新tenant_access_token"""
        if self._tenant_access_token and time.time() < self._token_expires_at:
            return self._tenant_access_token

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()
        if data.get("code") == 0:
            self._tenant_access_token = data["tenant_access_token"]
            self._token_expires_at = time.time() + data.get("expire", 7200) - 300
            return self._tenant_access_token
        else:
            raise Exception(f"获取飞书token失败: {data.get('msg', '未知错误')}")

    def _auth_headers(self) -> dict:
        """构造认证请求头"""
        token = self._get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ==================== 多维表格操作 ====================

    def clear_records(self, platform: str) -> int:
        """
        清空多维表格中的所有记录
        返回删除的记录数
        """
        config = FEISHU_BITABLE[platform]
        app_token = config["app_token"]
        table_id = config["table_id"]
        url = f"{self.base_url}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete"

        records = self.list_records(platform)
        if not records:
            return 0

        record_ids = [r["record_id"] for r in records]
        deleted_total = 0

        # 分批删除，每批最多500条
        batch_size = 500
        for i in range(0, len(record_ids), batch_size):
            batch_ids = record_ids[i:i + batch_size]
            headers = self._auth_headers()
            resp = requests.post(url, headers=headers, json={"records": batch_ids}, timeout=30)
            if resp.status_code == 200:
                deleted_total += len(batch_ids)
            else:
                print(f"删除批次 {i//batch_size + 1} 失败: {resp.text}")

        return deleted_total

    def list_records(self, platform: str, page_size: int = 100) -> list:
        """
        获取多维表格中已有记录（用于去重）
        platform: "gjdw" 或 "nfdw"
        """
        config = FEISHU_BITABLE[platform]
        app_token = config["app_token"]
        table_id = config["table_id"]
        url = f"{self.base_url}/bitable/v1/apps/{app_token}/tables/{table_id}/records"

        all_records = []
        page_token = None
        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=self._auth_headers(), params=params, timeout=30)
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"获取飞书表格记录失败: {data.get('msg', '未知错误')}")
            items = data.get("data", {}).get("items", [])
            all_records.extend(items)
            page_token = data.get("data", {}).get("page_token")
            if not page_token or not items:
                break
        return all_records

    def get_existing_keys(self, platform: str) -> set:
        """
        获取已有的唯一标识集合（项目编号+访问链接）
        用于增量去重
        """
        records = self.list_records(platform)
        keys = set()
        for record in records:
            fields = record.get("fields", {})
            project_code = fields.get("项目编号", [""])[0] if isinstance(fields.get("项目编号"), list) else fields.get("项目编号", "")
            visit_url = fields.get("访问链接", [""])[0] if isinstance(fields.get("访问链接"), list) else fields.get("访问链接", "")
            if project_code or visit_url:
                keys.add(f"{project_code}|{visit_url}")
        return keys

    def append_records(self, platform: str, records: list[dict]) -> dict:
        """
        批量写入记录到飞书多维表格
        records: 字段字典列表，每个字典的key对应表格字段名
        返回: {"success": True, "created": N} 或 {"success": False, "error": "..."}
        """
        if not records:
            return {"success": True, "created": 0}

        config = FEISHU_BITABLE[platform]
        app_token = config["app_token"]
        table_id = config["table_id"]
        url = f"{self.base_url}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"

        # 字段类型映射：不同字段类型需要不同的值格式
        # DateTime字段: 传毫秒时间戳数字
        # SingleSelect字段: 直接传字符串（飞书自动匹配选项）
        # Text字段: 直接传字符串
        # Email字段: 直接传字符串
        # 注意："访问链接"不使用飞书URL字段类型（会导致URLFieldConvFail），
        # 而是作为普通文本字段处理
        DATETIME_FIELDS = {"创建时间", "文件获取截止时间"}
        SINGLE_SELECT_FIELDS = {"公告类型", "项目状态", "数据来源", "处理情况"}
        # 以下字段在飞书中是URL类型，传任何值都会导致URLFieldConvFail，直接跳过
        SKIP_FIELDS = {"访问链接"}

        feishu_records = []
        for rec in records:
            fields = {}
            for key, value in rec.items():
                if value is None or value == "" or value == "None":
                    continue
                if key in SKIP_FIELDS:
                    continue
                if key in DATETIME_FIELDS:
                    # DateTime字段：转换为毫秒时间戳
                    ts = self._datetime_to_timestamp(value)
                    if ts:
                        fields[key] = ts
                elif key in SINGLE_SELECT_FIELDS:
                    # SingleSelect字段：直接传字符串
                    fields[key] = str(value)
                else:
                    # Text/Email等其他字段：直接传字符串，限制最大长度
                    str_val = str(value)
                    # 飞书单元格最大2000字符
                    if len(str_val) > 2000:
                        str_val = str_val[:1997] + "..."
                    fields[key] = str_val
            feishu_records.append({"fields": fields})

        # 分批写入（每批最多500条）
        batch_size = 500
        total_created = 0
        for i in range(0, len(feishu_records), batch_size):
            batch = feishu_records[i:i + batch_size]
            payload = {"records": batch}
            resp = requests.post(url, headers=self._auth_headers(), json=payload, timeout=60)
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"写入飞书表格失败: {data.get('msg', '未知错误')}")
            total_created += len(batch)

        return {"success": True, "created": total_created}

    def _datetime_to_timestamp(self, dt_str) -> int:
        """将日期字符串转换为飞书DateTime字段需要的毫秒时间戳"""
        if not dt_str:
            return 0
        from datetime import datetime
        # 尝试解析各种日期格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(str(dt_str).strip(), fmt)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        return 0

    def get_total_count(self, platform: str) -> int:
        """获取表格总记录数"""
        records = self.list_records(platform)
        return len(records)

    # ==================== 机器人消息通知 ====================

    def send_success_notification(self, task_name: str, execute_time: str,
                                   new_count: int, total_count: int,
                                   table_url: str):
        """发送采集成功通知"""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"✅ {task_name} - 采集完成"},
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务名称**\n{task_name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{execute_time}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**新增数据**\n{new_count} 条"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**总数据量**\n{total_count} 条"}},
                    ],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看数据表格"},
                            "type": "primary",
                            "url": table_url,
                        }
                    ],
                },
            ],
        }
        self._send_notification(card)

    def send_failure_notification(self, task_name: str, execute_time: str,
                                   error_msg: str):
        """发送采集失败通知"""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"❌ {task_name} - 采集失败"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**任务名称**\n{task_name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**执行时间**\n{execute_time}"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**错误信息：**\n{error_msg}"},
                },
            ],
        }
        self._send_notification(card)

    def _send_notification(self, card: dict):
        """
        发送通知消息
        优先使用Webhook方式（如已配置），否则使用API方式
        """
        # 方式1: Webhook（推荐，简单可靠）
        if self.webhook_url:
            try:
                self._send_via_webhook(self.webhook_url, card)
                return
            except Exception:
                pass  # Webhook失败，尝试API方式

        # 方式2: 通过API发送（需要配置receive_id）
        receive_id = FEISHU.get("receive_id", "")
        if receive_id:
            self._send_via_api(card, receive_id)
        else:
            # 没有配置通知渠道，仅记录日志
            print(f"[飞书通知] 未配置webhook_url或receive_id，跳过通知发送。请参考README配置通知渠道。")

    def _send_via_webhook(self, webhook_url: str, card: dict):
        """通过Webhook URL发送卡片消息"""
        headers = {"Content-Type": "application/json"}
        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        resp = requests.post(webhook_url, headers=headers, json=payload, timeout=30)
        data = resp.json()
        if data.get("code", -1) != 0 and data.get("StatusCode", -1) != 0:
            raise Exception(f"Webhook通知发送失败: {data}")

    def _send_via_api(self, card: dict, receive_id: str):
        """通过飞书API发送卡片消息到群聊"""
        token = self._get_tenant_access_token()
        # receive_id_type 必须通过query parameter传递
        url = f"{self.base_url}/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"发送飞书通知失败: {data.get('msg', '未知错误')}")
