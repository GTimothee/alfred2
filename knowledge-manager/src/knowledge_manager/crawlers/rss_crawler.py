import feedparser
import json
from typing import List, Dict, Any
from datetime import datetime
from .base_crawler import BaseCrawler


class RSSCrawler(BaseCrawler):
    def __init__(self, rss_feeds: List[str] = None, limit: int = 5):
        self.rss_feeds = rss_feeds or [
            "https://eugeneyan.com/rss/",
            "https://www.philschmid.de/rss",
            "https://lilianweng.github.io/index.xml",
            "https://huggingface.co/blog/feed.xml",
            "https://www.llamaindex.ai/blog/feed",
            "https://blog.python.org/feeds/posts/default?alt=rss",
        ]
        self.limit = limit

    def fetch(self, rss_feeds: List[str] = None, limit: int = None) -> List[Dict[str, Any]]:
        feeds = rss_feeds or self.rss_feeds
        limit = limit if limit is not None else self.limit
        all_articles = []

        for rss_feed in feeds:
            print("---------------")
            print(f"Fetching articles from {rss_feed}...")
            try:
                feed = feedparser.parse(rss_feed)
                print(f"Fetched {len(feed.entries)} entries.")

                # Extract articles
                articles = [
                    {
                        "crawler_name": "RSSCrawler",
                        "rss_feed": rss_feed,
                        "fetched_at": datetime.now().isoformat(),
                        "title": entry.title,
                        "link": entry.link,
                        "summary": entry.get("summary", ""),
                    }
                    for entry in feed.entries[:limit]
                ]

                if not articles:
                    print(f"No articles found in the RSS feed: {rss_feed}")
                else:
                    all_articles.extend(articles)

            except Exception as e:
                print(f"An error occurred while fetching the RSS feed from {rss_feed}: {e}")

        if not all_articles:
            print("No articles were fetched from any of the provided RSS feeds.")
        return all_articles

    def save(self, data: List[Dict[str, Any]], output_filepath: str) -> None:
        try:
            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"Data saved to {output_filepath}")
        except Exception as e:
            print(f"An error occurred while saving data to {output_filepath}: {e}")

    def load(self, input_filepath: str) -> List[Dict[str, Any]]:
        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            print(f"File {input_filepath} not found.")
            return []
        except Exception as e:
            print(f"An error occurred while loading data from {input_filepath}: {e}")
            return []

    def run(self):
        articles = self.fetch()
        if articles:
            self.save(articles, "store/agent_articles.json")
            for article in articles[: self.limit]:
                print(f"Title: {article['title']}")
                print(f"Link: {article['link']}")
                print(f"Fetched At: {article['fetched_at']}")
                print(f"RSS Feed: {article['rss_feed']}")
                print()
        else:
            print("No articles to display.")
