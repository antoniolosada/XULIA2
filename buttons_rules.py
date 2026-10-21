"""Reglas puras del modo "botones numerados": qué elemento recibe número y cuál no.

Sin UI Automation, sin ventanas y sin red: son funciones de decisión sobre tipos, rectángulos y
listas, para poder probarlas con datos medidos en aplicaciones reales. Adaptadas de la versión
1.5 de XULIA (BotonesNumerados.cs), donde cada regla nació de un defecto visto en pantalla
(correo web, WhatsApp, Drive, X, Explorador de archivos).

Principio común: ante la duda el número se queda. Un número que sobra estorba; un número que
falta deja al usuario sin forma de llegar al botón.

Equivalencias con la 1.5 (para seguir los cambios entre versiones):
  number_goes_away=NumeroSome, should_check=DeveConferir, check_is_plausible=ConferenciaPlausivel,
  cell_inside_row=CelulaDentroDeLinha, link_repeats_row_click=LinkRepeteOCliqueDaLinha,
  button_fills_row=BotaoQueOcupaALinha, frame_with_numbered_items=MolduraComItensNumerados,
  image_inside_numbered=ImagemDentroDeNumerado, is_emoji_only_image=EhImagemSoEmoji,
  chat_without_role=ConversaSemPapel, layer_verdict=VereditoDaCamada,
  decide_by_layers=DecidirPorCamadas, is_overlay_candidate=EhSobreposicaoCandidata,
  inside_overlay=DentroDaSobreposicao, overlays_covering=SobreposicoesQueCobrem,
  leaves_by_overlay=SaiPorSobreposicao, is_real_address=EnderecoDeVerdade,
  repeated_links=LinksRepetidos, aim_partners=ParceirosDeMira, is_ancestor=Ascendente,
  is_taskbar_class=EhBarraDeTarefas, is_duplicate=EsDuplicado, is_caption_name=EsNombreCaption,
  name_matches=CasaNome, is_interactive=EsInteractivo.
"""
import unicodedata

# UIA_ControlTypeIds
BUTTON, CHECKBOX, COMBOBOX, EDIT, HYPERLINK, IMAGE, LISTITEM = 50000, 50002, 50003, 50004, 50005, 50006, 50007
MENUBAR, MENU, RADIOBUTTON, SCROLLBAR, TABITEM, TOOLBAR = 50010, 50009, 50013, 50014, 50019, 50021
TEXT, TREEITEM, GROUP, DATAITEM, SPLITBUTTON, TITLEBAR = 50020, 50024, 50026, 50029, 50031, 50037
TAB, LIST, TREE, DATAGRID, DOCUMENT, WINDOW, PANE, HEADER = 50018, 50008, 50023, 50028, 50030, 50032, 50033, 50036

INTERACTIVE_TYPES = {BUTTON, CHECKBOX, COMBOBOX, EDIT, HYPERLINK, LISTITEM, 50011, RADIOBUTTON,
                     TABITEM, TREEITEM, SPLITBUTTON}  # 50011 = MenuItem
# focusable containers do not count (they would number the whole window)
CONTAINER_TYPES = {GROUP, DOCUMENT, WINDOW, PANE, HEADER, TAB, LIST, TREE, DATAGRID}
ROW_TYPES = {DATAITEM, LISTITEM, TREEITEM}

# window-frame buttons have their own voice command: they never get a number
CAPTION_NAMES = {"minimizar", "maximizar", "restaurar", "fechar",     # pt
                 "minimize", "maximize", "restore", "close",          # en
                 "cerrar"}                                            # es
DUPLICATE_DISTANCE = 6   # px: points closer than this with the same name are the same element
MAX_ELEMENTS = 99        # largest number that can be said


class Rect:
    """Rectángulo en píxeles con la semántica de System.Drawing.Rectangle (borde derecho/inferior excluido)."""
    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x=0, y=0, width=0, height=0):
        self.x, self.y, self.width, self.height = x, y, width, height

    @staticmethod
    def from_ltrb(left, top, right, bottom):
        return Rect(left, top, right - left, bottom - top)

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def is_empty(self):
        return self.width <= 0 or self.height <= 0

    def contains_point(self, px, py):
        return self.x <= px < self.right and self.y <= py < self.bottom

    def contains_rect(self, other):
        return (self.x <= other.x and other.right <= self.right
                and self.y <= other.y and other.bottom <= self.bottom)

    def intersects(self, other):
        return (other.x < self.right and self.x < other.right
                and other.y < self.bottom and self.y < other.bottom)

    def intersection(self, other):
        left, top = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right >= left and bottom >= top:
            return Rect.from_ltrb(left, top, right, bottom)
        return Rect()

    def center(self):
        return (self.x + self.width // 2, self.y + self.height // 2)

    def __eq__(self, other):
        return (isinstance(other, Rect) and (self.x, self.y, self.width, self.height)
                == (other.x, other.y, other.width, other.height))

    def __hash__(self):
        return hash((self.x, self.y, self.width, self.height))

    def __repr__(self):
        return f"Rect({self.x}, {self.y}, {self.width}, {self.height})"


EMPTY_POINT = None  # "sin punto" (Point.Empty de la 1.5)


# --- qué elemento recibe número --------------------------------------------------------------

def is_interactive(control_type, focusable):
    """Tipo interactivo, o enfocable que no sea un contenedor (cubre controles propios de apps web)."""
    if control_type in INTERACTIVE_TYPES:
        return True
    if focusable:
        return control_type not in CONTAINER_TYPES
    return False


def is_caption_name(name):
    return (name or "").strip().lower() in CAPTION_NAMES


def _row_above(type_numbered_above):
    return type_numbered_above in ROW_TYPES


def cell_inside_row(control_type, type_numbered_above, read_only):
    """Celda, texto o campo de solo lectura dentro de una fila ya numerada: no lleva número (regla A).

    Es por TIPO, nunca por nombre: el nombre de la fila agrega el texto de lo que hay dentro, y
    esos botones llevan a otro sitio. Botón, enlace, casilla y campo editable se quedan.
    """
    if not _row_above(type_numbered_above):
        return False
    if control_type in (DATAITEM, TEXT):
        return True
    return control_type == EDIT and read_only


def link_repeats_row_click(control_type, type_numbered_above, link_rect, row_click):
    """Enlace cuyo rectángulo contiene el punto de clic de la fila numerada: hace lo mismo que ella."""
    if control_type != HYPERLINK:
        return False
    return (_row_above(type_numbered_above) and row_click is not None
            and link_rect.contains_point(*row_click))


def button_fills_row(control_type, type_numbered_above, button_rect, row_rect):
    """Botón que cubre el 90 % o más de una fila ya numerada, con el centro de la fila dentro: la fila
    solo es su marco y dos números harían el mismo clic. Un botón pequeño dentro de la fila se queda."""
    if control_type != BUTTON or not _row_above(type_numbered_above) or row_rect is None or row_rect.is_empty:
        return False
    cx, cy = row_rect.center()
    if not button_rect.contains_point(cx, cy):
        return False
    common = button_rect.intersection(row_rect)
    row_area = row_rect.width * row_rect.height
    return row_area > 0 and common.width * common.height * 10 >= row_area * 9


def frame_with_numbered_items(control_type, has_numbered_item):
    """Barra de herramientas o menú que ya tiene elementos numerados dentro: pierde su propio número (regla B)."""
    return control_type in (TOOLBAR, MENU) and has_numbered_item


def image_inside_numbered(control_type, inside_numbered):
    """Imagen dentro de un elemento ya numerado: lleva al mismo sitio. Solo imágenes: un botón dentro
    de otro puede tener acción propia."""
    return control_type == IMAGE and inside_numbered


def is_emoji_only_image(control_type, name):
    """Imagen cuyo nombre no tiene ninguna letra ni cifra (solo emoji, modificador de piel, unión)."""
    if control_type != IMAGE:
        return False
    text = (name or "").strip()
    if not text:
        return False   # sin nombre: decide otra regla
    return not any(ch.isalnum() for ch in text)


def chat_without_role(control_type, clickable, rect, parent_type, parent_role, parent_focusable,
                      parent_rect, inside_numbered):
    """Conversación archivada de WhatsApp: un grupo clicable, del tamaño de una fila, dentro de un
    grupo enfocable SIN papel (para Chromium el papel "group" también es "sin papel")."""
    if control_type != GROUP or not clickable or inside_numbered:
        return False
    parent_without_role = (not parent_role) or parent_role == "group"
    if parent_type != GROUP or not parent_without_role or not parent_focusable:
        return False
    if rect.width < 100 or rect.height < 24 or rect.height >= 140:
        return False
    return parent_rect.contains_rect(rect)


def is_taskbar_class(root_class):
    return root_class in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")


def is_duplicate(points, names, point, name):
    """Duplicado de verdad: muy cerca Y con el mismo nombre accesible. Elementos distintos apilados
    en el mismo sitio tienen nombres distintos y se quedan los dos."""
    name = name or ""
    for (qx, qy), qname in zip(points, names):
        if abs(qx - point[0]) <= DUPLICATE_DISTANCE and abs(qy - point[1]) <= DUPLICATE_DISTANCE and qname == name:
            return True
    return False


# --- enlaces repetidos y puntería -------------------------------------------------------------

def is_real_address(url):
    u = (url or "").strip()
    if not u or u == "#":
        return False
    low = u.lower()
    if low.startswith("javascript:"):
        return False
    return low.startswith("http://") or low.startswith("https://")


def repeated_links(types, urls):
    """Para cada elemento, True si es un enlace a una dirección ya numerada antes (se queda el primero)."""
    leaves, seen = [False] * len(types), set()
    for i, kind in enumerate(types):
        if kind != HYPERLINK:
            continue
        url = (urls[i] or "").strip()
        if not is_real_address(url):
            continue
        if url in seen:
            leaves[i] = True
        else:
            seen.add(url)
    return leaves


def is_ancestor(a, b, parent_of_serial):
    """¿El numerado de serie `a` está por encima del de serie `b`?"""
    if a < 0 or b < 0 or b >= len(parent_of_serial):
        return False
    s, steps = parent_of_serial[b], 0
    while 0 <= s < len(parent_of_serial) and steps < 200:
        if s == a:
            return True
        s, steps = parent_of_serial[s], steps + 1
    return False


def aim_partners(centers, rects, serial_of, parent_of_serial):
    """Para cada elemento, los otros numerados en cuyo rectángulo caería su clic (y que no son su
    ascendiente ni su descendiente): son sospechosos de tapar el clic. None si no hay ninguno."""
    n = len(centers)
    result = [None] * n
    for i in range(n):
        for j in range(n):
            if i == j or not rects[j].contains_point(*centers[i]):
                continue
            if is_ancestor(serial_of[j], serial_of[i], parent_of_serial) or \
               is_ancestor(serial_of[i], serial_of[j], parent_of_serial):
                continue
            if result[i] is None:
                result[i] = []
            result[i].append(j)
    return result


# --- capas (diálogos y menús) y superposiciones ---------------------------------------------

def layer_verdict(classifications, buttons_in_layer):
    """1 = en pantalla, 0 = oculta, -1 = sin veredicto. Basta UN punto suyo para estar en pantalla;
    oculta solo con DOS "cubierto" (o uno, si la capa tenía un solo botón)."""
    covered = 0
    for c in classifications:
        if c == "OK":
            return 1
        if c == "COVERED":
            covered += 1
    if covered >= 2 or (covered == 1 and buttons_in_layer == 1):
        return 0
    return -1


def decide_by_layers(centers, layer_of, parent_of_layer, layer_rects, layer_state):
    """Por botón, si SALE de la numeración. layer_state: 1 en pantalla, 0 oculta, -1 sin veredicto."""
    leaves = [False] * len(centers)
    for i, center in enumerate(centers):
        layer = layer_of[i]
        if layer >= 0:
            k, steps = layer, 0
            while k >= 0 and steps < 50:
                if layer_state[k] == 0:
                    leaves[i] = True
                    break
                k, steps = parent_of_layer[k], steps + 1
            continue
        for k, rect in enumerate(layer_rects):
            if layer_state[k] == 1 and rect.contains_point(*center):
                leaves[i] = True
                break
    return leaves


def is_overlay_candidate(rect, parent_rect):
    """Ocupa el MISMO rectángulo del padre (se coloca encima de sus hermanos) y es del tamaño de una pantalla."""
    if rect.width < 200 or rect.height < 150 or parent_rect is None or parent_rect.is_empty:
        return False
    return (abs(rect.x - parent_rect.x) <= 2 and abs(rect.y - parent_rect.y) <= 2
            and abs(rect.width - parent_rect.width) <= 2 and abs(rect.height - parent_rect.height) <= 2)


def inside_overlay(overlay_of_button, parent_of_overlay, k):
    s, steps = overlay_of_button, 0
    while s >= 0 and steps < 80:
        if s == k:
            return True
        s, steps = parent_of_overlay[s], steps + 1
    return False


def overlays_covering(centers, rects, overlay_of, doc_of, parent_of_overlay, overlay_rects, overlay_doc):
    """Por botón, las superposiciones que lo cubren por geometría y de las que NO forma parte."""
    n, m = len(centers), len(overlay_rects)
    result = [None] * n
    inside = [0] * m
    for i in range(n):
        s, steps = overlay_of[i], 0
        while s >= 0 and steps < 80:
            inside[s] += 1
            s, steps = parent_of_overlay[s], steps + 1
    for i in range(n):
        if doc_of[i] < 0:
            continue
        for k in range(m):
            if inside[k] == 0 or overlay_doc[k] != doc_of[i]:
                continue
            if not overlay_rects[k].contains_point(*centers[i]):
                continue
            if rects[i].contains_rect(overlay_rects[k]):
                continue
            if inside_overlay(overlay_of[i], parent_of_overlay, k):
                continue
            if result[i] is None:
                result[i] = []
            result[i].append(k)
    return result


def leaves_by_overlay(step_of_button, step_of_overlay):
    """Subiendo desde el acierto del punto: sale solo si la superposición aparece ANTES que el propio botón."""
    return step_of_overlay >= 0 and (step_of_button < 0 or step_of_overlay < step_of_button)


# --- la pregunta del punto -----------------------------------------------------------------

def number_goes_away(classification):
    """Solo "COVERED" (la respuesta PRECISA dice que otra cosa ocupa el punto) quita el número.
    "ROUGH" (la app solo detalla hasta un ascendiente) y los errores se quedan."""
    return classification == "COVERED"


def should_check(enabled, is_web_content, point_is_ours):
    """Solo contenido web, y nunca un punto sobre una ventana del propio XULIA (preguntar al propio
    proceso por UI Automation es un bloqueo mortal)."""
    return enabled and is_web_content and not point_is_ours


def check_is_plausible(checked, covered, confirmed):
    """Una comprobación que dice "casi todo está cubierto" está rota, no acertada (en WhatsApp dio 67 de 67
    y borró todos los números). Con menos de 6 comprobados no hay base para desconfiar."""
    if checked < 6:
        return True
    if covered * 2 <= checked:
        return True
    return confirmed >= max(3, checked // 10)


# --- nombres -------------------------------------------------------------------------------

def _fold(text):
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def name_matches(real, target):
    """Compara sin mayúsculas ni acentos ("Cancelar gravação" == "cancelar gravacao"); un objetivo que
    empieza por '*' casa por CONTIENE."""
    if not real or not target:
        return False
    contains = target.startswith("*")
    if contains:
        target = target[1:]
    if contains:
        return _fold(target) in _fold(real)
    return _fold(real.strip()) == _fold(target.strip())
