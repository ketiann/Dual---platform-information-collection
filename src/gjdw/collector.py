# -*- coding: utf-8 -*-
"""
GJDW信息采集工具 - 浏览器自动化爬虫
数据源：电工交易平台 + 电子商务平台
采集内容：招标公告 + 采购公告

技术方案：通过Playwright加载SPA页面，从DOM表格中提取数据，支持翻页
"""
import re
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

from config.settings import GJDW_CONFIG, GENERAL
from common.utils import (
    clean_text, parse_date, extract_date_after_keyword,
    parse_gjdw_project_name, make_unique_key, is_after_date,
)
from common.zhipu_client import ZhipuAIClient


class GJDWCollector:
    """GJDW信息采集器"""

    def __init__(self, headless: bool = True, logger=None):
        self.headless = headless
        self.logger = logger
        self.zhipu = ZhipuAIClient()
        self.collected_data = []

    def _log(self, msg: str):
        if self.logger:
            self.logger.info(f"[GJDW] {msg}")
        else:
            print(f"[GJDW] {msg}")

    def _log_error(self, msg: str):
        if self.logger:
            self.logger.error(f"[GJDW] {msg}")
        else:
            print(f"[GJDW ERROR] {msg}")

    def run(self, existing_keys: set = None) -> list[dict]:
        """执行GJDW全量采集"""
        if existing_keys is None:
            existing_keys = set()
        self.collected_data = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)

            try:
                for source in GJDW_CONFIG["sources"]:
                    self._log(f"开始采集: {source['name']}")
                    self._collect_from_source(context, source, existing_keys)
            finally:
                browser.close()

        self._log(f"采集完成，共获取 {len(self.collected_data)} 条数据")
        return self.collected_data

    def _collect_from_source(self, context: BrowserContext, source: dict, existing_keys: set):
        """从单个数据源采集数据，支持翻页"""
        page = context.new_page()
        max_retries = GENERAL["max_retries"]

        # 加载页面
        for attempt in range(max_retries):
            try:
                page.goto(source["url"], wait_until="networkidle", timeout=60000)
                time.sleep(GJDW_CONFIG["page_wait"])
                break
            except Exception as e:
                self._log_error(f"加载页面失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(GENERAL["retry_interval"])
                else:
                    self._log_error(f"放弃采集: {source['name']}")
                    page.close()
                    return

        # 等待表格加载
        try:
            page.wait_for_selector("table tr", timeout=15000)
        except Exception:
            self._log("等待表格加载超时，尝试继续...")
            time.sleep(3)

        total_new = 0
        no_match_pages = 0
        max_no_match = 10  # 连续N页无匹配数据则停止
        max_pages = 50     # 最大翻页数

        for page_num in range(1, max_pages + 1):
            self._log(f"  采集第 {page_num} 页...")

            # 从当前页面表格中提取数据
            items = self._extract_table_rows(page, source)
            if not items:
                self._log(f"  第 {page_num} 页无数据")
                break

            page_new = 0
            page_has_old_data = False  # 标记是否遇到旧数据

            for item in items:
                try:
                    project_name = item.get("project_name", "")
                    create_time = item.get("create_time", "")

                    # 筛选：项目名称包含关键字
                    if GJDW_CONFIG["keyword_filter"] and GJDW_CONFIG["keyword_filter"] not in project_name:
                        continue

                    # 筛选：剔除已截止项目
                    status = item.get("status", "")
                    if status in GJDW_CONFIG["exclude_status"]:
                        continue

                    # 筛选：日期过滤
                    if create_time and not is_after_date(create_time, GJDW_CONFIG["start_date"]):
                        page_has_old_data = True
                        continue

                    # 去重
                    unique_key = make_unique_key(item.get("project_code", ""), item.get("visit_url", ""))
                    if unique_key in existing_keys:
                        continue

                    # 获取详情页
                    detail_url = item.get("detail_url", "")
                    if detail_url:
                        detail = self._get_detail_page(context, detail_url, source, project_name)
                        if detail:
                            item.update(detail)
                        time.sleep(1)

                    # 解析项目名称
                    name_parts = parse_gjdw_project_name(project_name)
                    item["单位"] = name_parts["单位"]
                    item["项目简称"] = name_parts["项目简称"]

                    if not item["单位"]:
                        try:
                            ai_result = self.zhipu.parse_project_name(project_name, "gjdw")
                            item["单位"] = ai_result.get("单位", "")
                            item["项目简称"] = ai_result.get("项目简称", project_name)
                        except Exception:
                            pass

                    # 设置固定字段
                    item["公告类型"] = source["type"]
                    item["数据来源"] = source["platform"]

                    # 清洗和标准化
                    for key in ["项目名称", "公告全文"]:
                        if key in item and item[key]:
                            item[key] = clean_text(item[key])
                    for key in ["创建时间", "文件获取截止时间"]:
                        if key in item and item[key]:
                            parsed = parse_date(str(item[key]))
                            if parsed:
                                item[key] = parsed

                    # 提取截止时间
                    if not item.get("文件获取截止时间") and item.get("公告全文"):
                        deadline = extract_date_after_keyword(
                            item["公告全文"],
                            ["文件获取截止时间", "获取截止时间", "截止时间", "投标截止时间",
                             "招标文件获取", "获取结束", "文件获取结束", "获取时间",
                             "招标文件发售", "发售截止", "标书获取", "标书发售"]
                        )
                        if deadline:
                            item["文件获取截止时间"] = deadline

                    # 项目状态判断逻辑
                    # 优先级：详情页"正在招标" > 截止时间判断 > 列表行状态 > 默认"进行中"
                    status = item.get("status", "")
                    if status == "正在招标":
                        item["status"] = "正在招标"
                    elif item.get("文件获取截止时间"):
                        # 根据截止时间判断状态
                        try:
                            deadline_dt = datetime.strptime(
                                item["文件获取截止时间"][:19], "%Y-%m-%d %H:%M:%S"
                            )
                            if deadline_dt > datetime.now():
                                item["status"] = "进行中"
                            else:
                                item["status"] = "已截止"
                        except (ValueError, IndexError):
                            # 无法解析截止时间，保留原有状态
                            if not status:
                                item["status"] = "进行中"
                    elif not status:
                        # 列表行无状态信息且无截止时间，默认设为"进行中"
                        item["status"] = "进行中"

                    # 构建记录
                    record = {
                        "项目名称": item.get("project_name", ""),
                        "单位": item.get("单位", ""),
                        "项目简称": item.get("项目简称", ""),
                        "项目编号": item.get("project_code", ""),
                        "公告类型": item.get("公告类型", ""),
                        "项目状态": item.get("status", ""),
                        "创建时间": item.get("create_time", ""),
                        "文件获取截止时间": item.get("文件获取截止时间", ""),
                        "访问链接": item.get("visit_url", ""),
                        "公告全文": item.get("公告全文", ""),
                        "数据来源": item.get("数据来源", ""),
                    }

                    final_key = make_unique_key(record["项目编号"], record["访问链接"])
                    if final_key not in existing_keys:
                        existing_keys.add(final_key)
                        self.collected_data.append(record)
                        page_new += 1
                        total_new += 1
                        self._log(f"    新增: {record['项目名称'][:60]}...")

                except Exception as e:
                    self._log_error(f"    处理失败: {e}")
                    continue

            self._log(f"  第 {page_num} 页新增 {page_new} 条数据")

            # 判断是否继续翻页
            if page_has_old_data:
                no_match_pages += 1
                if no_match_pages >= max_no_match:
                    self._log(f"  连续 {max_no_match} 页无符合条件的新数据，停止翻页")
                    break
            else:
                no_match_pages = 0

            # 尝试翻到下一页
            if not self._go_next_page(page):
                self._log("  已到最后一页")
                break

            time.sleep(GJDW_CONFIG["next_page_wait"])

        self._log(f"{source['name']} 共新增 {total_new} 条数据")
        page.close()

    def _extract_table_rows(self, page: Page, source: dict) -> list[dict]:
        """从页面表格中提取数据行"""
        items = []
        try:
            # 获取所有表格行（跳过表头）
            rows = page.query_selector_all("table tr")
            if len(rows) < 2:
                return items

            for row in rows[1:]:  # 跳过表头行
                try:
                    cells = row.query_selector_all("td")
                    if len(cells) < 3:
                        continue

                    item = {}

                    for i, cell in enumerate(cells):
                        text = cell.inner_text().strip()
                        link = cell.query_selector("a")
                        href = link.get_attribute("href") if link else None

                        # 第一个单元格通常是项目名称
                        if i == 0 and text:
                            item["project_name"] = text
                            # 如果有链接则记录（排除 #/ 开头的hash路由）
                            if href and not href.startswith("#/"):
                                if href.startswith("/portal/") or href.startswith("/"):
                                    item["detail_url"] = source["base_url"] + href
                                    item["visit_url"] = source["base_url"] + href
                                elif href.startswith("http"):
                                    item["detail_url"] = href
                                    item["visit_url"] = href
                            else:
                                # 没有有效链接时，尝试在整行中查找链接（排除hash路由）
                                row_links = row.query_selector_all("a[href]")
                                for row_link in row_links:
                                    row_href = row_link.get_attribute("href")
                                    if row_href and not row_href.startswith("#/"):
                                        if row_href.startswith("/portal/") or row_href.startswith("/"):
                                            item["detail_url"] = source["base_url"] + row_href
                                            item["visit_url"] = source["base_url"] + row_href
                                        elif row_href.startswith("http"):
                                            item["detail_url"] = row_href
                                            item["visit_url"] = row_href
                                        break

                        # 日期识别
                        date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
                        if date_match and not item.get("create_time"):
                            item["create_time"] = date_match.group(1)

                        # 状态识别
                        if "正在招标" in text and not item.get("status"):
                            item["status"] = "正在招标"
                        elif "已经截止" in text and not item.get("status"):
                            item["status"] = "已经截止"

                        # 项目编号识别（短文本+字母数字组合，排除项目名称列）
                        if not item.get("project_code") and len(text) < 30 and i > 0:
                            code_match = re.search(r"([A-Za-z0-9][\w\-]*)", text)
                            if code_match and len(code_match.group(1)) >= 3:
                                item["project_code"] = code_match.group(1)

                    if item.get("project_name"):
                        items.append(item)

                except Exception:
                    continue

        except Exception as e:
            self._log_error(f"提取表格行失败: {e}")

        return items

    def _go_next_page(self, page: Page) -> bool:
        """点击下一页按钮，返回是否成功"""
        next_selectors = [
            "button.btn-page:has-text('>')",
            "span.btn-page:has-text('>')",
            "a:has-text('下一页')",
            "button:has-text('下一页')",
            ".el-pagination .btn-next",
            ".next-btn",
            "li.next a",
            "[class*='next']",
        ]
        for selector in next_selectors:
            try:
                # 获取所有匹配的按钮，选择文本为">"的（排除">>"）
                buttons = page.query_selector_all(selector)
                for btn in buttons:
                    text = btn.inner_text().strip()
                    if text == ">" and btn.is_enabled():
                        btn.click()
                        time.sleep(GJDW_CONFIG["next_page_wait"])
                        page.wait_for_load_state("networkidle", timeout=15000)
                        return True
            except Exception:
                continue
        return False

    def _get_detail_page(self, context: BrowserContext, detail_url: str, source: dict, project_name: str = "") -> Optional[dict]:
        """获取详情页内容"""
        if not detail_url:
            return None

        if detail_url.startswith("/"):
            detail_url = source["base_url"] + detail_url

        page = context.new_page()
        max_retries = GENERAL["max_retries"]

        for attempt in range(max_retries):
            try:
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(GENERAL["retry_interval"])
                else:
                    page.close()
                    return None

        result = {}
        try:
            full_text = page.inner_text("body")

            # 如果页面内容为空或太短，尝试等待更长时间后重新获取
            if not full_text or len(full_text.strip()) < 100:
                self._log(f"  详情页内容过短（{len(full_text.strip()) if full_text else 0}字符），尝试等待更长时间...")
                time.sleep(3)
                try:
                    full_text = page.inner_text("body")
                except Exception:
                    pass

            # 如果详情页确实无法获取有效内容，使用项目名称作为公告全文摘要
            if not full_text or len(full_text.strip()) < 100:
                if project_name:
                    result["公告全文"] = project_name
                    self._log(f"  详情页无法获取内容，使用项目名称作为摘要")
                else:
                    result["公告全文"] = ""
                page.close()
                return result

            result["公告全文"] = full_text

            # 提取项目编号
            code_patterns = [
                r"项目编号[：:]\s*([A-Za-z0-9\-_]+)",
                r"编号[：:]\s*([A-Za-z0-9\-_]+)",
                r"([A-Z]-\d{4}-[A-Z]+-\w+)",
            ]
            for pattern in code_patterns:
                match = re.search(pattern, full_text)
                if match:
                    result["project_code"] = match.group(1)
                    break

            # 提取截止时间（扩展关键词列表）
            deadline = extract_date_after_keyword(
                full_text,
                [
                    "文件获取截止时间", "获取截止时间", "截止时间", "投标截止时间", "递交截止时间",
                    "招标文件获取", "获取结束", "文件获取结束", "获取时间",
                    "招标文件发售", "发售截止", "标书获取", "标书发售",
                ]
            )
            if deadline:
                result["文件获取截止时间"] = deadline

            # 提取状态
            if "正在招标" in full_text:
                result["status"] = "正在招标"
            elif "已经截止" in full_text:
                result["status"] = "已经截止"

            result["visit_url"] = detail_url

        except Exception as e:
            self._log_error(f"解析详情页失败: {e}")
        finally:
            page.close()

        return result
