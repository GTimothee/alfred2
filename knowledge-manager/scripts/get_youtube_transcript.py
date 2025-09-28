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
import time

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

# ----------------- Quota / Retry Helpers -----------------
def _parse_retry_delay_seconds(msg: str) -> float:
    import re
    m = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return 10.0
    return 10.0

def invoke_with_retry(model, messages, max_retries: int = 5, base_delay: float = 2.0):
    for attempt in range(1, max_retries + 1):
        try:
            return model.invoke(messages)
        except Exception as e:  # noqa
            emsg = str(e)
            if "Quota exceeded" in emsg or "rate limit" in emsg.lower():
                delay = _parse_retry_delay_seconds(emsg)
            else:
                delay = base_delay * attempt
            if attempt == max_retries:
                logging.error(f"Max retries reached. Failing. Last error: {emsg}")
                raise
            logging.warning(f"Model call failed (attempt {attempt}/{max_retries}): {emsg} -> sleeping {delay:.1f}s")
            time.sleep(delay)

# ----------------- Chunking & Correction Helpers -----------------

def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Split transcript into chunks not exceeding max_chars by grouping paragraphs.
    Paragraph = separated by two or more newlines. Falls back to raw slicing if needed.
    """
    if len(text) <= max_chars:
        return [text]
    
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        add_len = len(para) + 2  # account for joins
        if current and current_len + add_len > max_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += add_len
    if current:
        chunks.append("\n\n".join(current))

    # Fallback slicing if any chunk still too large (very long paragraph)
    final: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final.append(c)
        else:
            # hard slice
            for i in range(0, len(c), max_chars):
                final.append(c[i:i+max_chars])
    return final

# New helper to format chunk diagnostics
def _describe_chunks(chunks: list[str]) -> str:
    sizes = [len(c) for c in chunks]
    return " | ".join(f"{i+1}:{sz}" for i, sz in enumerate(sizes))

def generate_title(corrected_full: str) -> str:
    """
    Generate a single concise title for the full corrected transcript.
    """
    try:
        model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        prompt = (
            "You will receive a corrected transcript of a technical / informational video. "
            "Return ONLY a single concise title (max ~12 words). No quotes, no punctuation at end.\n\n"
            f"Transcript:\n{corrected_full[:25000]}"  # safety truncation
        )
        resp = model.invoke([
            ("system", "Generate only a terse, human-friendly title."),
            ("human", prompt),
        ])
        content = getattr(resp, "content", str(resp)).strip()
        # One line only
        return content.splitlines()[0][:120]
    except Exception as e:  # noqa
        logger.error(f"Title generation failed: {e}")
        return "Transcript"

def correct_transcript(raw_text: str, model_name: str = "gemini-2.0-flash") -> TranscriptResponse:
    """
    Chunk large transcripts and correct each chunk individually to mitigate API length/rate issues.
    Aggregates corrected chunks and generates a unified title.
    """
    logger.info("Initializing model for transcript correction...")
    model = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    model = model.with_structured_output(TranscriptResponse)
    messages = [
        ("system", "You are a special agent analyst for the NSA. Our system retrieved partial information from a video. The video transcript you are given has lots of errors due to the technical limitations of our recording system. Understand the text and fix the errors. Add some line breaks and section titles, so that the document is actually readable."),
        ("human", "Transcript:\n\n" + raw_text),
    ]
    logger.info("Invoking correction model (with retry)...")
    return invoke_with_retry(model, messages)

def correct_transcript_chunked(raw_text: str, chunk_size: int, model_name: str = "gemini-2.0-flash", per_chunk_sleep: float = 0.0, log_chunks: bool = False) -> TranscriptResponse:
    """
    Chunk large transcripts and correct each chunk individually to mitigate API length/rate issues.
    Aggregates corrected chunks and generates a unified title.
    """
    chunks = split_text_into_chunks(raw_text, chunk_size)
    if len(chunks) == 1:
        if log_chunks:
            logger.info(f"Single chunk (len={len(chunks[0])} <= chunk_size={chunk_size}); using single correction call.")
        return correct_transcript(raw_text, model_name=model_name)
    if log_chunks:
        logger.info(f"Chunk plan ({len(chunks)} chunks, chunk_size={chunk_size}): {_describe_chunks(chunks)}")
    logger.info(f"Transcript split into {len(chunks)} chunks (chunk_size={chunk_size}).")
    corrected_parts: list[str] = []
    total_before = sum(len(c) for c in chunks)
    for idx, chunk in enumerate(chunks, start=1):
        logger.info(f"[Chunk {idx}/{len(chunks)}] chars={len(chunk)}")
        try:
            resp = correct_transcript(chunk, model_name=model_name)
            corrected_parts.append(resp.transcript.strip())
            if log_chunks:
                logger.info(f"[Chunk {idx}] corrected_length={len(corrected_parts[-1])}")
        except Exception as e:  # noqa
            logger.error(f"Chunk {idx} correction failed: {e}")
            corrected_parts.append(f"[Chunk {idx} correction failed]\n{chunk}")
        if per_chunk_sleep > 0 and idx < len(chunks):
            logger.info(f"Sleeping {per_chunk_sleep}s before next chunk to respect rate limits.")
            time.sleep(per_chunk_sleep)
    combined = "\n\n".join(corrected_parts).strip()
    if log_chunks:
        logger.info(f"Total pre-correction chars={total_before}, post-correction chars={len(combined)}")
    title = generate_title(combined)
    return TranscriptResponse(title=title, transcript=combined)

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

# ----------------- Summary Helpers -----------------

def summarize_transcript(corrected: str, model_name: str = "gemini-2.0-flash") -> str:
    """Generate a summary for the corrected transcript."""
    logger.info("Initializing model for summary generation...")
    summary_model = ChatGoogleGenerativeAI(model=model_name, temperature=0.3)
    summary_prompt = f"""You are a technical analyst. Produce a crisp summary for an internal knowledge base about a technology-focused YouTube video.
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
Do NOT add any extra explanatory text outside the structure."""
    messages = [
        ("system", "You produce precise hierarchical summaries for technical video transcripts. No verbosity."),
        ("human", summary_prompt),
    ]
    resp = invoke_with_retry(summary_model, messages)
    return getattr(resp, "content", str(resp))

def summarize_paragraphs(corrected: str, model_name: str = "gemini-2.0-flash", batch_size: int = 40) -> str:
    """
    Batched paragraph summarization to reduce API calls.
    Splits paragraphs, groups into batches, one model call per batch.
    """
    logger.info("Initializing model for batched paragraph summarization...")
    blocks = [b.strip() for b in re.split(r"\n{2,}", corrected) if b.strip()]
    if not blocks:
        return "Paragraph Summaries:\n- (No content)"
    model = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    summaries: list[str] = []
    for start in range(0, len(blocks), batch_size):
        batch = blocks[start:start+batch_size]
        first_index = start + 1
        last_index = start + len(batch)
        logger.info(f"Summarizing paragraphs {first_index}-{last_index} / {len(blocks)} (1 request)...")
        numbered = "\n\n".join([f"[P{first_index+i}] {para}" for i, para in enumerate(batch)])
        prompt = f"""You will receive several transcript paragraphs each tagged like [P<number>].
For EACH paragraph return exactly one bullet line:
- P<number>: summary (<=25 words)
Keep order. No extra text. ONLY those bullet lines.

Paragraphs:
{numbered}
"""
        messages = [
            ("system", "You distill multiple transcript paragraphs into ultra-terse bullet summaries (<=25 words each)."),
            ("human", prompt),
        ]
        try:
            resp = invoke_with_retry(model, messages)
            content = getattr(resp, "content", str(resp)).strip()
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("-"):
                    line = "- " + line.lstrip("- ").strip()
                summaries.append(line)
        except Exception as e:  # noqa
            logger.error(f"Batch {first_index}-{last_index} summarization failed: {e}")
            for i in range(first_index, last_index + 1):
                summaries.append(f"- P{i}: (summary failed)")
    return "Paragraph Summaries:\n" + "\n".join(summaries)

# ----------------- Main Workflow -----------------

def process_video(
    url: str,
    force: bool = False,
    base_dir: str = "data/transcripts",
    chunk_size: int = 12000,
    model_name: str = "gemini-2.0-flash",
    disable_paragraph_summaries: bool = False,
    disable_summary: bool = False,
    paragraph_batch_size: int = 40,
    per_chunk_sleep: float = 5.0,
    log_chunks: bool = True
):
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

    logger.info(f"Config: chunk_size={chunk_size}, per_chunk_sleep={per_chunk_sleep}s, model={model_name}")

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

    # Step 2: Correct transcript (chunk-aware)
    if not force and os.path.isfile(corrected_path) and title_txt_in_dir(video_dir):
        logger.info(f"Skipping correction; exists: {corrected_path}")
        with open(corrected_path, "r", encoding="utf-8") as f:
            corrected = f.read()
    else:
        logger.info("Correcting transcript with LLM (chunked if large)...")
        correction = correct_transcript_chunked(
            transcript,
            chunk_size=chunk_size,
            model_name=model_name,
            per_chunk_sleep=per_chunk_sleep,
            log_chunks=log_chunks
        )
        corrected = correction.transcript
        with open(corrected_path, "w", encoding="utf-8") as f:
            f.write(corrected)
        logger.info(f"Corrected transcript saved to {corrected_path}")

        logger.info("Saving title...")
        safe_title = correction.title.replace(' ', '_')
        title_file_path = os.path.join(video_dir, f"title_{safe_title}.txt")
        with open(title_file_path, "w", encoding="utf-8") as f:
            f.write(correction.title)

    # Step 2.5: Paragraph-level summaries (skip if exists unless force)
    if disable_paragraph_summaries:
        logger.info("Paragraph summarization disabled by flag.")
    else:
        if not force and os.path.isfile(paragraph_summary_path):
            logger.info(f"Skipping paragraph summaries; exists: {paragraph_summary_path}")
        else:
            logger.info("Generating paragraph-level summaries (batched)...")
            try:
                para_summaries = summarize_paragraphs(corrected, model_name=model_name, batch_size=paragraph_batch_size)
                with open(paragraph_summary_path, "w", encoding="utf-8") as f:
                    f.write(para_summaries)
                logger.info(f"Paragraph summaries saved to {paragraph_summary_path}")
            except Exception as e:  # noqa
                logger.error(f"Failed to generate paragraph summaries: {e}")
    # Step 3: Summarize (skip if exists unless force)
    if disable_summary:
        logger.info("High-level summary generation disabled by flag.")
    else:
        if not force and os.path.isfile(summary_path):
            logger.info(f"Skipping summary; exists: {summary_path}")
        else:
            logger.info("Generating summary with LLM...")
            try:
                summary_text = summarize_transcript(corrected, model_name=model_name)
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
    p.add_argument("--chunk-size", type=int, default=12000, help="Max chars per correction chunk (default: 12000)")
    p.add_argument("--model-name", default="gemini-2.0-flash", help="Model name (default: gemini-2.0-flash)")
    p.add_argument("--disable-paragraph-summaries", action="store_true", help="Skip paragraph summaries to save quota")
    p.add_argument("--disable-summary", action="store_true", help="Skip global summary to save quota")
    p.add_argument("--paragraph-batch-size", type=int, default=40, help="Paragraphs per summarization batch (default: 40)")
    p.add_argument("--per-chunk-sleep", type=float, default=2.0,
                   help="Sleep seconds between chunk corrections (rate limit help, default: 2.0)")
    p.add_argument("--log-chunks", action="store_true", default=True, help="Verbose logging of chunk sizes and lengths (default: enabled)")
    return p

if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    process_video(
        args.url,
        force=args.force,
        base_dir=args.base_dir,
        chunk_size=args.chunk_size,
        model_name=args.model_name,
        disable_paragraph_summaries=args.disable_paragraph_summaries,
        disable_summary=args.disable_summary,
        paragraph_batch_size=args.paragraph_batch_size,
        per_chunk_sleep=args.per_chunk_sleep,
        log_chunks=args.log_chunks
    )