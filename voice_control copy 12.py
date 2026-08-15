import ctypes
import os
import re
import subprocess
import sys
import threading
import math
import time
import tkinter as tk
from queue import Queue

import pyautogui
import pystray
import speech_recognition as sr
from PIL import Image, ImageDraw
import pyperclip
from pywinauto import Desktop
try:
    from win10toast import ToastNotifier
except Exception:
    # If pkg_resources (setuptools) is missing or win10toast cannot be imported,
    # provide a minimal fallback that prints messages to console so the
    # application can still run without Windows toast support.
    class ToastNotifier:
        def show_toast(self, title, msg, duration=2, threaded=True):
            try:
                print(f"[TOAST] {title}: {msg}")
            except Exception:
                pass
import traceback
from collections import OrderedDict
import webbrowser

# Default patterns used when no external patterns file is present
DEFAULT_PATTERNS = {
    "activate": r"\b(activar|ativar)\b",
    "deactivate": r"\b(desactivar|desativar)\b",
    "pause": r"\b(pausar|silenciar|temporalmente|deshabilitar temporalmente|desativar temporariamente)\b",
    "dictation_on": r"\b(modo dictado)\b",
    "dictation_off": r"\b(salir(?: del| de)?(?: el)? modo(?: de)? dictado|salir(?: del| de)? dictado|fin(?: del| de)? dictado|terminar(?: el)? dictado|sair(?: do| de)?(?: modo(?: de)?)? ditado|sair(?: do| de)? ditado|terminar ditado|fim(?: do)? ditado|parar ditado)\b",
    "grid_show": r"\b(mostrar rejilla|mostrar grade|abrir rejilla|abrir grade)\b",
    "grid_hide": r"\b(ocultar rejilla|fechar grade|cerrar rejilla|cerrar grade)\b",
    "help": r"\b(ayuda|comandos|lista de comandos|ajuda|mostrar ayuda)\b",
    "correct_last": r"\b(corregir( la)? última frase|corrigir( a)? última frase|borrar( la)? última frase|eliminar( la)? última frase)\b",
    "click_button": r"\b(bot[oó]n|bot[oó]es|clicar|pulsar|press)\b",
    "button": r"\b(?:bot[oó]n|bot[oó]es|botao|button)\s+(.+)",
    "ribbon": r"\b(cinta|aba|guía|guia|ribbon)\b",
    "office_tab": r"\b(cinta de inicio|insertar|insert|disenar|diseñar|vista|revisar|arquivo|archivo|arquivo|dados|datos|fórmula|formula|arquivos|exibir|visualizar)\b",
    "cell_click": r"\bcelda\s*(?:n[úu]mero\s*)?(\d{1,2})\b",
    "mouse_up": r"\b(rat[oó]n\s+arriba|mouse\s+para\s+cima|mouse\s+cima)\b",
    "mouse_down": r"\b(rat[oó]n\s+abajo|mouse\s+para\s+baixo|mouse\s+baixo)\b",
    "mouse_left": r"\b(rat[oó]n\s+izquierda|mouse\s+para\s+a\s+esquerda|mouse\s+esquerda)\b",
    "mouse_right": r"\b(rat[oó]n\s+derecha|mouse\s+para\s+a\s+direita|mouse\s+direita)\b",
    "mouse_click": r"\b(rat[oó]n\s+clic|rat[oó]n\s+pulsar|mouse\s+clic|mouse\s+click|rat[oó]n\s+clicar)\b",
    "mouse_stop": r"\b(rat[oó]n\s+parado|parar\s+mouse)\b",
    "menu": r"\b(?:men[uú]|menu)\s+(.+)",
    # Keypress commands
    "enter": r"\b(enter|intro|introducir|entrar)\b",
    "tab": r"\b(tabulador|tabulador|tab)\b",
    "escape": r"\b(escape|esc)\b",
    "backspace": r"\b(borrar|retroceso|backspace)\b",
    "delete": r"\b(suprimir|supr|del|delete)\b",
    "borrarpalabra": r"\b(borrar\s*palabra|borrarpalabra)\b",
    "borrarsiguientepalabra": r"\b(borrar\s*siguiente\s*palabra|borrarsiguientepalabra)\b",
    "borrarlinea": r"\b(borrar\s*l[íi]nea|borrarlinea)\b",
    "cursor_up": r"\b(arriba|cursor\s+arriba|flecha\s+arriba)\b",
    "cursor_down": r"\b(abajo|cursor\s+abajo|flecha\s+abajo)\b",
    "cursor_left": r"\b(izquierda|cursor\s+izquierda|flecha\s+izquierda)\b",
    "cursor_right": r"\b(derecha|cursor\s+derecha|flecha\s+derecha)\b",
    "home": r"\b(inicio|home)\b",
    "end": r"\b(final|end|fin)\b",
    "page_next": r"\b(siguiente\s*página|siguientepágina|avanzar\s*página|avanzarpágina)\b",
    "page_prev": r"\b(página\s*anterior|anteriorpágina|retroceder\s*página|retrocederpágina)\b",
    "first_page": r"\b(primera\s*página|primerapágina|primera\s*pagina)\b",
    "last_page": r"\b(última\s*página|ultimapágina|ultimapagina)\b",
    "next_tab": r"\b(siguiente\s*solapa|siguiente\s*pestaña|siguientesolapa)\b",
    "prev_tab": r"\b(anterior\s*solapa|anterior\s*pestaña|anteriorsolapa)\b",
    "next_word": r"\b(siguiente)\b",
    "prev_word": r"\b(anterior)\b",
    "copiar": r"\bcopiar(?:\s+(?P<slot>\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez))?\b",
    "cortar": r"\bcortar(?:\s+(?P<slot>\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez))?\b",
    "pegar": r"\bpegar(?:\s+(?P<slot>\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez))?\b",
    # Window and application commands
    "activar_ventana": r"\bactivar ventana(?:\s*n[úu]mero)?\s*(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieciseis|dieciséis|diecisiete|dieciocho|diecinueve|veinte)\b",
    "siguiente_aplicacion": r"\b(siguiente aplicaci[oó]n|siguiente aplicacion|siguiente app)\b",
    "anterior_aplicacion": r"\b(anterior aplicaci[oó]n|anterior aplicacion|aplicaci[oó]n anterior|anterior app)\b",
    "maximizar_ventana": r"\b(maximizar ventana|maximizar|poner a pantalla completa)\b",
    "minimizar_ventana": r"\b(minimizar ventana|minimizar la ventana|minimizar)\b",
    "ventana_normal": r"\b(ventana normal|restaurar ventana|tama[ñn]o normal|restaurar)\b",
    "cerrar_ventana": r"\b(cerra.*?ventana.*|cerrar la ventana)\b",
    "cerrar_aplicacion": r"\b(cerrar aplicaci[oó]n|cerrar aplicacion|cerrar la aplicaci[oó]n)\b",
    "ventana_derecha": r"\b(ventana derecha|ventana a la derecha|mover ventana derecha)\b",
    "ventana_izquierda": r"\b(ventana izquierda|ventana a la izquierda|mover ventana izquierda)\b",
    "ejecutar_editor": r"\b(ejecutar editor|ejecutar word|abrir word|abrir editor)\b",
    "ejecutar_navegador": r"\b(ejecutar navegador|abrir navegador|abrir navegador predeterminado|abrir navegador por defecto)\b",
    "ejecutar_calculadora": r"\b(ejecutar calculadora|abrir calculadora)\b",
    "ejecutar_notas": r"\b(ejecutar notas|ejecutar notepad|abrir notas|abrir bloc de notas|abrir notepad)\b",
    "monitor_tareas": r"\b(monitor de tareas|administrador de tareas|task manager|monitor tareas)\b",
    "ejecutar_skype": r"\b(ejecutar skype|abrir skype)\b",
    "ejecutar_google_mail": r"\b(ejecutar google mail|ejecutar gmail|abrir gmail|abrir google mail)\b",
    "ejecutar_whatsapp": r"\b(ejecutar whatsapp|ejecutar whatsapp|abrir whatsapp|abrir whatapps|abrir whatsapp web)\b",
    "ejecutar_facebook": r"\b(ejecutar facebook|abrir facebook)\b",
    "explorar_disco": r"\b(explorar disco|abrir explorador|explorar archivos|abrir explorador de archivos)\b",
    }




class GridOverlay:
    def __init__(self, rows=4, cols=4, alpha=0.28):
        self.rows = rows
        self.cols = cols
        self.alpha = alpha
        self.root = None
        self.thread = None
        self.visible = False

    def show(self):
        if self.visible:
            return
        self.visible = True
        self.thread = threading.Thread(target=self._run_overlay, daemon=True)
        self.thread.start()

    def hide(self):
        self.visible = False
        if self.root:
            self.root.quit()
            self.root = None

    def _run_overlay(self):
        self.root = tk.Tk()
        self.root.title("Rejilla de Xulia2")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.alpha)
        self.root.overrideredirect(True)
        self.root.configure(background="black")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")

        canvas = tk.Canvas(self.root, width=screen_width, height=screen_height, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        for r in range(1, self.rows):
            y = int(screen_height * r / self.rows)
            canvas.create_line(0, y, screen_width, y, fill="white", width=2)
        for c in range(1, self.cols):
            x = int(screen_width * c / self.cols)
            canvas.create_line(x, 0, x, screen_height, fill="white", width=2)

        text = "Rejilla activada: di 'celda N' para mover y hacer clic"
        canvas.create_text(screen_width // 2, 30, text=text, fill="white", font=("Arial", 16, "bold"))

        self.root.mainloop()
        self.visible = False

    def cell_center(self, cell_number):
        cell_number = max(1, min(cell_number, self.rows * self.cols))
        row = (cell_number - 1) // self.cols
        col = (cell_number - 1) % self.cols
        screen_width, screen_height = pyautogui.size()
        x = int((col + 0.5) * screen_width / self.cols)
        y = int((row + 0.5) * screen_height / self.rows)
        return x, y


class VoiceControlAssistant:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.toaster = ToastNotifier()
        self.grid = GridOverlay(rows=4, cols=4)
        self.active = True
        self.dictation_mode = False
        # Spelling mode
        self.spell_mode = False
        self.mouse_direction = None
        # mouse speed index (1..6) and corresponding step sizes in pixels
        self.mouse_speed_idx = 2
        self.mouse_speed_steps = [4, 8, 12, 20, 36, 60]
        self.last_phrases = []
        self.silenced_until = 0
        self.language = "es-ES"
        self.recognition_engine = "auto"  # auto, vosk, google or sphinx
        # Track whether the desktop is currently shown via our command
        self._desktop_shown = False
        # Modifier key states
        self._ctrl_down = False
        self._alt_down = False
        self._altgr_down = False
        self._altgr_via_ctypes = False
        # Shift states: locked (mayúsculas) or single-use (una mayúscula)
        self._shift_locked = False
        self._single_shift = False
        # Manual shift hold (pulsar selección)
        self._shift_down = False
        self.mic_index = self._choose_microphone()
        self.mic_index = 1
        self.commands = self._build_command_patterns()
        # Initialize 10 clipboard memory slots (1..10 mapped to indices 0..9)
        self.clipboard_slots = [None] * 10
        # initialize handlers mapping after commands are built
        self._init_command_handlers()
        # Build spell-mode allowed keys set
        self._spell_allowed = set([
            'alicante','bilbao','cadiz','dinamarca','espana','francia','gerona','huelva','italia','jaen',
            'kilo','llamar','madrid','navarra','oviedo','portugal','queso','roma','sevilla','toledo','unico','valencia','uvedoble',
            'equis','yugoslavia','zaragoza','nono','espacio',
            'comillas','comillassimples','mas','menos','asterisco','dolar','abrirparentesis','cerrarparentesis','abrirllave','cerrarllave',
            'abrircorchete','cerrarcorchete','subrayado','subrrayado','barrainvertida','barra','arroba','porcentaje','sostenido','euro','mayorque','menorque','iguala','ampersan',
            'abrirexclamacion','cerrarexclamacion','abririnterrogacion','cerrarinterrogacion','barravertical','cerilla','primero','primera','angulo',
            'punto','coma','puntoycoma','dospuntos','puntoyaparte','acento','grave','circunflejo','dieresis'
        ])
        self.command_queue = Queue()
        self.icon = None
        self.running = True
        self._create_tray_icon()
        # Try to load a local Vosk model (optional). Models are expected under ./models
        self.vosk_available = False
        self.vosk_model = None
        try:
            from vosk import Model as VoskModel
            models_dir = os.path.join(os.path.dirname(__file__), "models")
            lang = (self.language or "").lower()
            model_map = {"es": "vosk-model-small-es-0.42", "pt": "vosk-model-small-pt-0.3"}
            selected_model = None
            # prefer explicit mapping by language prefix
            for prefix, name in model_map.items():
                if lang.startswith(prefix):
                    candidate = os.path.join(models_dir, name)
                    if os.path.exists(candidate):
                        selected_model = candidate
                        break
            # fallback: try to find any model directory in models_dir that looks like a vosk model
            if selected_model is None and os.path.exists(models_dir):
                for entry in os.listdir(models_dir):
                    if entry.startswith("vosk-model") and os.path.isdir(os.path.join(models_dir, entry)):
                        selected_model = os.path.join(models_dir, entry)
                        break
            if selected_model:
                try:
                    self.vosk_model = VoskModel(selected_model)
                    self.vosk_available = True
                    print(f"Vosk model loaded: {selected_model}")
                except Exception as e:
                    print("Error loading Vosk model:", e)
                    self.vosk_model = None
                    self.vosk_available = False
            else:
                print("No Vosk model found under ./models; Vosk will be disabled until a model is placed there.")
        except Exception:
            # vosk not installed or import failed
            self.vosk_model = None
            self.vosk_available = False

    def _choose_microphone(self):
        try:
            mic_names = sr.Microphone.list_microphone_names()
            print("Micrófonos disponibles:")
            for idx, name in enumerate(mic_names):
                print(f"  [{idx}] {name}")
            preferred = ["italk", "micrófono", "microphone", "usb audio", "input", "mic"]
            for idx, name in enumerate(mic_names):
                lower_name = name.lower()
                if any(pref in lower_name for pref in preferred):
                    print(f"Seleccionando micrófono [{idx}]: {name}")
                    return idx
        except Exception as exc:
            print("No se pudo obtener la lista de micrófonos:", exc)
        return None

    def _build_command_patterns(self):
        # Try to load patterns from a text configuration file first
        try:
            config_path = os.path.join(os.path.dirname(__file__), "patterns.txt")
            # read raw config values to pick up non-regex settings like vosk_language
            config_vals = self._read_config_values(config_path)
            if config_vals:
                # allow config to override recognizer language for Vosk
                vosk_lang = config_vals.get("vosk_language") or config_vals.get("language")
                if vosk_lang:
                    # normalize simple codes like 'es' -> 'es-ES' if needed
                    v = vosk_lang.strip()
                    if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", v) or re.fullmatch(r"[a-z]{2}", v, re.I):
                        self.language = v
                # allow config to override spelling prefix word(s) (e.g. 'tecla' or 'tecla,teclear')
                spell_pref = config_vals.get('spell_prefix') or config_vals.get('spell-prefix')
                if spell_pref:
                    try:
                        parts = [p.strip() for p in re.split(r"[|,;]", spell_pref) if p.strip()]
                        if parts:
                            self.spell_prefixes = parts
                    except Exception:
                        pass
                # allow config to override command prefix word(s) (e.g. 'comando' or 'comando,orden')
                command_pref = config_vals.get('command_prefix') or config_vals.get('command-prefix')
                if command_pref:
                    try:
                        parts = [p.strip() for p in re.split(r"[|,;]", command_pref) if p.strip()]
                        if parts:
                            self.command_prefixes = parts
                    except Exception:
                        pass
                engine_pref = config_vals.get('recognition_engine') or config_vals.get('speech_engine') or config_vals.get('recognizer') or config_vals.get('engine') or config_vals.get('voice_engine')
                if engine_pref:
                    engine = engine_pref.strip().lower()
                    if engine in ('google_free', 'googlecloud', 'google cloud'):
                        engine = 'google'
                    elif engine in ('auto', 'default', 'auto_detect', 'automatic'):
                        engine = 'auto'
                    if engine in ('vosk', 'google', 'sphinx', 'auto'):
                        self.recognition_engine = engine
                    else:
                        print(f"Opción de motor de reconocimiento desconocida en patterns.txt: {engine_pref}. Se usará 'auto'.")
                        self.recognition_engine = 'auto'
            patterns = self._load_patterns_from_file(config_path)
            if patterns:
                # also load dictation replacements and literal-word from same config
                try:
                    self.dictation_replacements = self._load_replacements_from_file(config_path)
                except Exception:
                    self.dictation_replacements = []
                # literal-word configurable via 'literal_word' key in patterns.txt
                lw = config_vals.get('literal_word') or config_vals.get('literal-word') or config_vals.get('literal')
                self.literal_word = (lw or 'literal').strip()
                return patterns
        except Exception:
            pass

        # Fallback to built-in defaults
        compiled = {}
        for k, p in DEFAULT_PATTERNS.items():
            compiled[k] = re.compile(p, re.I)
        # defaults for dictation replacements and literal word
        try:
            self.dictation_replacements = [ (re.compile(r"\bpunto\b", re.I), '.') ]
        except Exception:
            self.dictation_replacements = []
        self.literal_word = getattr(self, 'literal_word', 'literal')
        return compiled

    def _load_replacements_from_file(self, path: str):
        """Load replacement rules from patterns file.

        Rules use the '=>' separator: <regex> => <replacement string>
        Lines beginning with '#' are ignored. Returns list of (compiled_regex, repl).
        If no rules found, returns a default list containing 'punto' -> '.'.
        """
        repls = []
        if not os.path.exists(path):
            return [(re.compile(r"\bpunto\b", re.I), '.')]
        with open(path, 'r', encoding='utf-8') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if '=>' not in line:
                    continue
                left, right = line.split('=>', 1)
                pattern = left.strip()
                replacement = right.strip()
                # allow quoted replacement strings
                if (replacement.startswith('"') and replacement.endswith('"')) or (replacement.startswith("'") and replacement.endswith("'")):
                    replacement = replacement[1:-1]
                try:
                    cre = re.compile(pattern, re.I)
                    repls.append((cre, replacement))
                except re.error:
                    print(f"Patrón de reemplazo inválido en patterns.txt: {pattern}")
                    continue
        if not repls:
            # provide sensible default
            try:
                return [(re.compile(r"\bpunto\b", re.I), '.')]
            except Exception:
                return []
        return repls

    def _load_patterns_from_file(self, path: str):
        """Load key=regex lines from a patterns file. Lines starting with # are ignored."""
        if not os.path.exists(path):
            return None
        config_only_keys = {
            'vosk_language', 'language',
            'spell_prefix', 'spell-prefix', 'spell_prefixes',
            'command_prefix', 'command-prefix', 'command_prefixes',
            'literal_word', 'literal-word', 'literal',
            'recognition_engine', 'speech_engine', 'recognizer', 'engine', 'voice_engine'
        }
        compiled = {}
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    print(f"Línea mal formada en patterns.txt (sin '='): {line}")
                    continue
                key, pattern = line.split("=", 1)
                key = key.strip()
                pattern = pattern.strip()
                if not key:
                    print(f"Línea mal formada en patterns.txt (clave vacía): {line}")
                    continue
                if key.lower() in config_only_keys:
                    continue
                if not pattern:
                    print(f"Línea mal formada en patterns.txt (patrón vacío) para clave '{key}'")
                    continue
                try:
                    compiled[key] = re.compile(pattern, re.I)
                except re.error:
                    print(f"Patrón inválido en patterns.txt para '{key}': {pattern}")
                    continue
        return compiled

    def _read_config_values(self, path: str):
        """Read raw key=value pairs from config file (no regex compilation).

        Returns dict of key->value strings for each non-comment line.
        """
        if not os.path.exists(path):
            return {}
        vals = {}
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key:
                    vals[key] = value
        return vals

    def _init_command_handlers(self):
        """Initialize mapping of command keys to handler callables.

        Each handler receives (match, text, normalized) and should return True
        if it handled the command.
        """
        self._command_handlers = {
            "activate": lambda m, t, n: (self.activate() or True),
            "deactivate": lambda m, t, n: (self.deactivate() or True),
            "pause": lambda m, t, n: (self.pause_temporarily(30) or True),
            "help": lambda m, t, n: (self.show_help() or True),
            "grid_show": lambda m, t, n: (self.grid.show() or self.notify("Rejilla mostrada") or True),
            "grid_hide": lambda m, t, n: (self.grid.hide() or self.notify("Rejilla oculta") or True),
            "dictation_off": lambda m, t, n: (setattr(self, 'dictation_mode', False) or self._update_tray_icon() or self.notify("Modo dictado desactivado") or True),
            "dictation_on": lambda m, t, n: (setattr(self, 'dictation_mode', True) or self._update_tray_icon() or self.notify("Modo dictado activado") or True),
            "correct_last": lambda m, t, n: (self._correct_last_phrase() or True),
            "cell_click": self._handle_cell_click,
            "mouse_up": lambda m, t, n: (setattr(self, 'mouse_direction', 'up') or self.notify("Ratón arriba", toast=False) or True),
            "mouse_down": lambda m, t, n: (setattr(self, 'mouse_direction', 'down') or self.notify("Ratón abajo", toast=False) or True),
            "mouse_left": lambda m, t, n: (setattr(self, 'mouse_direction', 'left') or self.notify("Ratón izquierda", toast=False) or True),
            "mouse_right": lambda m, t, n: (setattr(self, 'mouse_direction', 'right') or self.notify("Ratón derecha", toast=False) or True),
            "mouse_click": lambda m, t, n: (setattr(self, 'mouse_direction', None) or (pyautogui.click() or self.notify("Ratón clic", toast=False)) or True),
            "mouse_stop": lambda m, t, n: (setattr(self, 'mouse_direction', None) or self.notify("Ratón parado", toast=False) or True),
            "ribbon": self._handle_ribbon,
            "button": self._handle_named_button,
            "menu": self._handle_named_menu,
            "click_button": self._handle_click_button,
            # keyboard and navigation handlers
            "enter": lambda m, t, n: (pyautogui.press('enter') or self.notify('Tecla Enter enviada') or True),
            "tab": lambda m, t, n: (pyautogui.press('tab') or self.notify('Tecla Tab enviada') or True),
            "escape": lambda m, t, n: (pyautogui.press('esc') or self.notify('Tecla Escape enviada') or True),
            "backspace": lambda m, t, n: (pyautogui.press('backspace') or self.notify('Tecla Borrar enviada') or True),
            "delete": lambda m, t, n: (pyautogui.press('delete') or self.notify('Tecla Suprimir enviada') or True),
            # Letter-key mappings (city-like names -> single-letter key presses)
            "teclaalicante": lambda m, t, n: (pyautogui.press('a') or self.notify('Tecla a enviada') or True),
            "teclabilbao": lambda m, t, n: (pyautogui.press('b') or self.notify('Tecla b enviada') or True),
            "teclacádiz": lambda m, t, n: (pyautogui.press('c') or self.notify('Tecla c enviada') or True),
            "tecladinamarca": lambda m, t, n: (pyautogui.press('d') or self.notify('Tecla d enviada') or True),
            "teclaespaña": lambda m, t, n: (pyautogui.press('e') or self.notify('Tecla e enviada') or True),
            "teclafrancia": lambda m, t, n: (pyautogui.press('f') or self.notify('Tecla f enviada') or True),
            "teclagerona": lambda m, t, n: (pyautogui.press('g') or self.notify('Tecla g enviada') or True),
            "teclahuelva": lambda m, t, n: (pyautogui.press('h') or self.notify('Tecla h enviada') or True),
            "teclaitalia": lambda m, t, n: (pyautogui.press('i') or self.notify('Tecla i enviada') or True),
            "teclajaén": lambda m, t, n: (pyautogui.press('j') or self.notify('Tecla j enviada') or True),
            "teclakilo": lambda m, t, n: (pyautogui.press('k') or self.notify('Tecla k enviada') or True),
            "teclallamar": lambda m, t, n: (pyautogui.press('l') or self.notify('Tecla l enviada') or True),
            "teclamadrid": lambda m, t, n: (pyautogui.press('m') or self.notify('Tecla m enviada') or True),
            "teclanavarra": lambda m, t, n: (pyautogui.press('n') or self.notify('Tecla n enviada') or True),
            "teclaoviedo": lambda m, t, n: (pyautogui.press('o') or self.notify('Tecla o enviada') or True),
            "teclaportugal": lambda m, t, n: (pyautogui.press('p') or self.notify('Tecla p enviada') or True),
            "teclaqueso": lambda m, t, n: (pyautogui.press('q') or self.notify('Tecla q enviada') or True),
            "teclaroma": lambda m, t, n: (pyautogui.press('r') or self.notify('Tecla r enviada') or True),
            "teclasevilla": lambda m, t, n: (pyautogui.press('s') or self.notify('Tecla s enviada') or True),
            "teclatoledo": lambda m, t, n: (pyautogui.press('t') or self.notify('Tecla t enviada') or True),
            "teclaúnico": lambda m, t, n: (pyautogui.press('u') or self.notify('Tecla u enviada') or True),
            "teclavalencia": lambda m, t, n: (pyautogui.press('v') or self.notify('Tecla v enviada') or True),
            "teclauvedoble": lambda m, t, n: (pyautogui.press('w') or self.notify('Tecla w enviada') or True),
            "teclaequis": lambda m, t, n: (pyautogui.press('x') or self.notify('Tecla x enviada') or True),
            "teclayugoslavia": lambda m, t, n: (pyautogui.press('y') or self.notify('Tecla y enviada') or True),
            "teclazaragoza": lambda m, t, n: (pyautogui.press('z') or self.notify('Tecla z enviada') or True),
            "teclañoño": lambda m, t, n: (pyautogui.press('ñ') or self.notify('Tecla ñ enviada') or True),
            "teclaespacio": lambda m, t, n: (pyautogui.press('space') or self.notify('Tecla espacio enviada') or True),
            # Numeric key handler (delegates to _handle_tecla_numero)
            "tecla_numero": self._handle_tecla_numero,
            "borrarpalabra": self._handle_borrar_palabra,
            "borrarsiguientepalabra": self._handle_borrar_siguiente_palabra,
            "borrarlinea": self._handle_borrar_linea,
            "cursor_up": lambda m, t, n: (pyautogui.press('up') or True),
            "cursor_down": lambda m, t, n: (pyautogui.press('down') or True),
            "cursor_left": lambda m, t, n: (pyautogui.press('left') or True),
            "cursor_right": lambda m, t, n: (pyautogui.press('right') or True),
            "home": lambda m, t, n: (pyautogui.press('home') or True),
            "end": lambda m, t, n: (pyautogui.press('end') or True),
            "page_next": lambda m, t, n: (pyautogui.press('pagedown') or True),
            "page_prev": lambda m, t, n: (pyautogui.press('pageup') or True),
            "first_page": lambda m, t, n: (pyautogui.hotkey('ctrl', 'home') or True),
            "last_page": lambda m, t, n: (pyautogui.hotkey('ctrl', 'end') or True),
            # Spanish aliases for page navigation
            "next_word": lambda m, t, n: (pyautogui.hotkey('ctrl', 'right') or True),
            "prev_word": lambda m, t, n: (pyautogui.hotkey('ctrl', 'left') or True),
            "next_tab": lambda m, t, n: (pyautogui.hotkey('ctrl', 'tab') or True),
            "prev_tab": lambda m, t, n: (pyautogui.hotkey('ctrl', 'shift', 'tab') or True),
            # Function keys F1..F12 mapped to 'función uno' .. 'función doce'
            "funcion_uno": lambda m, t, n: (pyautogui.press('f1') or self.notify('F1 enviada') or True),
            "funcion_dos": lambda m, t, n: (pyautogui.press('f2') or self.notify('F2 enviada') or True),
            "funcion_tres": lambda m, t, n: (pyautogui.press('f3') or self.notify('F3 enviada') or True),
            "funcion_cuatro": lambda m, t, n: (pyautogui.press('f4') or self.notify('F4 enviada') or True),
            "funcion_cinco": lambda m, t, n: (pyautogui.press('f5') or self.notify('F5 enviada') or True),
            "funcion_seis": lambda m, t, n: (pyautogui.press('f6') or self.notify('F6 enviada') or True),
            "funcion_siete": lambda m, t, n: (pyautogui.press('f7') or self.notify('F7 enviada') or True),
            "funcion_ocho": lambda m, t, n: (pyautogui.press('f8') or self.notify('F8 enviada') or True),
            "funcion_nueve": lambda m, t, n: (pyautogui.press('f9') or self.notify('F9 enviada') or True),
            "funcion_diez": lambda m, t, n: (pyautogui.press('f10') or self.notify('F10 enviada') or True),
            "funcion_once": lambda m, t, n: (pyautogui.press('f11') or self.notify('F11 enviada') or True),
            "funcion_doce": lambda m, t, n: (pyautogui.press('f12') or self.notify('F12 enviada') or True),
            # field navigation
            "siguiente_campo": lambda m, t, n: (pyautogui.press('tab') or self.notify('Siguiente campo (Tab)') or True),
            "anterior_campo": lambda m, t, n: (pyautogui.hotkey('shift', 'tab') or self.notify('Campo anterior (Shift+Tab)') or True),
            # mouse speed controls
            "raton_uno": lambda m, t, n: (self._set_mouse_speed(1) or True),
            "raton_dos": lambda m, t, n: (self._set_mouse_speed(2) or True),
            "raton_tres": lambda m, t, n: (self._set_mouse_speed(3) or True),
            "raton_cuatro": lambda m, t, n: (self._set_mouse_speed(4) or True),
            "raton_cinco": lambda m, t, n: (self._set_mouse_speed(5) or True),
            "raton_seis": lambda m, t, n: (self._set_mouse_speed(6) or True),
            "raton_rapido": lambda m, t, n: (self._increase_mouse_speed() or True),
            "raton_despacio": lambda m, t, n: (self._decrease_mouse_speed() or True),
            # diagonal movement (continuous until stopped)
            "raton_diagonal": lambda m, t, n: (setattr(self, 'mouse_direction', 'diag1') or self.notify('Ratón diagonal 1', toast=False) or True),
            "raton_diagonal_dos": lambda m, t, n: (setattr(self, 'mouse_direction', 'diag2') or self.notify('Ratón diagonal 2', toast=False) or True),
            "raton_diagonal_tres": lambda m, t, n: (setattr(self, 'mouse_direction', 'diag3') or self.notify('Ratón diagonal 3', toast=False) or True),
            "raton_diagonal_cuatro": lambda m, t, n: (setattr(self, 'mouse_direction', 'diag4') or self.notify('Ratón diagonal 4', toast=False) or True),
            # center and quadrant positioning
            "raton_centro": lambda m, t, n: (self._mouse_center() or True),
            "raton_cuadrante": lambda m, t, n: (self._mouse_quadrant(1) or True),
            "raton_cuadrante_dos": lambda m, t, n: (self._mouse_quadrant(2) or True),
            "raton_cuadrante_tres": lambda m, t, n: (self._mouse_quadrant(3) or True),
            "raton_cuadrante_cuatro": lambda m, t, n: (self._mouse_quadrant(4) or True),
            # mouse click and hold commands
            "raton_pulsar_doble": lambda m, t, n: (self._mouse_double_click() or True),
            "raton_pulsar_derecho": lambda m, t, n: (self._mouse_click_right() or True),
            "raton_pulsar_izquierdo": lambda m, t, n: (self._mouse_click_left() or True),
            "raton_pulsar_centro": lambda m, t, n: (self._mouse_click_middle() or True),
            "raton_mantener": lambda m, t, n: (self._mouse_hold() or True),
            "raton_parar": lambda m, t, n: (self._mouse_release_all_and_stop() or True),
            "raton_levantar": lambda m, t, n: (self._mouse_release_left() or True),
            # modifier and caps handlers
            "mayusculas": lambda m, t, n: (self._enable_shift_lock() or True),
            "fin_mayusculas": lambda m, t, n: (self._disable_shift_lock() or True),
            "una_mayuscula": lambda m, t, n: (self._single_shift_once() or True),
            "pulsar_control": lambda m, t, n: (self._press_control() or True),
            "levantar_control": lambda m, t, n: (self._release_control() or True),
            "alternativo": lambda m, t, n: (self._press_alt() or True),
            "levantar_alternativo": lambda m, t, n: (self._release_alt() or True),
            "alternativo_grafico": lambda m, t, n: (self._press_altgr() or True),
            "levantar_alternativo_grafico": lambda m, t, n: (self._release_altgr() or True),
            "pulsar_seleccion": lambda m, t, n: (self._press_shift() or True),
            "levantar_seleccion": lambda m, t, n: (self._release_shift() or True),
            # clipboard handlers
            "copiar": self._handle_copy,
            "cortar": self._handle_cut,
            "pegar": self._handle_paste,
            # Start menu and desktop show/restore
            "menu_inicio": lambda m, t, n: (self._open_start_menu(m, t, n) or True),
            "escritorio_mostrar": lambda m, t, n: (self._show_desktop(m, t, n) or True),
            "escritorio_restaurar": lambda m, t, n: (self._restore_desktop(m, t, n) or True),
            # Window / App management
            "activar_ventana": lambda m, t, n: (self._activate_window_by_token(m.group(1) if m else None) or True),
            "siguiente_aplicacion": lambda m, t, n: (self._switch_next_app() or True),
            "anterior_aplicacion": lambda m, t, n: (self._switch_prev_app() or True),
            "maximizar_ventana": lambda m, t, n: (self._maximize_window() or True),
            "minimizar_ventana": lambda m, t, n: (self._minimize_window() or True),
            "ventana_normal": lambda m, t, n: (self._restore_window() or True),
            "cerrar_ventana": lambda m, t, n: (self._close_window() or True),
            "cerrar_aplicacion": lambda m, t, n: (self._close_application() or True),
            "ventana_derecha": lambda m, t, n: (self._snap_window_right() or True),
            "ventana_izquierda": lambda m, t, n: (self._snap_window_left() or True),
            # Quick app launches
            "ejecutar_editor": lambda m, t, n: (self._exec_word() or True),
            "ejecutar_navegador": lambda m, t, n: (self._exec_browser() or True),
            "ejecutar_calculadora": lambda m, t, n: (self._exec_calc() or True),
            "ejecutar_notas": lambda m, t, n: (self._exec_notepad() or True),
            "monitor_tareas": lambda m, t, n: (self._exec_taskmgr() or True),
            "ejecutar_skype": lambda m, t, n: (self._exec_skype() or True),
            "ejecutar_google_mail": lambda m, t, n: (self._exec_gmail() or True),
            "ejecutar_whatsapp": lambda m, t, n: (self._exec_whatsapp() or True),
            "ejecutar_facebook": lambda m, t, n: (self._exec_facebook() or True),
            "explorar_disco": lambda m, t, n: (self._exec_explorer() or True),
        }

        # Spelling mode toggle handlers
        self._command_handlers["modo_deletrear"] = lambda m, t, n: (setattr(self, 'spell_mode', True) or self._update_tray_icon() or self.notify('Modo deletrear activado') or True)
        self._command_handlers["salir_modo_deletrear"] = lambda m, t, n: (setattr(self, 'spell_mode', False) or self._update_tray_icon() or self.notify('Modo deletrear desactivado') or True)

        # Map simple spelling words to characters
        spell_map = {
            'alicante':'a','bilbao':'b','cadiz':'c','dinamarca':'d','españa':'e','francia':'f','gerona':'g','huelva':'h','italia':'i','jaen':'j',
            'kilo':'k','llamar':'l','madrid':'m','navarra':'n','oviedo':'o','portugal':'p','queso':'q','roma':'r','sevilla':'s','toledo':'t','unico':'u',
            'valencia':'v','uvedoble':'w','equis':'x','yugoslavia':'y','zaragoza':'z','nono':'ñ','espacio':' ',
        }
        for k, ch in spell_map.items():
            self._command_handlers[k] = (lambda m, t, n, ch=ch: (self._send_text(ch) or self.notify(f'Tecla {ch} enviada') or True))

        # Ensure simple regex patterns exist for spelled keys so they can be matched
        try:
            for k in list(spell_map.keys()):
                if k not in self.commands:
                    self.commands[k] = re.compile(rf"\b{re.escape(k)}\b", re.I)
        except Exception:
            pass

        # punctuation and special symbols handlers
        raw_special_map = {
            'comillas simples':'\'','comillas':'"','más':'+','menos':'-','asterisco':'*','dolar':'$','abrirparéntesis':'(',
            # Variantes sin acentos ni espacios para coincidir con patterns.txt
            'abrirparentesis':'(',
            'cerrar paréntesis':')','cerrarparéntesis':')','cerrar parentesis':')',
            'abrirllave':'{','cerrar llave':'}','abrir corchete':'[','cerrar corchete':']','subrayado':'_','subrrayado':'_','barrainvertida':'\\',
            'barra':'/','arroba':'@','porcentaje':'%','sostenido':'#','euro':'€','mayor que':'>','menor que':'<','iguala':'=','ampersan':'&',
            'abrir exclamacion':'¡','cerrar exclamacion':'!','abrir interrogacion':'¿','cerrar interrogacion':'?','barravertical':'|','cerilla':'ç','primero':'º','primera':'ª','angulo':'º',
            'punto':'.','coma':',','punto y coma':';','dos puntos':':'
        }

        def _normalize_key(k: str) -> str:
            nk = (k or '').lower()
            nk = nk.replace(' ', '')
            nk = nk.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
            nk = nk.replace('ñ', 'n').replace('ü', 'u').replace('º', 'o').replace('ª', 'a').replace('ç', 'c')
            nk = re.sub(r'[^a-z0-9]', '', nk)
            return nk

        # Register handlers under normalized command keys (so matching returns command keys)
        for k, ch in raw_special_map.items():
            cmd_key = _normalize_key(k)
            self._command_handlers[cmd_key] = (lambda m, t, n, ch=ch: (self._send_text(ch) or self.notify(f"Símbolo '{ch}' enviado") or True))

        # Ensure regex patterns exist under the normalized command key so _get_recognized_command
        # returns the normalized key (command) instead of the raw recognized text.
        try:
            for k in list(raw_special_map.keys()):
                key_normalized = _normalize_key(k)
                if key_normalized not in self.commands:
                    # Pattern should match either the original phrase or the normalized variant
                    pattern = rf"\b(?:{re.escape(k)}|{re.escape(key_normalized)})\b"
                    self.commands[key_normalized] = re.compile(pattern, re.I)
        except Exception:
            pass

        # puntoyaparte = '.' + Enter
        self._command_handlers['puntoyaparte'] = lambda m, t, n: (self._send_text('.') or pyautogui.press('enter') or self.notify('Punto y aparte enviado') or True)

        # Accent dead-keys: press the accent and wait for the next letter (no extra state required)
        self._command_handlers['acento'] = lambda m, t, n: (self._send_text("'") or self.notify('Acento agudo enviado') or True)
        self._command_handlers['grave'] = lambda m, t, n: (self._send_text('`') or self.notify('Acento grave enviado') or True)
        self._command_handlers['circunflejo'] = lambda m, t, n: (self._send_text('^') or self.notify('Circunflejo enviado') or True)
        self._command_handlers['dieresis'] = lambda m, t, n: (self._send_text('"') or self.notify('Diéresis enviada') or True)

    def _create_tray_icon(self):
        icon_image = self._create_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Activar", lambda _, __: self.activate()),
            pystray.MenuItem("Desactivar", lambda _, __: self.deactivate()),
            pystray.MenuItem("Mostrar ayuda", lambda _, __: self.show_help()),
            pystray.MenuItem("Salir", lambda _, __: self.stop()),
        )
        self.icon = pystray.Icon("xulia2", icon_image, "Xulia2 - Control por voz", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def _create_icon_image(self, color=(20, 100, 220, 255)):
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=color, outline=(255, 255, 255, 255), width=3)
        draw.text((18, 18), "V", fill=(255, 255, 255, 255))
        return image

    def _update_tray_icon(self):
        if self.icon is not None:
            # If assistant is inactive show a neutral/gray icon
            if not getattr(self, 'active', True):
                color = (140, 140, 140, 255)
            elif getattr(self, 'spell_mode', False):
                color = (20, 220, 20, 255)
            else:
                color = (220, 20, 20, 255) if self.dictation_mode else (20, 100, 220, 255)
            self.icon.icon = self._create_icon_image(color)

    def notify(self, message: str, toast: bool = True):
        print(f"Xulia2: {message}")
        if toast and self.icon is not None:
            try:
                self.toaster.show_toast("Xulia2", message, duration=2, threaded=True)
            except Exception:
                pass

    def _get_recognized_command(self, text: str):
        """Return the first command key that matches `text`, or None."""
        # Strip an optional leading 'comando' prefix before matching
        stripped = self._strip_command_prefix(text)
        normalized = (stripped or "").lower()
        try:
            for key, pattern in self.commands.items():
                try:
                    match = pattern.search(stripped)
                except Exception:
                    match = pattern.search(normalized)
                if match:
                    return key
        except Exception:
            pass
        return None

    def _strip_command_prefix(self, text: str):
        """If text begins with the word 'comando', remove it and any following separators.

        Examples removed: leading 'comando ', 'comando:', 'comando -', etc.
        """
        if not text:
            return text
        try:
            prefixes = getattr(self, 'command_prefixes', None)
            if not prefixes:
                prefix = getattr(self, 'command_prefix', 'comando') or 'comando'
                prefixes = [prefix]
            # build an alternation group with escaped prefixes
            p = "|".join(re.escape(x) for x in prefixes)
            group = f"(?:{p})"
            return re.sub(rf"^\s*{group}\b[\s,:-]*", "", text, flags=re.I)
        except Exception:
            return text

    def _strip_tecla_prefix(self, text: str):
        """If text begins with the word 'tecla', remove it and following separators.

        Used in spell mode so phrases like 'tecla alicante' are treated as 'alicante'.
        """
        if not text:
            return text
        try:
            prefixes = getattr(self, 'spell_prefixes', None)
            if not prefixes:
                prefix = getattr(self, 'spell_prefix', 'tecla') or 'tecla'
                prefixes = [prefix]
            p = "|".join(re.escape(x) for x in prefixes)
            group = f"(?:{p})"
            return re.sub(rf"^\s*{group}\b[\s,:-]*", "", text, flags=re.I)
        except Exception:
            return text

    def _show_recognition_system_message(self, engine: str, text: str):
        """Show a system notification with the engine in brackets, the first 50 chars and the command info."""
        try:
            display = (text or "")[:50]
            eng = (engine or "unknown")
            cmd = self._get_recognized_command(text)
            cmd_text = cmd if cmd else "no reconocido"
            msg = f"[{eng}] {display}\ncomando: {cmd_text}"
            # Use notify to print and show toast (if available)
            self.notify(msg, toast=True)
        except Exception as e:
            print("Error mostrando mensaje de sistema:", e)

    def start(self):
        recognizer_thread = threading.Thread(target=self._listen_loop, daemon=True)
        processor_thread = threading.Thread(target=self._process_commands, daemon=True)
        mouse_thread = threading.Thread(target=self._mouse_move_loop, daemon=True)
        recognizer_thread.start()
        processor_thread.start()
        mouse_thread.start()

        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def _mouse_move_loop(self):
        delay = 0.015
        while self.running:
            if self.active and self.mouse_direction:
                try:
                    x, y = pyautogui.position()
                    screen_width, screen_height = pyautogui.size()
                    step = self.mouse_speed_steps[max(0, min(self.mouse_speed_idx - 1, len(self.mouse_speed_steps)-1))]
                    if self.mouse_direction == "up":
                        y = max(0, y - step)
                    elif self.mouse_direction == "down":
                        y = min(screen_height - 1, y + step)
                    elif self.mouse_direction == "left":
                        x = max(0, x - step)
                    elif self.mouse_direction == "right":
                        x = min(screen_width - 1, x + step)
                    elif self.mouse_direction == 'diag1':
                        # first quadrant: right and up
                        d = int(step / math.sqrt(2))
                        x = min(screen_width - 1, x + d)
                        y = max(0, y - d)
                    elif self.mouse_direction == 'diag2':
                        # second quadrant: left and up
                        d = int(step / math.sqrt(2))
                        x = max(0, x - d)
                        y = max(0, y - d)
                    elif self.mouse_direction == 'diag3':
                        # third quadrant: left and down
                        d = int(step / math.sqrt(2))
                        x = max(0, x - d)
                        y = min(screen_height - 1, y + d)
                    elif self.mouse_direction == 'diag4':
                        # fourth quadrant: right and down
                        d = int(step / math.sqrt(2))
                        x = min(screen_width - 1, x + d)
                        y = min(screen_height - 1, y + d)
                    pyautogui.moveTo(x, y)
                except Exception as e:
                    msg = f"Excepción al obtener rectángulo del control: {e}"
                    print(msg)
                    traceback.print_exc()
                    try:
                        self.notify(msg)
                    except Exception:
                        pass
            time.sleep(delay)

    def stop(self):
        self.running = False
        self.active = False
        self.grid.hide()
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        sys.exit(0)

    def activate(self):
        self.active = True
        self.silenced_until = 0
        self.notify("Asistente activado")
        try:
            self._update_tray_icon()
        except Exception:
            pass

    def deactivate(self):
        self.active = False
        self.notify("Asistente desactivado")
        try:
            self._update_tray_icon()
        except Exception:
            pass

    def pause_temporarily(self, seconds=30):
        self.active = False
        self.silenced_until = time.time() + seconds
        self.notify(f"Asistente desactivado temporalmente {seconds}s")
        try:
            self._update_tray_icon()
        except Exception:
            pass

    def _process_commands(self):
        while self.running:
            try:
                text = self.command_queue.get(timeout=0.5)
            except Exception:
                continue
            self._handle_command(text)

    def _listen_loop(self):
        # Keep the microphone open and listening, but when the assistant is
        # inactive only accept the 'activate' command. This preserves device
        # detection while preventing other commands from being handled.
        try:
            if self.mic_index is not None:
                mic = sr.Microphone(device_index=self.mic_index)
            else:
                mic = sr.Microphone()
        except Exception as exc:
            print("Error al abrir el micrófono:", exc)
            self.notify("Error de micrófono")
            return

        with mic as source:
            # Calibration and recognizer tuning
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
            except Exception as exc:
                print("No se pudo ajustar ruido ambiente:", exc)
            try:
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.energy_threshold = 150
            except Exception:
                pass
            self.recognizer.pause_threshold = 0.6
            if hasattr(self.recognizer, "non_speaking_duration"):
                self.recognizer.non_speaking_duration = 0.5
            if hasattr(self.recognizer, "phrase_threshold"):
                self.recognizer.phrase_threshold = 0.45
            self.notify("Xulia2 listo para escuchar")

            while self.running:
                # Respect temporary silence period
                if not self.active and time.time() < self.silenced_until:
                    time.sleep(0.5)
                    continue
                try:
                    audio = self.recognizer.listen(source, timeout=6)
                except sr.WaitTimeoutError:
                    continue
                except Exception as exc:
                    print("Error en listen:", exc)
                    traceback.print_exc()
                    continue

                engine_used, text = self._recognize_audio(audio)
                if not text:
                    continue

                # If inactive, only allow the 'activate' command through
                if not self.active:
                    try:
                        cmd = self._get_recognized_command(text)
                        if cmd == 'activate':
                            self._show_recognition_system_message(engine_used, text)
                            self.command_queue.put(text)
                        else:
                            # ignore other commands while inactive
                            continue
                    except Exception:
                        continue

                else:
                    self._show_recognition_system_message(engine_used, text)
                    self.command_queue.put(text)

    def _recognize_audio(self, audio):
        engine = getattr(self, 'recognition_engine', 'auto')
        engine = (engine or 'auto').strip().lower()

        def recognize_vosk():
            try:
                from vosk import KaldiRecognizer
                import json
                rec = KaldiRecognizer(self.vosk_model, 16000)
                data = audio.get_wav_data(convert_rate=16000, convert_width=2)
                if rec.AcceptWaveform(data):
                    res = rec.Result()
                else:
                    res = rec.FinalResult()
                j = json.loads(res)
                return j.get('text', '')
            except Exception as e:
                print('Vosk recognition error:', e)
                return ''

        def recognize_sphinx():
            try:
                return self.recognizer.recognize_sphinx(audio, language=self.language)
            except Exception as e:
                print('Pocketsphinx recognition error:', e)
                return ''

        def recognize_google():
            try:
                return self.recognizer.recognize_google(audio, language=self.language)
            except Exception as e:
                print('Google recognition error:', e)
                return ''

        if engine == 'vosk':
            if getattr(self, 'vosk_available', False) and self.vosk_model is not None:
                text = recognize_vosk()
                if text:
                    return ('vosk', text)
                print('Vosk no devolvió texto. Intentando fallback a Google/pocketsphinx.')
            else:
                print('Vosk no está disponible; intentando motores alternativos.')
            # If Vosk was selected but unavailable or failed, fall back to auto behavior.
            engine = 'auto'

        if engine == 'google':
            text = recognize_google()
            if text:
                return ('google', text)
            print('Google no devolvió texto. Intentando fallback a pocketsphinx.')
            t = recognize_sphinx()
            return ('sphinx', t)

        if engine == 'sphinx':
            t = recognize_sphinx()
            return ('sphinx', t)

        # auto behavior: prefer Vosk if available, then pocketsphinx, then Google.
        if getattr(self, 'vosk_available', False) and self.vosk_model is not None:
            text = recognize_vosk()
            if text:
                return ('vosk', text)
        # No Vosk available or Vosk failed, try pocketsphinx then Google.
        text = recognize_sphinx()
        if text:
            return ('sphinx', text)
        return ('google', recognize_google())

    def _handle_command(self, text: str):
        # Remove leading 'comando' if present so matching ignores it
        stripped = self._strip_command_prefix(text)
        normalized = (stripped or "").lower()
        # If assistant is deactivated, still listen but only accept the 'activate' command.
        if not getattr(self, 'active', True):
            try:
                cmd = self._get_recognized_command(text)
                if cmd == 'activate':
                    handler = self._command_handlers.get('activate')
                    if handler:
                        try:
                            handler(None, stripped, normalized)
                        except Exception as e:
                            print(f"Error handling activate while inactive: {e}")
                            traceback.print_exc()
                # ignore any other commands while inactive
            except Exception:
                pass
            return
        # If dictation mode is active, only allow the 'dictation_off' or 'modo_deletrear' commands.
        if getattr(self, 'dictation_mode', False):
            try:
                # check for explicit commands that should still function while dictating
                for cmd_key in ('dictation_off', 'modo_deletrear', 'salir_modo_deletrear'):
                    pat = self.commands.get(cmd_key)
                    if pat and pat.search(stripped):
                        handler = self._command_handlers.get(cmd_key)
                        if handler:
                            try:
                                handler(None, stripped, normalized)
                            except Exception:
                                pass
                        return
            except Exception:
                pass
            # otherwise treat the entire recognized phrase as dictation text
            try:
                self._dictate_text(stripped)
            except Exception:
                pass
            return
        # Process commands in the order defined by the configuration (self.commands is ordered)
        try:
            # If we are in spell mode, restrict matching to the allowed spell keys
            if getattr(self, 'spell_mode', False):
                # In spell mode, strip optional 'tecla' (or configured prefix)
                stripped_spell = self._strip_tecla_prefix(stripped)
                normalized_spell = (stripped_spell or '').lower()
                allowed = set(self._spell_allowed)
                allowed.update(['salir_modo_deletrear','modo_deletrear'])
                for key in list(self.commands.keys()):
                    # allow keys that match either the literal key or a normalized form
                    key_norm = key.replace(' ', '').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
                    if key not in allowed and key_norm not in allowed:
                        continue
                    pattern = self.commands.get(key)
                    try:
                        match = pattern.search(stripped_spell)
                    except Exception:
                        match = pattern.search(normalized_spell)
                    if not match:
                        continue
                    handler = self._command_handlers.get(key)
                    if handler:
                        try:
                            try:
                                matched_text = match.group(0) if match else ''
                            except Exception:
                                matched_text = ''
                            print(f"Comando reconocido (deletrear): key='{key}' matched='{matched_text}' text='{text}'")
                            handled = handler(match, stripped_spell, normalized_spell)
                            if handled:
                                return
                        except Exception as e:
                            print(f"Error handling spell command '{key}': {e}")
                            traceback.print_exc()
                            return
                # nothing matched in spell mode
                self.notify('Comando no reconocido en modo deletrear')
                return
            else:
                for key, pattern in self.commands.items():
                    try:
                        match = pattern.search(stripped)
                    except Exception:
                        # fallback to searching normalized text
                        match = pattern.search(normalized)
                    if not match:
                        continue
                    handler = self._command_handlers.get(key)
                    if handler:
                        try:
                            # Log the recognized command key and matched text
                            try:
                                matched_text = match.group(0) if match else ''
                            except Exception:
                                matched_text = ''
                            print(f"Comando reconocido: key='{key}' matched='{matched_text}' text='{text}'")
                            # Pass the stripped text to handlers so they receive the command without the word 'comando'
                            handled = handler(match, stripped, normalized)
                            if handled:
                                # If a single-use shift was active, release it after handling the next command
                                try:
                                    if getattr(self, '_single_shift', False) and key != 'una_mayuscula':
                                        pyautogui.keyUp('shift')
                                        self._single_shift = False
                                        self._shift_locked = False
                                        self.notify('Mayúscula (única) desactivada')
                                except Exception:
                                    pass
                                return
                        except Exception as e:
                            print(f"Error handling command '{key}': {e}")
                            traceback.print_exc()
                            return
        except Exception as e:
            print(f"Error iterating commands: {e}")
            traceback.print_exc()

        # If nothing matched and dictation mode is active, treat as dictation
        if self.dictation_mode:
            self._dictate_text(text)
            return

        # finally, generic mouse fallback
        self._handle_generic_mouse_commands(normalized)

    def _dictate_text(self, phrase):
        try:
            text = (phrase or '').strip()
            if not text:
                return

            # Determine literal-word handling
            literal = getattr(self, 'literal_word', 'literal') or 'literal'
            lower = text.lower()
            lit_lower = literal.lower()
            # If user said the literal word alone or twice, send the literal word as text
            if lower == lit_lower or lower == f"{lit_lower} {lit_lower}":
                send_text = literal
            elif lower.startswith(lit_lower + ' '):
                # send remainder literally (no replacements)
                send_text = text[len(literal):].lstrip()
            else:
                # apply replacement rules in order
                send_text = text
                repls = getattr(self, 'dictation_replacements', None) or []
                for pat, repl in repls:
                    try:
                        send_text = pat.sub(repl, send_text)
                    except Exception:
                        continue

            # Use clipboard paste to send the text to the active window (preserve clipboard)
            try:
                old_clip = pyperclip.paste()
            except Exception:
                old_clip = None
            try:
                pyperclip.copy(send_text + " ")
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.12)
            finally:
                if old_clip is not None:
                    try:
                        pyperclip.copy(old_clip)
                        time.sleep(0.03)
                    except Exception:
                        pass
            self.last_phrases.append(send_text)
            self.notify("Dictado escrito", toast=False)
        except Exception as exc:
            print("Error al dictar texto:", exc)
            traceback.print_exc()

    def _paste_text(self, text: str) -> bool:
        """Copy `text` to the clipboard and paste it (restoring clipboard)."""
        try:
            old_clip = None
            try:
                old_clip = pyperclip.paste()
            except Exception:
                old_clip = None
            try:
                pyperclip.copy(text)
                time.sleep(0.03)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.03)
            finally:
                if old_clip is not None:
                    try:
                        pyperclip.copy(old_clip)
                        time.sleep(0.02)
                    except Exception:
                        pass
            return True
        except Exception as e:
            print("Error en _paste_text:", e)
            traceback.print_exc()
            return False

    def _send_text(self, ch: str) -> bool:
        """Send text to the active window. Use clipboard-paste when in spell_mode, otherwise typewrite."""
        try:
            if getattr(self, 'spell_mode', False):
                return self._paste_text(ch)
            else:
                try:
                    pyautogui.typewrite(ch)
                    return True
                except Exception:
                    # Fallback to paste if typewrite fails
                    return self._paste_text(ch)
        except Exception as e:
            print("Error en _send_text:", e)
            traceback.print_exc()
            return False

    def _correct_last_phrase(self):
        if not self.last_phrases:
            self.notify("No hay frase para corregir")
            return
        phrase = self.last_phrases.pop()
        # remove phrase characters plus the trailing space
        to_erase = len(phrase) + 1
        try:
            pyautogui.press("backspace", presses=to_erase, interval=0.01)
        except Exception:
            # fallback to repeated calls
            for _ in range(to_erase):
                pyautogui.press("backspace")
        self.notify("Última frase corregida")

    def _click_grid_cell(self, cell_number):
        self.mouse_direction = None
        x, y = self.grid.cell_center(cell_number)
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click()
        self.notify(f"Clic en celda {cell_number}")

    def _set_mouse_speed(self, level: int):
        try:
            lvl = max(1, min(6, int(level)))
            self.mouse_speed_idx = lvl
            self.notify(f'Velocidad ratón establecida {lvl}', toast=False)
        except Exception:
            pass

    def _increase_mouse_speed(self):
        if self.mouse_speed_idx < 6:
            self.mouse_speed_idx += 1
            self.notify(f'Velocidad ratón {self.mouse_speed_idx}', toast=False)

    def _decrease_mouse_speed(self):
        if self.mouse_speed_idx > 1:
            self.mouse_speed_idx -= 1
            self.notify(f'Velocidad ratón {self.mouse_speed_idx}', toast=False)

    def _mouse_center(self):
        try:
            w, h = pyautogui.size()
            pyautogui.moveTo(int(w / 2), int(h / 2), duration=0.15)
            self.mouse_direction = None
            self.notify('Ratón al centro', toast=False)
        except Exception as e:
            print('Error en _mouse_center:', e)

    def _mouse_quadrant(self, q: int):
        try:
            w, h = pyautogui.size()
            half_w = int(w / 2)
            half_h = int(h / 2)
            # centers of quadrants: 1=top-right,2=top-left,3=bottom-left,4=bottom-right
            if q == 1:
                x = int((half_w + w) / 2)
                y = int(half_h / 2)
            elif q == 2:
                x = int(half_w / 2)
                y = int(half_h / 2)
            elif q == 3:
                x = int(half_w / 2)
                y = int((half_h + h) / 2)
            else:
                x = int((half_w + w) / 2)
                y = int((half_h + h) / 2)
            pyautogui.moveTo(x, y, duration=0.18)
            self.mouse_direction = None
            self.notify(f'Ratón al cuadrante {q}', toast=False)
        except Exception as e:
            print('Error en _mouse_quadrant:', e)

    def _mouse_double_click(self):
        try:
            # Ensure an explicit left-button double click
            pyautogui.doubleClick(button='left')
            self.mouse_direction = None
            self.notify('Doble clic izquierdo', toast=False)
        except Exception as e:
            print('Error en _mouse_double_click:', e)

    def _mouse_click_right(self):
        try:
            pyautogui.click(button='right')
            self.notify('Clic derecho', toast=False)
        except Exception as e:
            print('Error en _mouse_click_right:', e)

    def _mouse_click_left(self):
        try:
            pyautogui.click(button='left')
            self.notify('Clic izquierdo', toast=False)
        except Exception as e:
            print('Error en _mouse_click_left:', e)

    def _mouse_click_middle(self):
        try:
            # Some systems support middle click via button='middle'
            pyautogui.click(button='middle')
            self.notify('Clic central', toast=False)
        except Exception as e:
            print('Error en _mouse_click_middle:', e)

    def _mouse_hold(self):
        try:
            # press and hold left button
            pyautogui.mouseDown(button='left')
            # do not clear mouse_direction; allow movement while held
            self.notify('Manteniendo pulsación', toast=False)
        except Exception as e:
            print('Error en _mouse_hold:', e)

    def _mouse_release_all_and_stop(self):
        try:
            # release common buttons
            try:
                pyautogui.mouseUp(button='left')
            except Exception:
                pass
            try:
                pyautogui.mouseUp(button='right')
            except Exception:
                pass
            try:
                pyautogui.mouseUp(button='middle')
            except Exception:
                pass
            # stop directional movement
            self.mouse_direction = None
            self.notify('Ratón detenido y botones liberados', toast=False)
        except Exception as e:
            print('Error en _mouse_release_all_and_stop:', e)

    def _mouse_release_left(self):
        try:
            pyautogui.mouseUp(button='left')
            self.notify('Botón izquierdo soltado', toast=False)
        except Exception as e:
            print('Error en _mouse_release_left:', e)

    # Modifier and caps handling
    def _enable_shift_lock(self):
        try:
            # Toggle Caps Lock ON using Win API if not already on
            VK_CAPITAL = 0x14
            state = ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1
            if state == 0:
                # send key press to toggle CapsLock
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 2, 0)
                self._shift_locked = True
                self._single_shift = False
                self.notify('Bloq Mayúsculas activado')
            else:
                self._shift_locked = True
                self.notify('Bloq Mayúsculas ya estaba activado')
            return True
        except Exception as e:
            print('Error en _enable_shift_lock:', e)
            traceback.print_exc()
            return False

    def _disable_shift_lock(self):
        try:
            # Toggle Caps Lock OFF using Win API if currently on
            VK_CAPITAL = 0x14
            state = ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1
            if state == 1:
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.keybd_event(VK_CAPITAL, 0, 2, 0)
                self._shift_locked = False
                self._single_shift = False
                self.notify('Bloq Mayúsculas desactivado')
            else:
                self._shift_locked = False
                self.notify('Bloq Mayúsculas ya estaba desactivado')
            return True
        except Exception as e:
            print('Error en _disable_shift_lock:', e)
            traceback.print_exc()
            return False

    def _single_shift_once(self):
        try:
            # Hold shift until the next handled command completes
            pyautogui.keyDown('shift')
            self._single_shift = True
            self._shift_locked = True
            self.notify('Mayúscula (única) activada')
            return True
        except Exception as e:
            print('Error en _single_shift_once:', e)
            traceback.print_exc()
            return False

    def _press_control(self):
        try:
            if not getattr(self, '_ctrl_down', False):
                pyautogui.keyDown('ctrl')
                self._ctrl_down = True
                self.notify('Control pulsado')
            else:
                self.notify('Control ya estaba pulsado')
            return True
        except Exception as e:
            print('Error en _press_control:', e)
            traceback.print_exc()
            return False

    def _release_control(self):
        try:
            if getattr(self, '_ctrl_down', False):
                pyautogui.keyUp('ctrl')
                self._ctrl_down = False
                self.notify('Control levantado')
            else:
                self.notify('Control no estaba pulsado')
            return True
        except Exception as e:
            print('Error en _release_control:', e)
            traceback.print_exc()
            return False

    def _press_alt(self):
        try:
            if not getattr(self, '_alt_down', False):
                pyautogui.keyDown('alt')
                self._alt_down = True
                self.notify('Alt pulsado')
            else:
                self.notify('Alt ya estaba pulsado')
            return True
        except Exception as e:
            print('Error en _press_alt:', e)
            traceback.print_exc()
            return False

    def _release_alt(self):
        try:
            if getattr(self, '_alt_down', False):
                pyautogui.keyUp('alt')
                self._alt_down = False
                self.notify('Alt levantado')
            else:
                self.notify('Alt no estaba pulsado')
            return True
        except Exception as e:
            print('Error en _release_alt:', e)
            traceback.print_exc()
            return False

    def _press_altgr(self):
        try:
            if getattr(self, '_altgr_down', False):
                self.notify('AltGr ya estaba pulsado')
                return True
            # Try pyautogui keyDown variants
            try:
                pyautogui.keyDown('altgr')
                self._altgr_down = True
                self._altgr_via_ctypes = False
                self.notify('AltGr pulsado')
                return True
            except Exception:
                pass
            try:
                pyautogui.keyDown('altright')
                self._altgr_down = True
                self._altgr_via_ctypes = False
                self.notify('AltGr (altright) pulsado')
                return True
            except Exception:
                pass
            # Fallback: use keybd_event for VK_RMENU
            try:
                VK_RMENU = 0xA5
                ctypes.windll.user32.keybd_event(VK_RMENU, 0, 0, 0)
                self._altgr_down = True
                self._altgr_via_ctypes = True
                self.notify('AltGr pulsado (fallback)')
                return True
            except Exception as e:
                print('Error en _press_altgr fallback:', e)
                traceback.print_exc()
                return False
        except Exception as e:
            print('Error en _press_altgr (outer):', e)
            traceback.print_exc()
            return False

    def _release_altgr(self):
        try:
            if not getattr(self, '_altgr_down', False):
                self.notify('AltGr no estaba pulsado')
                return True
            # release depending on how it was pressed
            if getattr(self, '_altgr_via_ctypes', False):
                try:
                    VK_RMENU = 0xA5
                    KEYEVENTF_KEYUP = 0x0002
                    ctypes.windll.user32.keybd_event(VK_RMENU, 0, KEYEVENTF_KEYUP, 0)
                    self._altgr_down = False
                    self._altgr_via_ctypes = False
                    self.notify('AltGr levantado (fallback)')
                    return True
                except Exception as e:
                    print('Error liberando AltGr via ctypes:', e)
                    traceback.print_exc()
            # try pyautogui releases
            try:
                pyautogui.keyUp('altgr')
                self._altgr_down = False
                self._altgr_via_ctypes = False
                self.notify('AltGr levantado')
                return True
            except Exception:
                pass
            try:
                pyautogui.keyUp('altright')
                self._altgr_down = False
                self._altgr_via_ctypes = False
                self.notify('AltGr (altright) levantado')
                return True
            except Exception:
                pass
            # final fallback: try releasing VK_RMENU via ctypes keybd_event keyup
            try:
                VK_RMENU = 0xA5
                KEYEVENTF_KEYUP = 0x0002
                ctypes.windll.user32.keybd_event(VK_RMENU, 0, KEYEVENTF_KEYUP, 0)
                self._altgr_down = False
                self._altgr_via_ctypes = False
                self.notify('AltGr levantado (final fallback)')
                return True
            except Exception as e:
                print('Error final liberando AltGr:', e)
                traceback.print_exc()
                return False
        except Exception as e:
            print('Error en _release_altgr (outer):', e)
            traceback.print_exc()
            return False
        
    def _press_shift(self):
        try:
            if not getattr(self, '_shift_down', False):
                pyautogui.keyDown('shift')
                self._shift_down = True
                # cancel any single-shift pending
                self._single_shift = False
                self.notify('Shift pulsado (selección)')
            else:
                self.notify('Shift ya estaba pulsado')
            return True
        except Exception as e:
            print('Error en _press_shift:', e)
            traceback.print_exc()
            return False

    def _release_shift(self):
        try:
            if getattr(self, '_shift_down', False):
                pyautogui.keyUp('shift')
                self._shift_down = False
                self.notify('Shift levantado (selección)')
            else:
                self.notify('Shift no estaba pulsado')
            return True
        except Exception as e:
            print('Error en _release_shift:', e)
            traceback.print_exc()
            return False

    def _open_start_menu(self, match, text, normalized):
        try:
            # Try common pyautogui options first
            tried = []
            for keyname in ('winleft', 'win'):
                try:
                    pyautogui.press(keyname)
                    self.notify('Menú Inicio abierto')
                    return True
                except Exception:
                    tried.append(keyname)
            # try hotkey variants
            try:
                pyautogui.hotkey('winleft')
                self.notify('Menú Inicio abierto')
                return True
            except Exception:
                pass

            try:
                pyautogui.hotkey('win')
                self.notify('Menú Inicio abierto')
                return True
            except Exception:
                pass

            # Fallback: use Windows API keybd_event to press/release Left Win
            try:
                VK_LWIN = 0x5B
                KEYEVENTF_KEYUP = 0x0002
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                self.notify('Menú Inicio abierto (fallback)')
                return True
            except Exception as e:
                print('Fallback keybd_event failed in _open_start_menu:', e)
                traceback.print_exc()
                return False
        except Exception as e:
            print('Error en _open_start_menu (outer):', e)
            traceback.print_exc()
            return False

    def _show_desktop(self, match, text, normalized):
        try:
            # Toggle show desktop (Win+D). We mark the state as shown.
            pyautogui.hotkey('winleft', 'd')
            self._desktop_shown = True
            self.notify('Escritorio mostrado')
            return True
        except Exception as e:
            print('Error en _show_desktop:', e)
            traceback.print_exc()
            return False

    def _restore_desktop(self, match, text, normalized):
        try:
            if not self._desktop_shown:
                self.notify('El escritorio no está mostrado')
                return True
            # Toggle again to restore windows
            pyautogui.hotkey('winleft', 'd')
            self._desktop_shown = False
            self.notify('Ventanas restauradas')
            return True
        except Exception as e:
            print('Error en _restore_desktop:', e)
            traceback.print_exc()
            return False

    def _parse_slot_token(self, token: str) -> int:
        """Parse a slot token like 'uno' or '3' and return slot index 0..9. Returns 0 if None or invalid."""
        if not token:
            return 0
        t = token.strip().lower()
        word_map = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
            'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10
        }
        if t.isdigit():
            try:
                v = int(t)
                if 1 <= v <= 10:
                    return v - 1
            except Exception:
                return 0
        if t in word_map:
            return word_map[t] - 1
        return 0

    def _handle_copy(self, match, text, normalized):
        try:
            slot_token = match.groupdict().get('slot') if match else None
            # If no slot specified, use normal clipboard (Ctrl+C) and do not store in slots
            if not slot_token:
                try:
                    pyautogui.hotkey('ctrl', 'c')
                    time.sleep(0.06)
                except Exception:
                    pass
                self.notify('Copiado al portapapeles', toast=False)
                return True

            idx = self._parse_slot_token(slot_token)
            # copy selection to clipboard and store in slot
            try:
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.06)
                data = pyperclip.paste()
            except Exception:
                data = None
            if data is None:
                self.notify('Nada copiado')
                return True
            self.clipboard_slots[idx] = data
            self.notify(f'Copiado en ranura {idx+1}', toast=False)
            return True
        except Exception as e:
            print('Error en _handle_copy:', e)
            traceback.print_exc()
            return True

    def _handle_cut(self, match, text, normalized):
        try:
            slot_token = match.groupdict().get('slot') if match else None
            # If no slot specified, perform normal cut (Ctrl+X) and do not store in slots
            if not slot_token:
                try:
                    pyautogui.hotkey('ctrl', 'x')
                    time.sleep(0.06)
                except Exception:
                    pass
                self.notify('Cortado al portapapeles', toast=False)
                return True

            idx = self._parse_slot_token(slot_token)
            # cut selection to clipboard (Ctrl+X) and store in slot
            try:
                pyautogui.hotkey('ctrl', 'x')
                time.sleep(0.06)
                data = pyperclip.paste()
            except Exception:
                data = None
            if data is None:
                self.notify('Nada cortado')
                return True
            self.clipboard_slots[idx] = data
            self.notify(f'Cortado en ranura {idx+1}', toast=False)
            return True
        except Exception as e:
            print('Error en _handle_cut:', e)
            traceback.print_exc()
            return True

    def _handle_paste(self, match, text, normalized):
        try:
            slot_token = match.groupdict().get('slot') if match else None
            # If no slot specified, perform normal paste from system clipboard
            if not slot_token:
                try:
                    pyautogui.hotkey('ctrl', 'v')
                except Exception:
                    pass
                self.notify('Pegado desde portapapeles', toast=False)
                return True

            idx = self._parse_slot_token(slot_token)
            data = self.clipboard_slots[idx]
            if data is None:
                self.notify(f'Ranura {idx+1} vacía')
                return True
            # Save current clipboard and replace with slot content
            try:
                old = pyperclip.paste()
            except Exception:
                old = None
            try:
                pyperclip.copy(data)
                time.sleep(0.06)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.08)
            finally:
                if old is not None:
                    try:
                        pyperclip.copy(old)
                    except Exception:
                        pass
            self.notify(f'Pegado ranura {idx+1}', toast=False)
            return True
        except Exception as e:
            print('Error en _handle_paste:', e)
            traceback.print_exc()
            return True

    # Handlers used by the ordered dispatch table
    def _handle_cell_click(self, match, text, normalized):
        try:
            cell = int(match.group(1))
            self._click_grid_cell(cell)
            return True
        except Exception:
            return False

    def _handle_ribbon(self, match, text, normalized):
        # If office_tab pattern also present, delegate to opening office tab
        try:
            office_pat = self.commands.get("office_tab")
            if office_pat and office_pat.search(normalized):
                self._open_office_tab(normalized)
                return True
            # fallback: still try to open office tab by name
            self._open_office_tab(normalized)
            return True
        except Exception:
            return False

    def _handle_named_button(self, match, text, normalized):
        try:
            name = match.group(1).strip()
            if name:
                self._move_to_named_button(name)
                return True
        except Exception:
            pass
        return False

    def _handle_named_menu(self, match, text, normalized):
        try:
            name = match.group(1).strip()
            if name:
                self._move_to_named_menu(name)
                return True
        except Exception:
            pass
        return False

    def _handle_click_button(self, match, text, normalized):
        try:
            self._click_named_button(normalized)
            return True
        except Exception:
            return False

    def _handle_borrar_palabra(self, match, text, normalized):
        try:
            pyautogui.hotkey("ctrl", "left")
            pyautogui.hotkey("ctrl", "shift", "right")
            pyautogui.press("delete")
            self.notify("Palabra anterior borrada")
            return True
        except Exception:
            return False

    def _handle_borrar_siguiente_palabra(self, match, text, normalized):
        try:
            pyautogui.hotkey("ctrl", "right")
            pyautogui.hotkey("ctrl", "shift", "right")
            pyautogui.press("delete")
            self.notify("Siguiente palabra borrada")
            return True
        except Exception:
            return False

    def _handle_borrar_linea(self, match, text, normalized):
        try:
            pyautogui.press("home")
            pyautogui.hotkey("shift", "end")
            pyautogui.press("delete")
            self.notify("Línea borrada")
            return True
        except Exception:
            return False

    # --- Window and app helpers ---
    def _parse_number_token(self, token: str) -> int:
        if not token:
            return 0
        t = token.strip().lower()
        word_map = {
            'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
            'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
            'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15,
            'dieciseis': 16, 'dieciséis': 16, 'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19,
            'veinte': 20
        }
        if t.isdigit():
            try:
                v = int(t)
                if 1 <= v <= 20:
                    return v
            except Exception:
                return 0
        return word_map.get(t, 0)

    def _handle_tecla_numero(self, match, text, normalized):
        """Handle 'tecla N' commands where N is 0..30 (words or digits).

        Sends the digit characters of N to the active window (e.g. '12' -> presses '1' then '2').
        """
        try:
            token = None
            if match:
                try:
                    token = match.group(1)
                except Exception:
                    token = None
            if not token:
                m = re.search(r"\b(\d{1,2})\b", normalized)
                token = m.group(1) if m else None

            if not token:
                return False

            t = token.strip().lower()
            words = {
                'cero': 0, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
                'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
                'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15,
                'dieciseis': 16, 'dieciséis': 16, 'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19,
                'veinte': 20, 'veintiuno': 21, 'veintidos': 22, 'veintidós': 22, 'veintitrés': 23, 'veintitres': 23,
                'veinticuatro': 24, 'veinticinco': 25, 'veintiseis': 26, 'veintiséis': 26,
                'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29, 'treinta': 30
            }

            if t.isdigit():
                try:
                    n = int(t)
                except Exception:
                    return False
            else:
                n = words.get(t, None)
                if n is None:
                    # try to strip accents and retry
                    t2 = re.sub(r'[áéíóúÁÉÍÓÚ]', lambda m: {'á':'a','é':'e','í':'i','ó':'o','ú':'u'}[m.group(0).lower()], t)
                    n = words.get(t2, None)
            if n is None:
                return False
            if not (0 <= n <= 30):
                return False

            s = str(n)
            for ch in s:
                pyautogui.press(ch)
                time.sleep(0.02)
            self.notify(f'Tecla(s) {s} enviada(s)')
            return True
        except Exception as e:
            print('Error en _handle_tecla_numero:', e)
            traceback.print_exc()
            return False

    def _activate_window_by_token(self, token: str):
        try:
            if not token:
                return False
            n = self._parse_number_token(token)
            if n <= 0:
                return False
            # For taskbar shortcuts, Windows supports Win+1..Win+9 and Win+0 for 10
            if 1 <= n <= 10:
                key = '0' if n == 10 else str(n)
                try:
                    pyautogui.hotkey('winleft', key)
                    self.notify(f'Activando ventana {n}')
                    return True
                except Exception:
                    pass
            # Fallback: try to activate the N-th top-level window using pywinauto
            try:
                desktop = Desktop(backend='uia')
                wins = desktop.windows()
                if len(wins) >= n:
                    w = wins[n-1]
                    try:
                        w.set_focus()
                    except Exception:
                        try:
                            w.wrapper_object().set_focus()
                        except Exception:
                            pass
                    self.notify(f'Activando ventana {n} (fallback)')
                    return True
            except Exception:
                pass
            self.notify(f'No se pudo activar ventana {n}')
            return False
        except Exception as e:
            print('Error en _activate_window_by_token:', e)
            traceback.print_exc()
            return False

    def _switch_next_app(self):
        try:
            pyautogui.hotkey('alt', 'tab')
            return True
        except Exception as e:
            print('Error en _switch_next_app:', e)
            return False

    def _switch_prev_app(self):
        try:
            pyautogui.hotkey('alt', 'shift', 'tab')
            return True
        except Exception as e:
            print('Error en _switch_prev_app:', e)
            return False

    def _maximize_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                SW_MAXIMIZE = 3
                ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
                self.notify('Ventana maximizada')
                return True
        except Exception as e:
            print('Error en _maximize_window:', e)
        return False

    def _minimize_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                SW_MINIMIZE = 6
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
                self.notify('Ventana minimizada')
                return True
        except Exception as e:
            print('Error en _minimize_window:', e)
        return False

    def _restore_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                SW_RESTORE = 9
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                self.notify('Ventana restaurada')
                return True
        except Exception as e:
            print('Error en _restore_window:', e)
        return False

    def _close_window(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                WM_CLOSE = 0x0010
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                self.notify('Cerrando ventana')
                return True
        except Exception as e:
            print('Error en _close_window:', e)
        return False

    def _close_application(self):
        # Try graceful close first, fallback to Alt+F4
        try:
            if self._close_window():
                time.sleep(0.08)
                return True
            pyautogui.hotkey('alt', 'f4')
            self.notify('Cerrando aplicación')
            return True
        except Exception as e:
            print('Error en _close_application:', e)
            return False

    def _snap_window_left(self):
        try:
            pyautogui.hotkey('winleft', 'left')
            self.notify('Ventana a la izquierda')
            return True
        except Exception as e:
            print('Error en _snap_window_left:', e)
            return False

    def _snap_window_right(self):
        try:
            pyautogui.hotkey('winleft', 'right')
            self.notify('Ventana a la derecha')
            return True
        except Exception as e:
            print('Error en _snap_window_right:', e)
            return False

    # --- Quick exec helpers ---
    def _exec_word(self):
        try:
            subprocess.Popen(['winword'])
            self.notify('Abriendo Word')
            return True
        except Exception:
            try:
                subprocess.Popen(['start', 'winword'], shell=True)
                self.notify('Abriendo Word (fallback)')
                return True
            except Exception as e:
                print('Error abriendo Word:', e)
                return False

    def _exec_browser(self):
        try:
            webbrowser.open('about:blank')
            self.notify('Abriendo navegador')
            return True
        except Exception as e:
            print('Error abriendo navegador:', e)
            return False

    def _exec_calc(self):
        try:
            subprocess.Popen(['calc'])
            self.notify('Abriendo calculadora')
            return True
        except Exception as e:
            print('Error abriendo calculadora:', e)
            return False

    def _exec_notepad(self):
        try:
            subprocess.Popen(['notepad'])
            self.notify('Abriendo Bloc de notas')
            return True
        except Exception as e:
            print('Error abriendo notepad:', e)
            return False

    def _exec_taskmgr(self):
        try:
            # Try to launch Task Manager through the Shell (Explorer) process so
            # it runs non-elevated even if this Python process is elevated.
            try:
                import win32com.client
                shell = win32com.client.Dispatch("Shell.Application")
                shell.ShellExecute('taskmgr.exe', '', '', 'open', 1)
                self.notify('Abriendo monitor de tareas')
                return True
            except Exception:
                # Fallback to a normal subprocess spawn if pywin32 is not available
                subprocess.Popen(['taskmgr'])
                self.notify('Abriendo monitor de tareas')
                return True
        except Exception as e:
            print('Error abriendo taskmgr:', e)
            return False

    def _exec_skype(self):
        try:
            subprocess.Popen(['skype'])
            self.notify('Abriendo Skype')
            return True
        except Exception as e:
            print('Error abriendo Skype:', e)
            # fallback: try browser skype web
            try:
                webbrowser.open('https://web.skype.com')
                return True
            except Exception:
                return False

    def _exec_gmail(self):
        try:
            webbrowser.open('https://mail.google.com')
            self.notify('Abriendo Gmail')
            return True
        except Exception as e:
            print('Error abriendo Gmail:', e)
            return False

    def _exec_whatsapp(self):
        try:
            webbrowser.open('https://web.whatsapp.com')
            self.notify('Abriendo WhatsApp Web')
            return True
        except Exception as e:
            print('Error abriendo WhatsApp:', e)
            return False

    def _exec_facebook(self):
        try:
            webbrowser.open('https://www.facebook.com')
            self.notify('Abriendo Facebook')
            return True
        except Exception as e:
            print('Error abriendo Facebook:', e)
            return False

    def _exec_explorer(self):
        try:
            subprocess.Popen(['explorer'])
            self.notify('Abriendo Explorador de archivos')
            return True
        except Exception as e:
            print('Error abriendo explorador:', e)
            return False

    def _click_named_button(self, normalized):
        words = re.sub(r"\b(bot[oó]n|bot[oó]es|clicar|pulsar|press|sobre)\b", "", normalized)
        words = words.strip()
        if not words:
            self.notify("No se detectó nombre de botón")
            return
        try:
            desktop = Desktop(backend="uia")
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                active = desktop.window(handle=hwnd)
            except Exception:
                try:
                    wins = desktop.windows()
                    active = wins[0] if wins else None
                except Exception:
                        active = None
                return
            # try child button first
            control = active.child_window(title_re=f".*{re.escape(words)}.*", control_type="Button")
            if control.exists(timeout=2):
                try:
                    rect = control.rectangle()
                    x = int((rect.left + rect.right) / 2)
                    y = int((rect.top + rect.bottom) / 2)
                    pyautogui.moveTo(x, y, duration=0.12)
                    self.notify(f"Ratón colocado sobre botón '{words}'")
                    return
                except Exception:
                    pass

            # fallback: search any descendant with matching title text
            try:
                descendants = active.descendants(control_type="Button")
                for d in descendants:
                    try:
                        title = d.window_text()
                        if title and re.search(re.escape(words), title, re.I):
                            rect = d.rectangle()
                            x = int((rect.left + rect.right) / 2)
                            y = int((rect.top + rect.bottom) / 2)
                            pyautogui.moveTo(x, y, duration=0.12)
                            self.notify(f"Ratón colocado sobre botón '{title}'")
                            return
                    except Exception as e:
                        print(f"Excepción iterando descendant: {e}")
                        traceback.print_exc()
                        continue
            except Exception as e:
                msg = f"Excepción al listar descendants: {e}"
                print(msg)
                traceback.print_exc()
                try:
                    self.notify(msg)
                except Exception:
                    pass
        except Exception as e:
            msg = f"Excepción al listar descendants: {e}"
            print(msg)
            traceback.print_exc()
            pass
        self.notify(f"No se encontró botón '{words}'")

    def _move_to_named_menu(self, name: str):
        # Move mouse over a menu item with the given visible text in the active window
        words = name.strip()
        if not words:
            self.notify("No se detectó nombre de menú")
            return
        try:
            desktop = Desktop(backend="uia")
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                active = desktop.window(handle=hwnd)
            except Exception:
                try:
                    wins = desktop.windows()
                    active = wins[0] if wins else None
                except Exception:
                    active = None
            if active is None:
                self.notify("No hay ventana activa")
                return

            # Search for menu items in the window descendants
            try:
                items = active.descendants(control_type="MenuItem")
            except Exception:
                items = []

            # Normalize search
            target = words.lower()
            tokens = [t for t in re.split(r"\s+", target) if t]

            # 1) Exact match (title equals target)
            for it in items:
                try:
                    title = (it.window_text() or "").strip()
                    if title and title.lower() == target:
                        rect = it.rectangle()
                        x = int((rect.left + rect.right) / 2)
                        y = int((rect.top + rect.bottom) / 2)
                        pyautogui.moveTo(x, y, duration=0.12)
                        self.notify(f"Ratón colocado sobre menú '{title}' (coincidencia exacta)")
                        return
                except Exception as e:
                    print(f"Excepción iterando menu item (exact): {e}")
                    traceback.print_exc()
                    continue

            # 2) Containing all tokens (looser match)
            if tokens:
                for it in items:
                    try:
                        title = (it.window_text() or "").strip().lower()
                        if not title:
                            continue
                        if all(tok in title for tok in tokens):
                            rect = it.rectangle()
                            x = int((rect.left + rect.right) / 2)
                            y = int((rect.top + rect.bottom) / 2)
                            pyautogui.moveTo(x, y, duration=0.12)
                            self.notify(f"Ratón colocado sobre menú '{it.window_text()}' (contiene tokens)")
                            return
                    except Exception as e:
                        print(f"Excepción iterando menu item (tokens): {e}")
                        traceback.print_exc()
                        continue

            # 3) Looser fallback: search any descendant for exact then tokens
            try:
                descendants = active.descendants()
            except Exception:
                descendants = []

            for d in descendants:
                try:
                    title_raw = d.window_text() or ""
                    title = title_raw.strip()
                    if not title:
                        continue
                    if title.lower() == target:
                        rect = d.rectangle()
                        x = int((rect.left + rect.right) / 2)
                        y = int((rect.top + rect.bottom) / 2)
                        pyautogui.moveTo(x, y, duration=0.12)
                        self.notify(f"Ratón colocado sobre elemento de menú '{title}' (coincidencia exacta)")
                        return
                except Exception:
                    continue

            if tokens:
                for d in descendants:
                    try:
                        title_raw = d.window_text() or ""
                        title = title_raw.strip().lower()
                        if not title:
                            continue
                        if all(tok in title for tok in tokens):
                            rect = d.rectangle()
                            x = int((rect.left + rect.right) / 2)
                            y = int((rect.top + rect.bottom) / 2)
                            pyautogui.moveTo(x, y, duration=0.12)
                            self.notify(f"Ratón colocado sobre elemento de menú '{d.window_text()}' (contiene tokens)")
                            return
                    except Exception:
                        continue
        except Exception as e:
            msg = f"Excepción al obtener ventana activa para menú: {e}"
            print(msg)
            traceback.print_exc()
            try:
                self.notify(msg)
            except Exception:
                pass

        self.notify(f"No se encontró menú '{words}'")

    def _open_office_tab(self, normalized):
        words = normalized
        # Quick keyboard shortcuts for common Office apps: Alt+H typically opens 'Inicio' (Home)
        try:
            desktop = Desktop(backend="uia")
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                active = desktop.window(handle=hwnd)
            except Exception:
                try:
                    wins = desktop.windows()
                    active = wins[0] if wins else None
                except Exception:
                    active = None
            title = "" if active is None else active.window_text().lower()
        except Exception:
            title = ""

        # If user asked for 'inicio', prefer sending Alt+H which selects Home in Word/Excel/PowerPoint
        if re.search(r"inicio", words, re.I):
            try:
                pyautogui.hotkey("alt", "h")
                self.notify("Pestaña Inicio seleccionada (Alt+H)")
                return
            except Exception:
                # fallback to UI automation
                pass

        # Fallback: try to click a control with the tab name
        labels = [
            ("insertar", "Insertar"),
            ("dise[oñ]o|diseñar|disen[ãa]o", "Diseño"),
            ("presentaci[oó]n|apresenta[cç][ãa]o", "Presentación"),
            ("revisar|revis[ãa]o", "Revisar"),
            ("vista|visualizar|exibir", "Vista"),
            ("archivo|arquivo", "Archivo"),
            ("datos|dados", "Datos"),
            ("inicio", "Inicio"),
        ]
        for pattern, name in labels:
            if re.search(pattern, words, re.I):
                self._click_named_button(name)
                return
        self.notify("No se encontró la pestaña de cinta solicitada")

    def _handle_generic_mouse_commands(self, normalized):
        if "mover rat[oó]n" in normalized or "mover mouse" in normalized or "ir a" in normalized:
            self.mouse_direction = None
            coords = re.findall(r"(\d{2,4})", normalized)
            if len(coords) >= 2:
                x, y = int(coords[0]), int(coords[1])
                pyautogui.moveTo(x, y, duration=0.2)
                self.notify(f"Ratón movido a {x},{y}")
                return
        if "clic izquierdo" in normalized or "clicar izquierdo" in normalized:
            self.mouse_direction = None
            pyautogui.click(button="left")
            self.notify("Clic izquierdo realizado")
            return
        if "clic derecho" in normalized or "clicar derecho" in normalized:
            self.mouse_direction = None
            pyautogui.click(button="right")
            self.notify("Clic derecho realizado")
            return
        if "duplicar" in normalized or "doble clic" in normalized:
            self.mouse_direction = None
            pyautogui.doubleClick()
            self.notify("Doble clic realizado")
            return
        self.notify("Comando no reconocido")

    def show_help(self):
        help_text = (
            "Comandos disponibles:\n"
            "- activar / desactivar / pausar temporalmente\n"
            "- modo dictado / salir de dictado / corregir última frase\n"
            "- mostrar rejilla / ocultar rejilla / celda N\n"
            "- botón [nombre] / pulsar [nombre] / clicar [nombre]\n"
            "- cinta inicio / cinta insertar / cinta revisar / cinta vista / cinta archivo\n"
            "- abrir [Word, Excel, PowerPoint, Notepad, Edge] / abrir aplicación\n"
            "- mover ratón a X Y / clic izquierdo / clic derecho / doble clic\n"
            "- ratón arriba / ratón abajo / ratón izquierda / ratón derecha / ratón clic / ratón parar\n"
            "- ayuda"
        )
        window = tk.Tk()
        window.title("Ayuda Xulia2")
        window.geometry("520x420")
        text = tk.Text(window, wrap="word", font=("Segoe UI", 11), padx=10, pady=10)
        text.insert("1.0", help_text)
        text.config(state="disabled")
        text.pack(expand=True, fill="both")
        button = tk.Button(window, text="Cerrar", command=window.destroy, font=("Segoe UI", 11))
        button.pack(pady=8)
        window.attributes("-topmost", True)
        window.mainloop()


def main():
    assistant = VoiceControlAssistant()
    assistant.start()


if __name__ == "__main__":
    main()
