"""Pruebas de speech.py (voz de respuesta). Sin micrófono: python -m unittest discover -s tests

La más importante: NINGÚN texto hablado puede casar con una regla de comando de ningún idioma. El micrófono
oye la propia voz, y un aviso que contuviera una palabra de comando la ejecutaría.
"""
import os
import re
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import speech  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def load_rules(path):
    """[(clave, regex)] de un archivo de patrones (solo las líneas clave=regex; sin reemplazos '=>')."""
    rules = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line or "=>" in line:
                continue
            key, pattern = line.split("=", 1)
            if key.strip() in ("language", "vosk_language", "spell_prefix", "command_prefix", "recognition_engine",
                               "recognition_engine_command", "recognition_engine_dictation"):
                continue
            try:
                rules.append((key.strip(), re.compile(pattern.strip(), re.I)))
            except re.error:
                pass
    return rules


class EventTexts(unittest.TestCase):
    def test_every_event_has_text_in_both_languages(self):
        self.assertEqual(set(speech.EVENTS['es']), set(speech.EVENTS['pt']))
        for lang in ('es', 'pt'):
            for event, text in speech.EVENTS[lang].items():
                self.assertTrue(text.strip(), (lang, event))

    def test_no_spoken_text_matches_any_command_rule(self):
        files = [os.path.join(HERE, "patterns.txt")]
        files += [os.path.join(HERE, f) for f in os.listdir(HERE) if f.startswith("patterns.") and f.endswith(".txt")
                  and f != "patterns.txt"]
        checked = 0
        for path in files:
            rules = load_rules(path)
            for lang, events in speech.EVENTS.items():
                for event, text in events.items():
                    for key, rule in rules:
                        checked += 1
                        self.assertIsNone(rule.search(text),
                                          f"«{text}» ({lang}/{event}) casa con la regla '{key}' de {os.path.basename(path)}")
        self.assertGreater(checked, 500)

    def test_language_and_text(self):
        self.assertEqual(speech.language_key('pt-BR'), 'pt')
        self.assertEqual(speech.language_key('es-ES'), 'es')
        self.assertEqual(speech.language_key('es'), 'es')
        self.assertIsNone(speech.language_key('fr-FR'))
        self.assertEqual(speech.event_text('pt-BR', 'activated'), "Ativada")
        self.assertEqual(speech.event_text('es-ES', 'activated'), "Activada")
        self.assertIsNone(speech.event_text('fr-FR', 'activated'))
        self.assertIsNone(speech.event_text('pt-BR', 'no_existe'))


class VoiceChoice(unittest.TestCase):
    def test_voice_language_attribute(self):
        self.assertTrue(speech.voice_matches("416", 'pt-BR'))
        self.assertTrue(speech.voice_matches("816", 'pt-BR'))           # portugués de Portugal: mismo idioma primario
        self.assertTrue(speech.voice_matches("40A;C0A", 'es-ES'))
        self.assertTrue(speech.voice_matches("2C0A", 'es'))
        self.assertFalse(speech.voice_matches("409", 'pt-BR'))
        self.assertFalse(speech.voice_matches("416", 'es-ES'))
        self.assertFalse(speech.voice_matches("", 'pt-BR'))
        self.assertFalse(speech.voice_matches("zzz", 'pt-BR'))


class SelfHearingGuard(unittest.TestCase):
    def test_overlap_window_includes_the_tail(self):
        spoken = speech.Speaker(lambda: 'pt-BR', enabled=True)
        now = time.time()
        spoken._spans = [(now - 2.0, now - 1.5)]       # habló hace 1,5-2 s
        self.assertFalse(spoken.overlaps(now - 0.8, now - 0.5), "después de la cola: es otra cosa")
        self.assertTrue(spoken.overlaps(now - 1.7, now - 1.4), "captó mientras hablaba")
        spoken._spans = [(now - 2.0, now - 0.3)]       # acaba de terminar: la cola aún puede oírse
        self.assertTrue(spoken.overlaps(now - 0.2, now), "la cola de la voz cuenta")

    def test_disabled_speaker_says_nothing(self):
        spoken = speech.Speaker(lambda: 'pt-BR', enabled=False)
        self.assertIsNone(spoken.say('activated'))
        self.assertEqual(spoken._spans, [])

    def test_unsupported_language_says_nothing(self):
        spoken = speech.Speaker(lambda: 'fr-FR', enabled=True)
        self.assertIsNone(spoken.say('activated'))

    def test_enabled_by_environment_variable(self):
        old = os.environ.get('XULIA2_VOZ')
        try:
            os.environ['XULIA2_VOZ'] = '0'
            self.assertFalse(speech.speech_enabled())
            os.environ['XULIA2_VOZ'] = '1'
            self.assertTrue(speech.speech_enabled())
        finally:
            if old is None:
                os.environ.pop('XULIA2_VOZ', None)
            else:
                os.environ['XULIA2_VOZ'] = old


if __name__ == "__main__":
    unittest.main()
