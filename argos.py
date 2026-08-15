import threading
import time
import cv2
try:
    # reduce verbosity from OpenCV
    if hasattr(cv2, 'utils') and hasattr(cv2.utils, 'logging'):
        cv2.utils.logging.setLogLevel(cv2.utils.logging.ERROR)
except Exception:
    pass
import numpy as np
import configparser
import tkinter as tk
from tkinter import messagebox, simpledialog
import sys
import os

try:
    from pygrabber.dshow_graph import FilterGraph
except Exception:
    FilterGraph = None

try:
    import mediapipe as mp
    mp_face_mesh_module = getattr(mp, 'solutions', None)
    if mp_face_mesh_module is None:
        # some installs expose solutions as a submodule
        try:
            from mediapipe import solutions as _mp_solutions
            mp_face_mesh_module = _mp_solutions
        except Exception:
            mp_face_mesh_module = None
    else:
        mp_face_mesh_module = mp_face_mesh_module
except Exception:
    mp = None
    mp_face_mesh_module = None

try:
    from pynput.mouse import Controller as MouseController, Button
    from pynput import keyboard
except Exception:
    MouseController = None
    keyboard = None

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:
    pystray = None

from screeninfo import get_monitors

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.ini')


class ArgosApp:
    def __init__(self, root):
        self.root = root
        self.root.title('ARGOS')
        self.cfg = configparser.ConfigParser()
        self.cfg.read(CONFIG_PATH)
        self.read_config_defaults()

        self.mouse = MouseController() if MouseController else None
        self.enabled = True

        self.cameras = self.enumerate_cameras()
        self.cam_index = self.get_config_camera()

        self.cap = None
        self.running = False

        self.center_image_point = None
        self.calibrated = False

        self.mp_face_mesh = mp_face_mesh_module.face_mesh if mp_face_mesh_module is not None else None
        self.face_mesh = None

        self.create_ui()
        self.create_tray()

        # start capturing when user presses start

    def read_config_defaults(self):
        if 'general' not in self.cfg:
            self.cfg['general'] = {}
        if 'timing' not in self.cfg:
            self.cfg['timing'] = {}

        g = self.cfg['general']
        t = self.cfg['timing']
        # ensure keys exist
        defaults = {'camara': '', 'multimonitor': 'S'}
        for k, v in defaults.items():
            if k not in g:
                g[k] = v

        timing_defaults = {
            'ms_clic_derecho': '200',
            'ms_clic_izquierdo': '200',
            'ms_clic_central': '200',
            'ms_doble_clic_derecho': '300',
            'ms_pulsacion_derecho': '800',
            'ms_pulsacion_izquierdo': '800'
        }
        for k, v in timing_defaults.items():
            if k not in t:
                t[k] = v

    def enumerate_cameras(self, limit=6):
        self.camera_names = []
        if FilterGraph is None:
            return []
        try:
            self.camera_names = list(FilterGraph().get_input_devices())
        except Exception:
            self.camera_names = []
        return list(range(len(self.camera_names)))

    def get_config_camera(self):
        cam = self.cfg['general'].get('camara', '').strip()
        try:
            cam_i = int(cam) if cam != '' else None
        except Exception:
            cam_i = None
        if cam_i is not None and cam_i in self.cameras:
            return cam_i
        return self.cameras[0] if self.cameras else 0

    def create_ui(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=8, pady=8)

        tk.Label(frame, text='Cámaras detectadas:').grid(row=0, column=0)
        self.cam_var = tk.StringVar(value=str(self.cam_index))
        self.cams_label = tk.Label(frame, text='')
        self.cams_label.grid(row=0, column=1)
        self.update_cams_label()

        tk.Button(frame, text='Refrescar', command=self.refresh_cameras).grid(row=0, column=2)
        tk.Button(frame, text='Diagnosticar', command=self.run_diag).grid(row=0, column=4)
        tk.Button(frame, text='Seleccionar cámara', command=self.select_camera_dialog).grid(row=0, column=3)

        tk.Button(frame, text='Iniciar', command=self.start).grid(row=1, column=0)
        tk.Button(frame, text='Calibrar', command=self.calibrate).grid(row=1, column=1)
        tk.Button(frame, text='Salir', command=self.exit).grid(row=1, column=2)

    def create_tray(self):
        if not pystray:
            return
        # create simple icon
        img = Image.new('RGB', (64, 64), color=(64, 64, 64))
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill=(200, 200, 200))

        menu = pystray.Menu(
            pystray.MenuItem('Prueba', lambda: self.show_test()),
            pystray.MenuItem('Calibrar', lambda: self.calibrate()),
            pystray.MenuItem('Salir', lambda: self.exit())
        )
        self.tray = pystray.Icon('argos', img, 'ARGOS', menu)
        t = threading.Thread(target=self.tray.run, daemon=True)
        t.start()

    def start(self):
        if self.running:
            return
        # try opening with multiple backends for robustness
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        self.cap = None
        for b in backends:
            try:
                cap = cv2.VideoCapture(self.cam_index, b)
            except Exception:
                try:
                    cap = cv2.VideoCapture(self.cam_index)
                except Exception:
                    cap = None
            if cap and cap.isOpened():
                self.cap = cap
                break
            if cap:
                cap.release()
        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror('ERROR', f'No se puede abrir la cámara {self.cam_index}')
            return
        if not self.cap or not self.cap.isOpened():
            messagebox.showerror('ERROR', f'No se puede abrir la cámara {self.cam_index}')
            return
        # initialize mediapipe
        if self.mp_face_mesh:
            self.face_mesh = self.mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1,
                                                       refine_landmarks=True, min_detection_confidence=0.5)

        self.running = True
        self.worker = threading.Thread(target=self.capture_loop, daemon=True)
        self.worker.start()

    def exit(self):
        self.running = False
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.quit()

    def calibrate(self):
        # Show countdown
        w = tk.Toplevel(self.root)
        w.attributes('-topmost', True)
        w.geometry('400x200')
        lbl = tk.Label(w, text='Calibrando sistema, por favor mire el centro de la pantalla', font=('Arial', 12))
        lbl.pack(pady=10)
        cnt = tk.Label(w, text='4', font=('Arial', 48))
        cnt.pack()

        def countdown(n=4):
            if n == 0:
                w.destroy()
                self.perform_calibration()
                return
            cnt.config(text=str(n))
            self.root.after(1000, countdown, n - 1)

        countdown(4)

    def refresh_cameras(self):
        self.cameras = self.enumerate_cameras(limit=10)
        self.update_cams_label()

    def update_cams_label(self):
        names = getattr(self, 'camera_names', [])
        cams_display = ', '.join(f'{i}: {name}' for i, name in enumerate(names))
        if not cams_display:
            cams_display = 'ninguna'
        self.cams_label.config(text=cams_display)

    def select_camera_dialog(self):
        val = simpledialog.askinteger('Seleccionar cámara', 'Introduce número de cámara:', parent=self.root,
                                      minvalue=0, maxvalue=50)
        if val is not None:
            self.cam_index = val
            self.cam_var.set(str(val))

    def run_diag(self):
        self.refresh_cameras()
        w = tk.Toplevel(self.root)
        w.title('Diagnóstico cámaras')
        txt = tk.Text(w, width=60, height=15)
        txt.pack(padx=6, pady=6)
        if self.camera_names:
            txt.insert('end', 'Dispositivos DirectShow detectados:\n\n')
            for index, name in enumerate(self.camera_names):
                txt.insert('end', f'{index}: {name}\n')
        elif FilterGraph is None:
            txt.insert('end', 'No se puede enumerar: falta pygrabber.\n')
        else:
            txt.insert('end', 'Windows no informó cámaras DirectShow.\n\n')
            txt.insert('end', 'Revise Permitir acceso a la cámara en Privacidad de Windows, los controladores y que otra aplicación no la esté usando.\n')
        txt.config(state='disabled')

    def perform_calibration(self):
        if not self.cap or not self.cap.isOpened():
            self.start()
            time.sleep(0.5)
        ret, frame = self.cap.read()
        if not ret:
            messagebox.showerror('ERROR', 'Error leyendo cámara durante calibración')
            return

        red_pt = self.find_color_point(frame, 'red')
        green_pt = self.find_color_point(frame, 'green')
        missing = []
        if red_pt is None:
            missing.append('rojo')
        if green_pt is None:
            missing.append('verde')
        if missing:
            messagebox.showerror('ERROR', 'No localizó: ' + ', '.join(missing))
            return

        mid = ((red_pt[0] + green_pt[0]) // 2, (red_pt[1] + green_pt[1]) // 2)
        self.center_image_point = mid
        # move mouse to screen center
        monitors = get_monitors()
        if self.cfg['general'].get('multimonitor', 'S').upper() == 'S' and len(monitors) > 1:
            # choose primary monitor as center
            mon = monitors[0]
        else:
            mon = monitors[0]
        cx = mon.x + mon.width // 2
        cy = mon.y + mon.height // 2
        if self.mouse:
            self.mouse.position = (cx, cy)
        self.calibrated = True
        messagebox.showinfo('ARGOS', 'Calibración completada. Punto central establecido.')

    def find_color_point(self, frame, color):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        if color == 'red':
            lower1 = np.array([0, 120, 70])
            upper1 = np.array([10, 255, 255])
            lower2 = np.array([170, 120, 70])
            upper2 = np.array([180, 255, 255])
            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask = cv2.bitwise_or(mask1, mask2)
        else:
            lower = np.array([40, 50, 50])
            upper = np.array([90, 255, 255])
            mask = cv2.inRange(hsv, lower, upper)

        # morphological
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 50:
            return None
        M = cv2.moments(c)
        if M['m00'] == 0:
            return None
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])
        return (cx, cy)

    def capture_loop(self):
        last_time = time.time()
        # eye state
        left_closed = False
        right_closed = False
        left_close_time = None
        right_close_time = None

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # reduce size for speed
            small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)

            # find color points in small
            r = self.find_color_point(small, 'red')
            g = self.find_color_point(small, 'green')

            if self.calibrated and (r is not None and g is not None):
                # compute displacement of midpoint relative to calibration center
                mid = ((r[0] + g[0]) // 2, (r[1] + g[1]) // 2)
                dx = mid[0] - (self.center_image_point[0] // 2)
                dy = mid[1] - (self.center_image_point[1] // 2)
                # map to screen
                mon = get_monitors()[0]
                sx = mon.x + mon.width // 2 + int(dx * 4)
                sy = mon.y + mon.height // 2 + int(dy * 4)
                if self.mouse and self.enabled:
                    try:
                        self.mouse.position = (sx, sy)
                    except Exception:
                        pass

            # Eye blink detection using mediapipe if available
            if self.face_mesh is not None:
                img_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                results = self.face_mesh.process(img_rgb)
                if results.multi_face_landmarks:
                    lm = results.multi_face_landmarks[0]
                    h, w = small.shape[:2]
                    # simple distances for upper/lower eyelid for left/right
                    def eye_open(upper_idx, lower_idx):
                        up = lm.landmark[upper_idx]
                        lo = lm.landmark[lower_idx]
                        d = np.hypot((up.x - lo.x) * w, (up.y - lo.y) * h)
                        return d

                    # indices chosen for MediaPipe face mesh (approx)
                    right_eye_dist = eye_open(159, 145)
                    left_eye_dist = eye_open(386, 374)

                    # thresholds (empirical)
                    if right_eye_dist < 4.0:
                        if not right_closed:
                            right_closed = True
                            right_close_time = time.time()
                            self.on_eye_event('right', 'closed')
                    else:
                        if right_closed:
                            # opened
                            dur = int((time.time() - right_close_time) * 1000)
                            self.on_eye_blink('right', dur)
                        right_closed = False

                    if left_eye_dist < 4.0:
                        if not left_closed:
                            left_closed = True
                            left_close_time = time.time()
                            self.on_eye_event('left', 'closed')
                    else:
                        if left_closed:
                            dur = int((time.time() - left_close_time) * 1000)
                            self.on_eye_blink('left', dur)
                        left_closed = False

            # sleep to reduce CPU
            time.sleep(0.02)

    def on_eye_event(self, which, state):
        # change indicator - for simplicity, we use tray notifications if available
        if not self.enabled:
            return
        if which == 'right' and state == 'closed':
            # set cursor indicator red (not implemented complexly)
            pass
        if which == 'left' and state == 'closed':
            pass
        if which == 'both' and state == 'closed':
            pass

    def on_eye_blink(self, which, duration_ms):
        # perform action based on config thresholds
        t = self.cfg['timing']
        if which == 'right':
            ms_click = int(t.get('ms_clic_derecho', '200'))
            ms_double = int(t.get('ms_doble_clic_derecho', '300'))
            ms_puls = int(t.get('ms_pulsacion_derecho', '800'))
            if duration_ms < ms_click:
                self.do_mouse_click(Button.right)
            elif duration_ms < ms_double:
                self.do_mouse_click(Button.right)
            elif duration_ms >= ms_puls:
                # press and hold until open - already opened
                self.do_mouse_press(Button.right)
        elif which == 'left':
            ms_click = int(t.get('ms_clic_izquierdo', '200'))
            ms_puls = int(t.get('ms_pulsacion_izquierdo', '800'))
            if duration_ms < ms_click:
                self.do_mouse_click(Button.left)
            elif duration_ms >= ms_puls:
                self.do_mouse_press(Button.left)

    def do_mouse_click(self, button):
        if not self.mouse or not self.enabled:
            return
        try:
            self.mouse.click(button)
        except Exception:
            pass

    def do_mouse_press(self, button):
        if not self.mouse or not self.enabled:
            return
        try:
            self.mouse.press(button)
            # release will be done when eye opens (logic simplified)
            self.mouse.release(button)
        except Exception:
            pass

    def show_test(self):
        # Open a window showing camera with overlays
        if not self.cap or not self.cap.isOpened():
            self.start()
            time.sleep(0.5)

        win = tk.Toplevel(self.root)
        win.title('Prueba')
        label = tk.Label(win)
        label.pack()

        def update():
            ret, frame = self.cap.read()
            if ret:
                r = self.find_color_point(frame, 'red')
                g = self.find_color_point(frame, 'green')
                if r:
                    cv2.rectangle(frame, (r[0]-10, r[1]-10), (r[0]+10, r[1]+10), (0,0,255), 2)
                if g:
                    cv2.rectangle(frame, (g[0]-10, g[1]-10), (g[0]+10, g[1]+10), (0,255,0), 2)
                # convert to PIL for Tkinter
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                label.imgtk = imgtk
                label.config(image=imgtk)
            if win.winfo_exists():
                win.after(30, update)

        # lazy-import ImageTk to avoid heavy import earlier
        from PIL import ImageTk, Image
        update()


def main():
    root = tk.Tk()
    app = ArgosApp(root)
    root.protocol('WM_DELETE_WINDOW', app.exit)
    root.mainloop()


if __name__ == '__main__':
    main()
