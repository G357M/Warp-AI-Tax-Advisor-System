"""
Scrapling-powered extraction helpers for repair/audit/fallback flows.

This module does NOT replace the current ingestion pipeline.
It adds a safer pilot path that can:
- fetch a page with the existing aiohttp-based scraper stack
- parse/extract content through Scrapling's selector engine
- provide cleaner targeted extraction for difficult pages

The intended use cases are:
- repair extraction for suspicious/incomplete documents
- audit comparisons between source page and normalized corpus
- fallback extraction for pages where the current parser is noisy
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from scraper.base_scraper import BaseScraper
from core.time_utils import utc_now

logger = logging.getLogger(__name__)

try:
    from scrapling.parser import Selector
except Exception:  # pragma: no cover - dependency may be optional until installed
    Selector = None  # type: ignore


class ScraplingScraper(BaseScraper):
    """Pilot extractor using Scrapling as a parsing/extraction layer."""

    def __init__(self, adaptive: bool = True):
        super().__init__(base_url="https://infohub.rs.ge")
        self.adaptive = adaptive

    def _require_scrapling(self) -> None:
        if Selector is None:
            raise RuntimeError(
                "Scrapling is not installed in this environment. "
                "Install the backend requirements with scrapling enabled first."
            )

    def _build_selector(self, html: str):
        self._require_scrapling()
        return Selector(
            html,
            adaptive=self.adaptive,
            huge_tree=True,
            keep_comments=False,
            keep_cdata=False,
        )

    def extract_from_html(self, html: str, url: str) -> Dict[str, Any]:
        page = self._build_selector(html)

        title = ""
        try:
            title = page.css("h1::text").get() or page.css("title::text").get() or ""
        except Exception:
            title = ""

        main_html = ""
        main_text = ""
        extraction_mode = "body_fallback"

        selectors = [
            "main",
            "article",
            ".content",
            "#content",
            ".document-content",
            ".workspace-document",
            ".ProseMirror",
            ".ql-editor",
            "body",
        ]

        for css in selectors:
            try:
                nodes = page.css(css)
            except Exception:
                continue
            if not nodes:
                continue
            node = nodes[0]
            try:
                html_candidate = node.html_content or ""
                text_candidate = node.get_all_text(ignore_tags=("script", "style", "noscript")) or ""
            except Exception:
                continue
            text_candidate = self.clean_text(text_candidate)
            if len(text_candidate) < 200:
                continue
            main_html = html_candidate
            main_text = text_candidate
            extraction_mode = css
            break

        return {
            "url": url,
            "title": self.clean_text(title),
            "extraction_mode": extraction_mode,
            "scraped_at": utc_now().isoformat(),
            "content_length": len(main_text),
            "html": main_html,
            "text": main_text,
        }

    async def extract_url(self, url: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            html = await self.fetch_page(url, session)
        if not html:
            raise RuntimeError(f"Failed to fetch {url}")
        return self.extract_from_html(html, url)


async def probe_url(url: str, adaptive: bool = True) -> Dict[str, Any]:
    scraper = ScraplingScraper(adaptive=adaptive)
    return await scraper.extract_url(url)


def probe_url_sync(url: str, adaptive: bool = True) -> Dict[str, Any]:
    return asyncio.run(probe_url(url, adaptive=adaptive))
