"""Modo botones numerados: enumeración de los elementos clicables de la ventana activa.

Adaptado de la versión 1.5 de XULIA (BotonesNumerados.cs). Usa UI Automation por COM (comtypes):
la UI Automation "gestionada" antigua no ve dentro de WinUI 3 / WebView2 (WhatsApp, Configuración).

Robustez (quien controla el PC solo por voz no puede quedarse con el programa colgado):
  - búsqueda en ANCHURA con poda (un nodo fuera del área de la ventana no se visita) y presupuesto
    de tiempo y de nodos: las aplicaciones web enormes no estiran el comando;
  - todo corre en un hilo de fondo con tiempo máximo;
  - nunca se inspecciona el propio proceso (un cliente UIA sobre uno mismo es un bloqueo mortal).

Numeración CONTENIDO PRIMERO: en un navegador la búsqueda en anchura halla el "cromo" (barra,
pestañas, favoritos) antes que la página; los elementos dentro de un Document se numeran primero.
"""
import collections
import ctypes
import os
import time
from ctypes import wintypes

import buttons_rules as br
from buttons_rules import Rect

BFS_BUDGET = 3.0          # s: presupuesto interno de la búsqueda
MAX_NODES = 5000          # tope de nodos recorridos (apps web enormes)
ENUM_TIMEOUT = 4.0        # s: tope duro del hilo de enumeración
BAND_TOP_PX = 46          # franja superior donde vive el marco de la ventana
# Con el tope de 99 y "contenido primero" (como en la 1.5), una página con mucho contenido se lleva los
# 99 números y las pestañas y la barra de favoritos del navegador se quedan sin ninguno. Se reservan
# hasta CHROME_RESERVE números para el marco SOLO cuando no cabe todo; con 0 se obtiene la 1.5 exacta.
CHROME_RESERVE = int(os.environ.get("XULIA2_CHROME_RESERVE", "15"))

# propiedades UIA que se piden en la caché (una sola llamada entre procesos por elemento)
_P_RECT, _P_PID, _P_TYPE, _P_NAME, _P_FOCUSABLE, _P_ENABLED = 30001, 30002, 30003, 30005, 30009, 30010
_P_OFFSCREEN, _P_ARIA, _P_VALUE, _P_READONLY, _P_INVOKABLE, _P_ISDIALOG = 30022, 30101, 30045, 30046, 30031, 30174
LAYER_ROLES = {"dialog", "alertdialog", "menu"}

user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_ENUM_PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_ENUM_PROC, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, _ENUM_PROC, wintypes.LPARAM]


# --- ventanas ----------------------------------------------------------------------------------

def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(200)
    user32.GetClassNameW(hwnd, buf, 200)
    return buf.value


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(300)
    user32.GetWindowTextW(hwnd, buf, 300)
    return buf.value


def window_pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return Rect.from_ltrb(r.left, r.top, r.right, r.bottom)


def render_windows(window, include_own=False):
    """Ventanas de contenido web (Chrome_RenderWidgetHostHWND) que pertenecen a `window` pero la
    ventana de arriba NO alcanza: contenido alojado en OTRA ventana superior de otro proceso
    (WebView2 es multiproceso; en WhatsApp la ventana de render tiene otro PID). Si la render es de
    la propia ventana (Chrome/Edge normales) la búsqueda normal ya pasa por ella."""
    found = []
    own_title = window_title(window).strip().lower()

    def on_child(kid, _):
        if class_name(kid) != "Chrome_RenderWidgetHostHWND":
            return True
        root = user32.GetAncestor(kid, 2)   # GA_ROOT
        if root == window and not include_own:
            return True
        root_title = window_title(root).strip().lower()
        if len(own_title) >= 3 and len(root_title) >= 3 and (own_title in root_title or root_title in own_title):
            found.append(kid)
        return True

    child_cb = _ENUM_PROC(on_child)

    def on_top(top, _):
        user32.EnumChildWindows(top, child_cb, 0)
        return True

    try:
        user32.EnumWindows(_ENUM_PROC(on_top), 0)
    except Exception:
        pass
    return found


def behind_taskbar(x, y):
    """El centro está debajo de la barra de tareas (pregunta barata de Windows, sin UIA). Se mira la
    RAÍZ de la ventana en el punto, no el área útil: en pantalla completa la barra no está."""
    try:
        h = user32.WindowFromPoint(wintypes.POINT(x, y))
        if not h:
            return False
        return br.is_taskbar_class(class_name(user32.GetAncestor(h, 2) or h))
    except Exception:
        return False   # ante la duda, el número se queda


# --- UI Automation -----------------------------------------------------------------------------

def load_uia():
    """(módulo UIAutomationClient, IUIAutomation) para el hilo actual; COM multihilo."""
    import comtypes
    import comtypes.client
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except OSError:
        pass   # el hilo ya tenía COM iniciado
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as uc
    return uc, comtypes.client.CreateObject(uc.CUIAutomation8, interface=uc.IUIAutomation)


def _make_cache(uia):
    cache = uia.CreateCacheRequest()
    for prop in (_P_RECT, _P_TYPE, _P_NAME, _P_FOCUSABLE, _P_ENABLED, _P_OFFSCREEN, _P_ARIA, _P_PID,
                 _P_READONLY, _P_VALUE, _P_INVOKABLE):
        cache.AddProperty(prop)
    try:
        cache.AddProperty(_P_ISDIALOG)   # Windows 10 1809+
    except Exception:
        pass
    return cache


def _cached(el, prop):
    try:
        return el.GetCachedPropertyValue(prop)
    except Exception:
        return None


def _cached_text(el, prop):
    value = _cached(el, prop)
    return value if isinstance(value, str) else ""


def _cached_bool(el, prop):
    value = _cached(el, prop)
    return value if isinstance(value, bool) else False


def _cached_rect(el):
    r = el.CachedBoundingRectangle
    return Rect.from_ltrb(r.left, r.top, r.right, r.bottom)


def _is_layer(el, control_type, in_doc):
    """Diálogo o menú dentro del contenido web (Chrome da role=dialog como Window)."""
    if not in_doc or control_type == br.DOCUMENT:
        return False
    if control_type in (br.MENU, br.WINDOW):
        return True
    if _cached_text(el, _P_ARIA) in LAYER_ROLES:
        return True
    return _cached_bool(el, _P_ISDIALOG)


class _Node:
    """Nodo de la búsqueda en anchura, con la región en la que está."""
    __slots__ = ("el", "in_tab", "in_doc", "layer", "in_numbered", "via_render", "numbered_type",
                 "numbered_serial", "numbered_center", "numbered_rect", "overlay", "document")

    def __init__(self, el, in_tab=False, in_doc=False, layer=-1, in_numbered=False, via_render=False):
        self.el, self.in_tab, self.in_doc, self.layer = el, in_tab, in_doc, layer
        self.in_numbered, self.via_render = in_numbered, via_render
        self.numbered_type, self.numbered_serial = 0, -1
        self.numbered_center, self.numbered_rect = None, Rect()
        self.overlay, self.document = -1, -1


class Target:
    """Un elemento numerable y lo que las fases siguientes necesitan saber de él."""
    __slots__ = ("element", "point", "rect", "ctype", "is_content", "layer", "overlay", "doc", "serial", "url")

    def __init__(self, element, point, rect, ctype, is_content, layer, overlay, doc, serial, url):
        self.element, self.point, self.rect, self.ctype = element, point, rect, ctype
        self.is_content, self.layer, self.overlay, self.doc, self.serial, self.url = is_content, layer, overlay, doc, serial, url


class Enumeration:
    """Resultado de enumerate_targets: los objetivos en el orden del número, más los datos de capas y
    superposiciones que usa la detección de fantasmas."""

    def __init__(self):
        self.targets = []
        self.layer_rects, self.layer_parent = [], []
        self.overlay_rects, self.overlay_parent, self.overlay_doc, self.overlay_elements = [], [], [], []
        self.parent_of_serial = []
        self.hosted = False        # la app aloja su contenido en una ventana de render propia
        self.visited = 0
        self.elapsed = 0.0
        self.note = ""


def enumerate_targets(hwnd, area, show_close_tab=False):
    """Recorre la ventana `hwnd` (y sus ventanas de render) y devuelve una Enumeration. Corre en un
    hilo de fondo; ver collect_targets para llamarla con tope de tiempo."""
    uc, uia = load_uia()
    cache = _make_cache(uia)
    walker = uia.RawViewWalker
    out = Enumeration()

    layer_rects, layer_parent = out.layer_rects, out.layer_parent
    overlay_rects, overlay_parent, overlay_doc = out.overlay_rects, out.overlay_parent, out.overlay_doc
    overlay_elements, parent_of_serial = out.overlay_elements, out.parent_of_serial
    content, chrome = [], []              # Target de la página y del marco, en orden de hallazgo
    with_numbered_item = set()
    taken_points, taken_names = [], []
    next_serial = documents = visited = 0

    root = uia.ElementFromHandleBuildCache(hwnd, cache)
    renders = render_windows(hwnd)
    out.hosted = bool(renders)
    extra_roots = []
    for hr in renders:
        try:
            el = uia.ElementFromHandleBuildCache(hr, cache)
            if el:
                extra_roots.append(el)
        except Exception:
            pass
    is_chromium = class_name(hwnd) == "Chrome_WidgetWin_1"
    render_pids = {window_pid(hr) for hr in renders if window_pid(hr)}

    queue = collections.deque([_Node(root)])
    # contenido web alojado: entra como CONTENIDO (delante en la numeración)
    for el in extra_roots:
        queue.append(_Node(el, in_doc=True, via_render=True))

    started = time.time()
    limit_reached = lambda: (time.time() - started >= BFS_BUDGET or visited >= MAX_NODES
                             or (len(content) >= br.MAX_ELEMENTS and len(chrome) >= br.MAX_ELEMENTS))

    while queue and not limit_reached():
        node = queue.popleft()
        try:
            child = walker.GetFirstChildElementBuildCache(node.el, cache)
        except Exception:
            continue
        try:
            parent_rect = _cached_rect(node.el)
        except Exception:
            parent_rect = Rect()
        parent_type, parent_role, parent_focusable = 0, "", False
        if node.via_render:   # el padre, para la conversación sin papel
            try:
                parent_type = node.el.CachedControlType
                parent_focusable = bool(node.el.CachedIsKeyboardFocusable)
            except Exception:
                pass
            parent_role = _cached_text(node.el, _P_ARIA)

        while child and not limit_reached():
            visited += 1
            try:
                ctype = child.CachedControlType
                repeated_content = False
                if not node.via_render and render_pids:
                    try:
                        repeated_content = child.CachedProcessId in render_pids
                    except Exception:
                        pass
                # se poda (ni se numera ni se baja): barra de título, menú de sistema, barra de
                # desplazamiento (tienen comando propio) y el contenido de render que llegó por arriba
                if repeated_content or ctype in (br.TITLEBAR, br.MENUBAR, br.SCROLLBAR):
                    child = _next(walker, child, cache)
                    continue

                rect = _cached_rect(child)
                rect_valid = rect.width > 1 and rect.height > 1
                layer_here = node.layer
                if rect_valid and _is_layer(child, ctype, node.in_doc):
                    layer_here = len(layer_rects)
                    layer_rects.append(rect)
                    layer_parent.append(node.layer)
                doc_here = documents if ctype == br.DOCUMENT else node.document
                if ctype == br.DOCUMENT:
                    documents += 1
                overlay_here = node.overlay
                if (node.in_doc and rect_valid and ctype != br.DOCUMENT and layer_here == node.layer
                        and br.is_overlay_candidate(rect, parent_rect)):
                    overlay_here = len(overlay_rects)
                    overlay_rects.append(rect)
                    overlay_parent.append(node.overlay)
                    overlay_doc.append(doc_here)
                    overlay_elements.append(child)

                # poda: subárbol totalmente fuera de la ventana; rect vacío = contenedor, sigue bajando
                if not rect_valid or rect.intersects(area):
                    cx, cy = rect.x + rect.width // 2, rect.y + rect.height // 2
                    in_top_band = cy < area.y + BAND_TOP_PX
                    focusable = bool(child.CachedIsKeyboardFocusable)
                    name = child.CachedName or ""
                    name_empty = name.strip() == ""

                    # (1) en el marco de un navegador solo se numera lo ENFOCABLE: quita de golpe los
                    #     "botones fantasma" (favoritos de una barra oculta, restos de pestañas)
                    chrome_not_focusable = (is_chromium and not node.in_doc and not focusable
                                            and not (node.in_tab and show_close_tab))
                    # (2) botones del marco de la ventana: tienen comando de voz propio
                    frame_button = not node.in_doc and in_top_band and br.is_caption_name(name)
                    # (3) sin nombre y (no enfocable o grande): contenedor o icono invisible
                    chat_no_role = node.via_render and node.in_doc and br.chat_without_role(
                        ctype, _cached_bool(child, _P_INVOKABLE), rect, parent_type, parent_role,
                        parent_focusable, parent_rect, node.in_numbered)
                    no_name = name_empty and (not focusable or rect.width >= 220 or rect.height >= 140) and not chat_no_role
                    # (4) imagen dentro de algo ya numerado; (5) emoji suelto en el texto
                    image_inside = br.image_inside_numbered(ctype, node.in_numbered)
                    emoji_only = br.is_emoji_only_image(ctype, name)
                    # (6) pieza de una fila ya numerada; (7) botón que ocupa la fila entera
                    read_only = ctype == br.EDIT and _cached_bool(child, _P_READONLY)
                    row_piece = (br.cell_inside_row(ctype, node.numbered_type, read_only)
                                 or (node.in_doc and br.link_repeats_row_click(
                                     ctype, node.numbered_type, rect, node.numbered_center)))
                    fills_row = node.in_doc and br.button_fills_row(ctype, node.numbered_type, rect, node.numbered_rect)

                    exclude = (chrome_not_focusable or frame_button or no_name or image_inside
                               or emoji_only or row_piece or fills_row)
                    numbered_here, serial_here = False, -1
                    if (rect_valid and not exclude and (br.is_interactive(ctype, focusable) or chat_no_role)
                            and child.CachedIsEnabled and not child.CachedIsOffscreen
                            and area.contains_point(cx, cy) and not behind_taskbar(cx, cy)):
                        point = (cx, cy)
                        if not br.is_duplicate(taken_points, taken_names, point, name):
                            taken_points.append(point)
                            taken_names.append(name)
                            numbered_here, serial_here = True, next_serial
                            next_serial += 1
                            parent_of_serial.append(node.numbered_serial)
                            if node.numbered_serial >= 0:
                                with_numbered_item.add(node.numbered_serial)
                            url = _cached_text(child, _P_VALUE) if ctype == br.HYPERLINK else ""
                            if node.in_doc and len(content) < br.MAX_ELEMENTS:
                                content.append(Target(child, point, rect, ctype, True, layer_here, overlay_here, doc_here, serial_here, url))
                            elif not node.in_doc and len(chrome) < br.MAX_ELEMENTS:
                                chrome.append(Target(child, point, rect, ctype, False, layer_here, overlay_here, doc_here, serial_here, url))

                    nxt = _Node(child, node.in_tab or ctype == br.TABITEM, node.in_doc or ctype == br.DOCUMENT,
                                layer_here, node.in_numbered or numbered_here, node.via_render)
                    nxt.numbered_type = ctype if numbered_here else node.numbered_type
                    nxt.numbered_serial = serial_here if numbered_here else node.numbered_serial
                    nxt.numbered_center = (rect.x + rect.width // 2, rect.y + rect.height // 2) if numbered_here else node.numbered_center
                    nxt.numbered_rect = rect if numbered_here else node.numbered_rect
                    nxt.overlay, nxt.document = overlay_here, doc_here
                    queue.append(nxt)
            except Exception:
                pass   # el elemento desapareció a mitad de camino
            child = _next(walker, child, cache)

    # salida CONTENIDO-PRIMERO; el marco (barra de herramientas, menú) con elementos numerados dentro
    # se queda fuera (regla B)
    content_ok = [x for x in content if not br.frame_with_numbered_items(x.ctype, x.serial in with_numbered_item)]
    chrome_ok = [x for x in chrome if not br.frame_with_numbered_items(x.ctype, x.serial in with_numbered_item)]
    room = br.MAX_ELEMENTS
    if len(content_ok) + len(chrome_ok) > room:   # no cabe todo: el marco conserva su reserva
        room -= min(len(chrome_ok), CHROME_RESERVE)
    out.targets = content_ok[:room]
    out.targets += chrome_ok[:br.MAX_ELEMENTS - len(out.targets)]
    out.visited = visited
    find_ghosts(out, hwnd, started)   # capas, superposiciones y enlaces repetidos, antes de dibujar
    out.elapsed = time.time() - started
    return out


def _next(walker, child, cache):
    try:
        nxt = walker.GetNextSiblingElementBuildCache(child, cache)
        return nxt if nxt else None
    except Exception:
        return None


def collect_targets(hwnd, show_close_tab=False):
    """Enumera la ventana `hwnd` con tope de tiempo. Devuelve (Enumeration o None, motivo)."""
    import threading
    if not hwnd:
        return None, "sin ventana en primer plano"
    if window_pid(hwnd) == os.getpid():
        return None, "la ventana activa es el propio XULIA2"   # cliente UIA sobre uno mismo = bloqueo
    area = window_rect(hwnd)
    box = {}

    def work():
        try:
            box["result"] = enumerate_targets(hwnd, area, show_close_tab)
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(ENUM_TIMEOUT)
    if worker.is_alive():
        return None, f"tiempo agotado en la enumeración UIA ({ENUM_TIMEOUT:.0f} s)"
    if "error" in box:
        return None, "error en la enumeración: " + box["error"]
    result = box["result"]
    if not result.targets:
        return None, "ningún elemento clicable encontrado"
    return result, ""


# --- números hablados ------------------------------------------------------------------------

_UNITS = {
    "es": {"uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9},
    "pt": {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9},
}
_TEENS = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16,
    "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19, "dezanove": 19, "vinte": 20,
}
_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
         "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "oitenta": 80}


def _plain(text):
    """Minúsculas sin tildes ni eñes."""
    import unicodedata
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_FILLERS = {"numero", "boton", "botao", "el", "la", "o", "a"}


def spoken_number(text):
    """Número del 1 al 99 si la frase ENTERA es un número: cifras ("12"), palabras en español o
    portugués ("doce", "treinta y cinco", "trinta e cinco"), con "número" o "botón" delante.
    None en cualquier otro caso: "función cinco" es un comando, no el botón 5."""
    import re
    words = [w for w in re.findall(r"[a-z]+|\d+", _plain(text or "")) if w]
    while words and words[0] in _FILLERS:
        words = words[1:]
    units = {**_UNITS["es"], **_UNITS["pt"]}
    if len(words) == 1:
        word = words[0]
        if word.isdigit():
            return int(word) if 1 <= int(word) <= br.MAX_ELEMENTS else None
        return _TENS.get(word) or _TEENS.get(word) or units.get(word)
    if len(words) == 3 and words[0] in _TENS and words[1] in ("y", "e") and words[2] in units:
        return _TENS[words[0]] + units[words[2]]
    return None


# --- clic -----------------------------------------------------------------------------------

CLICK_PATTERN_TIMEOUT = 1.5   # s: un proveedor colgado no puede congelar el reconocimiento de voz
_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP = 0x02, 0x04
_PATTERN_INVOKE, _PATTERN_TOGGLE, _PATTERN_SELECTION_ITEM, _PATTERN_EXPAND_COLLAPSE = 10000, 10015, 10010, 10005


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _Input(ctypes.Structure):
    class _Union(ctypes.Union):
        _fields_ = [("mi", _MouseInput)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


_MOVE, _ABSOLUTE, _VIRTUALDESK = 0x0001, 0x8000, 0x4000


def _send_mouse(point, button_flag):
    """Un evento de ratón en una posición ABSOLUTA: el evento lleva su propia posición, así que cae en el
    punto aunque el puntero se esté moviendo (ratón de cabeza, otro dispositivo)."""
    left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)      # SM_XVIRTUALSCREEN / YVIRTUALSCREEN
    width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)  # SM_CXVIRTUALSCREEN / CYVIRTUALSCREEN
    nx = int((point[0] - left) * 65535 / max(1, width - 1))
    ny = int((point[1] - top) * 65535 / max(1, height - 1))
    event = _Input(type=0, mi=_MouseInput(nx, ny, 0, _MOVE | _ABSOLUTE | _VIRTUALDESK | button_flag, 0, 0))
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input))


def physical_click(point):
    """Clic físico con pulsación y suelta separadas (un solo evento suele no registrarse en Chrome ni en
    apps modernas), cada una con la posición absoluta del punto. Exige que la ventana de números deje
    pasar el ratón."""
    point = (int(point[0]), int(point[1]))
    _send_mouse(point, 0)
    time.sleep(0.06)
    _send_mouse(point, _MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.04)
    _send_mouse(point, _MOUSEEVENTF_LEFTUP)


def _act_by_pattern(element):
    """Invoke, Toggle, Select o Expand/Collapse: lo primero que el elemento admita. False si ninguno."""
    uc, _ = load_uia()

    def pattern(pattern_id, interface):
        try:
            found = element.GetCurrentPattern(pattern_id)
            return found.QueryInterface(interface) if found else None
        except Exception:
            return None

    p = pattern(_PATTERN_INVOKE, uc.IUIAutomationInvokePattern)
    if p:
        p.Invoke()
        return True
    p = pattern(_PATTERN_TOGGLE, uc.IUIAutomationTogglePattern)
    if p:
        p.Toggle()
        return True
    p = pattern(_PATTERN_SELECTION_ITEM, uc.IUIAutomationSelectionItemPattern)
    if p:
        p.Select()
        return True
    p = pattern(_PATTERN_EXPAND_COLLAPSE, uc.IUIAutomationExpandCollapsePattern)
    if p:
        if p.CurrentExpandCollapseState == uc.ExpandCollapseState_Expanded:
            p.Collapse()
        else:
            p.Expand()
        return True
    return False   # sin patrón: quien llama cae al clic físico


def act_by_pattern(element):
    """_act_by_pattern con tiempo máximo."""
    import threading
    box = {}

    def work():
        try:
            box["ok"] = _act_by_pattern(element)
        except Exception:
            box["ok"] = False

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(CLICK_PATTERN_TIMEOUT)
    return bool(box.get("ok"))


# --- la ventana de números ------------------------------------------------------------------

_GWL_EXSTYLE = -20
# sin foco, fuera de Alt+Tab y que deje pasar el ratón (clic a través)
_NO_FOCUS_STYLE = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000


def monitor_rect(hwnd):
    """Rectángulo del monitor donde está la ventana (la ventana de números cubre ese monitor)."""
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    monitor = user32.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        m = info.rcMonitor
        return Rect.from_ltrb(m.left, m.top, m.right, m.bottom)
    return Rect(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def layout_labels(targets, hidden, sizes):
    """Posición de cada etiqueta (x, y, ancho, alto) en coordenadas de pantalla, sin solaparse.

    Se ancla en la esquina superior izquierda del ELEMENTO (marca sin ambigüedad cuál es cuál); en
    elementos anchos (pestañas de 256 px) la esquina queda pegada al vecino de la izquierda y confunde:
    ahí se ancla en el CENTRO. Si choca con otra etiqueta ya puesta, baja; si no cabe, va a la derecha.
    `sizes[i]` = (ancho, alto) de la etiqueta i. Los números ocultos (cubiertos) se saltan.
    """
    placed, result = [], {}
    for i, target in enumerate(targets):
        if i < len(hidden) and hidden[i]:
            continue
        w, h = sizes[i]
        rect = target.rect
        if rect.width >= 100:
            x, y = rect.x + rect.width // 2 - w // 2, rect.y + 2
        else:
            x, y = rect.x - 2, rect.y - 2
        candidate = Rect(x, y, w, h)
        for _ in range(6):
            if any(o.intersects(candidate) for o in placed):
                candidate = Rect(candidate.x, candidate.y + h + 2, w, h)
        for _ in range(6):
            if any(o.intersects(candidate) for o in placed):
                candidate = Rect(candidate.x + w + 2, candidate.y, w, h)
        placed.append(candidate)
        result[i] = (candidate.x, candidate.y, w, h)
    return result


class NumberOverlay:
    """Ventana a pantalla completa con los números. Vive en el hilo de Tk de XULIA2: el resto de
    hilos solo encolan trabajo (`tk_queue`)."""

    def __init__(self, tk_queue, root_getter):
        self._queue, self._root_getter = tk_queue, root_getter
        self.window = self.canvas = None
        self._bounds = Rect()

    def show(self, targets, hidden, bounds):
        self._queue.put((self._show, (list(targets), list(hidden), bounds), {}))

    def redraw(self, targets, hidden):
        self._queue.put((self._draw, (list(targets), list(hidden)), {}))

    def hide(self):
        self._queue.put((self._hide, (), {}))

    # --- lo que sigue corre en el hilo de Tk ---
    def _show(self, targets, hidden, bounds):
        import tkinter as tk
        root = self._root_getter()
        if root is None:
            return
        if self.window is None:
            win = tk.Toplevel(root)
            win.withdraw()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(background="#ff00ff")
            win.attributes("-transparentcolor", "#ff00ff")   # el magenta no se pinta: se ve lo de debajo
            win.attributes("-alpha", 0.85)
            self.canvas = tk.Canvas(win, bg="#ff00ff", highlightthickness=0)
            self.canvas.pack(fill="both", expand=True)
            self.window = win
        self._bounds = bounds
        self.window.geometry(f"{bounds.width}x{bounds.height}+{bounds.x}+{bounds.y}")
        self.window.update_idletasks()
        hwnd = user32.GetAncestor(self.window.winfo_id(), 2) or self.window.winfo_id()
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) | _NO_FOCUS_STYLE)
        self._draw(targets, hidden)
        self.window.deiconify()

    def _draw(self, targets, hidden):
        if self.window is None or self.canvas is None:
            return
        import tkinter.font as tkfont
        font = tkfont.Font(family="Arial", size=11, weight="bold")
        sizes = [(font.measure(str(i + 1)) + 10, font.metrics("linespace") + 2) for i in range(len(targets))]
        spots = layout_labels(targets, hidden, sizes)
        self.canvas.delete("all")
        for i, (x, y, w, h) in spots.items():
            x, y = x - self._bounds.x, y - self._bounds.y
            x = max(0, min(x, self._bounds.width - w))
            y = max(0, y)
            self.canvas.create_rectangle(x, y, x + w, y + h, fill="#ffeb3b", outline="black")
            self.canvas.create_text(x + w // 2, y + h // 2, text=str(i + 1), font=font, fill="black")

    def _hide(self):
        if self.window is not None:
            self.window.withdraw()
            if self.canvas is not None:
                self.canvas.delete("all")


# --- el controlador -------------------------------------------------------------------------

AUTO_HIDE_SECONDS = 45   # red de seguridad: la pantalla nunca se queda con números presos


class NumberedButtons:
    """Enumera, numera y hace clic. No sabe de voz: XULIA2 le pasa el número hablado.

    on_auto_hide() se llama si la ventana de números se apaga sola (45 s): quien escucha tiene que
    salir del modo, o el usuario seguiría diciendo números que no hacen nada.
    """

    def __init__(self, tk_queue, root_getter, on_auto_hide=None, log=print):
        self.overlay = NumberOverlay(tk_queue, root_getter)
        self.on_auto_hide, self.log = on_auto_hide, log
        self.enumeration = None
        self.covered = []
        self.reason = ""          # por qué show() devolvió 0 (va al registro)
        self.active = False
        self._timer = None
        self._generation = 0      # cada show() la sube: una comprobación de fondo vieja se descarta sola

    @property
    def targets(self):
        return self.enumeration.targets if self.enumeration else []

    def show(self):
        """Numera la ventana en primer plano. Devuelve cuántos elementos numeró (0 = nada o error)."""
        self.reason = ""
        hwnd = user32.GetForegroundWindow()
        result, why = collect_targets(hwnd)
        # Chromium solo construye el árbol de accesibilidad de la página cuando nota un cliente, y la
        # PRIMERA consulta suele traer solo el marco del navegador: se reintenta hasta 2 veces.
        if result is not None and class_name(hwnd) == "Chrome_WidgetWin_1":
            for _ in range(2):
                if any(target.is_content for target in result.targets):
                    break
                time.sleep(0.5)
                again, _why = collect_targets(hwnd)
                if again is not None:
                    result = again
        if result is None:
            self.reason = why
            self.log(f"Botones: sin números ({why})")
            self.hide()
            return 0
        self.enumeration, self.covered, self.active = result, [False] * len(result.targets), True
        self.overlay.show(result.targets, self.covered, monitor_rect(hwnd))
        self._restart_timer()
        self.log(f"Botones: {len(result.targets)} numerados en {result.elapsed:.2f} s ({result.visited} nodos)")
        if result.note:
            self.log("Botones: " + result.note)
        # los números salen YA; la comprobación de fondo (~33 ms por punto) esconde después los cubiertos
        if any(target.is_content for target in result.targets):
            import threading
            self._generation += 1
            generation = self._generation
            threading.Thread(target=self._check_in_background, args=(result, hwnd, self.covered, generation),
                             daemon=True).start()
        return len(result.targets)

    def _check_in_background(self, result, hwnd, covered, generation):
        def current():
            return self.active and generation == self._generation
        applied = check_points(result, hwnd, covered, current, self.log)
        if applied and current():
            self.overlay.redraw(result.targets, covered)

    def is_covered(self, number):
        return 1 <= number <= len(self.covered) and self.covered[number - 1]

    def click(self, number):
        """Hace clic en el elemento `number`. True solo si lo consiguió (entonces se sigue en el modo)."""
        targets = self.targets
        if not 1 <= number <= len(targets):
            self.reason = f"el número {number} no existe (hay {len(targets)})"
            return False
        if self.is_covered(number):
            self.reason = f"el número {number} estaba cubierto por otra cosa"
            return False
        target = targets[number - 1]
        # contenido web: el Invoke de UIA muchas veces no dispara el manejador de clic de la página,
        # así que va PRIMERO el clic físico. App nativa: el patrón UIA es más preciso e ignora lo que
        # tape o dónde esté el cursor, y el clic físico queda de refuerzo.
        try:
            if target.is_content:
                physical_click(target.point)
                return True
            if act_by_pattern(target.element):
                return True
            physical_click(target.point)
            return True
        except Exception as exc:
            self.reason = f"error al hacer clic: {exc}"
            return False

    def hide(self):
        self.active = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.overlay.hide()

    def _restart_timer(self):
        import threading
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(AUTO_HIDE_SECONDS, self._auto_hide)
        self._timer.daemon = True
        self._timer.start()

    def _auto_hide(self):
        self.hide()
        if self.on_auto_hide:
            try:
                self.on_auto_hide()
            except Exception:
                pass


# --- botones fantasma: lo que está en el árbol pero NO a la vista -------------------------------
# Adaptado de la versión 1.5 (AplicarCamadas, AplicarSobreposicoes, ConferirPontos, PontoPreciso).
#
# El árbol de accesibilidad de una página trae también lo que no se ve: diálogos que la página
# mantiene escondidos (opacity:0 no cuenta como invisible para Chromium), la lista que queda POR
# DEBAJO de un menú abierto, la pantalla anterior viva detrás de un panel... Sin esto esos botones
# reciben número "encima" del vídeo o del menú, "yerran la puntería y salen duplicados".
#
# Lo que separa lo visible del fantasma es preguntarle a Windows QUÉ HAY DE VERDAD en ese punto
# (ElementFromPoint). Chromium responde la PRIMERA pregunta por aproximación; la respuesta precisa
# llega en la SEGUNDA, 10 ms después (medido en la 1.5: sin la espera se equivoca hasta en 11 de 61).
#
# Dos momentos: ANTES de dibujar se deciden las capas y las superposiciones (pocos puntos); DESPUÉS,
# en segundo plano, se comprueban uno a uno los puntos del contenido web (unos 33 ms cada uno): el
# número de un botón cubierto desaparece, los demás NO cambian (renumerar a mitad de lectura sería
# peor que el fantasma) y decir un número que desapareció no hace clic.
# Todo se queda del lado de MANTENER números: un error o una respuesta dudosa nunca borran uno.

CHECK_WAIT = 0.010        # s entre la 1ª y la 2ª pregunta del punto
# Quitar un número es lo único irreversible a la vista del usuario, y la respuesta de Chromium sobre
# un punto OSCILA (medido en un menú abierto: la 1.5 también pierde a veces opciones visibles). Por eso
# "cubierto" solo vale si se repite en CONFIRM_ASKS preguntas seguidas; una sola respuesta distinta
# basta para dejar el número. Con 1 se obtiene el comportamiento exacto de la 1.5.
CONFIRM_ASKS = int(os.environ.get("XULIA2_CONFIRM_ASKS", "3"))
CONFIRM_GAP = 0.015       # s entre una pregunta y su confirmación
CHECK_CAP = 8.0           # s: tope de la comprobación de fondo
LAYERS_CAP = 0.7          # s: tope de las capas (antes de dibujar)
OVERLAP_CAP = 1.2         # s: tope de las superposiciones (antes de dibujar)
ENUM_TOTAL_CAP = 3.6      # s: ENUM_TIMEOUT tiene que sobrar
_OBJID_CLIENT = 0xFFFFFFFC
_ROLE_DOCUMENT = 15       # ROLE_SYSTEM_DOCUMENT


class PrecisePoint:
    """Qué ocupa un punto de la pantalla, con dos caminos.

    UIA: ElementFromPoint dos veces. Si la respuesta es el marco WinUI ("Microsoft.UI.Content.", el caso
    de WhatsApp: WinUI 3 + WebView2) la pregunta se desvía por MSAA a la ventana de RENDER y el botón se
    reconoce por su RECTÁNGULO. Respuestas: "OK" (es él o algo dentro), "ROUGH" (un ascendiente: la app
    no detalla el punto), "COVERED" (otra cosa lo ocupa), "ERROR".
    """

    def __init__(self, uia, window):
        self.uia, self.walker, self.window = uia, uia.RawViewWalker, window
        self._msaa_roots = None
        self.island = False        # ya se vio el marco WinUI: se va directo por MSAA
        self.last = ""             # descripción de lo último que había en el punto (para el registro)

    def classify(self, point, element, rect, own_pid, layer_rect=None, insist=False):
        if not self.island:
            uc, _ = load_uia()
            pt = uc.tagPOINT(int(point[0]), int(point[1]))
            self.uia.ElementFromPoint(pt)          # dispara la prueba precisa
            time.sleep(CHECK_WAIT)
            hit = self.uia.ElementFromPoint(pt)
            if not self._is_winui_frame(hit):
                self.last = self._describe(hit, own_pid)
                verdict = self._classify_uia(hit, element)
                for _ in range(CONFIRM_ASKS - 1):
                    if verdict != "COVERED":
                        break   # una sola respuesta distinta basta: el número se queda
                    time.sleep(CONFIRM_GAP)
                    verdict = self._classify_uia(self.uia.ElementFromPoint(pt), element)
                return verdict
            self.island = True
        return self._classify_msaa(point, rect, layer_rect, insist)

    @staticmethod
    def _is_winui_frame(hit):
        try:
            return bool(hit) and (hit.CurrentClassName or "").startswith("Microsoft.UI.Content.")
        except Exception:
            return False

    @staticmethod
    def _describe(hit, own_pid):
        """Qué había en el punto SIN el texto de la página (el diario no guarda contenido)."""
        if not hit:
            return "(nada)"
        try:
            cls = (hit.CurrentClassName or "")[:40]
            return f"tipo={hit.CurrentControlType} cls={cls}" + (" (EL PROPIO XULIA2)" if hit.CurrentProcessId == own_pid else "")
        except Exception as exc:
            return f"({exc})"

    def _classify_uia(self, hit, element):
        """¿Lo que hay en el punto es el propio botón (o algo dentro)? OK. ¿Un ascendiente suyo? ROUGH."""
        if not hit:
            return "ERROR"
        a = hit
        for _ in range(30):
            if not a:
                break
            if self.uia.CompareElements(a, element):
                return "OK"
            a = self.walker.GetParentElement(a)
        b = self.walker.GetParentElement(element)
        for _ in range(30):
            if not b:
                break
            if self.uia.CompareElements(b, hit):
                return "ROUGH"
            b = self.walker.GetParentElement(b)
        return "COVERED"

    # --- camino MSAA (WinUI 3 + WebView2) ---
    def _roots(self):
        if self._msaa_roots is None:
            import comtypes.client
            comtypes.client.GetModule("oleacc.dll")
            from comtypes.gen import Accessibility as acc
            self._msaa_roots = []
            for h in render_windows(self.window):
                ptr = ctypes.POINTER(acc.IAccessible)()
                hr = ctypes.windll.oleacc.AccessibleObjectFromWindow(
                    h, _OBJID_CLIENT, ctypes.byref(acc.IAccessible._iid_), ctypes.byref(ptr))
                if hr == 0 and ptr:
                    self._msaa_roots.append((window_rect(h), ptr))
        return self._msaa_roots

    def _classify_msaa(self, point, rect, layer_rect, insist):
        root, root_rect = None, Rect()
        for r, ptr in self._roots():
            if r.contains_point(*point):
                root, root_rect = ptr, r
                break
        if root is None:
            self.last = "msaa: sin ventana de render en el punto"
            return "ERROR"
        verdict = self._msaa_once(root, root_rect, point, rect, layer_rect, CHECK_WAIT)
        if verdict == "ROUGH" and insist:
            verdict = self._msaa_once(root, root_rect, point, rect, layer_rect, 0.060)
        return verdict

    def _msaa_once(self, root, root_rect, point, rect, layer_rect, wait):
        hit = self._msaa_hit(root, point, wait)
        if hit is None:
            self.last = "msaa: nada"
            return "ERROR"
        try:
            role = hit.accRole(0)
            role = role if isinstance(role, int) else -1
        except Exception:
            role = -1
        self.last = f"msaa role={role} ({int(wait * 1000)} ms)"
        if self._has_rect(hit, rect, 30):
            return "OK"
        if layer_rect is not None and not layer_rect.is_empty and self._has_rect(hit, layer_rect, 30):
            return "OK"
        # el DOCUMENTO entero es la respuesta aproximada: no decide (el número se queda)
        if role == _ROLE_DOCUMENT or self._has_rect(hit, root_rect, 1):
            return "ROUGH"
        # lo que envuelve al botón entero no prueba que esté cubierto (el WhatsApp pone una capa
        # transparente detrás del menú para cerrarlo con un clic fuera); solo es COVERED cuando OTRA
        # cosa, que no lo envuelve, ocupa el punto
        try:
            x, y, w, h = hit.accLocation(0)
            if Rect(x - 2, y - 2, w + 4, h + 4).contains_rect(rect):
                return "ROUGH"
        except Exception:
            return "ROUGH"
        return "COVERED"

    @staticmethod
    def _msaa_hit(root, point, wait):
        from comtypes.gen import Accessibility as acc
        try:
            root.accHitTest(int(point[0]), int(point[1]))
        except Exception:
            pass
        time.sleep(wait)
        try:
            found = root.accHitTest(int(point[0]), int(point[1]))
        except Exception:
            return None
        if isinstance(found, int):
            if found == 0:
                return root
            try:
                return root.accChild(found).QueryInterface(acc.IAccessible)
            except Exception:
                return None
        try:
            return found.QueryInterface(acc.IAccessible)
        except Exception:
            return None

    @staticmethod
    def _has_rect(accessible, target, levels):
        """Subiendo hasta `levels` nodos desde `accessible`: ¿alguno tiene el rectángulo `target` (±2 px)?"""
        from comtypes.gen import Accessibility as acc
        a = accessible
        for _ in range(levels):
            if a is None:
                break
            try:
                x, y, w, h = a.accLocation(0)
                if (abs(x - target.x) <= 2 and abs(y - target.y) <= 2
                        and abs(w - target.width) <= 2 and abs(h - target.height) <= 2):
                    return True
            except Exception:
                pass
            try:
                parent = a.accParent
                a = parent.QueryInterface(acc.IAccessible) if parent else None
            except Exception:
                a = None
        return False


def _drop(enumeration, leaving):
    """Quita de la enumeración los objetivos cuyo índice está en `leaving` (conserva el orden)."""
    if leaving:
        enumeration.targets = [t for i, t in enumerate(enumeration.targets) if i not in leaving]


def apply_layers(uia, hwnd, enumeration):
    """Capas (diálogos y menús): decide con 1–2 puntos por capa si está en pantalla. Capa escondida: sus
    botones salen. Capa visible: salen los botones de la PÁGINA que quedan debajo. Devuelve un resumen."""
    layer_rects, layer_parent, targets = enumeration.layer_rects, enumeration.layer_parent, enumeration.targets
    if not layer_rects:
        return ""
    started = time.time()
    precise = PrecisePoint(uia, hwnd)
    hosted = enumeration.hosted
    own_pid = os.getpid()
    # LA PRUEBA DE QUE LA PREGUNTA FUNCIONA AQUÍ: uno o dos botones de la PÁGINA (fuera de capa) tienen
    # que responder "es él". Si hasta ellos salen "cubierto", la pregunta está rota en esta ventana
    # (borró todo WhatsApp en la 1.5) y las capas no deciden nada.
    page = [i for i, t in enumerate(targets) if t.layer < 0 and t.is_content]
    if page:
        probe = [page[0]] if len(page) == 1 else [page[0], page[len(page) // 2]]
        proven = False
        for i in probe:
            try:
                if precise.classify(targets[i].point, targets[i].element, targets[i].rect, own_pid) != "COVERED":
                    proven = True
                    break
            except Exception:
                proven = True   # un error no prueba que esté rota
        if not proven:
            return (f"capas: {len(layer_rects)} -- NO APLICADAS: ni los botones de la página respondieron "
                    f"al punto en esta ventana ({int((time.time() - started) * 1000)} ms)")
    state = [-1] * len(layer_rects)
    for k in range(len(layer_rects)):
        if time.time() - started > LAYERS_CAP:
            break   # el resto queda sin veredicto
        own = [i for i, t in enumerate(targets) if t.layer == k]
        if not own:
            continue
        sample = [own[0]] if len(own) == 1 else [own[0], own[len(own) // 2]]
        classes = []
        for i in sample:
            try:
                c = precise.classify(targets[i].point, targets[i].element, targets[i].rect, own_pid, layer_rects[k], True)
            except Exception:
                c = "ERROR"
            # En apps con ventana de render propia (WhatsApp) la capa solo se CONFIRMA, nunca se condena:
            # el punto de una opción de menú responde el botón de la página que cierra el menú.
            if (precise.island or hosted) and c == "COVERED":
                c = "UNSURE"
            classes.append(c)
            if c == "OK":
                break
        state[k] = br.layer_verdict(classes, len(own))
    leaves = br.decide_by_layers([t.point for t in targets], [t.layer for t in targets], layer_parent, layer_rects, state)
    _drop(enumeration, {i for i, gone in enumerate(leaves) if gone})
    hidden, shown, unknown = state.count(0), state.count(1), state.count(-1)
    return (f"capas: {len(layer_rects)} ({hidden} escondidas, {shown} en pantalla, {unknown} sin veredicto) -- "
            f"{sum(leaves)} botones fuera, {int((time.time() - started) * 1000)} ms" + (" (por MSAA)" if precise.island else ""))


def apply_overlaps(uia, enumeration, budget):
    """Superposiciones (la pantalla anterior viva por debajo de un panel) y puntería (clic que caería en
    otro botón). Un botón solo sale con PRUEBA POSITIVA: error, acierto de un tercero (la barra de tareas)
    o la pregunta que atraviesa dejan el número."""
    targets = enumeration.targets
    centers, rects = [t.point for t in targets], [t.rect for t in targets]
    covering = br.overlays_covering(centers, rects, [t.overlay for t in targets], [t.doc for t in targets],
                                    enumeration.overlay_parent, enumeration.overlay_rects, enumeration.overlay_doc)
    partners = br.aim_partners(centers, rects, [t.serial for t in targets], enumeration.parent_of_serial)
    who_can_hide = [None] * len(targets)
    under = suspects = 0
    for i, t in enumerate(targets):
        if covering[i] is not None and t.is_content:
            under += 1
            who_can_hide[i] = [enumeration.overlay_elements[k] for k in covering[i]]
        # En WhatsApp el punto de una opción de menú responde el botón de la página que cierra el menú:
        # un botón DENTRO de capa nunca sale por puntería allí.
        if partners[i] is not None and not (enumeration.hosted and t.layer >= 0):
            suspects += 1
            who_can_hide[i] = (who_can_hide[i] or []) + [targets[j].element for j in partners[i]]
    work = [i for i in range(len(targets)) if who_can_hide[i] is not None]
    if not work:
        return ""
    summary = f"superposición: {under} botones debajo, puntería: {suspects} sospechosos"
    if budget < 0.150:
        return summary + ", sin tiempo antes de dibujar (queda para la comprobación de fondo)"
    started, checked = time.time(), 0
    walker = uia.RawViewWalker
    uc, _ = load_uia()
    leaving = set()
    for i in work:
        if time.time() - started > budget:
            break
        checked += 1
        try:
            pt = uc.tagPOINT(int(targets[i].point[0]), int(targets[i].point[1]))
            uia.ElementFromPoint(pt)                 # la primera respuesta de Chromium es aproximada
            time.sleep(CHECK_WAIT)
            hit = uia.ElementFromPoint(pt)
            decisions = 0
            for ask in range(CONFIRM_ASKS):
                if ask:
                    time.sleep(CONFIRM_GAP)
                    hit = uia.ElementFromPoint(pt)
                step_button = step_cover = -1
                probe = hit
                for d in range(40):
                    if not probe:
                        break
                    if uia.CompareElements(probe, targets[i].element):
                        step_button = d
                        break
                    if any(uia.CompareElements(probe, other) for other in who_can_hide[i]):
                        step_cover = d
                        break
                    probe = walker.GetParentElement(probe)
                if not br.leaves_by_overlay(step_button, step_cover):
                    break   # una sola respuesta distinta basta: el número se queda
                decisions += 1
            if decisions == CONFIRM_ASKS:
                leaving.add(i)
        except Exception:
            pass   # una pregunta que falla no borra números
    _drop(enumeration, leaving)
    return f"{summary}, {checked} comprobados en {int((time.time() - started) * 1000)} ms, {len(leaving)} fuera"


def apply_repeated_links(enumeration):
    """Enlaces a la misma dirección: se queda el primero. SE HACE AL FINAL: después de todo lo que quita
    números, o un enlace escondido se quedaría con el número y el visible, con la misma dirección, sin ninguno."""
    leaves = br.repeated_links([t.ctype for t in enumeration.targets], [t.url for t in enumeration.targets])
    _drop(enumeration, {i for i, gone in enumerate(leaves) if gone})
    return sum(leaves)


def find_ghosts(enumeration, hwnd, started):
    """Capas, superposiciones y enlaces repetidos sobre una enumeración recién hecha (en el hilo de
    enumeración, antes de dibujar). Nunca tumba la recogida: un error aquí deja la numeración de siempre."""
    notes = []
    try:
        uc, uia = load_uia()
        try:
            note = apply_layers(uia, hwnd, enumeration)
            if note:
                notes.append(note)
        except Exception as exc:
            notes.append(f"capas: error {exc}")
        try:
            left = min(OVERLAP_CAP, ENUM_TOTAL_CAP - (time.time() - started))
            note = apply_overlaps(uia, enumeration, left)
            if note:
                notes.append(note)
        except Exception as exc:
            notes.append(f"superposición: error {exc}")
        try:
            removed = apply_repeated_links(enumeration)
            if removed:
                notes.append(f"enlaces repetidos: {removed} fuera")
        except Exception:
            pass
    except Exception as exc:
        notes.append(f"fantasmas: error {exc}")
    enumeration.note = " | ".join(notes)


def check_points(enumeration, hwnd, covered, still_current, log=print):
    """Comprobación de FONDO de los puntos del contenido web, uno a uno. Rellena `covered[i]` (el número
    se esconde) solo al final y de una vez, y solo si el resultado es plausible: una comprobación que dice
    "casi todo está cubierto" está rota, no acertada. `still_current()` False = la pantalla cambió."""
    targets = enumeration.targets
    checked = covered_count = confirmed = 0
    started, end, found, examples = time.time(), "completa", [], []
    precise = None
    try:
        uc, uia = load_uia()
        own_pid = os.getpid()
        precise = PrecisePoint(uia, hwnd)
        hosted = enumeration.hosted
        for i, t in enumerate(targets):
            if not still_current():
                end = "interrumpida (la pantalla cambió)"
                break
            if time.time() - started > CHECK_CAP:
                end = f"paró en el tope de {CHECK_CAP:.0f} s"
                break
            try:
                owner = user32.WindowFromPoint(wintypes.POINT(t.point[0], t.point[1]))
                point_is_ours = bool(owner) and window_pid(owner) == own_pid
            except Exception:
                point_is_ours = False
            if not br.should_check(True, t.is_content, point_is_ours):
                continue
            try:
                c = precise.classify(t.point, t.element, t.rect, own_pid)
            except Exception:
                c = "ERROR"
            # WhatsApp: el punto atraviesa menús y diálogos; un botón DENTRO de capa nunca se borra aquí
            if (precise.island or hosted) and t.layer >= 0 and c == "COVERED":
                c = "UNSURE"
            checked += 1
            confirmed += c == "OK"
            if br.number_goes_away(c):
                found.append(i)
                if len(examples) < 3:
                    examples.append(precise.last)
    except Exception as exc:
        end = f"error: {exc}"
    if precise is not None and precise.island:
        end += " (por MSAA: marco WinUI)"
    plausible = br.check_is_plausible(checked, len(found), confirmed)
    applied = 0
    if plausible and still_current():
        for i in found:
            covered[i] = True
        applied = len(found)
    log(f"Botones: comprobación {end} -- {checked} de {len(targets)} comprobados en "
        f"{int((time.time() - started) * 1000)} ms, {confirmed} confirmados en pantalla, {applied} cubiertos escondidos"
        + ("" if plausible else f" -- DESCARTADA: {len(found)} de {checked} cubiertos no es plausible, no se escondió ningún número")
        + (f" | en el punto: {' ; '.join(examples)}" if examples else ""))
    return applied


if __name__ == "__main__":   # sonda: python numbered_buttons.py [hwnd]   (sin argumento, la ventana activa)
    import sys
    handle = int(sys.argv[1], 0) if len(sys.argv) > 1 else user32.GetForegroundWindow()
    result, why = collect_targets(handle)
    if result is None:
        print("sin resultado:", why)
    else:
        print(f"{len(result.targets)} numerados, {result.visited} nodos, {result.elapsed:.2f} s, "
              f"alojado={result.hosted}, capas={len(result.layer_rects)}, superposiciones={len(result.overlay_rects)}")
        for number, t in enumerate(result.targets, 1):
            print(f"{number:3}  tipo={t.ctype}  {'web' if t.is_content else 'app'}  {t.rect}  capa={t.layer}")
