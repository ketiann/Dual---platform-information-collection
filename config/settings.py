# -*- coding: utf-8 -*-
"""
双平台信息采集工具 - 配置文件
GJDW（国家电网）+ NFDW（南方电网）
"""

# ==================== 飞书机器人配置 ====================
FEISHU = {
    "app_id": "cli_a93613be0cf95ccf",
    "app_secret": "ukxhIZGIQ5z8e0tsCI0eMbFwgrRToQdI",
    "encrypt_key": "nRPEDltgwQA9yYiAONVvlcNjM8uZv77M",
    "verification_token": "qPnuO2RHxU5VqC8IsKdFVh2K07PHANDc",
    # 通知配置（二选一）：
    # 方式1（推荐）：Webhook URL - 在飞书群聊中添加机器人，获取Webhook地址
    "webhook_url": "",  # 例: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
    # 方式2：API方式 - 需要配置群聊ID（chat_id）
    "receive_id": "oc_6d9c9d972dde2a895fea9ad091500171",
}

# ==================== 飞书多维表格配置 ====================
FEISHU_BITABLE = {
    # GJDW 数据存储表
    "gjdw": {
        "app_token": "Ra2PbSXZJaOFoTsz0d8czsIXnye",
        "table_id": "tblLmjYN2bFazFX8",
        "view_id": "vewKaoSApy",
        "url": "https://ccny8jg66j80.feishu.cn/base/Ra2PbSXZJaOFoTsz0d8czsIXnye?table=tblLmjYN2bFazFX8&view=vewKaoSApy",
    },
    # NFDW 数据存储表
    "nfdw": {
        "app_token": "Ra2PbSXZJaOFoTsz0d8czsIXnye",
        "table_id": "tblHyQmSkkzBbceK",
        "view_id": "vewKaoSApy",
        "url": "https://ccny8jg66j80.feishu.cn/base/Ra2PbSXZJaOFoTsz0d8czsIXnye?table=tblHyQmSkkzBbceK&view=vewKaoSApy",
    },
}

# ==================== GJDW 采集配置 ====================
GJDW_CONFIG = {
    # 数据源页面
    "sources": [
        {
            "name": "电工交易平台-招标公告",
            "platform": "电工交易平台",
            "type": "招标公告",
            "url": "https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032700291334/old/1",
            "base_url": "https://sgccetp.com.cn",
        },
        {
            "name": "电工交易平台-采购公告",
            "platform": "电工交易平台",
            "type": "采购公告",
            "url": "https://sgccetp.com.cn/portal/#/list/list-spe/2018032600289606_1_2018032900295987/old/1",
            "base_url": "https://sgccetp.com.cn",
        },
        {
            "name": "电子商务平台-招标公告",
            "platform": "电子商务平台",
            "type": "招标公告",
            "url": "https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032700291334",
            "base_url": "https://ecp.sgcc.com.cn",
        },
        {
            "name": "电子商务平台-采购公告",
            "platform": "电子商务平台",
            "type": "采购公告",
            "url": "https://ecp.sgcc.com.cn/ecp2.0/portal/#/list/list-spe/2018032600289606_1_2018032900295987",
            "base_url": "https://ecp.sgcc.com.cn",
        },
    ],
    # 筛选关键字（项目名称必须包含）
    "keyword_filter": "湖南",
    # 剔除的项目状态
    "exclude_status": ["已经截止"],
    # 首次采集起始日期（最近10天）
    "start_date": "2026-04-03",
    # 每页等待时间（秒）
    "page_wait": 3,
    # 翻页等待时间（秒）
    "next_page_wait": 2,
}

# ==================== NFDW 采集配置 ====================
NFDW_CONFIG = {
    # 数据源页面
    "sources": [
        {
            "name": "招标公告",
            "platform": "南方电网",
            "type": "招标公告",
            "url": "https://www.bidding.csg.cn/zbgg/index.jhtml",
            "base_url": "https://www.bidding.csg.cn",
            "channel_id": 52,
        },
        {
            "name": "零星采购公告",
            "platform": "南方电网",
            "type": "零星采购公告",
            "url": "https://www.bidding.csg.cn/lxcggg/index.jhtml",
            "base_url": "https://www.bidding.csg.cn",
            "channel_id": 495,
        },
    ],
    # 剔除的公告类型
    "exclude_types": ["零星采购澄清公告"],
    # 首次采集起始日期（最近10天）
    "start_date": "2026-04-03",
    # 请求间隔（秒）
    "request_interval": 2,
    # 详情页请求间隔（秒）
    "detail_interval": 1.5,
}

# ==================== 智谱AI配置 ====================
ZHIPU_AI = {
    "api_key": "ed51ac2ce25f45ab9b529d9d77df46fa.oqxyQ6MsJnqdhxYQ",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
}

# ==================== 定时任务配置 ====================
SCHEDULE = {
    # 采集执行时间（每日）
    "crawl_hour": 8,
    "crawl_minute": 30,
    # 通知推送时间（每日）
    "notify_hour": 9,
    "notify_minute": 0,
}

# ==================== 通用配置 ====================
GENERAL = {
    # 日志级别
    "log_level": "INFO",
    # 日志文件保留天数
    "log_keep_days": 30,
    # 重试次数
    "max_retries": 3,
    # 重试间隔（秒）
    "retry_interval": 5,
    # 浏览器无头模式
    "headless": True,
    # 数据去重标识字段
    "unique_fields": ["project_code", "visit_url"],
}
