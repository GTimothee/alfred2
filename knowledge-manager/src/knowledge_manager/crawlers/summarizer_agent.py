import logging
from pathlib import Path
from time import sleep
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from .prompts import SUMMARIZATION_PROMPT

logger = logging.getLogger(__name__)


class Summary(BaseModel):
    summary: str = Field(
        ...,
        description="The summarized content of the web page."
    )

class SummarizerAgent:
    """Agent to summarize fetched pages and persist per-page & combined summaries."""

    def __init__(self, model_name: str = "gemini-2.5-pro", delay_seconds: int = 5):
        self.model_name = model_name
        self.delay_seconds = delay_seconds
        self.model = ChatGoogleGenerativeAI(model=model_name, temperature=0).with_structured_output(Summary)

    def summarize(self, pages: List[str], summary_dir: Path) -> Path:
        summary_dir.mkdir(parents=True, exist_ok=True)
        summaries = []
        for idx, page in enumerate(pages, start=1):
            prompt = f"Summarize the following web page (page {idx} of {len(pages)}):\n{page}"
            messages = [
                ("system", SUMMARIZATION_PROMPT),
                ("human", prompt),
            ]
            try:
                result = self.model.invoke(messages)
                summary_text = result.summary
            except Exception as e:  # noqa
                logger.error(f"Summary generation failed for page {idx}: {e}")
                summary_text = f"(Error summarizing page {idx}: {e})"
            summaries.append(summary_text)
            per_page_path = summary_dir / f"page_{idx}_summary.md"
            per_page_path.write_text(summary_text, encoding="utf-8")
            logger.info(f"Saved summary for page {idx} to {per_page_path}")
            logger.info(f"Waiting {self.delay_seconds} seconds before next summary to avoid rate limits...")
            sleep(self.delay_seconds)

        combined = "\n\n".join([f"# Page {i+1} Summary\n{txt}" for i, txt in enumerate(summaries)])
        combined_path = summary_dir / "combined_summary.md"
        combined_path.write_text(combined, encoding="utf-8")
        logger.info(f"Combined summary saved to {combined_path}")
        return combined_path
