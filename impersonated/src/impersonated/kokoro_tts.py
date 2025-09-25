
from kokoro import KPipeline
from IPython.display import display, Audio
from .audio import play_audio_stream

import logging 
logger = logging.getLogger(__name__)

class KokoroText2Speech:
    """
    Supported languages: 
    - 🇺🇸 'a' => American English, 🇬🇧 'b' => British English
    - 🇪🇸 'e' => Spanish es
    - 🇫🇷 'f' => French fr-fr
    - 🇮🇳 'h' => Hindi hi
    - 🇮🇹 'i' => Italian it
    - 🇯🇵 'j' => Japanese: pip install misaki[ja]
    - 🇧🇷 'p' => Brazilian Portuguese pt-br
    - 🇨🇳 'z' => Mandarin Chinese: pip install misaki[zh]
    """

    def __init__(self, voice: str = "af_heart", lang_code: str = "a", speed=1):
        self.voice = voice
        self._pipeline = KPipeline(lang_code=lang_code)
        self.speed = speed
        logger.info(f"Kokoro TTS initialized with voice={voice}, lang_code={lang_code}, speed={speed}")

    def speak(self, text: str):
        logging.info(f"Kokoro TTS speaking text of length {len(text)}")
        generator = self._pipeline(
            text, voice=self.voice, # <= change voice here
            speed=self.speed, split_pattern=r'\n+'
        )

        # Alternatively, load voice tensor directly:
        # voice_tensor = torch.load('path/to/voice.pt', weights_only=True)
        # generator = pipeline(
        #     text, voice=voice_tensor,
        #     speed=1, split_pattern=r'\n+'
        # )

        for i, (gs, ps, audio) in enumerate(generator):
            print(i)  # i => index
            print(gs) # gs => graphemes/text
            # print(ps) # ps => phonemes
            play_audio_stream(audio, 24000)
            # display(Audio(data=audio, rate=24000, autoplay=i==0))
            # sf.write(f'{i}.wav', audio, 24000) # save each audio file