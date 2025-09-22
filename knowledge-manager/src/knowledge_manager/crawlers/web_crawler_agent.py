import logging
import os
import re
import random
import string
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import List, Optional
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from knowledge_manager.crawlers.web_crawler import fetch_webpage_as_markdown
from .prompts import FIND_NEXT_PAGE_SYSTEM_MSG

load_dotenv()

logger = logging.getLogger(__name__)


class NextPage(BaseModel):
    next_page_url: Optional[str] = Field(
        default=None,
        description="Absolute URL of the next page if pagination continues; None or '' if no next page.")
    confidence: Optional[int] = Field(
        default=None,
        ge=0,
        le=3,
        description="Model confidence (0 to 3) that next_page_url is correct.")


class Title(BaseModel):
    folder_title: str = Field(
        ..., min_length=1, max_length=60,
        description="Sanitized short folder title (letters and underscores only, 3-6 words ideally).")


def _random_slug(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.ascii_uppercase, k=length))


def _sanitize_folder_name(name: str) -> str:
    name = name.replace(' ', '_')
    name = re.sub(r'[^A-Za-z_]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if not name:
        name = _random_slug(6)
    return name[:60]


class WebCrawlerAgent:
    """Agent responsible for fetching one or multiple chained pages and organizing artifacts."""

    def __init__(self, base_output_dir: str = "data", model_name: str = "gemini-2.0-flash"):
        self.base_output_dir = base_output_dir
        self.link_finder_llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        self.title_llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    # --------------- LLM helpers ---------------
    def _find_next_link_llm(self, content: str, url: str) -> Optional[str]:
        logger.info("Invoking LLM to find next page URL...")
        result = self.link_finder_llm.with_structured_output(NextPage).invoke([
            ("system", FIND_NEXT_PAGE_SYSTEM_MSG),
            ("human", f"Page content:\n{content}\nCurrent URL: {url}"),
        ])
        logger.info(f"LLM next_page_url: {result.next_page_url}")
        sleep(5)  # To avoid rate limits
        return result.next_page_url.strip() or None if result.next_page_url else None

    def _generate_title(self, pages: List[str], first_url: str) -> str:
        sample = pages[0][:4000] if pages else ""
        system_msg = (
            "You will create a SHORT (3-6 words) descriptive folder title for fetched web content. "
            "Allowed characters: letters and underscores."
        )
        human = f"First URL: {first_url}\nContent sample (may be truncated):\n{sample}"
        try:
            result = self.title_llm.with_structured_output(Title).invoke([
                ("system", system_msg),
                ("human", human)
            ])
            sleep(5)  # To avoid rate limits
            raw_title = result.folder_title
        except Exception as e:  # noqa
            logger.error(f"Title generation failed: {e}; falling back to slug")
            raw_title = _random_slug(10)
        return _sanitize_folder_name(raw_title)

    # --------------- File helpers ---------------
    def _save_content(self, content: str, directory: Path, filename: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        logger.info(f"Saved data to {path}")
        return path

    def _create_run_dir(self) -> Path:
        base = Path(self.base_output_dir)
        base.mkdir(parents=True, exist_ok=True)
        slug = _random_slug()
        run_dir = base / f"run_{slug}"
        run_dir.mkdir()
        return run_dir

    def _rename_run_dir(self, run_dir: Path, new_name: str) -> Path:
        parent = run_dir.parent
        date_stamp = datetime.now().strftime("%Y_%m_%d")
        base_name = f"{new_name}_{date_stamp}" if not new_name.endswith(date_stamp) else new_name
        target = parent / base_name
        suffix = 1
        while target.exists():
            target = parent / f"{base_name}_{suffix}"
            suffix += 1
        try:
            run_dir.rename(target)
            return target
        except Exception as e:  # noqa
            logger.error(f"Could not rename directory ({e}); keeping original {run_dir}")
            return run_dir

    # --------------- Public API ---------------
    def fetch(self, start_url: str, crawl: bool = False) -> dict:
        """Fetch one page or crawl through paginated sequence.

        Returns metadata dict with keys: run_dir, pages (list[str]), fetched_paths (list[Path])
        """
        run_dir = self._create_run_dir()
        logger.info(f"Created run directory: {run_dir}")

        pages: List[str] = []
        fetched_paths: List[Path] = []

        if crawl:
            fetched_dir = run_dir / "fetched"
            url = start_url
            idx = 1
            logger.info(f"Starting crawl from: {start_url}")
            while url:
                content = asyncio.run(fetch_webpage_as_markdown(url))  
                page_path = self._save_content(content, fetched_dir, f"page_{idx}.md")
                fetched_paths.append(page_path)
                pages.append(content)
                next_url = self._find_next_link_llm(content, url)
                if next_url:
                    url = next_url
                    idx += 1
                else:
                    break
        else:
            logger.info(f"Fetching single page: {start_url}")
            content = asyncio.run(fetch_webpage_as_markdown(start_url))  
            page_path = self._save_content(content, run_dir, "raw.md")
            fetched_paths.append(page_path)
            pages.append(content)

        folder_title = self._generate_title(pages, start_url)
        logger.info(f"Generated folder title: {folder_title}")
        new_run_dir = self._rename_run_dir(run_dir, folder_title)
        if new_run_dir != run_dir:
            logger.info(f"Run directory renamed to: {new_run_dir}")
        run_dir = new_run_dir

        return {
            "run_dir": run_dir,
            "pages": pages,
            "fetched_paths": fetched_paths,
            "folder_title": folder_title,
        }
