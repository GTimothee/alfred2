from __future__ import annotations
import logging
from impersonated.kokoro_tts import KokoroText2Speech 
from impersonated.chatbot import ChatBot, BOT_NAME
import sys
import argparse

from dotenv import load_dotenv



load_dotenv()

LOG_FILE = "chatbot_app.log"
LOG_MAX_BYTES = 524288  # 512 KB
LOG_BACKUP_COUNT = 3



def setup_logging(
    name: str = "impersonated.cli",
    log_file: str = LOG_FILE,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT
) -> logging.Logger:
    """
    Centralized logger configuration. Safe to call multiple times.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.debug(f"File logging enabled -> {log_file}")
    except Exception as e:  
        logger.warning(f"Failed to set up file logging ({e}); continuing without file log.")
    return logger

logger = setup_logging()



def parse_args():
    parser = argparse.ArgumentParser(description="Chat + Kokoro TTS CLI")
    parser.add_argument("--lang-code", "-l", default="a", help="Kokoro language code (default: a)")
    return parser.parse_args()

def conversation_loop(bot, tts): 
    print(f"{BOT_NAME}. Type {{/exit, :q, quit, exit}} to quit.")

    while True:

        # get user input
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()  
            break

        # exit handling
        if user_text.lower() in {"/exit", "exit", "quit", ":q"}:
            break
        if not user_text:
            continue

        # compute answer
        answer = bot.ask(user_text)
        print(f"{BOT_NAME}: {answer}")

        # convert to audio
        try:
            if tts:
                tts.speak(answer)
        except Exception as e: 
            logger.error(f"TTS playback failed: {e}")

    print("Goodbye.")


if __name__ == "__main__": 
    args = parse_args()

    try:
        bot = ChatBot(
            model_name="gemini-2.5-flash",
            history_max_size=6,
            temperature=0.7
        )
    except Exception as e:  # noqa
        logger.error(f"Failed to initialize chat session: {e}")
        sys.exit(1)

    try:
        tts = KokoroText2Speech(lang_code=args.lang_code, speed=.8)
    except Exception as e:
        logger.error(f"Failed to initialize Kokoro TTS: {e}")
        sys.exit(1)

    print(f"Using Kokoro lang_code={args.lang_code}")
    conversation_loop(bot, tts)

