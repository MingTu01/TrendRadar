# coding=utf-8
"""
GitHub Trending 爬虫

抓取 GitHub 热门项目，支持按编程语言筛选
"""

import re
import html
import requests
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import List, Optional

from trendradar.storage.base import RSSItem
from trendradar.utils.time import get_configured_time, DEFAULT_TIMEZONE


@dataclass
class GitHubTrendingItem:
    """GitHub Trending 项目"""
    name: str
    author: str
    description: str
    language: str
    stars: int
    forks: int
    stars_today: int
    url: str


class GitHubTrendingCrawler:
    """GitHub Trending 爬虫"""

    BASE_URL = "https://github.com/trending"

    def __init__(
        self,
        request_interval: int = 2000,
        timeout: int = 15,
        timezone: str = DEFAULT_TIMEZONE,
    ):
        self.request_interval = request_interval
        self.timeout = timeout
        self.timezone = timezone
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建请求会话"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "TrendRadar/2.0 GitHub Trending (https://github.com/trendradar)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return session

    def fetch_trending(
        self,
        language: Optional[str] = None,
        since: str = "daily",
    ) -> List[GitHubTrendingItem]:
        """
        获取 GitHub Trending 列表

        Args:
            language: 编程语言筛选（如 "Python", "TypeScript"，None 表示所有语言）
            since: 时间范围 ("daily", "weekly", "monthly")

        Returns:
            Trending 项目列表
        """
        url = self.BASE_URL
        if language:
            url = f"{self.BASE_URL}/{language}"
        if since != "daily":
            url += f"?since={since}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return self._parse_response(response.text)
        except requests.RequestException as e:
            print(f"[GitHub Trending] 请求失败: {e}")
            return []

    def fetch_all(
        self,
        languages: Optional[List[str]] = None,
    ) -> tuple:
        """
        获取多个语言的 Trending

        Args:
            languages: 语言列表，None 表示所有语言

        Returns:
            (items_dict, id_to_name, failed_ids) 元组
        """
        import time

        all_items = {}
        id_to_name = {}
        failed_ids = []

        feed_id = "github-trending"
        feed_name = "GitHub Trending"

        items = self.fetch_trending()
        if items:
            all_items[feed_id] = items
            id_to_name[feed_id] = feed_name
        else:
            failed_ids.append(feed_id)

        if languages:
            for lang in languages:
                time.sleep(self.request_interval / 1000)
                feed_id = f"github-trending-{lang.lower()}"
                feed_name = f"GitHub Trending - {lang}"
                items = self.fetch_trending(language=lang)
                if items:
                    all_items[feed_id] = items
                    id_to_name[feed_id] = feed_name
                else:
                    failed_ids.append(feed_id)

        total_items = sum(len(items) for items in all_items.values())
        print(f"[GitHub Trending] 抓取完成: {len(all_items)} 个源成功, {len(failed_ids)} 个失败, 共 {total_items} 个项目")

        return all_items, id_to_name, failed_ids

    def _parse_response(self, html_content: str) -> List[GitHubTrendingItem]:
        """解析 GitHub Trending 页面"""
        items = []

        article_pattern = r'<article class="Box-row">.*?</article>'
        for article_match in re.finditer(article_pattern, html_content, re.DOTALL):
            article_html = article_match.group(0)

            item = self._parse_article(article_html)
            if item:
                items.append(item)

        return items

    def _parse_article(self, article_html: str) -> Optional[GitHubTrendingItem]:
        """解析单个项目"""
        name_match = re.search(r'<a href="/([^/]+)/([^"]+)"[^>]*>\s*<span[^>]*>\s*([^<]+)\s*</span>', article_html)
        if not name_match:
            name_match = re.search(r'<h2[^>]*><a href="/([^/]+)/([^"]+)"[^>]*>([^<]+)</a>', article_html)

        if not name_match:
            return None

        author = name_match.group(1)
        repo_name = name_match.group(2)
        name = name_match.group(3).strip()

        url = f"https://github.com/{author}/{repo_name}"

        desc_match = re.search(r'<p[^>]*class="[^"]*color-fg-muted[^"]*"[^>]*>([^<]+)</p>', article_html)
        description = ""
        if desc_match:
            description = self._clean_html(desc_match.group(1))

        lang_match = re.search(r'<span[^>]*class="[^"]*text-([^"]*)"[^>]*>\s*<span[^>]*class="[^"]*d-inline-flex[^"]*"[^>]*>[^<]*</span>\s*([^<]+)</span>', article_html)
        language = ""
        if not lang_match:
            lang_match = re.search(r'<span[^>]*class="[^"]*color-fg-([^"]*)"[^>]*>([^<]+)</span>', article_html)
        if lang_match:
            language = lang_match.group(2).strip()

        stars_match = re.search(r'([\d,]+)\s*stars?', article_html)
        stars = int(stars_match.group(1).replace(",", "")) if stars_match else 0

        forks_match = re.search(r'([\d,]+)\s*forks?', article_html)
        forks = int(forks_match.group(1).replace(",", "")) if forks_match else 0

        today_match = re.search(r'([\d,]+)\s*stars today', article_html)
        stars_today = int(today_match.group(1).replace(",", "")) if today_match else 0

        return GitHubTrendingItem(
            name=name,
            author=author,
            description=description,
            language=language,
            stars=stars,
            forks=forks,
            stars_today=stars_today,
            url=url,
        )

    def _clean_html(self, text: str) -> str:
        """清理 HTML 实体"""
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def to_rss_items(self, items: List[GitHubTrendingItem], feed_id: str, feed_name: str) -> List[RSSItem]:
        """将 GitHub Trending 项目转换为 RSSItem"""
        now = get_configured_time(self.timezone)
        crawl_time = now.strftime("%H:%M")

        rss_items = []
        for item in items:
            summary = f"{item.description}" if item.description else ""
            if item.language:
                summary += f" | 语言: {item.language}"
            summary += f" | ⭐ {item.stars:,} | 🍴 {item.forks:,}"
            if item.stars_today > 0:
                summary += f" | +{item.stars_today} stars today"

            rss_item = RSSItem(
                title=f"{item.author}/{item.name}",
                feed_id=feed_id,
                feed_name=feed_name,
                url=item.url,
                published_at=now.isoformat(),
                summary=summary,
                author=item.author,
                crawl_time=crawl_time,
                first_time=crawl_time,
                last_time=crawl_time,
                count=1,
            )
            rss_items.append(rss_item)

        return rss_items


def from_config(config: dict) -> GitHubTrendingCrawler:
    """从配置创建爬虫"""
    return GitHubTrendingCrawler(
        request_interval=config.get("request_interval", 2000),
        timeout=config.get("timeout", 15),
        timezone=config.get("timezone", DEFAULT_TIMEZONE),
    )
