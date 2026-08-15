import ctypes
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from queue import Queue

import pyautogui
import pystray
import speech_recognition as sr
from PIL import Image, ImageDraw
import pyperclip
from pywinauto import Desktop
from win10toast import ToastNotifier
import traceback


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
        self.mouse_direction = None
        self.last_phrases = []
        self.silenced_until = 0
        self.language = "es-ES"
        self.mic_index = self._choose_microphone()
        self.mic_index = 1
        self.commands = self._build_command_patterns()
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
        return {
            "activate": re.compile(r"\b(activar|ativar)\b", re.I),
            "deactivate": re.compile(r"\b(desactivar|desativar)\b", re.I),
            "pause": re.compile(r"\b(pausar|silenciar|temporalmente|deshabilitar temporalmente|desativar temporariamente)\b", re.I),
            "dictation_on": re.compile(r"\b(modo dictado)\b", re.I),
            "dictation_off": re.compile(
                r"\b(salir(?: del| de)?(?: el)? modo(?: de)? dictado|salir(?: del| de)? dictado|fin(?: del| de)? dictado|terminar(?: el)? dictado|sair(?: do| de)?(?: modo(?: de)?)? ditado|sair(?: do| de)? ditado|terminar ditado|fim(?: do)? ditado|parar ditado)\b",
                re.I,
            ),
            "grid_show": re.compile(r"\b(mostrar rejilla|mostrar grade|abrir rejilla|abrir grade)\b", re.I),
            "grid_hide": re.compile(r"\b(ocultar rejilla|fechar grade|cerrar rejilla|cerrar grade)\b", re.I),
            "help": re.compile(r"\b(ayuda|comandos|lista de comandos|ajuda|mostrar ayuda)\b", re.I),
            "correct_last": re.compile(r"\b(corregir( la)? última frase|corrigir( a)? última frase|borrar( la)? última frase|eliminar( la)? última frase)\b", re.I),
            "click_button": re.compile(r"\b(bot[oó]n|bot[oó]es|clicar|pulsar|press)\b", re.I),
            "ribbon": re.compile(r"\b(cinta|aba|guía|guia|ribbon)\b", re.I),
            "office_tab": re.compile(r"\b(cinta de inicio|insertar|insert|disenar|diseñar|vista|revisar|arquivo|archivo|arquivo|dados|datos|fórmula|formula|arquivos|exibir|visualizar)\b", re.I),
            "open_app": re.compile(r"\b(abrir|iniciar|inicia|executar|ejecutar|abrir programa|abrir aplicación|abrir aplicação)\b", re.I),
            "cell_click": re.compile(r"\bcelda\s*(?:n[úu]mero\s*)?(\d{1,2})\b", re.I),
            "mouse_up": re.compile(r"\b(rat[oó]n\s+arriba|mouse\s+para\s+cima|mouse\s+cima)\b", re.I),
            "mouse_down": re.compile(r"\b(rat[oó]n\s+abajo|mouse\s+para\s+baixo|mouse\s+baixo)\b", re.I),
            "mouse_left": re.compile(r"\b(rat[oó]n\s+izquierda|mouse\s+para\s+a\s+esquerda|mouse\s+esquerda)\b", re.I),
            "mouse_right": re.compile(r"\b(rat[oó]n\s+derecha|mouse\s+para\s+a\s+direita|mouse\s+direita)\b", re.I),
            "mouse_click": re.compile(r"\b(rat[oó]n\s+clic|rat[oó]n\s+click|mouse\s+clic|mouse\s+click|rat[oó]n\s+clicar)\b", re.I),
            "mouse_stop": re.compile(r"\b(rat[oó]n\s+parado|parar\s+mouse)\b", re.I),
        }

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
            color = (220, 20, 20, 255) if self.dictation_mode else (20, 100, 220, 255)
            self.icon.icon = self._create_icon_image(color)

    def notify(self, message: str, toast: bool = True):
        print(f"Xulia2: {message}")
        if toast and self.icon is not None:
            try:
                self.toaster.show_toast("Xulia2", message, duration=2, threaded=True)
            except Exception:
                pass

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
        step = 10
        delay = 0.015
        while self.running:
            if self.active and self.mouse_direction:
                try:
                    x, y = pyautogui.position()
                    screen_width, screen_height = pyautogui.size()
                    if self.mouse_direction == "up":
                        y = max(0, y - step)
                    elif self.mouse_direction == "down":
                        y = min(screen_height - 1, y + step)
                    elif self.mouse_direction == "left":
                        x = max(0, x - step)
                    elif self.mouse_direction == "right":
                        x = min(screen_width - 1, x + step)
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

    def deactivate(self):
        self.active = False
        self.notify("Asistente desactivado")

    def pause_temporarily(self, seconds=30):
        self.active = False
        self.silenced_until = time.time() + seconds
        self.notify(f"Asistente desactivado temporalmente {seconds}s")

    def _process_commands(self):
        while self.running:
            try:
                text = self.command_queue.get(timeout=0.5)
            except Exception:
                continue
            self._handle_command(text)

    def _listen_loop(self):
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
            # Tune thresholds to avoid cutting words mid-phrase
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            # Wait a bit longer for silence before considering phrase ended
            self.recognizer.pause_threshold = 0.8
            if hasattr(self.recognizer, "non_speaking_duration"):
                self.recognizer.non_speaking_duration = 0.6
            if hasattr(self.recognizer, "phrase_threshold"):
                self.recognizer.phrase_threshold = 0.5
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            except Exception as exc:
                print("No se pudo ajustar ruido ambiente:", exc)
            self.notify("Xulia2 listo para escuchar")
            while self.running:
                if not self.active and time.time() < self.silenced_until:
                    time.sleep(0.5)
                    continue
                if not self.active:
                    time.sleep(0.2)
                    continue
                try:
                    # Remove short phrase_time_limit so listen waits for end-of-speech silence
                    audio = self.recognizer.listen(source, timeout=4)
                except sr.WaitTimeoutError:
                    continue
                except Exception as exc:
                    print("Error en listen:", exc)
                    traceback.print_exc()
                    continue
                text = self._recognize_audio(audio)
                if not text:
                    continue
                self.notify(f"Reconocido: {text}", toast=False)
                self.command_queue.put(text)

    def _recognize_audio(self, audio):
        # Prefer Vosk (offline) if a model was loaded, then fall back to pocketsphinx and Google
        if getattr(self, "vosk_available", False) and self.vosk_model is not None:
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
                return j.get("text", "")
            except Exception as e:
                print("Vosk recognition error:", e)

        # Fallback: pocketsphinx (offline) then Google (online)
        try:
            text = self.recognizer.recognize_sphinx(audio, language=self.language)
            return text
        except Exception:
            try:
                text = self.recognizer.recognize_google(audio, language=self.language)
                return text
            except Exception:
                return ""

    def _handle_command(self, text: str):
        normalized = text.lower()
        if self.commands["activate"].search(normalized):
            self.activate()
            return
        if self.commands["deactivate"].search(normalized):
            self.deactivate()
            return
        if self.commands["pause"].search(normalized):
            self.pause_temporarily(30)
            return
        if self.commands["help"].search(normalized):
            self.show_help()
            return
        if self.commands["grid_show"].search(normalized):
            self.grid.show()
            self.notify("Rejilla mostrada")
            return
        if self.commands["grid_hide"].search(normalized):
            self.grid.hide()
            self.notify("Rejilla oculta")
            return
        if self.commands["dictation_off"].search(normalized):
            self.dictation_mode = False
            self._update_tray_icon()
            self.notify("Modo dictado desactivado")
            return
        if self.commands["dictation_on"].search(normalized):
            self.dictation_mode = True
            self._update_tray_icon()
            self.notify("Modo dictado activado")
            return
        if self.commands["correct_last"].search(normalized):
            self._correct_last_phrase()
            return
        if self.commands["cell_click"].search(normalized):
            match = self.commands["cell_click"].search(normalized)
            cell = int(match.group(1))
            self._click_grid_cell(cell)
            return
        if self.commands["mouse_up"].search(normalized):
            self.mouse_direction = "up"
            self.notify("Ratón arriba", toast=False)
            return
        if self.commands["mouse_down"].search(normalized):
            self.mouse_direction = "down"
            self.notify("Ratón abajo", toast=False)
            return
        if self.commands["mouse_left"].search(normalized):
            self.mouse_direction = "left"
            self.notify("Ratón izquierda", toast=False)
            return
        if self.commands["mouse_right"].search(normalized):
            self.mouse_direction = "right"
            self.notify("Ratón derecha", toast=False)
            return
        if self.commands["mouse_click"].search(normalized):
            self.mouse_direction = None
            try:
                pyautogui.click()
                self.notify("Ratón clic", toast=False)
            except Exception:
                self.notify("Error al realizar clic", toast=False)
            return
        if self.commands["mouse_stop"].search(normalized):
            self.mouse_direction = None
            self.notify("Ratón parado", toast=False)
            return
        if self.commands["ribbon"].search(normalized) and self.commands["office_tab"].search(normalized):
            self._open_office_tab(normalized)
            return
        # If user said 'botón <nombre>' or 'botao <nombre>', move mouse to center of that button
        # If user said 'menú <nombre>' or 'menu <nombre>', move mouse to that menu item
        mm = re.search(r"\bmen[uú]\s+(.+)", text, re.I)
        if mm:
            menu_name = mm.group(1).strip()
            if menu_name:
                self._move_to_named_menu(menu_name)
                return

        # If user said 'botón <nombre>' or 'botao <nombre>', move mouse to center of that button
        m = re.search(r"\b(?:bot[oó]n|bot[oó]es|botao)\s+(.+)", text, re.I)
        if m:
            name = m.group(1).strip()
            if name:
                self._move_to_named_button(name)
                return
        if self.commands["click_button"].search(normalized):
            self._click_named_button(normalized)
            return
        if self.commands["open_app"].search(normalized):
            self._open_application(normalized)
            return
        if self.dictation_mode:
            self._dictate_text(text)
            return
        self._handle_generic_mouse_commands(normalized)

    def _dictate_text(self, phrase):
        try:
            # Use clipboard paste to send the text to the active window
            try:
                old_clip = pyperclip.paste()
            except Exception:
                old_clip = None
            try:
                pyperclip.copy(phrase + " ")
                time.sleep(0.05)  # Allow clipboard to register the text
                # paste using Ctrl+V for reliability
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.15)  # Wait for target application to paste before restoring clipboard
            finally:
                if old_clip is not None:
                    try:
                        pyperclip.copy(old_clip)
                        time.sleep(0.03)  # Brief pause to normalize clipboard state
                    except Exception:
                        pass
            self.last_phrases.append(phrase)
            self.notify("Dictado escrito", toast=False)
        except Exception as exc:
            print("Error al dictar texto:", exc)
            traceback.print_exc()

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

    def _open_application(self, normalized):
        app_names = {
            "word": ["word", "palabra", "word 365", "documento"],
            "excel": ["excel", "hoja de cálculo", "planilha"],
            "powerpoint": ["powerpoint", "presentación", "apresentação"],
            "notepad": ["notepad", "bloc de notas", "notas"],
            "edge": ["edge", "navegador", "browser"],
        }
        for exe, keys in app_names.items():
            if any(key in normalized for key in keys):
                try:
                    subprocess.Popen([exe])
                    self.notify(f"Abriendo {exe}")
                    return
                except Exception:
                    pass
        try:
            subprocess.Popen(normalized.replace("abrir ", ""), shell=True)
            self.notify("Aplicación abierta")
        except Exception:
            self.notify("No se pudo abrir la aplicación")

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
            control = active.child_window(title_re=f".*{re.escape(words)}.*", control_type="Button")
            if control.exists(timeout=2):
                control.click_input()
                self.notify(f"Pulsado botón '{words}'")
                return
            control = active.window(title_re=f".*{re.escape(words)}.*")
            if control.exists(timeout=2):
                control.click_input()
                self.notify(f"Pulsado control '{words}'")
                return
        except Exception:
            pass
        self.notify(f"No se encontró botón '{words}'")

    def _move_to_named_button(self, name: str):
        # Move the mouse to the center of a button with the given visible text in the active window
        words = name.strip()
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
            if active is None:
                self.notify("No hay ventana activa")
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

            for it in items:
                try:
                    title = it.window_text()
                    if title and re.search(re.escape(words), title, re.I):
                        rect = it.rectangle()
                        x = int((rect.left + rect.right) / 2)
                        y = int((rect.top + rect.bottom) / 2)
                        pyautogui.moveTo(x, y, duration=0.12)
                        self.notify(f"Ratón colocado sobre menú '{title}'")
                        return
                except Exception as e:
                    print(f"Excepción iterando menu item: {e}")
                    traceback.print_exc()
                    continue

            # Some apps expose menus as plain buttons or panes; try a looser search
            try:
                descendants = active.descendants()
                for d in descendants:
                    try:
                        title = d.window_text()
                        if title and re.search(re.escape(words), title, re.I):
                            rect = d.rectangle()
                            x = int((rect.left + rect.right) / 2)
                            y = int((rect.top + rect.bottom) / 2)
                            pyautogui.moveTo(x, y, duration=0.12)
                            self.notify(f"Ratón colocado sobre elemento de menú '{title}'")
                            return
                    except Exception:
                        continue
            except Exception as e:
                msg = f"Excepción al buscar menú: {e}"
                print(msg)
                traceback.print_exc()
                try:
                    self.notify(msg)
                except Exception:
                    pass
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
