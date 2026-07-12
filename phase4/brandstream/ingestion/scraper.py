import os
import urllib.request
import re
import logging
from typing import Optional, Any

logger = logging.getLogger("BrandStream.Scraper")

class CompetitorScraper:
    def __init__(self, memory_engine: Any, model_router: Optional[Any] = None, budget_manager: Optional[Any] = None):
        self.memory_engine = memory_engine
        self.model_router = model_router
        self.budget_manager = budget_manager

    def scrape(self, url: str, name: str) -> str:
        """
        Scrapes a URL. If the page is fetched successfully, it extracts text content.
        If offline or request fails, falls back to a structural mock markdown.
        Saves research markdown to MemoryEngine under research/{name}.md.
        """
        html_content = ""
        try:
            # Attempt a real network fetch
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                html_content = response.read().decode('utf-8', errors='ignore')
            logger.info(f"Successfully scraped content from {url}")
            
            # Simple regex parser to get body text and headers
            title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else f"Scraped Page: {name}"
            
            # Extract basic text content by removing scripts/styles and tags
            # Remove scripts & styles
            clean_html = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
            # Find all visible headings and paragraphs
            elements = re.findall(r"<(h1|h2|h3|p)>(.*?)</\1>", clean_html, re.DOTALL | re.IGNORECASE)
            
            markdown_lines = [f"# {title}", f"Source URL: {url}", ""]
            for tag, text in elements:
                clean_text = re.sub(r"<.*?>", "", text).strip()
                clean_text = re.sub(r"\s+", " ", clean_text)
                if not clean_text:
                    continue
                if tag.startswith("h"):
                    level = int(tag[1])
                    markdown_lines.append(f"{'#' * level} {clean_text}\n")
                else:
                    markdown_lines.append(f"{clean_text}\n")
            
            markdown_content = "\n".join(markdown_lines)
            if not elements:
                # If we got html but couldn't parse structured tags, just dump cleaned body
                body_text = re.sub(r"<.*?>", "", clean_html)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                markdown_content = f"# {title}\nSource URL: {url}\n\n{body_text[:2000]}"
                
        except Exception as e:
            logger.warning(f"Failed to fetch {url} due to {e}. Using structural mock markdown instead.")
            # Fallback to structural mock markdown
            markdown_content = self._get_mock_markdown(url, name)
            
        # Save to MemoryEngine-backed workspace
        filepath = f"research/{name}.md"
        self.memory_engine.write_file_sync(filepath, markdown_content)
        logger.info(f"Saved research markdown to {filepath}")
        return markdown_content

    def _get_mock_markdown(self, url: str, name: str) -> str:
        return f"""# Competitor Research: {name.capitalize()}
Source URL: {url}

## Overview
This is a mock scraped profile for {name}. They focus on high-conversion social media ads and short-video campaigns.

## Core Offerings
- Premium visual styling with GSAP animations.
- Dynamic localized translations across European regions.
- Structured product catalog listings via clean Excel templates.

## Key Performance Claims
- 35% higher engagement on vertically oriented narrative scripts.
- Budget optimization using runaway loop detection thresholds.
- Absolute compliance verified through chess-based simulation logic.

## Competitor Strategy Tags
- Banned terms: "guaranteed success", "cheapest price ever", "100% risk free"
- Style reference: split screen, spatial coordinates layout [0.1, 0.2, 0.8, 0.4]
"""
