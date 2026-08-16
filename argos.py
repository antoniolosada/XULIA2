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
        self.mouse_tracking_enabled = False
        self.detection_params = None
        self.calibration_requested = False
        self.calibration_cancel_requested = False
        self.reference_requested = False
        self.search_zone = None
        self.camera_frame_size = None
        self.tracking_model = None
        self.target_size = None
        self.white_reference = None
        self.black_reference = None
        self.hotkey_listener = None

        self.mp_face_mesh = mp_face_mesh_module.face_mesh if mp_face_mesh_module is not None else None
        self.face_mesh = None

        self.create_ui()
        self.create_tray()
        self.start_hotkey_listener()

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

        if 'detection' not in self.cfg:
            self.cfg['detection'] = {}
        detection_defaults = {
            'white_s_max': '55', 'white_v_min': '150',
            'black_v_max': '85', 'min_area': '12',
            'cross_ratio_min': '0.005', 'cross_ratio_max': '0.50',
            'inner_ratio_min': '0.03', 'inner_ratio_max': '0.50',
            'white_deviation_pct': '45', 'black_deviation_pct': '15'
        }
        for k, v in detection_defaults.items():
            if k not in self.cfg['detection']:
                self.cfg['detection'][k] = v

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

    def configure_hd_ready_resolution(self):
        requested = (1280, 720)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested[1])
        actual = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                  int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        return actual if actual == requested else None

    def get_primary_monitor(self):
        monitors = get_monitors()
        if not monitors:
            return None
        return next((monitor for monitor in monitors
                     if getattr(monitor, 'is_primary', False)), monitors[0])

    def start_hotkey_listener(self):
        if keyboard is None:
            return
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse('<ctrl>+<shift>+<alt>+s'),
            lambda: self.root.after(0, self.exit))

        def on_press(key):
            hotkey.press(keyboard.Listener.canonical(key))
            try:
                key_char = key.char.lower()
                if key_char == 'c':
                    self.reference_requested = True
                elif key_char == 'r':
                    self.mouse_tracking_enabled = True
                elif key_char == 'm':
                    self.mouse_tracking_enabled = False
                elif key_char == 's':
                    self.calibration_cancel_requested = True
            except AttributeError:
                pass

        def on_release(key):
            hotkey.release(keyboard.Listener.canonical(key))

        self.hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

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
        self.camera_resolution = self.configure_hd_ready_resolution()
        if self.camera_resolution is None:
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.cap.release()
            self.cap = None
            messagebox.showerror(
                'ERROR',
                f'La cámara no soporta HD Ready (1280x720). Resolución disponible: '
                f'{actual_width}x{actual_height}.')
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
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None
        if self.cap:
            self.cap.release()
            self.cap = None
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        if hasattr(self, 'tray') and self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.quit()

    def calibrate(self):
        if not self.running:
            self.start()
        else:
            self.calibration_requested = True

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

    def detection_values(self):
        section = self.cfg['detection']
        params = {
            'white_s': min(70, int(section.get('white_s_max', '55'))),
            'white_v': max(140, int(section.get('white_v_min', '150'))),
            'black_v': min(100, int(section.get('black_v_max', '85'))),
            'min_area': int(section['min_area']),
            'cross_ratio': (float(section.get('cross_ratio_min', '0.005')),
                            float(section.get('cross_ratio_max', '0.50'))),
            'inner_ratio': (float(section.get('inner_ratio_min', '0.03')),
                            float(section.get('inner_ratio_max', '0.50'))),
            'white_deviation_pct': float(section.get('white_deviation_pct', '45')),
            'black_deviation_pct': float(section.get('black_deviation_pct', '15'))
        }
        if self.target_size:
            params['target_size'] = self.target_size
        if self.white_reference is not None and self.black_reference is not None:
            params['white_reference'] = self.white_reference
            params['black_reference'] = self.black_reference
        return params

    def save_detection_values(self, params):
        section = self.cfg['detection']
        section['white_s_max'] = str(params['white_s'])
        section['white_v_min'] = str(params['white_v'])
        section['black_v_max'] = str(params['black_v'])
        section['min_area'] = str(params['min_area'])
        section['cross_ratio_min'], section['cross_ratio_max'] = map(str, params['cross_ratio'])
        section['inner_ratio_min'], section['inner_ratio_max'] = map(str, params['inner_ratio'])
        section['white_deviation_pct'] = str(params['white_deviation_pct'])
        section['black_deviation_pct'] = str(params['black_deviation_pct'])
        with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
            self.cfg.write(config_file)

    def load_search_zone(self):
        value = self.cfg['detection'].get('search_zone', '').strip()
        if not value:
            return None
        try:
            zone = tuple(int(part.strip()) for part in value.split(','))
        except (TypeError, ValueError):
            return None
        if len(zone) != 4 or zone[2] <= 0 or zone[3] <= 0:
            return None
        return zone

    def save_search_zone(self, zone):
        self.cfg['detection']['search_zone'] = ','.join(str(value) for value in zone)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
            self.cfg.write(config_file)

    def select_target_sample(self):
        window_name = 'ARGOS - marque la forma (clic y arrastre, ESC cancela)'
        display_scale = 1.5
        selection = {'start': None, 'current': None, 'zone': None, 'frame': None}

        def on_mouse(event, x, y, flags, param):
            x = int(x / display_scale)
            y = int(y / display_scale)
            if event == cv2.EVENT_LBUTTONDOWN:
                selection['start'] = (x, y)
                selection['current'] = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and selection['start']:
                selection['current'] = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and selection['start']:
                selection['current'] = (x, y)
                x0, y0 = selection['start']
                x1, y1 = selection['current']
                left, top = min(x0, x1), min(y0, y1)
                width, height = abs(x1 - x0), abs(y1 - y0)
                if width >= 8 and height >= 8:
                    selection['zone'] = (left, top, width, height)

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 720)
        cv2.setMouseCallback(window_name, on_mouse)
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            selection['frame'] = frame
            small = frame
            preview = small.copy()
            if selection['start'] and selection['current']:
                cv2.rectangle(preview, selection['start'], selection['current'], (0, 0, 255), 1)
            cv2.putText(preview, 'Marque el circulo blanco con cuadrado negro y suelte el raton', (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(preview, 'Se evaluaran intensidades de blanco y negro', (8, 46),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window_name, cv2.resize(preview, (0, 0), fx=display_scale,
                                               fy=display_scale, interpolation=cv2.INTER_NEAREST))
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if selection['zone']:
                left, top, width, height = selection['zone']
                sample = small[top:top + height, left:left + width]
                if sample.size:
                    cv2.rectangle(preview, (left, top), (left + width, top + height),
                                  (0, 255, 0), 2)
                    cv2.putText(preview, 'Forma marcada: analizando blanco, negro y geometria',
                                (8, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                (0, 255, 0), 2, cv2.LINE_AA)
                    cv2.imshow(window_name, cv2.resize(preview, (0, 0), fx=display_scale,
                                                       fy=display_scale, interpolation=cv2.INTER_NEAREST))
                    cv2.waitKey(400)
                    cv2.destroyWindow(window_name)
                    scale_x = frame.shape[1] / small.shape[1]
                    scale_y = frame.shape[0] / small.shape[0]
                    return sample, (int(left * scale_x), int(top * scale_y),
                                    int(width * scale_x), int(height * scale_y))
        cv2.destroyWindow(window_name)
        return None, None

    def calibrate_detection_from_sample(self, sample):
        hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
        brightness = hsv[:, :, 2].astype(np.float32)
        saturation = hsv[:, :, 1]
        white_level = float(np.percentile(brightness, 60))
        black_level = float(np.percentile(brightness, 35))
        white_saturation = saturation[brightness >= white_level]
        white_s_max = int(np.clip(np.percentile(white_saturation, 90)
                                  if white_saturation.size else 55, 20, 100))
        white_v_min = int(np.clip(white_level - 10, 100, 235))
        black_v_max = int(np.clip(black_level + 15, 35, 140))
        params = self.detection_values()
        params['white_s'] = white_s_max
        params['white_v'] = white_v_min
        params['black_v'] = black_v_max
        params['white_reference'] = float(np.percentile(brightness, 90))
        params['black_reference'] = float(np.percentile(brightness, 10))
        params['target_size'] = (sample.shape[1], sample.shape[0])
        self.target_size = params['target_size']
        self.white_reference = params['white_reference']
        self.black_reference = params['black_reference']
        return params

    def select_search_zone(self):
        window_name = 'ARGOS - seleccione zona (clic y arrastre, ESC cancela)'
        display_scale = 1.5
        selection = {'start': None, 'current': None, 'zone': None}

        def on_mouse(event, x, y, flags, param):
            x = int(x / display_scale)
            y = int(y / display_scale)
            if event == cv2.EVENT_LBUTTONDOWN:
                selection['start'] = (x, y)
                selection['current'] = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and selection['start']:
                selection['current'] = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and selection['start']:
                selection['current'] = (x, y)
                x0, y0 = selection['start']
                x1, y1 = selection['current']
                left, top = min(x0, x1), min(y0, y1)
                width, height = abs(x1 - x0), abs(y1 - y0)
                if width >= 20 and height >= 20:
                    selection['zone'] = (left, top, width, height)

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 720)
        cv2.setMouseCallback(window_name, on_mouse)
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            small = frame
            preview = small.copy()
            if selection['start'] and selection['current']:
                x0, y0 = selection['start']
                x1, y1 = selection['current']
                cv2.rectangle(preview, (x0, y0), (x1, y1), (0, 255, 255), 2)
            cv2.putText(preview, 'Arrastre un rectangulo sobre la zona de busqueda', (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(preview, 'Suelte el raton para seleccionar   ESC cancela', (8, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(window_name, cv2.resize(preview, (0, 0), fx=display_scale, fy=display_scale,
                                               interpolation=cv2.INTER_NEAREST))
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if selection['zone']:
                left, top, width, height = selection['zone']
                scale_x = frame.shape[1] / small.shape[1]
                scale_y = frame.shape[0] / small.shape[0]
                zone = (int(left * scale_x), int(top * scale_y),
                        int(width * scale_x), int(height * scale_y))
                cv2.destroyWindow(window_name)
                return zone
        cv2.destroyWindow(window_name)
        return None

    def zone_for_frame(self, frame):
        if not self.search_zone:
            return (0, 0, frame.shape[1], frame.shape[0])
        x, y, width, height = self.search_zone
        if self.camera_frame_size:
            reference_width, reference_height = self.camera_frame_size
            x = int(x * frame.shape[1] / reference_width)
            y = int(y * frame.shape[0] / reference_height)
            width = int(width * frame.shape[1] / reference_width)
            height = int(height * frame.shape[0] / reference_height)
        x = max(0, min(x, frame.shape[1] - 1))
        y = max(0, min(y, frame.shape[0] - 1))
        width = min(width, frame.shape[1] - x)
        height = min(height, frame.shape[0] - y)
        return x, y, width, height

    def target_screen_position(self, center, frame, monitor):
        zone_x, zone_y, zone_width, zone_height = self.zone_for_frame(frame)
        relative_x = (center[0] - zone_x) / max(1.0, zone_width - 1)
        relative_y = (center[1] - zone_y) / max(1.0, zone_height - 1)
        relative_x = float(np.clip(relative_x, 0.0, 1.0))
        relative_y = float(np.clip(relative_y, 0.0, 1.0))
        relative_x = 1.0 - relative_x
        screen_x = monitor.x + int(relative_x * (monitor.width - 1))
        screen_y = monitor.y + int(relative_y * (monitor.height - 1))
        return screen_x, screen_y

    def move_mouse_to_target(self, target, frame, monitor):
        if not self.mouse_tracking_enabled or not self.enabled or not self.mouse or not monitor:
            return
        sx, sy = self.target_screen_position(target['center'], frame, monitor)
        try:
            self.mouse.position = (sx, sy)
        except Exception:
            pass

    def set_tracking_reference(self, target, params):
        reference_size = (target['bbox'][2], target['bbox'][3])
        self.tracking_model = (target['center'], reference_size)
        self.target_size = reference_size
        self.detection_params = dict(params)
        self.detection_params['target_size'] = reference_size
        self.center_image_point = target['center']
        self.calibrated = True
        self.save_detection_values(self.detection_params)

    def detect_target_in_zone(self, frame, params, reference=None):
        x, y, width, height = self.zone_for_frame(frame)
        local_reference = reference
        if reference:
            reference_center, reference_size = reference
            local_reference = ((reference_center[0] - x, reference_center[1] - y), reference_size)
        target = self.detect_target(frame[y:y + height, x:x + width], params, local_reference)
        if target:
            gx, gy, gw, gh = target['bbox']
            rx, ry, rw, rh = target['red_bbox']
            target['bbox'] = (gx + x, gy + y, gw, gh)
            target['red_bbox'] = (rx + x, ry + y, rw, rh)
            target['center'] = (target['center'][0] + x, target['center'][1] + y)
        return target

    def masks_for_target(self, frame, params):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white_threshold = params['white_v']
        black_threshold = params['black_v']
        if 'white_reference' in params and 'black_reference' in params:
            brightness_range = max(1.0, params['white_reference'] - params['black_reference'])
            white_threshold = int(np.clip(
                params['white_reference'] - brightness_range * params['white_deviation_pct'] / 100.0,
                0, 255))
            black_threshold = int(np.clip(
                params['black_reference'] + brightness_range * params['black_deviation_pct'] / 100.0,
                0, 255))
        white = cv2.inRange(hsv, np.array([0, 0, white_threshold]),
                            np.array([180, params['white_s'], 255]))
        black = cv2.inRange(hsv, np.array([0, 0, 0]),
                            np.array([180, 255, black_threshold]))
        open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, close_kernel)
        black = cv2.morphologyEx(black, cv2.MORPH_OPEN, open_kernel)
        return white, black

    def detect_target(self, frame, params, reference=None):
        white_mask, black_mask = self.masks_for_target(frame, params)
        grouping_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
        grouped_white = cv2.dilate(white_mask, grouping_kernel)
        white_contours, _ = cv2.findContours(grouped_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for white_contour in white_contours:
            group_x, group_y, group_width, group_height = cv2.boundingRect(white_contour)
            white_area = cv2.countNonZero(
                white_mask[group_y:group_y + group_height, group_x:group_x + group_width])
            if white_area < params['min_area']:
                continue
            rect = cv2.minAreaRect(white_contour)
            (center_x, center_y), (rect_width, rect_height), angle = rect
            if min(rect_width, rect_height) < 5 or max(rect_width, rect_height) / min(rect_width, rect_height) > 1.6:
                continue
            target_size = params.get('target_size')
            if target_size:
                expected_width, expected_height = target_size
                width_ratio = rect_width / max(1.0, expected_width)
                height_ratio = rect_height / max(1.0, expected_height)
                if not 0.45 <= width_ratio <= 1.8 or not 0.45 <= height_ratio <= 1.8:
                    continue
            box = cv2.boxPoints(rect).astype(np.float32)
            destination = np.array([[0, 0], [63, 0], [63, 63], [0, 63]], dtype=np.float32)
            ordered = np.zeros((4, 2), dtype=np.float32)
            coordinate_sum = box.sum(axis=1)
            coordinate_difference = np.diff(box, axis=1).reshape(-1)
            ordered[0] = box[np.argmin(coordinate_sum)]
            ordered[2] = box[np.argmax(coordinate_sum)]
            ordered[1] = box[np.argmin(coordinate_difference)]
            ordered[3] = box[np.argmax(coordinate_difference)]
            transform = cv2.getPerspectiveTransform(ordered, destination)
            roi = cv2.warpPerspective(black_mask, transform, (64, 64), flags=cv2.INTER_NEAREST)
            white_roi = cv2.warpPerspective(white_mask, transform, (64, 64), flags=cv2.INTER_NEAREST)
            perimeter = cv2.arcLength(white_contour, True)
            circularity = (4.0 * np.pi * cv2.contourArea(white_contour) /
                           max(1.0, perimeter * perimeter))
            if circularity < 0.55:
                continue

            black_contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL,
                                                 cv2.CHAIN_APPROX_SIMPLE)
            if not black_contours:
                continue
            inner_contour = max(black_contours, key=cv2.contourArea)
            inner_area = cv2.contourArea(inner_contour)
            inner_x, inner_y, inner_width, inner_height = cv2.boundingRect(inner_contour)
            inner_ratio = inner_area / float(roi.size)
            inner_fill = inner_area / max(1.0, inner_width * inner_height)
            inner_aspect = inner_width / max(1.0, inner_height)
            inner_center = (inner_x + inner_width / 2.0, inner_y + inner_height / 2.0)
            if (not params['inner_ratio'][0] <= inner_ratio <= params['inner_ratio'][1] or
                    inner_fill < 0.55 or not 0.65 <= inner_aspect <= 1.5 or
                    not 16 <= inner_center[0] <= 48 or not 16 <= inner_center[1] <= 48):
                continue
            x, y, width, height = cv2.boundingRect(white_contour)
            score = white_area * (1.0 - abs(rect_width - rect_height) / max(rect_width, rect_height))
            if reference:
                reference_center, reference_size = reference
                distance = np.hypot(center_x - reference_center[0], center_y - reference_center[1])
                size_difference = abs(rect_width - reference_size[0]) + abs(rect_height - reference_size[1])
                score /= 1.0 + distance / max(8.0, min(rect_width, rect_height) * 2.0)
                score /= 1.0 + size_difference / max(8.0, rect_width + rect_height)
            if best is None or score > best['score']:
                black_roi = black_mask[y:y + height, x:x + width]
                black_points = cv2.findNonZero(black_roi)
                bx, by, bw, bh = cv2.boundingRect(black_points) if black_points is not None else (0, 0, 0, 0)
                best = {'bbox': (x, y, width, height), 'red_bbox': (x + bx, y + by, bw, bh),
                        'center': (x + width // 2, y + height // 2), 'score': score,
                        'masks': (white_mask, black_mask)}
        return best

    def target_candidates(self):
        base = self.detection_values()
        candidates = [base]
        for white_s, white_v, black_v in ((35, 170, 65), (70, 135, 100), (50, 190, 80)):
            candidate = dict(base)
            candidate['white_s'] = white_s
            candidate['white_v'] = white_v
            candidate['black_v'] = black_v
            candidates.append(candidate)
        return candidates

    def find_target_with_filters(self, frame, reference=None):
        best = None
        best_params = None
        for params in self.target_candidates():
            target = self.detect_target_in_zone(frame, params, reference)
            if target and (best is None or target['score'] > best['score']):
                best, best_params = target, params
        return best, best_params

    def locate_target(self):
        self.search_zone = self.select_search_zone()
        if not self.search_zone:
            self.running = False
            if self.cap:
                self.cap.release()
                self.cap = None
            self.root.after(0, lambda: messagebox.showerror(
                'ERROR', 'No se definio una zona de busqueda.'))
            return False
        self.save_search_zone(self.search_zone)

        sample, sample_zone = self.select_target_sample()
        if sample is None:
            self.running = False
            if self.cap:
                self.cap.release()
                self.cap = None
            self.root.after(0, lambda: messagebox.showerror(
                'ERROR', 'No se marco ninguna forma para calibrar.'))
            return False

        started = time.time()
        stable_target = None
        stable_frames = 0
        target = None
        last_candidate = None
        params = self.calibrate_detection_from_sample(sample)
        self.reference_requested = False
        self.calibration_cancel_requested = False
        window_name = 'ARGOS - calibracion (ESC cancela)'
        display_scale = 1.5
        monitor = self.get_primary_monitor()
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        if monitor:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.resizeWindow(window_name, 1280, 720)
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            self.camera_frame_size = (frame.shape[1], frame.shape[0])
            small = frame
            previous_reference = None
            if last_candidate:
                previous_reference = (last_candidate['center'],
                                      (last_candidate['bbox'][2], last_candidate['bbox'][3]))
            target, candidate_params = self.find_target_with_filters(small, previous_reference)
            if target:
                last_candidate = target
            if candidate_params:
                params = candidate_params
            white_mask, black_mask = self.masks_for_target(small, params)
            zone_x, zone_y, zone_width, zone_height = self.zone_for_frame(small)
            zone_mask = np.zeros(white_mask.shape, dtype=np.uint8)
            zone_mask[zone_y:zone_y + zone_height, zone_x:zone_x + zone_width] = 255
            white_mask = cv2.bitwise_and(white_mask, zone_mask)
            black_mask = cv2.bitwise_and(black_mask, zone_mask)
            filtered = np.zeros_like(small)
            filtered[white_mask > 0] = (0, 0, 255)
            filtered[black_mask > 0] = (0, 255, 0)
            preview = small.copy()
            cv2.rectangle(preview, (zone_x, zone_y),
                          (zone_x + zone_width, zone_y + zone_height), (255, 255, 0), 1)

            possible_contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            blue_candidate = None
            blue_candidate_area = 0.0
            for contour in possible_contours:
                if cv2.contourArea(contour) >= params['min_area']:
                    x, y, w, h = cv2.boundingRect(contour)
                    black_inside = black_mask[y:y + h, x:x + w]
                    black_contours, _ = cv2.findContours(
                        black_inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    inner_square = None
                    for black_contour in black_contours:
                        ix, iy, iw, ih = cv2.boundingRect(black_contour)
                        inner_area = cv2.contourArea(black_contour)
                        inner_fill = inner_area / max(1.0, iw * ih)
                        inner_aspect = iw / max(1.0, ih)
                        centered = (0.20 <= (ix + iw / 2.0) / max(1, w) <= 0.80 and
                                    0.20 <= (iy + ih / 2.0) / max(1, h) <= 0.80)
                        away_from_edge = ix > 0 and iy > 0 and ix + iw < w and iy + ih < h
                        if (away_from_edge and inner_area >= params['min_area'] and
                                inner_fill >= 0.55 and 0.65 <= inner_aspect <= 1.5 and
                                params['inner_ratio'][0] <= inner_area / max(1, w * h) <= params['inner_ratio'][1] and
                                centered):
                            inner_square = black_contour
                            break
                    target_size = params.get('target_size')
                    similar_size = True
                    if target_size:
                        similar_size = (0.45 <= w / max(1, target_size[0]) <= 1.8 and
                                        0.45 <= h / max(1, target_size[1]) <= 1.8)
                    if inner_square is not None and similar_size:
                        contour_area = cv2.contourArea(contour)
                        if contour_area > blue_candidate_area:
                            blue_candidate = {'center': (x + w // 2, y + h // 2),
                                              'bbox': (x, y, w, h)}
                            blue_candidate_area = contour_area
                        cv2.rectangle(preview, (x, y), (x + w, y + h), (255, 0, 0), 1)
            if blue_candidate:
                last_candidate = target or blue_candidate
            if target:
                x, y, w, h = target['bbox']
                rx, ry, rw, rh = target['red_bbox']
                cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.rectangle(preview, (rx, ry), (rx + rw, ry + rh), (0, 0, 0), 2)
                if stable_target and abs(target['center'][0] - stable_target[0]) < 8 and abs(target['center'][1] - stable_target[1]) < 8:
                    stable_frames += 1
                else:
                    stable_frames = 1
                stable_target = target['center']
            else:
                stable_frames = 0
                stable_target = None
            cv2.putText(preview, 'Buscando circulo blanco con cuadrado negro', (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            status = 'ACEPTADA (amarillo)' if target else 'CANDIDATO (azul)'
            cv2.putText(preview, status, (8, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 255) if target else (255, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(preview, 'Rojo: claros  Verde: oscuros  Desviacion: '
                        f'{params["white_deviation_pct"]:.0f}%/{params["black_deviation_pct"]:.0f}%', (8, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(preview, 'C: aceptar candidato  S: salir  R: mover  M: detener', (8, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0) if self.mouse_tracking_enabled else (0, 0, 255), 1, cv2.LINE_AA)
            canvas = np.hstack((preview, filtered))
            if monitor:
                display_canvas = cv2.resize(canvas, (monitor.width, monitor.height),
                                            interpolation=cv2.INTER_NEAREST)
            else:
                display_canvas = cv2.resize(canvas, (0, 0), fx=display_scale, fy=display_scale,
                                            interpolation=cv2.INTER_NEAREST)
            coordinate_target = target or blue_candidate or last_candidate
            if coordinate_target:
                position_x = coordinate_target['center'][0] - zone_x
                position_y = coordinate_target['center'][1] - zone_y
                percent_x = 100.0 * position_x / max(1, zone_width - 1)
                percent_y = 100.0 * position_y / max(1, zone_height - 1)
                coordinate_label = 'Candidato zona' if target else 'Ultimo candidato'
                coordinate_text = (f'{coordinate_label}: x={position_x} y={position_y} '
                                   f'({percent_x:.1f}%, {percent_y:.1f}%)')
            else:
                coordinate_text = 'Candidato zona: --'
            text_size, _ = cv2.getTextSize(coordinate_text, cv2.FONT_HERSHEY_SIMPLEX,
                                           0.65, 2)
            text_x = max(10, display_canvas.shape[1] - text_size[0] - 20)
            cv2.putText(display_canvas, coordinate_text, (text_x, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(window_name, display_canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('c'):
                self.reference_requested = True
            elif key == ord('s'):
                self.calibration_cancel_requested = True
            if key == ord('r'):
                self.mouse_tracking_enabled = True
            elif key == ord('m'):
                self.mouse_tracking_enabled = False
            movement_target = target or blue_candidate or last_candidate
            if movement_target and monitor:
                self.move_mouse_to_target(movement_target, small, monitor)
            if self.reference_requested and last_candidate:
                self.reference_requested = False
                target = last_candidate
                self.set_tracking_reference(target, params)
                cv2.destroyWindow(window_name)
                self.root.after(0, lambda: messagebox.showinfo('ARGOS', 'Forma localizada y filtros guardados.'))
                return True
            if self.calibration_cancel_requested:
                self.calibration_cancel_requested = False
                break

        cv2.destroyWindow(window_name)
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.calibrated = False
        self.root.after(0, lambda: messagebox.showinfo(
            'ARGOS', 'Calibracion cancelada sin guardar la forma.'))
        return False

    def capture_loop(self):
        if not self.locate_target():
            return
        # eye state
        left_closed = False
        right_closed = False
        left_close_time = None
        right_close_time = None
        frame_number = 0
        last_target = None

        while self.running:
            if self.calibration_requested:
                self.calibration_requested = False
                self.calibrated = False
                if not self.locate_target():
                    return
                last_target = None
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            frame_number += 1

            # reduce size for speed
            small = frame

            if frame_number % 2 == 0:
                last_target = self.detect_target_in_zone(small, self.detection_params, self.tracking_model)
                if last_target:
                    self.tracking_model = (last_target['center'],
                                           (last_target['bbox'][2], last_target['bbox'][3]))

            if self.reference_requested and last_target:
                self.reference_requested = False
                self.set_tracking_reference(last_target, self.detection_params)

            if self.calibrated and last_target:
                monitor = self.get_primary_monitor()
                self.move_mouse_to_target(last_target, small, monitor)

            # Eye blink detection using mediapipe if available
            if self.face_mesh is not None and frame_number % 3 == 0:
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
        current_target = None
        last_candidate = None
        current_params = None

        def set_reference_from_double_click(event):
            target = current_target or last_candidate
            if target is not None and current_params is not None:
                self.set_tracking_reference(target, current_params)

        def update():
            nonlocal current_target, last_candidate, current_params
            ret, frame = self.cap.read()
            if ret:
                params = self.detection_params or self.detection_values()
                target = self.detect_target(frame, params)
                current_target = target
                current_params = params
                if target is not None:
                    last_candidate = target
                if target:
                    x, y, w, h = target['bbox']
                    rx, ry, rw, rh = target['red_bbox']
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 2)
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 0, 0), 2)
                # convert to PIL for Tkinter
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                label.imgtk = imgtk
                label.config(image=imgtk)
            if win.winfo_exists():
                win.after(30, update)

        label.bind('<Double-Button-1>', set_reference_from_double_click)

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
