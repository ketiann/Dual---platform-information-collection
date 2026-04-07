# 双平台信息采集工具（GJDW + NFDW）

## 项目概述

本项目包含两套独立的信息采集工具，分别用于采集国家电网（GJDW）和南方电网（NFDW）的招标/采购公告信息，数据自动写入飞书多维表格，支持定时执行和飞书通知。

## 项目结构

```
bid_collector/
├── main.py                  # 项目入口
├── requirements.txt         # Python依赖
├── config/
│   ├── __init__.py
│   └── settings.py          # 全部配置（飞书、数据源、定时任务等）
├── src/
│   ├── __init__.py
│   ├── scheduler.py         # 定时任务调度器
│   ├── common/              # 通用模块
│   │   ├── __init__.py
│   │   ├── logger.py        # 日志工具
│   │   ├── feishu_client.py # 飞书API客户端（表格写入+消息通知）
│   │   ├── zhipu_client.py  # 智谱AI客户端（内容智能解析）
│   │   └── utils.py         # 通用工具函数
│   ├── gjdw/                # GJDW采集模块
│   │   ├── __init__.py
│   │   ├── collector.py     # GJDW爬虫核心
│   │   └── main.py          # GJDW任务入口
│   └── nfdw/                # NFDW采集模块
│       ├── __init__.py
│       ├── collector.py     # NFDW爬虫核心
│       └── main.py          # NFDW任务入口
├── logs/                    # 日志目录（自动创建）
└── data/                    # 数据缓存目录
```

## 环境要求

- Python 3.8+
- Chromium浏览器（Playwright自动安装）
- 网络可访问目标网站和飞书API

## 安装部署

### 1. 安装Python依赖

```bash
cd bid_collector
pip install -r requirements.txt
```

### 2. 安装Playwright浏览器

```bash
playwright install chromium
playwright install-deps  # 安装系统依赖（Linux需要）
```

### 3. 配置修改

编辑 `config/settings.py`，根据需要修改：

- **飞书配置**：APP ID、App Secret等（已预填）
- **飞书表格**：app_token、table_id（已预填）
- **采集配置**：筛选关键字、起始日期等
- **定时配置**：采集和通知时间
- **智谱AI**：API密钥（已预填）

### 4. 飞书机器人配置

1. 在飞书开放平台创建应用，获取 APP ID 和 App Secret
2. 配置机器人权限：`bitable:app`（多维表格读写）、`im:message`（消息发送）
3. 将机器人添加到需要接收通知的群聊
4. 在 `config/settings.py` 中更新 `FEISHU` 配置

## 使用方法

### 立即执行一次采集

```bash
# 执行全部采集（GJDW + NFDW）
python main.py --once

# 仅执行GJDW采集
python main.py --once --gjdw

# 仅执行NFDW采集
python main.py --once --nfdw
```

### 启动定时调度模式

```bash
# 后台运行定时调度（每日08:30采集，09:00通知）
nohup python main.py --schedule > /dev/null 2>&1 &
```

### 调试模式（显示浏览器）

```bash
python main.py --once --gjdw --no-headless
```

## 数据源说明

### GJDW（国家电网）

| 数据源 | URL | 采集内容 |
|--------|-----|----------|
| 电工交易平台 | sgccetp.com.cn | 招标公告、采购公告 |
| 电子商务平台 | ecp.sgcc.com.cn | 招标公告、采购公告 |

- 筛选规则：项目名称包含"湖南"
- 过滤规则：剔除"已经截止"项目
- 技术方案：Playwright浏览器自动化（SPA页面）

### NFDW（南方电网）

| 数据源 | URL | 采集内容 |
|--------|-----|----------|
| 招标公告 | bidding.csg.cn/zbgg | 招标公告 |
| 零星采购公告 | bidding.csg.cn/lxcggg | 零星采购公告 |

- 筛选规则：剔除"零星采购澄清公告"
- 技术方案：requests + BeautifulSoup（传统HTML页面）

## 采集字段

| 字段 | 说明 |
|------|------|
| 项目名称 | 原始完整名称 |
| 单位 | 从项目名称拆分提取 |
| 项目简称 | 从项目名称拆分提取 |
| 项目编号 | 页面/全文提取 |
| 公告类型 | 招标公告/采购公告等 |
| 项目状态 | 进行中/已截止 |
| 创建时间 | 公告发布时间 |
| 文件获取截止时间 | 投标截止时间 |
| 访问链接 | 项目详情页URL |
| 公告全文 | 完整正文内容 |
| 数据来源 | 平台名称 |

## 日志

日志文件位于 `logs/` 目录，按日期命名：
- `gjdw_20260403.log` - GJDW采集日志
- `nfdw_20260403.log` - NFDW采集日志
- `scheduler_20260403.log` - 调度器日志

## 注意事项

1. **反爬机制**：GJDW平台使用国密加密，本工具通过浏览器自动化绕过；NFDW平台为传统HTML，使用适当的请求间隔
2. **增量采集**：以项目编号+访问链接为唯一标识，避免重复入库
3. **异常处理**：网络失败、解析失败、入库失败均会触发飞书失败通知
4. **AI辅助**：当正则解析无法提取字段时，自动调用智谱AI进行智能解析
