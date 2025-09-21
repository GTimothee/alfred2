import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from langchain_google_genai import ChatGoogleGenerativeAI

from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
import argparse
from typing import Optional
from pathlib import Path

load_dotenv()

# Configure logging: write to root 'alfred.log' (append mode) and also console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("get_youtube_transcript.log", mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TranscriptResponse(BaseModel):
    title: str = Field(description="Give a one-line title to the transcript.")
    transcript: str = Field(description="The corrected transcript text.")

# ----------------- Utility Functions -----------------

def extract_video_id(youtube_url: str) -> Optional[str]:
    """Extract the 11-char YouTube video ID from various URL patterns."""
    # Try query param 'v'
    parsed = urlparse(youtube_url)
    qv = parse_qs(parsed.query).get("v", [])
    if qv and len(qv[0]) == 11:
        return qv[0]
    # Try common path forms
    candidates = [seg for seg in parsed.path.split('/') if seg]
    for seg in reversed(candidates):
        if len(seg) == 11:
            return seg
    # Fallback regex patterns
    patterns = [r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', r'youtu\.be\/([0-9A-Za-z_-]{11})']
    for pattern in patterns:
        m = re.search(pattern, youtube_url)
        if m:
            return m.group(1)
    return None

def get_transcript_from_url(youtube_url: str) -> str:
    """Retrieve full transcript text for the video or an error string."""
    vid = extract_video_id(youtube_url)
    if not vid:
        return "Error: Could not extract video ID from the URL."
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(vid)
        if transcript_list:
            logger.info(f"Fetched {len(transcript_list)} transcript segments for video {vid}.")
        return ''.join([item.text for item in transcript_list])
    except TranscriptsDisabled:
        return "Error: Transcripts are disabled for this video."
    except NoTranscriptFound:
        return "Error: No transcript could be found for this video."
    except Exception as e:  # noqa
        return f"An unexpected error occurred: {e}"

def correct_transcript(raw_text: str) -> TranscriptResponse:
    """Use LLM to clean / correct transcript formatting."""
    logger.info("Initializing model for transcript correction...")
    model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
    model = model.with_structured_output(TranscriptResponse)
    messages = [
        ("system", "You are a special agent analyst for the NSA. Our system retrieved partial information from a video. The video transcript you are given has lots of errors due to the technical limitations of our recording system. Understand the text and fix the errors. Add some line breaks and section titles, so that the document is actually readable."),
        ("human", "Transcript:\n\n" + raw_text),
    ]
    logger.info("Invoking correction model...")
    return model.invoke(messages)

def summarize_transcript(corrected: str) -> str:
    """Generate a summary for the corrected transcript."""
    logger.info("Initializing model for summary generation...")
    summary_model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
    summary_prompt = f"""
You are a technical analyst. Produce a crisp summary for an internal knowledge base about a technology-focused YouTube video.
Transcript (already cleaned/corrected):
{corrected}

Format EXACTLY like this:
<Headline: one or two lines capturing the core topic and value>
Summary:
- Core point 1
  - Key detail / insight
  - Key detail / insight
- Core point 2
  - Implementation / architecture / concept
- (Add only as many bullets as truly needed, no fluff)
If applicable, end with:
Key Takeaways:
- (3 to 5 ultra-concise bullets)
Do NOT add any extra explanatory text outside the structure.
"""
    summary_result = summary_model.invoke([
        ("system", "You produce precise hierarchical summaries for technical video transcripts. No verbosity."),
        ("human", summary_prompt),
    ])
    return getattr(summary_result, "content", str(summary_result))

def summarize_paragraphs(corrected: str, model_name: str = "gemini-2.0-flash") -> str:
    """Return a version of the transcript where each paragraph is replaced by a concise summary.

    Paragraph heuristic: split on two or more consecutive newlines. Ignore empty blocks.
    Each paragraph summary should be a single bullet beginning with '- ' capturing ONLY the
    essential point (who/what/how) in <= 25 words when possible. Preserve original order.

    Output format:
    Paragraph Summaries:\n
    - P1: <summary>\n
    - P2: <summary>\n
    ...
    """
    logger.info("Initializing model for per-paragraph summarization...")
    model = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    blocks = [b.strip() for b in re.split(r"\n{2,}", corrected) if b.strip()]
    if not blocks:
        return "Paragraph Summaries:\n- (No content)"

    summaries: list[str] = []
    system_msg = (
        "You distill individual transcript paragraphs into ultra-terse bullet summaries (<=25 words). "
        "Do not add numbering; keep any technical terms."
    )
    for idx, para in enumerate(blocks, start=1):
        prompt = f"Paragraph {idx}:\n{para}\n\nReturn ONLY one bullet summary (no numbering, begin with '- ')."
        try:
            resp = model.invoke([("system", system_msg), ("human", prompt)])
            content = getattr(resp, "content", str(resp)).strip()
            # Normalize to single line bullet
            first_line = content.splitlines()[0].strip()
            if not first_line.startswith("-"):
                first_line = "- " + first_line.lstrip('- ').strip()
            summaries.append(f"- P{idx}: " + first_line.lstrip('- ').strip())
        except Exception as e:  # noqa
            logger.error(f"Paragraph {idx} summarization failed: {e}")
            summaries.append(f"- P{idx}: (summary failed)")

    return "Paragraph Summaries:\n" + "\n".join(summaries)

# ----------------- Main Workflow -----------------

def process_video(url: str, force: bool = False, base_dir: str = "data/transcripts"):
    vid = extract_video_id(url)
    if not vid:
        logger.error("Could not extract video ID from URL.")
        raise ValueError("Invalid YouTube URL - cannot find video ID.")

    video_dir = os.path.join(base_dir, vid)
    os.makedirs(video_dir, exist_ok=True)

    original_path = os.path.join(video_dir, "original_transcript.md")
    corrected_path = os.path.join(video_dir, "corrected_transcript.md")
    summary_path = os.path.join(video_dir, "summary.md")
    paragraph_summary_path = os.path.join(video_dir, "paragraph_summaries.md")

    # Step 1: Fetch transcript (skip if exists unless force)
    if not force and os.path.isfile(original_path):
        logger.info(f"Skipping transcript fetch; exists: {original_path}")
        with open(original_path, "r", encoding="utf-8") as f:
            transcript = f.read()
    else:
        logger.info("Fetching transcript from YouTube API...")
        transcript = get_transcript_from_url(url)
        if transcript.startswith("Error:"):
            logger.error(transcript)
            return
        with open(original_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        logger.info(f"Transcript saved to {original_path}")

    # Step 2: Correct transcript (skip if exists unless force)
    if not force and os.path.isfile(corrected_path) and title_txt_in_dir(video_dir):
        logger.info(f"Skipping correction; exists: {corrected_path}")
        with open(corrected_path, "r", encoding="utf-8") as f:
            corrected = f.read()
    else:
        logger.info("Correcting transcript with LLM...")
        correction = correct_transcript(transcript)
        corrected = correction.transcript
        with open(corrected_path, "w", encoding="utf-8") as f:
            f.write(corrected)
        logger.info(f"Corrected transcript saved to {corrected_path}")
        
        logger.info("Saving title...")
        title_file_path = os.path.join(video_dir, "title_" + correction.title.replace(' ', '_') + ".txt")
        with open(title_file_path, "w", encoding="utf-8") as f:  # write the title so that we can find
            f.write(correction.title)

    # Step 2.5: Paragraph-level summaries (skip if exists unless force)
    if not force and os.path.isfile(paragraph_summary_path):
        logger.info(f"Skipping paragraph summaries; exists: {paragraph_summary_path}")
    else:
        logger.info("Generating paragraph-level summaries with LLM (each paragraph -> bullet)...")
        try:
            para_summaries = summarize_paragraphs(corrected)
            with open(paragraph_summary_path, "w", encoding="utf-8") as f:
                f.write(para_summaries)
            logger.info(f"Paragraph summaries saved to {paragraph_summary_path}")
        except Exception as e:  # noqa
            logger.error(f"Failed to generate paragraph summaries: {e}")

    # Step 3: Summarize (skip if exists unless force)
    if not force and os.path.isfile(summary_path):
        logger.info(f"Skipping summary; exists: {summary_path}")
    else:
        logger.info("Generating summary with LLM...")
        try:
            summary_text = summarize_transcript(corrected)
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
            logger.info(f"Summary saved to {summary_path}")
        except Exception as e:  # noqa
            logger.error(f"Failed to generate summary: {e}")

    logger.info("Processing complete.")


def title_txt_in_dir(video_dir: str | Path) -> bool:
    """
    Return True if there is at least one .txt file starting with 'title_' in video_dir.
    """
    video_path = Path(video_dir)
    if not video_path.is_dir():
        raise NotADirectoryError(f"{video_dir} is not a directory")

    # Look for any file matching the pattern title_*.txt
    return any(video_path.glob("title_*.txt"))


# ----------------- CLI Entry -----------------

def build_arg_parser():
    p = argparse.ArgumentParser(description="Fetch, correct, and summarize a YouTube transcript with caching.")
    p.add_argument("--url", required=True, help="YouTube video URL")
    p.add_argument("--force", action="store_true", help="Force regeneration of all artifacts")
    p.add_argument("--base-dir", default="data/transcripts", help="Base directory for storing outputs")
    return p

if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    process_video(args.url, force=args.force, base_dir=args.base_dir)