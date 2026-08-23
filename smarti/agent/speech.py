"""Text-to-speech cleanup, synthesis, and playback helpers."""
from .shared import *


class SpeechMixin:
    def stop_speaking(self):
        self._stop_speech_flag = True

    def _clean_text_for_tts(self, text):
        clean = html.unescape(str(text or ""))
        clean = re.sub(r"```.*?```", " קטע קוד. ", clean, flags=re.DOTALL)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        clean = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        clean = re.sub(r"\b(?:https?|file)://\S+", " קישור ", clean, flags=re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"^[ \t]*[-*•●▪▫◦]+[ \t]+", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"^[ \t]*(?:#{1,6}|>+)[ \t]*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"[*_#`~]+", "", clean)
        clean = re.sub(r"[|{}\[\]<>^=\\]+", " ", clean)

        emoji_ranges = (
            (0x1F000, 0x1FAFF),
            (0x2600, 0x27BF),
            (0xFE00, 0xFE0F),
            (0x200D, 0x200D),
        )
        chars = []
        for ch in clean:
            cp = ord(ch)
            if any(start <= cp <= end for start, end in emoji_ranges):
                continue
            category = unicodedata.category(ch)
            if category[0] == "C" and ch not in "\n\t ":
                continue
            if category in {"So", "Sk", "Co"}:
                continue
            chars.append(ch)
        clean = "".join(chars)
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\s*[\r\n]+\s*", ". ", clean)
        clean = re.sub(r"([.!?]){2,}", r"\1", clean)
        clean = re.sub(r"\s+([,.!?;:])", r"\1", clean)
        return clean.strip(" \t\r\n.-")

    def speak_text(self, text):
        if not TTS_INSTALLED: return
        clean = self._clean_text_for_tts(text)
        if not clean.strip():
            return
        self.stop_speaking()
        with self.tts_lock:
            self._stop_speech_flag = False
            self._tts_is_playing = True
            if self.tts_status_callback: self.tts_status_callback(True)
            try:
                voice_id = str(self.settings.get("tts_voice_id", "co.il") or "co.il").strip()
                if voice_id.startswith("edge:") and EDGE_TTS_INSTALLED:
                    self._speak_text_with_edge(clean, voice_id)
                elif GTTS_INSTALLED:
                    self._speak_text_with_gtts(clean)
            except Exception as e: logging.error(f"TTS Error: {e}")
            finally:
                self._tts_is_playing = False
                if self.tts_status_callback: self.tts_status_callback(False)

    def _tts_volume_fraction(self):
        try:
            volume = float(self.settings.get("tts_volume", 100))
        except Exception:
            volume = 100
        return max(0.0, min(1.0, volume / 100.0 if volume > 1 else volume))

    def _play_tts_mp3_bytes(self, audio_bytes):
        if not audio_bytes:
            return
        import pygame
        audio_buffer = io.BytesIO(audio_bytes)
        path = ""
        try:
            pygame.mixer.init()
            try:
                pygame.mixer.music.load(audio_buffer, "mp3")
            except Exception:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                    path = fp.name
                    fp.write(audio_buffer.getvalue())
                pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._tts_volume_fraction())
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self._stop_speech_flag: pygame.time.Clock().tick(10)
        finally:
            try: pygame.mixer.music.stop()
            except: pass
            try: pygame.mixer.music.unload()
            except: pass
            pygame.mixer.quit()
            if path:
                try: os.remove(path)
                except: pass

    def _speak_text_with_edge(self, clean, voice_id):
        import asyncio
        import edge_tts
        voice_name = str(voice_id or "").split(":", 1)[-1].strip()
        valid = {voice.get("voice") for voice in EDGE_HEBREW_TTS_VOICES}
        if voice_name not in valid:
            voice_name = "he-IL-HilaNeural"

        async def collect_audio():
            communicate = edge_tts.Communicate(clean, voice_name)
            chunks = []
            async for chunk in communicate.stream():
                if self._stop_speech_flag:
                    break
                if chunk.get("type") == "audio":
                    chunks.append(chunk.get("data", b""))
            return b"".join(chunks)

        audio_bytes = asyncio.run(collect_audio())
        self._play_tts_mp3_bytes(audio_bytes)

    def _speak_text_with_gtts(self, clean):
        from gtts import gTTS
        tld = str(self.settings.get("tts_voice_id", "co.il") or "co.il").strip()
        tld = tld if any(tld == voice.get("id") for voice in GOOGLE_HEBREW_TTS_VOICES) else "co.il"
        try: tts = gTTS(text=clean, lang='iw', tld=tld, slow=False)
        except: tts = gTTS(text=clean, lang='he', tld=tld, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        self._play_tts_mp3_bytes(audio_buffer.getvalue())
