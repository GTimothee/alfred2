
try:
    import pyttsx3  # type: ignore
except ImportError as e:  # pragma: no cover
    raise SystemExit("pyttsx3 not installed. Please add it to dependencies.") from e


class TTSPlayer:
    def __init__(self, voice_name_contains: str | None = None, rate_delta: int = 0):
        self.engine = pyttsx3.init()
        if rate_delta:
            base_rate = self.engine.getProperty("rate")
            self.engine.setProperty("rate", base_rate + rate_delta)
        if voice_name_contains:
            for v in self.engine.getProperty("voices"):
                if voice_name_contains.lower() in (v.name or '').lower():
                    self.engine.setProperty("voice", v.id)
                    break

    def speak(self, text: str):
        if not text.strip():
            return
        self.engine.say(text)
        self.engine.runAndWait()