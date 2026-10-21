"""Pruebas de las partes puras de numbered_buttons.py (números hablados y colocación de etiquetas).
Sin UI Automation ni ventanas: python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numbered_buttons as nb  # noqa: E402
from buttons_rules import Rect  # noqa: E402


class SpokenNumber(unittest.TestCase):
    def test_digits_and_words_in_both_languages(self):
        for text, expected in (("12", 12), ("número 12", 12), ("botón siete", 7), ("doce", 12), ("veintiuno", 21),
                               ("treinta y cinco", 35), ("trinta e cinco", 35), ("noventa y nueve", 99),
                               ("quarenta e dois", 42), ("três", 3), ("tres", 3)):
            self.assertEqual(nb.spoken_number(text), expected, text)

    def test_a_command_with_a_number_is_not_a_number(self):
        for text in ("función cinco", "copiar dos", "abrir 3", "dos cosas", "tecla 5"):
            self.assertIsNone(nb.spoken_number(text), text)

    def test_out_of_range_and_noise(self):
        for text in ("100", "0", "cero", "cien", "nada", "", None):
            self.assertIsNone(nb.spoken_number(text), text)


class _Target:
    def __init__(self, rect):
        self.rect = rect


class LayoutLabels(unittest.TestCase):
    def test_small_element_anchors_top_left_wide_element_anchors_center(self):
        targets = [_Target(Rect(100, 100, 40, 20)), _Target(Rect(300, 50, 256, 30))]
        spots = nb.layout_labels(targets, [False, False], [(20, 16), (20, 16)])
        self.assertEqual(spots[0][:2], (98, 98))
        self.assertEqual(spots[1][:2], (300 + 128 - 10, 52))

    def test_labels_never_overlap(self):
        targets = [_Target(Rect(100, 100, 10, 10)) for _ in range(8)]   # todos en el mismo sitio
        spots = nb.layout_labels(targets, [False] * 8, [(20, 16)] * 8)
        rects = [Rect(x, y, w, h) for (x, y, w, h) in spots.values()]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertFalse(a.intersects(b))

    def test_hidden_numbers_are_not_drawn_but_keep_their_number(self):
        targets = [_Target(Rect(10, 10, 10, 10)), _Target(Rect(100, 10, 10, 10))]
        spots = nb.layout_labels(targets, [True, False], [(20, 16), (20, 16)])
        self.assertEqual(list(spots), [1])


class ShowPattern(unittest.TestCase):
    """La palabra suelta "botones"/"botões" abre (o renueva) el modo; con un nombre detrás es otro comando."""

    def setUp(self):
        import re
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patterns.txt")
        with open(path, encoding="utf-8") as fh:
            line = next(l for l in fh if l.startswith("buttons_show="))
        self.pattern = re.compile(line.split("=", 1)[1].strip(), re.I)

    def test_bare_word_and_phrases(self):
        for text in ("botones", "botões", "Botões", "mostrar botones", "mostrar botónes"):
            self.assertTrue(self.pattern.search(text), text)

    def test_with_a_name_it_is_not_show(self):
        for text in ("botón guardar", "botões salvar", "clicar botões", "cancelar"):
            self.assertFalse(self.pattern.search(text), text)


if __name__ == "__main__":
    unittest.main()
