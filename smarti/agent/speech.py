"""Text-to-speech cleanup, synthesis, and playback helpers."""
from .shared import *


class SpeechMixin:
    def stop_speaking(self, request_id=None):
        self._stop_speech_flag = True
        return self._tts_session.stop(request_id)

    def speech_status(self):
        return self._tts_session.snapshot()

    def _on_speech_status(self, playing):
        self._tts_is_playing = playing
        if self.tts_status_callback:
            self.tts_status_callback(playing)

    def start_speaking(self, text, owner_id=""):
        return self._tts_session.start(self._speech_text(text), owner_id=owner_id)

    def _speech_text(self, text):
        if not TTS_INSTALLED:
            raise RuntimeError("מנוע ההקראה או רכיב השמע אינו מותקן")
        clean = self._clean_text_for_tts(text)
        if not clean:
            raise ValueError("אין טקסט שניתן להקריא")
        return clean

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
        # Legacy QThread callers retain synchronous completion.
        try:
            clean = self._speech_text(text)
        except (RuntimeError, ValueError):
            logging.exception("Could not start speech")
            return
        return self._tts_session.start(clean, background=False)

    def _synthesize_and_play(self, clean, cancel):
        voice_id = str(self.settings.get("tts_voice_id") or "edge:he-IL-HilaNeural").strip()
        if EDGE_TTS_INSTALLED and (voice_id.startswith("edge:") or not GTTS_INSTALLED):
            try:
                audio = self._speak_text_with_edge(clean, voice_id, cancel)
            except Exception:
                if cancel.is_set():
                    return
                if not GTTS_INSTALLED:
                    raise
                logging.warning("Edge TTS synthesis failed; trying Google TTS", exc_info=True)
                audio = self._speak_text_with_gtts(clean, cancel)
        else:
            audio = self._speak_text_with_gtts(clean, cancel)
        if not cancel.is_set():
            if not audio:
                raise RuntimeError("שירות ההקראה לא החזיר שמע")
            self._play_tts_mp3_bytes(audio, cancel)

    def _tts_volume_fraction(self):
        try:
            volume = float(self.settings.get("tts_volume", 100))
        except Exception:
            volume = 100
        return max(0.0, min(1.0, volume / 100.0))

    def _play_tts_mp3_bytes(self, audio_bytes, cancel):
        if not audio_bytes or cancel.is_set():
            return
        if os.name == "nt":
            from ..tts_service import play_windows_mp3
            return play_windows_mp3(audio_bytes, cancel, self._tts_volume_fraction)
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
            if cancel.is_set():
                return
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not cancel.wait(0.1):
                pygame.mixer.music.set_volume(self._tts_volume_fraction())
        finally:
            try: pygame.mixer.music.stop()
            except: pass
            try: pygame.mixer.music.unload()
            except: pass
            pygame.mixer.quit()
            if path:
                try: os.remove(path)
                except: pass

    def _speak_text_with_edge(self, clean, voice_id, cancel):
        import asyncio
        from contextlib import aclosing, suppress
        import aiohttp
        import edge_tts
        voice_name = str(voice_id or "").split(":", 1)[-1].strip()
        valid = {voice.get("voice") for voice in EDGE_HEBREW_TTS_VOICES}
        if voice_name not in valid:
            voice_name = "he-IL-HilaNeural"

        async def collect_audio():
            context = create_ssl_context(self.settings, url="https://speech.platform.bing.com")

            class SpeechConnector(aiohttp.TCPConnector):
                def _get_ssl_context(self, request):
                    # edge-tts supplies its own certifi SSL context per request,
                    # overriding the public connector ssl option. Scope this
                    # adapter to speech so Windows/custom CA settings apply.
                    return context if request.is_ssl() else None

            chunks = []
            async with SpeechConnector(ssl=context) as connector:
                communicate = edge_tts.Communicate(clean, voice_name, connector=connector)
                async with aclosing(communicate.stream()) as stream:
                    async for chunk in stream:
                        if cancel.is_set():
                            break
                        if chunk.get("type") == "audio":
                            chunks.append(chunk.get("data", b""))
            return b"".join(chunks)

        async def cancellable_audio():
            task = asyncio.create_task(collect_audio())
            try:
                while not task.done():
                    if cancel.is_set():
                        return b""
                    await asyncio.wait({task}, timeout=0.1)
                return await task
            finally:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return asyncio.run(cancellable_audio())

    def _speak_text_with_gtts(self, clean, cancel):
        from gtts import gTTS
        tld = str(self.settings.get("tts_voice_id", "co.il") or "co.il").strip()
        tld = tld if any(tld == voice.get("id") for voice in GOOGLE_HEBREW_TTS_VOICES) else "co.il"
        tts = gTTS(text=clean, lang='iw', tld=tld, slow=False, timeout=(10, 30))
        chunks = []
        # gTTS.stream hard-codes verify=False. Reuse its request preparation,
        # but send through Smarti's verified transport without global patches.
        with requests.Session() as session:
            for prepared in tts._prepare_requests():
                if cancel.is_set():
                    return b""
                with session.send(
                    prepared, timeout=(10, 30), proxies=urllib.request.getproxies(),
                    **ssl_request_kwargs(self.settings, url=prepared.url),
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if cancel.is_set():
                            return b""
                        try:
                            batch = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue  # The response also contains framing lines.
                        if not isinstance(batch, list):
                            continue
                        for item in batch:
                            if isinstance(item, list) and len(item) > 2 and item[1] == "jQ1olc" and item[2]:
                                encoded = json.loads(item[2])[0]
                                if isinstance(encoded, str):
                                    chunks.append(base64.b64decode(encoded))
        return b"".join(chunks)
