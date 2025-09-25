import os

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing dependency 'langchain-google-genai'. Install it first.") from e
from typing import List, Tuple

import logging

logger = logging.getLogger(__name__)

BOT_NAME = "Sarah"  # "Alfred"


SYSTEM_PROMPT = (
    "You are {bot_name}, the helpful assistant of the family. You respond in a concise and friendly manner. "
).format(bot_name=BOT_NAME)


class ChatBot:
    def __init__(self, model_name: str = "gemini-2.5-flash", history_max_size: int = 6, temperature: float = 0.7):
        self.model_name = model_name
        self.history_max_size = history_max_size
        self.history: List[Tuple[str, str]] = []  # list of (role, content)
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment.")
        self.model = ChatGoogleGenerativeAI(model=model_name, temperature=temperature)

    def _build_messages(self) -> List[Tuple[str, str]]:
        system_prompt = SYSTEM_PROMPT
        messages: List[Tuple[str, str]] = [("system", system_prompt)]
        recent = self.history[-(self.history_max_size * 2):]
        messages.extend(recent)
        return messages

    def ask(self, user_text: str) -> str:
        self.history.append(("human", user_text))
        messages = self._build_messages()
        try:
            resp = self.model.invoke(messages)
            if hasattr(resp, "content"):
                answer = resp.content if isinstance(resp.content, str) else str(resp.content)
            else:  # fallback
                answer = str(resp)
        except Exception as e:  # noqa
            logger.error(f"LLM call failed: {e}")
            answer = "I'm sorry, I had an internal error generating a response."
        self.history.append(("ai", answer))
        if len(self.history) > self.history_max_size * 2 + 4:
            self.history = self.history[-(self.history_max_size * 2 + 4):]
        return answer