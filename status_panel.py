"""Panel de estado de XULIA2: una franja siempre visible con el modo actual y, según el modo,
cómo actuar y cómo salir.

Quien controla el PC solo por voz necesita saber DÓNDE ESTÁ y QUÉ PUEDE DECIR sin mirar la
consola. El panel:
  - no roba el foco, no sale en Alt+Tab y deja pasar el clic (WS_EX_NOACTIVATE |
    WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT): nunca estorba lo que se está haciendo;
  - consulta el estado del asistente cada 300 ms (no depende de que cada cambio avise);
  - muestra siempre el modo y el último comando entendido; las líneas de ayuda se quedan
    mientras el modo lo pida (rejilla, botones, desactivada) o salen unos segundos al cambiar
    de modo;
  - en el dictado nunca muestra lo dictado.

Se apaga con `[general] panel = no` en %APPDATA%\\Xulia2\\config.ini.
"""
import configparser
import ctypes
import os
import time
import tkinter as tk
from ctypes import wintypes

# modo -> (rótulo, cómo actuar, cómo salir, color del rótulo)
TEXTS = {
    'es': {
        'command': ("COMANDO", "Di «ayuda» para ver lo que puedes decir", "«modo dictado» para escribir"),
        'dictation': ("DICTADO", "Lo que digas se escribe en la ventana activa",
                      "«salir del modo dictado» para volver a los comandos"),
        'spell': ("DELETREAR", "Di una letra (alicante, bilbao, cadiz…) o «tecla 5»",
                  "«salir del modo deletrear» para volver"),
        'accent': ("ACENTO", "Di la vocal que lleva el acento", ""),
        'grid': ("REJILLA", "Di «casilla N» (1 a 300) para mover el cursor", "«ocultar rejilla» para cerrarla"),
        'buttons': ("BOTONES", "Di el número para hacer clic (por ejemplo «doce» o «número doce»)", "los números vuelven para el siguiente · «cancelar» sale"),
        'inactive': ("DESACTIVADA", "No ejecuto comandos", "Di «activar» para volver"),
        'paused': ("EN PAUSA", "Silencio temporal", "Después quedará desactivada: di «activar»"),
        'understood': "entendido", 'not_understood': "no entendí",
    },
    'pt': {
        'command': ("COMANDO", "Diga «ajuda» para ver o que pode dizer", "«modo ditado» para escrever"),
        'dictation': ("DITADO", "O que você disser é escrito na janela ativa",
                      "«sair do ditado» para voltar aos comandos"),
        'spell': ("SOLETRAR", "Diga uma letra (alicante, bilbao, cadiz…) ou «tecla 5»",
                  "«sair do modo soletrar» para voltar"),
        'accent': ("ACENTO", "Diga a vogal que leva o acento", ""),
        'grid': ("GRADE", "Diga «célula N» (1 a 300) para mover o cursor", "«fechar grade» para fechá-la"),
        'buttons': ("BOTÕES", "Diga o número para clicar (por exemplo «doze» ou «número doze»)", "os números voltam para o próximo · «cancelar» sai"),
        'inactive': ("DESATIVADA", "Não executo comandos", "Diga «ativar» para voltar"),
        'paused': ("EM PAUSA", "Silêncio temporário", "Depois fica desativada: diga «ativar»"),
        'understood': "entendido", 'not_understood': "não entendi",
    },
}
COLORS = {
    'command': '#1f6fe0', 'dictation': '#d62b2b', 'spell': '#1e9e3a', 'accent': '#c9a400',
    'grid': '#7b3fc4', 'buttons': '#7b3fc4', 'inactive': '#707070', 'paused': '#707070',
}
# modos cuyas líneas de ayuda no se apagan solas
PERSISTENT_HINTS = {'grid', 'buttons', 'inactive', 'paused', 'accent'}
HINT_SECONDS = 8
LAST_SECONDS = 4
POLL_MS = 300

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_GA_ROOT = 2
_HWND_TOPMOST = -1
_SWP_NOSIZE_NOMOVE_NOACTIVATE = 0x0001 | 0x0002 | 0x0010
NO_FOCUS_STYLE = _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE


def panel_enabled():
    """True salvo que %APPDATA%\\Xulia2\\config.ini diga `[general] panel = no`."""
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Xulia2', 'config.ini'),
                 encoding='utf-8')
        return cfg.get('general', 'panel', fallback='si').strip().lower() not in ('no', 'off', '0', 'false')
    except Exception:
        return True


def mode_from_state(active, paused, grid, buttons, dictation, spell, accent):
    """Modo que debe mostrar el panel; la prioridad es de arriba abajo."""
    if not active:
        return 'paused' if paused else 'inactive'
    if grid:
        return 'grid'
    if buttons:
        return 'buttons'
    if dictation:
        return 'dictation'
    if spell:
        return 'spell'
    if accent:
        return 'accent'
    return 'command'


def texts_for(language):
    """Textos del idioma ('pt-BR' -> pt); cualquier otro usa español."""
    return TEXTS['pt'] if (language or '').lower().startswith('pt') else TEXTS['es']


def _apply_no_focus_style(window):
    """Quita el foco, el Alt+Tab y el clic a la ventana. Devuelve el identificador de la ventana."""
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    hwnd = user32.GetAncestor(window.winfo_id(), _GA_ROOT) or window.winfo_id()
    style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style | NO_FOCUS_STYLE)
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    return hwnd


def _work_area():
    """(izquierda, arriba, derecha, abajo) del área sin la barra de tareas, en el monitor principal."""
    rect = wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


class StatusPanel:
    """Franja de estado. `start()` se ejecuta en el hilo de Tk (por la cola `_tk_queue`).

    state_getter() -> (modo, idioma, (instante, frase o None) o None)
    """

    def __init__(self, root_getter, state_getter):
        self._root_getter = root_getter
        self._state_getter = state_getter
        self.window = None
        self.hwnd = None
        self._shown = None          # (modo, idioma, texto del último, mostrar ayuda)
        self._mode_since = 0.0
        self._last_mode = None

    def start(self):
        root = self._root_getter()
        if root is None or self.window is not None:
            return
        win = tk.Toplevel(root)
        win.withdraw()
        win.title("Estado de Xulia2")
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.attributes('-alpha', 0.93)
        win.configure(background='#202124')
        self._chip = tk.Label(win, font=('Segoe UI', 13, 'bold'), fg='white', padx=12, pady=2)
        self._last = tk.Label(win, font=('Segoe UI', 12), fg='#cfd8dc', bg='#202124', padx=10, anchor='w')
        self._how = tk.Label(win, font=('Segoe UI', 12), fg='white', bg='#202124', padx=12, anchor='w',
                             justify='left', wraplength=620)
        self._exit = tk.Label(win, font=('Segoe UI', 12), fg='#ffd54f', bg='#202124', padx=12, anchor='w',
                              justify='left', wraplength=620)
        self.window = win
        win.update_idletasks()
        self.hwnd = _apply_no_focus_style(win)
        self._tick()

    def stop(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None

    # --- bucle de consulta -------------------------------------------------------------------
    def _tick(self):
        win = self.window
        if win is None:
            return
        try:
            mode, language, last = self._state_getter()
            now = time.time()
            if mode != self._last_mode:
                self._last_mode, self._mode_since = mode, now
            show_hint = mode in PERSISTENT_HINTS or (now - self._mode_since) < HINT_SECONDS
            last_text = None
            if last and (now - last[0]) < LAST_SECONDS and mode != 'dictation':
                t = texts_for(language)
                last_text = (t['understood'] + ': ' + last[1]) if last[1] else t['not_understood']
            key = (mode, texts_for(language) is TEXTS['pt'], last_text, show_hint)
            if key != self._shown:
                self._shown = key
                self._render(mode, language, last_text, show_hint)
            self._keep_on_top()
        except Exception as exc:
            print('Error en el panel de estado:', exc)
        finally:
            if self.window is not None:
                self.window.after(POLL_MS, self._tick)

    def _render(self, mode, language, last_text, show_hint):
        win = self.window
        label, how, leave = texts_for(language)[mode]
        for widget in (self._chip, self._last, self._how, self._exit):
            widget.grid_forget()
        self._chip.configure(text=label, bg=COLORS[mode])
        self._chip.grid(row=0, column=0, sticky='w', padx=(10, 0), pady=(8, 4))
        if last_text:
            self._last.configure(text=last_text)
            self._last.grid(row=0, column=1, sticky='w', pady=(8, 4))
        row = 1
        if show_hint and how:
            self._how.configure(text=how)
            self._how.grid(row=row, column=0, columnspan=2, sticky='w')
            row += 1
        if show_hint and leave:
            self._exit.configure(text=leave)
            self._exit.grid(row=row, column=0, columnspan=2, sticky='w', pady=(0, 6))
        win.update_idletasks()
        width, height = win.winfo_reqwidth(), win.winfo_reqheight() + 4
        left, top, right, bottom = _work_area()
        x = left + (right - left - width) // 2
        y = bottom - height - 10
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.deiconify()

    def _keep_on_top(self):
        """La barra de tareas puede subir sobre el panel: se vuelve a poner encima sin activarlo."""
        if self.hwnd:
            ctypes.windll.user32.SetWindowPos(self.hwnd, wintypes.HWND(_HWND_TOPMOST), 0, 0, 0, 0,
                                              _SWP_NOSIZE_NOMOVE_NOACTIVATE)
