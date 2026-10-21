"""Voz de respuesta de XULIA2: avisos hablados de los eventos importantes.

Es el único canal que no depende de la pantalla ni del reconocedor: quien usa XULIA2 solo por voz oye si
la activó, si entró en el dictado o si el micrófono no responde. Usa las voces de Windows (SAPI, ya
instaladas, sin internet y sin dependencias nuevas: pywin32 ya se usa).

Cuidados que vienen de la versión 1.5 y de un ensayo con micrófono real:
  - UN AVISO HABLADO NUNCA PUEDE CONTENER UNA PALABRA DE COMANDO: el micrófono oye la propia voz y la
    ejecutaría ("mensaje ativo" se oyó como el comando 'mensaje ativo' en el primer ensayo). La prueba
    comprueba que ningún texto de aviso casa con ninguna regla de ningún idioma;
  - mientras se habla (y un poco después) lo que capta el micrófono se descarta: `overlaps()`;
  - la voz va en un hilo propio: hablar nunca retrasa la escucha ni un comando, y un aviso nuevo
    sustituye al que espera (no se acumulan);
  - solo se habla con una voz del idioma elegido: leer español con una voz portuguesa es peor que callar.

Se apaga con `[general] voz = no` en %APPDATA%\\Xulia2\\config.ini o con la variable XULIA2_VOZ=0.
"""
import configparser
import os
import queue
import threading
import time

# evento -> texto por idioma. Sin palabras de comando (ver la nota de arriba).
EVENTS = {
    'es': {
        'activated': "Activada",
        'deactivated': "Desactivada",
        'paused': "En pausa",
        'dictation_on': "Dictado encendido",
        'dictation_off': "Dictado apagado",
        'no_buttons': "Nada que numerar aquí",
        'mic_error': "Micrófono no disponible",
    },
    'pt': {
        'activated': "Ativada",
        'deactivated': "Desativada",
        'paused': "Em pausa",
        'dictation_on': "Ditado ligado",
        'dictation_off': "Ditado desligado",
        'no_buttons': "Nada para numerar aqui",
        'mic_error': "Microfone indisponível",
    },
}
_PRIMARY_LANGUAGE = {'pt': 0x16, 'es': 0x0A}   # id de idioma primario de Windows
TAIL = 0.6        # s tras el final de la voz en los que el micrófono aún puede oír su cola


def speech_enabled():
    """XULIA2_VOZ (0/1) manda; si no, `[general] voz` de %APPDATA%\\Xulia2\\config.ini; por defecto, sí."""
    env = os.environ.get('XULIA2_VOZ')
    if env is not None:
        return env.strip().lower() not in ('0', 'no', 'off', 'false', '')
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Xulia2', 'config.ini'),
                 encoding='utf-8')
        return cfg.get('general', 'voz', fallback='si').strip().lower() not in ('no', 'off', '0', 'false')
    except Exception:
        return True


def language_key(language):
    """'pt-BR' -> 'pt'; 'es-ES' o 'es' -> 'es'; otro idioma -> None (no se habla)."""
    prefix = (language or '').lower().split('-')[0]
    return prefix if prefix in EVENTS else None


def event_text(language, event):
    key = language_key(language)
    return EVENTS[key].get(event) if key else None


def voice_matches(attribute, language):
    """¿El atributo 'Language' de una voz SAPI (p. ej. "416" o "40A;C0A", en hexadecimal) es del idioma?"""
    wanted = _PRIMARY_LANGUAGE.get(language_key(language))
    if wanted is None:
        return False
    for part in (attribute or '').replace(',', ';').split(';'):
        try:
            if int(part.strip(), 16) & 0x3FF == wanted:
                return True
        except ValueError:
            continue
    return False


def estimate_seconds(text):
    """Duración aproximada de una frase hablada (la voz real la corrige al terminar)."""
    return 0.5 + 0.075 * len(text or '')


class Speaker:
    """Habla en un hilo propio. `say(evento)` no bloquea y solo guarda el último aviso pendiente."""

    def __init__(self, language_getter, enabled=True, volume=100, log=print):
        self._language_getter = language_getter
        self.enabled = enabled
        self.volume = volume
        self._log = log
        self._queue = queue.Queue()
        self._thread = None
        self._spans = []            # [(inicio, fin)] de lo hablado, para descartar lo que el micrófono oyó
        self._speaking_since = None
        self._warned_language = set()

    # --- API ---
    def say(self, event):
        """Habla el aviso `event` en el idioma actual. Devuelve el texto o None si no se habla."""
        if not self.enabled:
            return None
        language = self._language_getter()
        text = event_text(language, event)
        if not text:
            return None
        self._ensure_thread()
        while True:   # un aviso nuevo sustituye al que esperaba
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put((text, language))
        # el micrófono puede oír el aviso desde ya: se anota la ventana estimada
        now = time.time()
        self._spans.append((now, now + estimate_seconds(text)))
        self._spans = self._spans[-8:]
        return text

    def overlaps(self, start, end):
        """¿La voz sonó (o su cola) mientras el micrófono captaba entre `start` y `end`?"""
        now = time.time()
        if self._speaking_since is not None:
            return True
        return any(s - 0.2 < end and e + TAIL > start for s, e in self._spans)

    def stop(self):
        self.enabled = False
        self._queue.put(None)

    # --- hilo de voz ---
    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Volume = int(self.volume)
        except Exception as exc:
            self._log(f"Voz de respuesta no disponible: {exc}")
            self.enabled = False
            return
        while True:
            item = self._queue.get()
            if item is None:
                break
            text, language = item
            try:
                token = self._token_for(voice, language)
                if token is None:
                    key = language_key(language)
                    if key not in self._warned_language:
                        self._warned_language.add(key)
                        self._log(f"No hay una voz de Windows para el idioma '{key}': la voz de respuesta queda en silencio")
                    continue
                voice.Voice = token
                self._speaking_since = time.time()
                started = self._speaking_since
                voice.Speak(text, 0)            # síncrono: este hilo es solo de voz
                self._spans.append((started, time.time()))
                self._spans = self._spans[-8:]
            except Exception as exc:
                self._log(f"Error al hablar: {exc}")
            finally:
                self._speaking_since = None

    @staticmethod
    def _token_for(voice, language):
        voices = voice.GetVoices()
        for i in range(voices.Count):
            token = voices.Item(i)
            if voice_matches(token.GetAttribute("Language"), language):
                return token
        return None
