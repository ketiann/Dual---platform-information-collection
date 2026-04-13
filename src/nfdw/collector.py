# -*- coding: utf-8 -*-
"""
NFDW信息采集工具 - 基于Playwright浏览器自动化的爬虫
数据源：南方电网招标网站 (bidding.csg.cn)
采集内容：招标公告 + 零星采购公告

注意：该网站有WAF防护，直接HTTP请求会被拦截，需使用浏览器自动化
"""
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

from config.settings import NFDW_CONFIG, GENERAL
from common.utils import (
    clean_text, clean_text_preserve_format, parse_date, extract_date_after_keyword,
    parse_nfdw_project_name, make_unique_key, is_after_date,
)
from common.zhipu_client import ZhipuAIClient


class NFDWCollector:
    """NFDW信息采集器"""

    def __init__(self, headless: bool = True, logger=None):
        self.headless = headless
        self.logger = logger
        self.zhipu = ZhipuAIClient()
        self.collected_data = []

    def _log(self, msg: str):
        if self.logger:
            self.logger.info(f"[NFDW] {msg}")
        else:
            print(f"[NFDW] {msg}")

    def _log_error(self, msg: str):
        if self.logger:
            self.logger.error(f"[NFDW] {msg}")
        else:
            print(f"[NFDW ERROR] {msg}")

    def run(self, existing_keys: set = None) -> list[dict]:
        """
        执行NFDW全量采集
        existing_keys: 已有数据的唯一键集合（用于去重）
        返回: 新采集的数据列表
        """
        if existing_keys is None:
            existing_keys = set()

        self.collected_data = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
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
                for source in NFDW_CONFIG["sources"]:
                    self._log(f"开始采集: {source['name']}")
                    self._collect_from_source(context, source, existing_keys)
            finally:
                browser.close()

        self._log(f"采集完成，共获取 {len(self.collected_data)} 条数据")
        return self.collected_data

    def _collect_from_source(self, context: BrowserContext, source: dict, existing_keys: set):
        """从单个数据源采集数据"""
        base_url = source["base_url"]
        list_url = source["url"]

        page = context.new_page()

        # 逐页采集
        page_num = 1
        max_pages = 100
        no_new_data_pages = 0
        max_no_new_pages = 5

        while page_num <= max_pages:
            # 构建分页URL
            if page_num == 1:
                url = list_url
            else:
                url = list_url.replace("index.jhtml", f"index_{page_num}.jhtml")

            self._log(f"  采集第 {page_num} 页: {url}")

            # 请求列表页
            html = self._request_page(page, url)
            if not html:
                self._log_error(f"  第 {page_num} 页请求失败，跳过")
                break

            # 检查是否被WAF拦截
            if "安全威胁" in html or "访问请求" in html:
                self._log_error("  被WAF拦截，等待后重试...")
                time.sleep(10)
                html = self._request_page(page, url)
                if not html or "安全威胁" in html:
                    self._log_error("  WAF拦截无法绕过，跳过此数据源")
                    break

            # 解析列表
            items = self._parse_list_page(html, source)
            if not items:
                self._log(f"  第 {page_num} 页无数据，停止翻页")
                break

            page_new_count = 0

            for item in items:
                try:
                    # 筛选：剔除零星采购澄清公告
                    notice_type = item.get("notice_type", "")
                    if any(exclude in notice_type for exclude in NFDW_CONFIG["exclude_types"]):
                        continue

                    # 筛选：日期过滤
                    create_time = item.get("create_time", "")
                    if create_time and not is_after_date(create_time, NFDW_CONFIG["start_date"]):
                        continue

                    # 去重检查
                    unique_key = make_unique_key(item.get("project_code", ""), item.get("visit_url", ""))
                    if unique_key in existing_keys:
                        continue

                    # 获取详情页内容
                    detail_url = item.get("detail_url", "")
                    if detail_url:
                        detail_page = context.new_page()
                        detail_html = self._request_page(detail_page, detail_url)
                        if detail_html:
                            detail_data = self._parse_detail_page(detail_html, source)
                            item.update(detail_data)
                        detail_page.close()
                        time.sleep(NFDW_CONFIG["detail_interval"])

                    # 解析项目名称
                    project_name = item.get("project_name", "")
                    name_parts = parse_nfdw_project_name(project_name)
                    item["单位"] = name_parts["单位"]
                    item["项目简称"] = name_parts["项目简称"]

                    # 如果正则解析失败，使用AI辅助
                    if not item["单位"]:
                        try:
                            ai_result = self.zhipu.parse_project_name(project_name, "nfdw")
                            item["单位"] = ai_result.get("单位", "")
                            item["项目简称"] = ai_result.get("项目简称", project_name)
                        except Exception:
                            pass

                    # 计算项目状态
                    deadline = item.get("文件获取截止时间", "")
                    if deadline:
                        try:
                            deadline_dt = datetime.strptime(deadline[:19], "%Y-%m-%d %H:%M:%S")
                            item["项目状态"] = "进行中" if datetime.now() < deadline_dt else "已截止"
                        except ValueError:
                            item["项目状态"] = "进行中"
                    else:
                        item["项目状态"] = "进行中"

                    # 设置固定字段
                    item["公告类型"] = source["type"]
                    item["数据来源"] = source["type"]

                    # 清洗文本
                    if item.get("项目名称"):
                        item["项目名称"] = clean_text(item["项目名称"])
                    if item.get("公告全文"):
                        item["公告全文"] = clean_text_preserve_format(item["公告全文"])

                    # 标准化日期格式
                    for key in ["创建时间", "文件获取截止时间"]:
                        if key in item and item[key]:
                            parsed = parse_date(str(item[key]))
                            if parsed:
                                item[key] = parsed

                    # 如果截止时间未获取，使用AI提取
                    if not item.get("文件获取截止时间") and item.get("公告全文"):
                        try:
                            ai_fields = self.zhipu.extract_fields_from_content(
                                item["公告全文"][:2000],
                                ["文件获取截止时间", "发布时间"]
                            )
                            if ai_fields.get("文件获取截止时间"):
                                parsed = parse_date(ai_fields["文件获取截止时间"])
                                if parsed:
                                    item["文件获取截止时间"] = parsed
                            if ai_fields.get("发布时间") and not item.get("创建时间"):
                                parsed = parse_date(ai_fields["发布时间"])
                                if parsed:
                                    item["创建时间"] = parsed
                        except Exception:
                            pass

                    # 构建最终记录
                    record = {
                        "项目名称": item.get("project_name", ""),
                        "单位": item.get("单位", ""),
                        "项目简称": item.get("项目简称", ""),
                        "项目编号": item.get("project_code", ""),
                        "公告类型": item.get("公告类型", ""),
                        "项目状态": item.get("项目状态", ""),
                        "创建时间": item.get("create_time", ""),
                        "文件获取截止时间": item.get("文件获取截止时间", ""),
                        "访问链接": item.get("visit_url", ""),
                        "公告全文": item.get("公告全文", ""),
                        "数据来源": item.get("数据来源", ""),
                    }

                    # 最终去重
                    final_key = make_unique_key(record["项目编号"], record["访问链接"])
                    if final_key not in existing_keys:
                        existing_keys.add(final_key)
                        self.collected_data.append(record)
                        page_new_count += 1
                        self._log(f"    新增: {record['项目名称'][:50]}...")

                except Exception as e:
                    self._log_error(f"    处理列表项失败: {e}")
                    continue

            self._log(f"  第 {page_num} 页新增 {page_new_count} 条数据")

            # 判断是否继续翻页
            if page_new_count == 0:
                no_new_data_pages += 1
                if no_new_data_pages >= max_no_new_pages:
                    self._log(f"  连续 {max_no_new_pages} 页无新数据，停止翻页")
                    break
            else:
                no_new_data_pages = 0

            # 检查是否还有下一页
            if not self._has_next_page(html):
                self._log("  已到最后一页，停止翻页")
                break

            page_num += 1
            time.sleep(NFDW_CONFIG["request_interval"])

        page.close()

    def _request_page(self, page: Page, url: str) -> Optional[str]:
        """使用Playwright请求页面"""
        max_retries = GENERAL["max_retries"]
        for attempt in range(max_retries):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                html = page.content()
                if html and len(html) > 500:
                    return html
                else:
                    self._log_error(f"  页面内容为空 (尝试 {attempt + 1}/{max_retries})")
            except Exception as e:
                self._log_error(f"  页面请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(GENERAL["retry_interval"])
        return None

    def _parse_list_page(self, html: str, source: dict) -> list[dict]:
        """解析列表页HTML"""
        items = []
        base_url = source["base_url"]
        soup = BeautifulSoup(html, "html.parser")

        # 策略1: 查找class="list"的ul
        list_container = soup.find("ul", class_="list")
        if not list_container:
            # 策略2: 查找包含数字ID链接的ul（数据列表特征）
            for ul in soup.find_all("ul"):
                direct_lis = ul.find_all("li", recursive=False)
                if len(direct_lis) >= 5:
                    # 检查是否包含详情链接（如 /zbgg/1200426431.jhtml）
                    has_detail_links = False
                    for li in direct_lis:
                        for a in li.find_all("a", href=True):
                            if re.search(r"/\d+\.jhtml", a.get("href", "")):
                                has_detail_links = True
                                break
                        if has_detail_links:
                            break
                    if has_detail_links:
                        list_container = ul
                        break

        if not list_container:
            # 策略3: 查找class包含list的div
            list_container = soup.find("div", class_=re.compile(r"list", re.I))

        if not list_container:
            self._log_error("  未找到列表容器")
            return items

        # 获取直接子li元素
        all_lis = list_container.find_all("li", recursive=False)
        if not all_lis:
            all_lis = list_container.find_all("li")

        for li in all_lis:
            try:
                item = {}
                links = li.find_all("a")

                # 查找详情链接（包含数字.jhtml的链接，如 /zbgg/1200426431.jhtml）
                detail_link = None
                for link in links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    # 详情链接特征：路径中包含数字ID
                    if re.search(r"/\d+\.jhtml", href) and text and len(text) > 5:
                        detail_link = link
                        break

                if not detail_link:
                    # 备选：任何包含.jhtml的非导航链接
                    for link in links:
                        href = link.get("href", "")
                        text = link.get_text(strip=True)
                        if ".jhtml" in href and text and len(text) > 10:
                            # 排除导航链接（index.jhtml等）
                            if "index" not in href:
                                detail_link = link
                                break

                if detail_link:
                    href = detail_link.get("href", "")
                    text = detail_link.get_text(strip=True)
                    item["project_name"] = text

                    if href.startswith("/"):
                        item["detail_url"] = base_url + href
                    elif href.startswith("http"):
                        item["detail_url"] = href
                    else:
                        item["detail_url"] = base_url + "/" + href
                    item["visit_url"] = item["detail_url"]
                else:
                    continue

                # 提取日期
                date_span = li.find("span", class_="Gray")
                if not date_span:
                    date_span = li.find("span", class_=re.compile(r"date|time|gray", re.I))
                if date_span:
                    date_text = date_span.get_text(strip=True)
                    item["create_time"] = date_text
                else:
                    full_text = li.get_text()
                    date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", full_text)
                    if date_match:
                        item["create_time"] = date_match.group(1)

                # 提取公告类型（从非详情链接中）
                for link in links:
                    link_text = link.get_text(strip=True)
                    if link_text in ["招标公告", "采购公告", "零星采购公告", "零星采购澄清公告"]:
                        item["notice_type"] = link_text
                        break

                items.append(item)
            except Exception as e:
                self._log_error(f"    解析列表项失败: {e}")
                continue

        return items

    def _parse_detail_page(self, html: str, source: dict) -> dict:
        """解析详情页HTML"""
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # 提取正文内容
        content_div = soup.find("div", class_="content")
        if not content_div:
            content_div = soup.find("div", class_=re.compile(r"content|article|detail|text|news", re.I))
        if not content_div:
            content_div = soup.find("div", id=re.compile(r"content|article|detail|newsbody", re.I))

        if content_div:
            result["公告全文"] = content_div.get_text(separator="\n", strip=True)
        else:
            body = soup.find("body")
            if body:
                # 移除script和style标签
                for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                result["公告全文"] = body.get_text(separator="\n", strip=True)
            else:
                result["公告全文"] = ""

        full_text = result.get("公告全文", "")

        # 提取项目编号
        code_patterns = [
            r"编号[：:]\s*([A-Za-z0-9\-_]+)",
            r"项目编号[：:]\s*([A-Za-z0-9\-_]+)",
            r"采购编号[：:]\s*([A-Za-z0-9\-_]+)",
            r"招标编号[：:]\s*([A-Za-z0-9\-_]+)",
        ]
        for pattern in code_patterns:
            match = re.search(pattern, full_text)
            if match:
                result["project_code"] = match.group(1).strip()
                break

        # 提取发布时间 - 优先从标题下方的发布时间行提取
        publish_time = None
        if content_div:
            # 在content_div中查找包含"发布时间"或"发布日期"的元素
            for tag in content_div.find_all(["p", "span", "div"]):
                tag_text = tag.get_text(strip=True)
                if re.search(r"发布时间|发布日期", tag_text):
                    # 提取该元素中的日期
                    date_match = re.search(
                        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]?\d{1,2}:\d{1,2}(:\d{1,2})?|\d{4}年\d{1,2}月\d{1,2}日)",
                        tag_text
                    )
                    if date_match:
                        parsed = parse_date(date_match.group(1))
                        if parsed:
                            publish_time = parsed
                            break

        # 备选：从全文中搜索发布时间
        if not publish_time:
            publish_time = extract_date_after_keyword(full_text, ["发布时间", "发布日期", "发布时间："])
        if publish_time:
            result["create_time"] = publish_time

        # 提取截止时间 - 扩充关键词列表
        deadline = extract_date_after_keyword(
            full_text,
            ["获取结束时间：", "获取结束时间", "截止时间：", "截止时间",
             "文件获取截止时间", "投标截止时间", "递交截止时间",
             "获取结束", "文件获取结束", "获取时间",
             "招标文件发售", "发售截止", "标书获取", "标书发售",
             "招标文件获取结束", "文件获取结束时间", "招标文件获取结束",
             "标书发售截止", "采购文件获取", "采购文件发售",
             "应答截止", "响应截止"]
        )
        if deadline:
            result["文件获取截止时间"] = deadline

        # 公告全文内容裁剪 - 移除不需要的章节
        trim_patterns = [
            r"2\.3[\s\.]*招标项目所在地区",
            r"2\.4[\s\.]*资格审查方式",
            r"2\.5[\s\.]*招标分类",
            r"2\.6[\s\.]*标的清单及分包情况",
            r"3\.[\s\.]*投标人资格要求",
        ]
        earliest_pos = len(full_text)
        for pattern in trim_patterns:
            match = re.search(pattern, full_text)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()
        if earliest_pos < len(full_text):
            result["公告全文"] = full_text[:earliest_pos].strip()

        return result

    def _has_next_page(self, html: str) -> bool:
        """检查是否有下一页"""
        if "下一页" not in html:
            return False

        soup = BeautifulSoup(html, "html.parser")
        next_links = soup.find_all("a", string=re.compile(r"下一页"))
        for link in next_links:
            href = link.get("href", "")
            if href and "javascript" not in href.lower():
                return True
        return False
