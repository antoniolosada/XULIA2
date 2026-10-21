"""Pruebas de buttons_rules.py. Sin dependencias: python -m unittest discover -s tests

Los casos y los números salen de las pruebas de la versión 1.5 de XULIA, que a su vez se escribieron
con medidas de aplicaciones reales (correo web, WhatsApp, Drive, X, Explorador de archivos).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import buttons_rules as br  # noqa: E402
from buttons_rules import Rect  # noqa: E402


def centers_of(rects):
    return [r.center() for r in rects]


class DecideByLayers(unittest.TestCase):
    def test_hidden_layer_removes_its_buttons_and_page_stays(self):
        rects = [Rect(0, 87, 1905, 945)]
        centers = [(864, 414), (1143, 331), (300, 127)]
        leaves = br.decide_by_layers(centers, [0, 0, -1], [-1], rects, [0])
        self.assertEqual(leaves, [True, True, False])

    def test_drive_open_menu_removes_list_under_it_and_keeps_menu(self):
        rects = [Rect(12, 143, 257, 272)]
        centers = [(140, 202), (102, 214), (102, 393), (102, 440), (1000, 540)]
        leaves = br.decide_by_layers(centers, [0, -1, -1, -1, -1], [-1], rects, [1])
        self.assertEqual(leaves, [False, True, True, False, False])

    def test_real_dialog_open_only_its_buttons_stay(self):
        rects = [Rect(0, 87, 1905, 945)]
        centers = [(864, 414), (300, 500), (300, 40)]
        self.assertEqual(br.decide_by_layers(centers, [0, -1, -1], [-1], rects, [1]), [False, True, False])

    def test_no_verdict_nothing_leaves(self):
        rects = [Rect(0, 87, 1905, 945)]
        self.assertEqual(br.decide_by_layers([(864, 414), (300, 500)], [0, -1], [-1], rects, [-1]), [False, False])

    def test_layer_inside_hidden_layer_leaves_with_it(self):
        rects = [Rect(0, 0, 500, 500), Rect(10, 10, 100, 100)]
        self.assertTrue(br.decide_by_layers([(50, 50)], [1], [-1, 0], rects, [0, -1])[0])

    def test_layer_verdict(self):
        self.assertEqual(br.layer_verdict(["OK"], 9), 1)
        self.assertEqual(br.layer_verdict(["COVERED", "OK"], 9), 1)
        self.assertEqual(br.layer_verdict(["COVERED", "COVERED"], 9), 0)
        self.assertEqual(br.layer_verdict(["COVERED"], 9), -1)
        self.assertEqual(br.layer_verdict(["COVERED"], 1), 0)
        self.assertEqual(br.layer_verdict(["ROUGH", "ERROR"], 9), -1)


class Ghosts(unittest.TestCase):
    def test_only_covered_goes_away(self):
        self.assertTrue(br.number_goes_away("COVERED"))
        self.assertFalse(br.number_goes_away("OK"))
        self.assertFalse(br.number_goes_away("ROUGH"))
        self.assertFalse(br.number_goes_away("ERROR"))

    def test_only_web_content_and_never_our_own_window(self):
        self.assertTrue(br.should_check(True, True, False))
        self.assertFalse(br.should_check(True, False, False))
        self.assertFalse(br.should_check(True, True, True))
        self.assertFalse(br.should_check(False, True, False))

    def test_check_saying_everything_covered_is_discarded(self):
        self.assertFalse(br.check_is_plausible(67, 67, 0))
        self.assertFalse(br.check_is_plausible(61, 40, 0))
        self.assertFalse(br.check_is_plausible(61, 40, 2))
        self.assertTrue(br.check_is_plausible(61, 1, 50))
        self.assertTrue(br.check_is_plausible(88, 1, 80))
        self.assertTrue(br.check_is_plausible(10, 5, 0))
        self.assertTrue(br.check_is_plausible(3, 3, 0))

    def test_screen_hidden_underneath_valid_when_there_are_confirmed(self):
        self.assertTrue(br.check_is_plausible(37, 20, 17))
        self.assertTrue(br.check_is_plausible(37, 30, 3))
        self.assertFalse(br.check_is_plausible(100, 90, 9))
        self.assertTrue(br.check_is_plausible(100, 90, 10))


class Filters(unittest.TestCase):
    def test_image_inside_numbered(self):
        self.assertTrue(br.image_inside_numbered(br.IMAGE, True))
        self.assertFalse(br.image_inside_numbered(br.IMAGE, False))
        self.assertFalse(br.image_inside_numbered(br.BUTTON, True))

    def test_emoji_only_image(self):
        self.assertTrue(br.is_emoji_only_image(br.IMAGE, "🐶"))
        self.assertTrue(br.is_emoji_only_image(br.IMAGE, "👏🏻"))
        self.assertTrue(br.is_emoji_only_image(br.IMAGE, " 💥 "))
        self.assertFalse(br.is_emoji_only_image(br.IMAGE, "Foto do perfil"))
        self.assertFalse(br.is_emoji_only_image(br.IMAGE, "IMG 2590"))
        self.assertFalse(br.is_emoji_only_image(br.IMAGE, ""))
        self.assertFalse(br.is_emoji_only_image(br.BUTTON, "👍"))

    def test_row_piece_gets_no_number_button_inside_row_does(self):
        self.assertTrue(br.cell_inside_row(br.DATAITEM, br.DATAITEM, False))
        self.assertTrue(br.cell_inside_row(br.TEXT, br.LISTITEM, False))
        self.assertTrue(br.cell_inside_row(br.EDIT, br.LISTITEM, True))
        self.assertFalse(br.cell_inside_row(br.EDIT, br.LISTITEM, False))
        self.assertFalse(br.cell_inside_row(br.BUTTON, br.DATAITEM, False))
        self.assertFalse(br.cell_inside_row(br.CHECKBOX, br.DATAITEM, False))
        self.assertFalse(br.cell_inside_row(br.BUTTON, br.HYPERLINK, False))
        self.assertFalse(br.cell_inside_row(br.DATAITEM, br.BUTTON, False))
        self.assertFalse(br.cell_inside_row(br.DATAITEM, 0, False))

    def test_frame_with_numbered_items_only_when_it_has_items(self):
        self.assertTrue(br.frame_with_numbered_items(br.TOOLBAR, True))
        self.assertTrue(br.frame_with_numbered_items(br.MENU, True))
        self.assertFalse(br.frame_with_numbered_items(br.TOOLBAR, False))
        self.assertFalse(br.frame_with_numbered_items(br.BUTTON, True))

    def test_link_that_repeats_the_row_click(self):
        row = Rect(250, 300, 1662, 26)
        click = row.center()
        subject, name = Rect(560, 303, 1288, 19), Rect(300, 303, 181, 19)
        self.assertTrue(br.link_repeats_row_click(br.HYPERLINK, br.DATAITEM, subject, click))
        self.assertFalse(br.link_repeats_row_click(br.HYPERLINK, br.DATAITEM, name, click))
        self.assertFalse(br.link_repeats_row_click(br.BUTTON, br.DATAITEM, subject, click))
        self.assertFalse(br.link_repeats_row_click(br.HYPERLINK, br.BUTTON, subject, click))
        self.assertFalse(br.link_repeats_row_click(br.HYPERLINK, br.DATAITEM, subject, None))

    def test_button_that_fills_the_row(self):
        row = Rect(65, 253, 428, 73)
        self.assertTrue(br.button_fills_row(br.BUTTON, br.LISTITEM, Rect(75, 253, 408, 73), row))
        self.assertFalse(br.button_fills_row(br.BUTTON, br.DATAITEM, Rect(88, 211, 48, 48), Rect(65, 199, 428, 73)))
        gmail = Rect(250, 300, 1662, 26)
        self.assertFalse(br.button_fills_row(br.BUTTON, br.DATAITEM, Rect(560, 303, 1288, 19), gmail))
        self.assertFalse(br.button_fills_row(br.HYPERLINK, br.LISTITEM, Rect(75, 253, 408, 73), row))
        self.assertFalse(br.button_fills_row(br.BUTTON, br.BUTTON, Rect(75, 253, 408, 73), row))
        self.assertFalse(br.button_fills_row(br.BUTTON, br.LISTITEM, Rect(75, 253, 408, 73), Rect()))

    def test_archived_chat_gets_number_message_does_not(self):
        row, clickable = Rect(65, 213, 428, 73), Rect(75, 213, 408, 73)
        self.assertTrue(br.chat_without_role(br.GROUP, True, clickable, br.GROUP, "group", True, row, False))
        self.assertTrue(br.chat_without_role(br.GROUP, True, clickable, br.GROUP, "", True, row, False))
        self.assertTrue(br.chat_without_role(br.GROUP, True, Rect(75, 289, 408, 92), br.GROUP, "group", True,
                                             Rect(65, 289, 428, 92), False))
        self.assertFalse(br.chat_without_role(br.GROUP, True, clickable, br.GROUP, "article", True, row, False))
        message = Rect(502, 64, 1408, 47)
        self.assertFalse(br.chat_without_role(br.GROUP, True, message, br.DATAITEM, "row", True, message, False))
        self.assertFalse(br.chat_without_role(br.GROUP, True, clickable, br.GROUP, "", True, row, True))
        self.assertFalse(br.chat_without_role(br.GROUP, False, clickable, br.GROUP, "", True, row, False))
        self.assertFalse(br.chat_without_role(br.GROUP, True, clickable, br.GROUP, "", False, row, False))
        self.assertFalse(br.chat_without_role(br.GROUP, True, Rect(65, 213, 428, 8190), br.GROUP, "", True,
                                              Rect(65, 213, 428, 8190), False))
        self.assertFalse(br.chat_without_role(br.GROUP, True, Rect(0, 0, 400, 80), br.GROUP, "", True, row, False))
        self.assertFalse(br.chat_without_role(br.BUTTON, True, clickable, br.GROUP, "", True, row, False))

    def test_interactive_and_caption(self):
        self.assertTrue(br.is_interactive(br.BUTTON, False))
        self.assertTrue(br.is_interactive(br.PANE + 1000, True))      # control propio enfocable
        self.assertFalse(br.is_interactive(br.GROUP, True))           # contenedor enfocable: no
        self.assertFalse(br.is_interactive(br.TEXT, False))
        for name in ("Fechar", " minimizar ", "Close", "Cerrar"):
            self.assertTrue(br.is_caption_name(name))
        self.assertFalse(br.is_caption_name("Fechar aba"))

    def test_duplicates_need_same_name_and_proximity(self):
        pts, names = [(100, 100)], ["Buscar"]
        self.assertTrue(br.is_duplicate(pts, names, (104, 98), "Buscar"))
        self.assertFalse(br.is_duplicate(pts, names, (104, 98), "Estrella"))
        self.assertFalse(br.is_duplicate(pts, names, (120, 100), "Buscar"))


class Overlays(unittest.TestCase):
    def test_communities_buttons_below_are_checked_theirs_are_not(self):
        parent = Rect(0, 34, 1920, 998)
        communities = Rect(0, 34, 1920, 998)
        self.assertTrue(br.is_overlay_candidate(communities, parent))
        self.assertFalse(br.is_overlay_candidate(Rect(57, 34, 381, 998), parent))
        self.assertFalse(br.is_overlay_candidate(Rect(0, 0, 100, 100), Rect(0, 0, 100, 100)))

        overlay_rects = [Rect(0, 0, 1920, 1032), communities]
        parent_of_overlay, overlay_doc = [-1, 0], [0, 0]
        centers = [(28, 61), (103, 153), (243, 212), (250, 131), (960, 10), (200, 500)]
        rects = [Rect(10, 43, 37, 37), Rect(76, 139, 54, 29), Rect(58, 179, 370, 66),
                 Rect(58, 98, 380, 66), Rect(940, 0, 40, 20), Rect(190, 490, 20, 20)]
        overlay_of, doc_of = [0, 0, 0, 1, 0, -1], [0, 0, 0, 0, 0, -1]
        covering = br.overlays_covering(centers, rects, overlay_of, doc_of, parent_of_overlay, overlay_rects, overlay_doc)
        self.assertEqual(covering[0], [1])
        self.assertEqual(covering[1], [1])
        self.assertEqual(covering[2], [1])
        self.assertIsNone(covering[3])
        self.assertIsNone(covering[4])
        self.assertIsNone(covering[5])

    def test_plain_page_wrapper_containing_everything_covers_nobody(self):
        overlay_rects = [Rect(0, 87, 1905, 945)]
        centers = [(300, 300), (900, 600)]
        rects = [Rect(290, 290, 20, 20), Rect(890, 590, 20, 20)]
        for overlay_of in ([0, 0], [-1, -1]):
            covering = br.overlays_covering(centers, rects, overlay_of, [0, 0], [-1], overlay_rects, [0])
            self.assertEqual(covering, [None, None])
        covering = br.overlays_covering([(500, 500), (400, 400)], [Rect(0, 0, 1920, 1080), Rect(390, 390, 20, 20)],
                                        [-1, 0], [0, 0], [-1], overlay_rects, [0])
        self.assertIsNone(covering[0])

    def test_leaves_only_with_positive_proof(self):
        self.assertTrue(br.leaves_by_overlay(-1, 4))
        self.assertFalse(br.leaves_by_overlay(0, -1))
        self.assertFalse(br.leaves_by_overlay(2, -1))
        self.assertFalse(br.leaves_by_overlay(-1, -1))
        self.assertTrue(br.inside_overlay(3, [-1, 0, 1, 2], 1))
        self.assertFalse(br.inside_overlay(3, [-1, 0, 1, 2], 4))
        self.assertFalse(br.inside_overlay(-1, [-1], 0))

    def test_taskbar_by_root_class(self):
        self.assertTrue(br.is_taskbar_class("Shell_TrayWnd"))
        self.assertTrue(br.is_taskbar_class("Shell_SecondaryTrayWnd"))
        self.assertFalse(br.is_taskbar_class("Chrome_WidgetWin_1"))
        self.assertFalse(br.is_taskbar_class(""))


class AimAndLinks(unittest.TestCase):
    def test_click_that_lands_on_another_button_is_suspect_inner_one_is_not(self):
        rects = [Rect(640, 95, 238, 48), Rect(690, 102, 34, 34), Rect(697, 208, 467, 104),
                 Rect(710, 290, 94, 21), Rect(1300, 600, 60, 20)]
        centers = centers_of(rects)
        serial, parent = [0, 1, 2, 3, 4], [-1, -1, -1, 2, -1]
        partners = br.aim_partners(centers, rects, serial, parent)
        self.assertEqual(partners[1], [0])
        self.assertIsNone(partners[3])
        self.assertIsNone(partners[2])
        self.assertIsNone(partners[4])
        self.assertIsNone(partners[0])
        self.assertTrue(br.is_ancestor(2, 3, parent))
        self.assertFalse(br.is_ancestor(3, 2, parent))
        self.assertFalse(br.is_ancestor(-1, 3, parent))

    def test_links_to_the_same_address_get_one_number(self):
        types = [br.HYPERLINK, br.HYPERLINK, br.HYPERLINK, br.BUTTON, br.HYPERLINK, br.HYPERLINK, br.HYPERLINK, br.HYPERLINK]
        urls = ["https://x.com/a", "https://x.com/a", "https://x.com/b", "https://x.com/a", "#", "#",
                "javascript:void(0)", ""]
        self.assertEqual(br.repeated_links(types, urls), [False, True, False, False, False, False, False, False])
        self.assertTrue(br.is_real_address("https://mail.google.com/mail/u/0/#inbox"))
        self.assertFalse(br.is_real_address("JavaScript:abrir()"))
        self.assertFalse(br.is_real_address(None))


class Names(unittest.TestCase):
    def test_match_ignores_case_and_accents(self):
        self.assertTrue(br.name_matches("Cancelar gravação", "cancelar gravacao"))
        self.assertTrue(br.name_matches("  Enviar ", "enviar"))
        self.assertFalse(br.name_matches("Enviar mensagem de voz", "Enviar"))
        self.assertTrue(br.name_matches("Enviar mensagem de voz", "*mensagem de VOZ"))
        self.assertFalse(br.name_matches("", "x"))
        self.assertFalse(br.name_matches("x", ""))


class RectSemantics(unittest.TestCase):
    """Rect sigue System.Drawing.Rectangle: el borde derecho e inferior no pertenecen al rectángulo."""

    def test_edges(self):
        r = Rect(10, 10, 20, 20)
        self.assertTrue(r.contains_point(10, 10))
        self.assertFalse(r.contains_point(30, 15))
        self.assertTrue(r.contains_rect(Rect(10, 10, 20, 20)))
        self.assertFalse(r.contains_rect(Rect(10, 10, 21, 20)))
        self.assertFalse(r.intersects(Rect(30, 10, 5, 5)))
        self.assertTrue(r.intersects(Rect(29, 29, 5, 5)))
        self.assertTrue(r.intersection(Rect(40, 40, 5, 5)).is_empty)


if __name__ == "__main__":
    unittest.main()
