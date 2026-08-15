import cv2
import sys
import numpy as np
import mediapipe as mp
from PIL import Image
import pyautogui

print('Python and module quick check')
print('cv2 version:', cv2.__version__)
print('numpy version:', np.__version__)
print('mediapipe available:', hasattr(mp, 'solutions'))
print('Pillow available:', Image.PILLOW_VERSION if hasattr(Image, 'PILLOW_VERSION') else 'ok')
print('pyautogui size:', pyautogui.size())

print('\nProbing camera indices 0..5')
for i in range(6):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    ok = cap.isOpened()
    print('Camera', i, '->', 'OPEN' if ok else 'NO')
    if ok:
        cap.release()

print('\nDiag complete')
