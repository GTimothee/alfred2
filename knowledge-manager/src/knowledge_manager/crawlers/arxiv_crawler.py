import json
import feedparser
from typing import List, Dict, Any
from datetime import datetime
from .base_crawler import BaseCrawler


class ArxivCrawler(BaseCrawler):
    def __init__(self, limit: int = 10):
        self.limit = limit

    def fetch(self, query: str, limit: int = None) -> List[Dict[str, Any]]:
        """Fetches arxiv entries based on a query."""
        if limit is None:
            limit = self.limit
        print(f"Fetching arxiv with query={query}...")
        feed = feedparser.parse(
            f'http://export.arxiv.org/api/query?search_query={query}&max_results={limit}&sortBy=lastUpdatedDate&sortOrder=descending'
        )

        if feed.bozo:
            print("Error fetching arxiv feed.")
            entries = []
        else:
            print(f"Fetched {len(feed.entries)} entries.")
            entries = [
                {
                    "crawler_name": "ArxivCrawler",
                    "query": query,
                    "fetched_at": datetime.now().isoformat(),
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "updated": entry.get("updated", ""),
                    "summary": entry.get("summary", ""),
                    "author": entry.get("author", ""),
                    "category": [tag['term'] for tag in entry.get('tags', [])] if 'tags' in entry else [],
                }
                for entry in feed.entries
            ]
        return entries

    def save(self, data: List[Dict[str, Any]], output_filepath: str) -> None:
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {output_filepath}")

    def load(self, input_filepath: str) -> List[Dict[str, Any]]:
        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"File {input_filepath} not found.")
            data = []
        return data

    def run(self):
        for query in ["llm", "agents", "RAG"]:
            entries = self.fetch(query=query)
            self.save(entries, f"store/arxiv_{query}.json")
