from crawl4ai import AsyncWebCrawler


async def fetch_webpage_as_markdown(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown
    