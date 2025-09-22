
import argparse
import logging
from pathlib import Path
import csv
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from knowledge_manager.crawlers.web_crawler_agent import WebCrawlerAgent
from knowledge_manager.crawlers.summarizer_agent import SummarizerAgent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("web_crawler_agent.log", mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main(start_url: str, crawl: bool = False, summarize: bool | None = None):
    crawler = WebCrawlerAgent()
    result = crawler.fetch(start_url=start_url, crawl=crawl)
    run_dir: Path = result["run_dir"]

    if summarize is None:
        resp = input("Fetching done. Launch summarization? (y/n): ").strip().lower()
        summarize = resp == 'y'

    if summarize:
        summarizer = SummarizerAgent()
        summaries_dir = run_dir / "summaries"
        combined_path = summarizer.summarize(result["pages"], summaries_dir)
        # Also write a plain summary.txt with combined content
        summary_txt = run_dir / "summary.txt"
        summary_txt.write_text(combined_path.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info(f"Summary saved to {summary_txt}")
    else:
        logger.info("Summarization skipped.")

    logger.info(f"Artifacts available in: {run_dir}")


def process_csv(csv_path: Path, summarize: Optional[bool]):
    """Batch mode: fetch ALL entries first, then optionally summarize ALL."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    crawler = WebCrawlerAgent()
    rows: list[tuple[str, bool]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader, None)
        for line_num, row in enumerate(reader, start=2):
            if not row or len(row) < 1:
                continue
            url = row[0].strip()
            crawl_flag = False
            if len(row) > 1:
                val = row[1].strip().lower()
                crawl_flag = val in {"true", "1", "yes", "y"}
            rows.append((url, crawl_flag))

    logger.info(f"[CSV] Loaded {len(rows)} entries. Starting fetch phase...")
    run_results: list[dict] = []
    for url, crawl_flag in rows:
        logger.info(f"[CSV][FETCH] URL={url} crawl={crawl_flag}")
        result = crawler.fetch(start_url=url, crawl=crawl_flag)
        run_results.append(result)
        logger.info(f"[CSV][FETCH] Done: {result['run_dir']}")

    # Decide summarization once for all runs
    do_summary = summarize
    if do_summary is None:
        resp = input("All fetches complete. Summarize ALL runs now? (y/n): ").strip().lower()
        do_summary = resp == 'y'

    if not do_summary:
        logger.info("Batch summarization skipped.")
        return

    summarizer = SummarizerAgent()
    logger.info("Starting batch summarization phase...")
    for result in run_results:
        run_dir: Path = result['run_dir']
        summaries_dir = run_dir / "summaries"
        combined_path = summarizer.summarize(result['pages'], summaries_dir)
        summary_txt = run_dir / "summary.txt"
        summary_txt.write_text(combined_path.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info(f"[CSV][SUMMARY] Saved summary: {summary_txt}")
    logger.info("Batch summarization complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl web pages and (optionally) summarize after fetching.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Starting URL (single run)")
    group.add_argument("--csv", help="Path to CSV file with 'url; crawl' rows")
    parser.add_argument("--crawl", action="store_true", help="Automatically crawl pagination using an LLM.")
    parser.add_argument("--no-summary", action="store_true", help="Skip summarization without prompting.")
    parser.add_argument("--summary", action="store_true", help="Force summarization without prompting.")
    args = parser.parse_args()

    summarize_flag = None
    if args.no_summary:
        summarize_flag = False
    elif args.summary:
        summarize_flag = True

    if args.csv:
        process_csv(Path(args.csv), summarize_flag)
    else:
        main(args.url, crawl=args.crawl, summarize=summarize_flag)