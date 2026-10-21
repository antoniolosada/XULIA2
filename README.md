# ARGOS — Asistencia del Ratón mediante Guiado Óptico Síncrono

Pequeño prototipo en Python que usa una cámara para seguir dos puntos (rojo/verde) pegados a las patillas de las gafas y detectar cierres de ojos para simular clics.

Archivos:
- [argos.py](argos.py): script principal.
- [config.ini](config.ini): fichero de configuración.
- [requirements.txt](requirements.txt): dependencias.

Instalación (recomendado en un virtualenv):

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Ejecución:

```bash
python argos.py
```

Notas importantes:
- El código usa MediaPipe para detección de la malla facial; la detección de ojos es heurística y puede requerir ajuste de umbrales.
- El mapeado de mirada es una aproximación basada en el punto medio entre los marcadores y una ganancia; calibrar en un entorno con buena iluminación.
- En Windows, para registrar atajos globales puede ser necesario ejecutar con privilegios suficientes.
# Xulia2 - Asistente de control por voz para Windows

Un sistema en Python para personas tetrapléjicas que permite controlar aplicaciones en Windows por voz en español o portugués.

## Características

- Control de cualquier aplicación con comandos de voz.
- Modo dictado con posibilidad de corregir la última frase.
- Rejilla superpuesta para mover el cursor rápidamente.
- Pulsado de botones por nombre usando lectura de pantalla con UI Automation.
- Soporte básico para pestañas de la cinta Office por nombre.
- Activación, desactivación y desactivación temporal.
- Icono en la zona de sistema y notificaciones con globo.
- Ayuda integrada con los comandos disponibles.

## Requisitos

- Python 3.12 en Windows.
- Las dependencias fijadas en [requirements.txt](requirements.txt) (incluyen las de ARGOS).
- Modelos de Vosk en `models/` (incluidos en el repositorio).

## Instalación

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Uso

```powershell
.venv\Scripts\python.exe xulia2.py
```

Di comandos como:

- "modo dictado"
- "corregir la última frase"
- "mostrar rejilla"
- "casilla 120"
- "botón Guardar"
- "cinta Inicio"
- "desactivar"
- "ayuda"

## Configuración

- [patterns.txt](patterns.txt): las frases de cada comando (`clave=expresión regular`, gana la primera que coincide), los reemplazos del dictado (`regex => texto`) y el motor de reconocimiento (`recognition_engine`).

## Notas

- El reconocimiento puede usar Google (necesita internet) o Vosk (local, sin internet); se elige con `recognition_engine` en `patterns.txt`.
- La rejilla se superpone en una ventana transparente, se divide en 20x15 casillas y muestra el número de cada casilla en la esquina superior izquierda.
- ARGOS (`argos.py`) es el ratón con la cabeza; ver arriba.
