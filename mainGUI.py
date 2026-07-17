import cv2
import numpy as np
from pathlib import Path
from pygrabber.dshow_graph import FilterGraph # Package um angeschlossene Geräte zu scannen
import tkinter as tk # GUI-Toolkit
from tkinter import ttk, simpledialog, messagebox # Moderne Tkinter-Widgets
from PIL import Image, ImageTk # Für die Anzeige von OpenCV-Bildern in Tkinter
import sv_ttk # Dark-Mode Theme für Tkinter
import darkdetect # Erkennt ob Windows im Dark Mode ist
from datetime import datetime # Funktionen für den Timestamp
import json

##### Kamerakalibrierung #####
from cameraCalibration import (
    start_calibration_gui
   )

##### Vision Pipeline #####
from visionPipeline import (
    runVisionPipeline,
    undistortFrame
)




##### Globale Variablen #####
sCam = None # Selected Camera
sCamID = None # Selected Camera ID
max_resolution = None # Maximale Auflösung der gewählten Camera
calibration_file = None # Pfad zur Kalibrierdatei
camera_info = None # Dictionary wird später mit allen Kamerainfos gefüllt, die für die Kamerakalibrierung nötig sind
current_full_frame = None # Aktuell aufgenommener Frame
last_cad_data = None
DATA_OUTPUT_PATH = Path(__file__).parent / "data.json"

# Kamera Parameter #
CAM_PARAMETER_SETZEN = True
CAM_PARAMETER = [
    # Name, OpenCV-Property, Soll-Wert
    ("autofocus", cv2.CAP_PROP_AUTOFOCUS, 1),
    ("focus", cv2.CAP_PROP_FOCUS, None),

    ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE, -1),
    ("exposure", cv2.CAP_PROP_EXPOSURE, -1),

    ("gain", cv2.CAP_PROP_GAIN, 5),
    ("brightness", cv2.CAP_PROP_BRIGHTNESS, 0),
    ("contrast", cv2.CAP_PROP_CONTRAST, 80),
    ("saturation", cv2.CAP_PROP_SATURATION, 50),

    # Optional, falls unterstützt
    ("auto_wb",        getattr(cv2, "CAP_PROP_AUTO_WB", None), None),
    ("white_balance",  getattr(cv2, "CAP_PROP_WB_TEMPERATURE", None), None),
    ("gamma",          getattr(cv2, "CAP_PROP_GAMMA", None), None),
    ("sharpness",      getattr(cv2, "CAP_PROP_SHARPNESS", None), None),
]

# Pipeline-Mode Variablen
assisted_analyze_button = None
auto_analyze_button = None

assisted_pipeline_icon = None
auto_pipeline_icon = None

ICON_DIR = Path(__file__).parent / "icons"
ICON_SIZE = 86
ICON_SOURCE_SIZE = 256

# Assistierter Polygon-Modus
assisted_mode_active = True
assisted_base_frame = None # Entzerrtes Originalbild in voller Auflösung
assisted_polygon_points = [] # Pixelpunkte des gezeichneten Polygons
preview_base_width = 800 # Setzt die Skalierung des Bildes zurück, wenn der assistierte Modus beendet wird
resize_after_id = None # Soll das Bild nochmal neu zeichnen, sobald das Fenster verschoben oder die Größe verändert wird. So entstehen dadurch keine fehlerhaften Punkte

display_zoom = 1.0
current_display_frame = None

MIN_DISPLAY_ZOOM = 1.0
MAX_DISPLAY_ZOOM = 12.0

# Canvas-Bildanzeige
image_canvas = None
canvas_photo = None
canvas_image_id = None

display_scale = 1.0
display_image_w = 0
display_image_h = 0

#################### TEMP ###################
plate_thickness = 0.0 # in Milimeter

USE_TEST_IMAGE = False 
TEST_IMAGE_PATH = Path(__file__).parent / "finaltest_aruco_spannsituation.png"
#TEST_IMAGE_PATH = Path(__file__).parent / "autopipeline-testbilder" / "auto_schmale_platte.png"
TEST_CALIB_PATH = Path(__file__).parent / "EMEET_SmartCam_Nova_4k_3840x2160p_20260607_173908.npz"

#finaltest_aruco_spannsituation.png
#calibration_reference_marker.png
#fastleereplatte.png
TEST_CAMERA_NAME = "WAAM-Webcam-Testbild"
#################### TEMP ###################

### Testbild Funktion ###
def load_test_image():
    frame = cv2.imread(str(TEST_IMAGE_PATH), cv2.IMREAD_COLOR)

    if frame is None:
        print(f"Testbild konnte nicht geladen werden: {TEST_IMAGE_PATH}")
        return None

    print(f"Testbild geladen: {TEST_IMAGE_PATH.name} | Größe: {frame.shape[1]}x{frame.shape[0]}")
    
    return frame

def load_test_cam_info_from_image(frame):
    height, width = frame.shape[:2]

    return {
        "camera_id": -1,
        "camera_name": TEST_CAMERA_NAME,
        "display_text": f"TEST - {TEST_CAMERA_NAME}",
        "resolution_width": width,
        "resolution_height": height
    }

def load_test_calibration_file():
    global calibration_file

    if TEST_CALIB_PATH.exists():
        calibration_file = TEST_CALIB_PATH
        caminfo_calib_val.config(text=f"✓ TEST:\n{TEST_CALIB_PATH.name}")
        caminfo_calibdate_val.config(text="-")
        return True
    
    calibration_file = None
    caminfo_calib_val.config(text=f"Test-Kalibrierdatei fehlt:\n{TEST_CALIB_PATH.name}")
    caminfo_calibdate_val.config(text="-")
    print(f"Test-Kalibrierdatei nicht gefunden: {TEST_CALIB_PATH}")
    return False


def close_gui():
    root.destroy()
    return

### Kameraauswahl ###

def create_capture():
    # Öffnet eine Kamera mit der aktuellen ID mit dem besten verfügbaren Backend
    backends_to_try = [
        ("DSHOW", cv2.CAP_DSHOW),
        ("MSMF", cv2.CAP_MSMF)
    ]

    # Öffnen der Kamera mit den verschiedenen Backends
    for backend_name, backend_flag in backends_to_try:
        capture = cv2.VideoCapture(sCamID, backend_flag)

        if capture is not None and capture.isOpened():
            print(f"Kamera {sCamID} erfolgreich geöffnet mit Backend: {backend_name}")
            return capture, backend_name
        
        if capture is not None:
            capture.release()

    return None, None


def load_cam_info():

    global max_resolution, camera_info

    camera_info = None
    camCalibButton.config(state="disabled")
    capture_button.config(state="disabled")
    set_analyze_buttons_state("disabled")

    # Wenn keine Kamera ausgewählt ist 
    if sCam is None:
        return
    
    cap, backend = create_capture()

    # Wenn Kamera nicht geöffnet werden kann
    if cap is None:
        update_caminfo_labels(fehler="Kamera konnte nicht geöffnet werden")
        camCalibButton.config(state="disabled")
        capture_button.config(state="disabled")
        set_analyze_buttons_state("disabled")
        return
    
    # Ermitteln der höchste Auflösung
    # Liste mit Standardauflösungen (16:9)
    resolutions = [
        (3840, 2160), # 4K
        (2560, 1440), # 1440p
        (1920, 1200), # WUXGA
        (1920, 1080), # Full HD
        (1280, 720), # HD
        (800, 600), # SVGA
        (640, 480), # VGA
    ]
    max_resolution = None
    for width, height in resolutions:

        # 
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Wenn die Auflösung akzeptiert wurde, als Maximum speichern
        if actual_w == width and actual_h == height:
            max_resolution = (width, height)
            print(f"Maximale Auflösung erkannt: {width}x{height}")
            break
    
    # Falls die for-Schleife vorher failed:
    if max_resolution is None:
        max_resolution = (640, 480) # Fallback Auflösung, wenn die höheren failen
        print(f"Fallback-Auflösung: {max_resolution[0]}x{max_resolution[1]}")

    autofocus = cap.get(cv2.CAP_PROP_AUTOFOCUS)

    cap.release()

    update_caminfo_labels(
        resolution=f"{max_resolution[0]}x{max_resolution[1]}",
        autofocus="Ja" if autofocus == 1.0 else "Nein",
        backend=backend
    )

    # Check ob für diese Kamera eine Kalibrierdatei vorhanden ist
    check_calibration_file()

    camera_info = {
        "camera_id": sCam["camera_id"],
        "camera_name": sCam["capture_name"],
        "display_text": sCam["display_text"],
        "resolution_width": max_resolution[0],
        "resolution_height": max_resolution[1]
    }
    camCalibButton.config(state="normal")
    capture_button.config(state="normal")
    set_analyze_buttons_state("disabled")

def update_caminfo_labels(resolution="-", autofocus="-", backend="-", fehler=None):
    if fehler:
        caminfo_res_val.config(text=fehler)
        caminfo_af_val.config(text="-")
        caminfo_backend_val.config(text="-")
        caminfo_calib_val.config(text="-")
        caminfo_calibdate_val.config(text="-")
        return
    
    caminfo_res_val.config(text=resolution)
    caminfo_af_val.config(text=autofocus)
    caminfo_backend_val.config(text=backend)


# Checkt ob eine Kalibrierdatei für die ausgewählte Kamera existiert
def check_calibration_file():

    global calibration_file
    calibration_file = None

    if sCam is None or max_resolution is None:
        caminfo_calib_val.config(text="")
        caminfo_calibdate_val.config(text="")
        return
    
    # Check ob eine npz Datei im Root Verzeichnis existiert
    npz_files = list(Path(".").glob("*.npz"))
    if not npz_files:
        caminfo_calib_val.config(text="Keine Kalibrierdateien gefunden!")
        caminfo_calibdate_val.config(text="")
        return
    
    # Generiert den String mit dem nach der Datei gesucht wird:
    safe_name = sCam["capture_name"].replace(" ", "_")
    resolution_str = f"{max_resolution[0]}x{max_resolution[1]}p"

    # DEBUG
    print(f"Sucher nach: startswith='{safe_name}_' enthält='{resolution_str}'")
    for f in npz_files:
        print(f" gefunden: {f.name}")

    # Dateien filtern die den Kameranamen beinhalten
    passende_dateien = [
        f for f in npz_files
        if f.name.lower().startswith((safe_name + "").lower()) # Überprüft auf Lower Case & Upper Case
        and resolution_str.lower() in f.name.lower()
    ]

    if not passende_dateien:
        caminfo_calib_val.config(text="Keine passende Datei gefunden")
        caminfo_calibdate_val.config(text="")
        return

    # Timestamp aus dem Dateinamen parsen
    def file_timestamp(f):
        parts = f.stem.split("_")
        try:
            return datetime.strptime(parts[-2] + parts[-1], "%Y%m%d%H%M%S")
        except (ValueError, IndexError):
            return datetime.min


    # Neueste Kalibrierdatei auswählen
    newest = max(passende_dateien, key=file_timestamp)

    calibration_file = newest
    caminfo_calib_val.config(text=f"✓ Vorhanden:\n{newest.name}")

    # Timestamp der gefunden Datei anzeigen
    date = file_timestamp(newest)
    if date != datetime.min:
        caminfo_calibdate_val.config(text=date.strftime("%d.%m.%Y %H:%M"))
    else:
        caminfo_calibdate_val.config(text="Unbekannt")
    
    return


def open_calibration_gui():
    global camera_info

    if sCam is None or camera_info is None:
        print("Keine gültige Kamera ausgewählt.")
        return 
    
    start_calibration_gui(
        cam_info = camera_info.copy(),
        return_theme=app_theme
    )



def refresh_camera_list():
    # Aktualisiert das Dropdownmenü zur Kamerawahl

    global available_cameras

    if USE_TEST_IMAGE:
        available_cameras = [{
            "camera_id": -1,
            "capture_name": TEST_CAMERA_NAME,
            "display_text": f"TEST - {TEST_CAMERA_NAME}"
        }]

        camera_combo["values"] = [available_cameras[0]["display_text"]]
        camera_combo.current(0)

        on_camera_selected()
        return


    # Aktuelle Auswahl merken
    if sCam is not None:
        prev_selection = sCam["capture_name"]
    else:
        prev_selection = None

    available_cameras = []

    camera_list = FilterGraph().get_input_devices()

    for camera_id, camera_name in enumerate(camera_list):
        available_cameras.append({
            "camera_id": camera_id,
            "capture_name": camera_name,
            "display_text": f"{camera_id} - {camera_name}"
        })

    # Aktualisiere Dropdownmenü-Liste
    camera_combo["values"] = [cam["display_text"] for cam in available_cameras]

    # Falls keine Kamera gefunden wurde
    if not available_cameras:
        camera_combo.set("")
        on_camera_selected() # Setzt sCam zurück
        print("Keine Kamera gefunden!")
        return
    
    # Falls die alte Kamera noch vorhanden ist, diese Auswahl wiederherstellen
    index_prev_selection = None
    # Check ob alte Kamera in neuer Liste vorkommt
    for i, cam in enumerate(available_cameras):
        if cam["capture_name"] == prev_selection:
            index_prev_selection = i
            break

    # Wiederherstellung der Auswahl
    if index_prev_selection is not None:
        camera_combo.current(index_prev_selection)
    else:
        camera_combo.current(0)

    # Aktualisieren der globalen Kameraobjekte
    on_camera_selected()


def on_camera_selected(event=None):
    global sCam, sCamID, camera_info, current_full_frame
    global max_resolution, calibration_file

    current_full_frame = None
    set_analyze_buttons_state("disabled")

    if USE_TEST_IMAGE:
        selected_index = camera_combo.current()

        if selected_index != -1 and selected_index < len(available_cameras):
            selected = available_cameras[selected_index]
            sCamID = selected["camera_id"]
            sCam = selected

            camera_info = None
            max_resolution = None
            calibration_file = None
            
            clear_image_canvas("Testmodus: Bild laden")

            camCalibButton.config(state="disabled")
            capture_button.config(state="normal")
            set_analyze_buttons_state("disabled")

            update_caminfo_labels(
                resolution="-",
                autofocus="-",
                backend="TEST_IMAGE"
            )
        return

    selected_index = camera_combo.current()

    # Wenn die aktuelle Auswahl nicht null ist und in available_cameras existiert
    if selected_index != -1 and selected_index < len(available_cameras):
        selected = available_cameras[selected_index]
        sCamID = selected["camera_id"]
        sCam = selected
        print(f"Kamera ausgewählt: {selected['display_text']}")
        # Altes Testbild entfernen
        clear_image_canvas("Kein Bild")
        load_cam_info()
    else:
        sCam = None
        sCamID = None
        camera_info = None
        camCalibButton.config(state="disabled")
        capture_button.config(state="disabled")
    return

# Testbild aufnehmen

def capture_image():
    global current_full_frame, camera_info, calibration_file, last_cad_data

    last_cad_data = None
    cad_button.config(state="disabled")

    info_plattenerkennung.config(text="Platte erkannt: -")
    info_spanneisen.config(text="Spanneisen erkannt: -")
    info_statusmsg.config(text="Status: Neues Bild aufgenommen / noch nicht analysiert")
    

    # Check ob der Testmodus aktiv ist - Wenn ja, wird statt das Livebild ein Testbild eingelesen
    if USE_TEST_IMAGE:
        frame = load_test_image()

        if frame is None:
            current_full_frame = None
            camera_info = None
            calibration_file = None
            set_analyze_buttons_state("disabled")
            clear_image_canvas("Testbild nicht gefunden")
            return
        
        camera_info = load_test_cam_info_from_image(frame)
        has_calibration = load_test_calibration_file()

        update_caminfo_labels(
            resolution=f"{camera_info['resolution_width']}x{camera_info['resolution_height']}",
            autofocus="-",
            backend="TEST_IMAGE"
        )



    # Normalmodus, mit echter Kamera, nimmt das Livebild auf
    else:

        if sCam is None:
            return
        
        cap, _ = create_capture()

        if cap is None:
            clear_image_canvas("Kamera nicht verfügbar")
            current_full_frame = None
            set_analyze_buttons_state("disabled")
            capture_button.config(state="disabled")
            update_caminfo_labels(fehler="Kamera nicht verfügbar / möglicherweise ausgesteckt")
            refresh_camera_list()
            return
        
        # Auflösung einstellen
        if max_resolution is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, max_resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, max_resolution[1])

        # Kamera-Parameter kurz vor der Aufnahme setzen
        if CAM_PARAMETER_SETZEN:
            print("Kamera-Parameter setzen:")

            for name, prop_id, value in CAM_PARAMETER:
                if prop_id is None or value is None:
                    continue

                ok = cap.set(prop_id, value)
                actual = cap.get(prop_id)

                print(f"    {name:16s}: Soll-Wert = {value}, Ist-Wert = {actual}, set_ok = {ok}")

        # Ein paar Frames verwerfen, damit die Auflösung Zeit hat zu greifen
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            current_full_frame = None
            set_analyze_buttons_state("disabled")
            clear_image_canvas("Kein Bild")
            return
        
        has_calibration = calibration_file is not None

    # Gemeinsamer Teil - Anzeige und Button-Updates
    print(f"Frame-Größe: {frame.shape[1]}x{frame.shape[0]}")
    current_full_frame = frame.copy()
    
    update_preview_base_width()
    set_display_frame(frame, reset_zoom=True, resize_window=True)

    # Aktivieren des Analyse-Buttons, nur wenn die Kalibrierdatei vorhanden ist:
    if calibration_file is not None:
        set_analyze_buttons_state("normal")
    else:
        set_analyze_buttons_state("disabled")
        print("Bild aufgenommen, aber keine Kalibrierdatei vorhanden.")

def ask_plate_thickness():
    global plate_thickness

    value = simpledialog.askfloat(
        "Schweißplattendicke", # Fenstertitel
        "Dicke der Substratplatte in mm:", # Eingabeaufforderung
        initialvalue=plate_thickness, # Standardwert
        minvalue=0.0 # Mindestwert der akzeptiert wird
    )

    if value is None:
        info_statusmsg.config(text="Status: Analyse abgebrochen - keine Plattendicke angegeben.")
        return False

    plate_thickness = float(value)
    return True

def startVisionPipeline(pipeline_mode, assisted_polygon_pixels=None, ask_thickness=True):
    global last_cad_data

    if pipeline_mode not in ("auto", "assisted"):
        print(f"Unbekannter Pipeline-Modus: {pipeline_mode}")
        return
    
    print(f"Starte Pipeline im Modus: {pipeline_mode}")

    if current_full_frame is None:
        print("Kein Bild aufgenommen.")
        return
    
    if camera_info is None:
        print("Fehlende Kamerinfos.")
        return
    
    if calibration_file is None:
        print("Kalibrierdaten fehlen.")
        return
    
    if pipeline_mode == "assisted" and assisted_polygon_pixels is None:
        print("Assistierter Modus benötigt Polygonpunkte.")
        return
    
    ### Assisted Modus ###

    ### Assisted Modus ###

    # Plattendicke-Eingabe:
    if ask_thickness:
        if not ask_plate_thickness():
            if current_full_frame is not None and calibration_file is not None:
                set_analyze_buttons_state("normal")
            return

    processed_frame, msg, cad_data = runVisionPipeline(
        current_full_frame, 
        camera_info, 
        calibration_file, 
        plate_thickness,
        pipeline_mode,
        assisted_polygon_pixels = assisted_polygon_pixels
        )
    
    last_cad_data = cad_data
    



    # processed_frame: Originalbild mit eingezeichneter Kontur und erkannten Markern
    # msg: Dictionary mit allen Infos gespeichert

    ## Aktivieren des CAD-Import Buttons
    if msg.get("plate_detected", False):
        cad_button.config(state="normal")
    else:
        cad_button.config(state="disabled")

    ## Anzeigen der erkannten Kontur ## Übernommen aus capture_image()
    update_preview_base_width()
    set_display_frame(processed_frame, reset_zoom=True, resize_window=True)

    # Ab hier soll msg verarbeitet werden, damit alle Infos im mainGUI angezeigt werden

    # Button zur Übertragung ins CAD soll aktiviert werden

    info_plattenerkennung.config(text=f"Platte erkannt: {msg.get('plate_detected', False)}")
    info_spanneisen.config(text=f"Spanneisen erkannt: {msg.get('clamp_count', '-')}")
    info_statusmsg.config(text=f"Status: {msg.get('status', '-')}")

    set_analyze_buttons_state("disabled")


def set_analyze_buttons_state(state):
    if assisted_analyze_button is not None:
        assisted_analyze_button.config(state=state)

    if auto_analyze_button is not None:
        auto_analyze_button.config(state=state)

def load_pipeline_button_icons(theme):
    global assisted_pipeline_icon, auto_pipeline_icon

    if theme == "dark":
        mode = "dark"
    else: 
        mode = "light"

    assisted_path = ICON_DIR / f"assisted_pipeline_icon_{mode}_{ICON_SOURCE_SIZE}.png"
    auto_path = ICON_DIR / f"auto_pipeline_icon_{mode}_{ICON_SOURCE_SIZE}.png"

    assisted_pipeline_icon = ImageTk.PhotoImage(
        Image.open(assisted_path).resize(
            (ICON_SIZE, ICON_SIZE), 
            Image.Resampling.LANCZOS
        )
    )

    auto_pipeline_icon = ImageTk.PhotoImage(
        Image.open(auto_path).resize(
            (ICON_SIZE, ICON_SIZE), 
            Image.Resampling.LANCZOS
        )
    )

def set_display_frame(frame_bgr, reset_zoom=True, resize_window=False):
    global current_display_frame, display_zoom
    
    if frame_bgr is None:
        return
    
    current_display_frame = frame_bgr.copy()

    if reset_zoom:
        display_zoom = MIN_DISPLAY_ZOOM

    show_current_display_frame()

    if resize_window:
        resize_window_to_display_image()
        show_current_display_frame()

def show_current_display_frame():
    global canvas_photo, canvas_image_id
    global display_scale, display_image_w, display_image_h

    if current_display_frame is None:
        return

    root.update_idletasks()

    frame_bgr = current_display_frame
    frame_h, frame_w = frame_bgr.shape[:2]

    canvas_w = image_canvas.winfo_width()

    if canvas_w < 10:
        canvas_w = main_frame.winfo_width()

    if canvas_w < 10:
        canvas_w = 800

    target_w = int(canvas_w * display_zoom)
    target_w = max(target_w, 1)

    frame_ratio = frame_h / frame_w
    target_h = int(target_w * frame_ratio)
    target_h = max(target_h, 1)

    frame_resized = cv2.resize(
        frame_bgr,
        (target_w, target_h),
        interpolation=cv2.INTER_LINEAR
    )

    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb)

    canvas_photo = ImageTk.PhotoImage(image)

    image_canvas.delete("all")

    canvas_image_id = image_canvas.create_image(
        0,
        0,
        anchor="nw",
        image=canvas_photo
    )

    image_canvas.configure(
        scrollregion=(0, 0, target_w, target_h)
    )

    display_scale = target_w / frame_w
    display_image_w = target_w
    display_image_h = target_h

def resize_window_to_display_image():
    if current_display_frame is None:
        return

    root.update_idletasks()

    screen_h = root.winfo_screenheight()
    max_window_h = int(screen_h * 0.90)

    # Wie viel Höhe außerhalb des Canvas bereits durch Steuerung, Buttons, Rahmen etc. belegt ist
    non_canvas_h = root.winfo_height() - image_canvas.winfo_height()

    # Ziel: Canvas soll so hoch werden wie das angezeigte Bild,
    # aber nicht größer als der verfügbare Bildschirmbereich
    target_canvas_h = display_image_h
    max_canvas_h = max_window_h - non_canvas_h

    target_canvas_h = max(250, min(target_canvas_h, max_canvas_h))

    image_canvas.configure(height=target_canvas_h)

    root.update_idletasks()

    new_w = root.winfo_width()
    new_h = min(root.winfo_reqheight(), max_window_h)

    root.geometry(f"{new_w}x{new_h}")

def on_canvas_pan_start(event):
    image_canvas.scan_mark(event.x, event.y)

def on_canvas_pan_move(event):
    image_canvas.scan_dragto(event.x, event.y, gain=1)

### Assisted Mode ###


def update_preview_base_width():
    global preview_base_width

    root.update_idletasks()

    canvas_w = image_canvas.winfo_width()

    if canvas_w >= 10:
        preview_base_width = canvas_w
    else:
        main_w = main_frame.winfo_width()

        if main_w >= 10:
            preview_base_width = main_w
        else:
            preview_base_width = 800

def clear_image_canvas(text="Kein Bild"):
    global canvas_photo, canvas_image_id
    global current_display_frame, display_zoom

    if image_canvas is None:
        return

    image_canvas.delete("all")
    canvas_photo = None
    canvas_image_id = None
    current_display_frame = None
    display_zoom = 1.0

    root.update_idletasks()

    x = max(image_canvas.winfo_width() // 2, 100)
    y = 40

    image_canvas.create_text(
        x,
        y,
        text=text,
        fill="gray",
        font=("TkDefaultFont", 12, "bold"),
        anchor="n"
    )

def canvas_event_to_original_pixel(event):
    if assisted_base_frame is None:
        return None

    canvas_x = image_canvas.canvasx(event.x)
    canvas_y = image_canvas.canvasy(event.y)

    u = canvas_x / display_scale
    v = canvas_y / display_scale

    frame_h, frame_w = assisted_base_frame.shape[:2]

    if u < 0 or v < 0 or u >= frame_w or v >= frame_h:
        return None

    return float(u), float(v) # Als float gespeichert = subpixelgenaue Genauigkeit

def draw_assisted_polygon_overlay(frame_bgr, points):
    output = frame_bgr.copy()

    if len(points) == 0:
        return output
    
    pts = np.round(np.array(points, dtype=np.float64)).astype(np.int32) # Array welches alle Punkte speichert, für die Anzeige werden die subpixelgenauen Punkt gerundet

    for u, v in points:
        cv2.circle(output, (int(u), int(v)), 8, (0, 255, 255), 2)

    if len(points) >= 2:
        cv2.polylines(
            output, 
            [pts.reshape(-1, 1, 2)],
            isClosed=False,
            color=(0, 255, 255),
            thickness=2
        )

    if len(points) >= 3:
        overlay = output.copy()

        cv2.fillPoly(
            overlay,
            [pts.reshape(-1, 1, 2)],
            color=(0, 255, 255)
        )

        # Overlay auf das Bild legen
        output = cv2.addWeighted(
            overlay, 
            0.25,
            output, 
            0.75,
            0
        )

        cv2.polylines(
            output, 
            [pts.reshape(-1, 1, 2)],
            isClosed=True,
            color=(0, 180, 255),
            thickness=3
        )

    return output

def update_assisted_polygon_display():
    
    if assisted_base_frame is None:
        return
    
    frame_with_overlay = draw_assisted_polygon_overlay(
        assisted_base_frame,
        assisted_polygon_points
    )

    set_display_frame(
        frame_with_overlay,
        reset_zoom = False
    )

    if len(assisted_polygon_points) > 0:
        u, v = assisted_polygon_points[-1]
        info_statusmsg.config(
            text=f"Status: Assistierter Modus - {len(assisted_polygon_points)} Punkte gesetzt\nletzter Punkt: u={u:.1f}, v={v:.1f}"
        )
    else:
        info_statusmsg.config(
            text="Status: Assistierter Modus - 0 Punkte gesetzt"
        )

def assisted_on_left_click(event):

    # Shift-Klick reserviert für Pan:
    if event.state & 0x0001:
        return

    point = canvas_event_to_original_pixel(event)

    if point is None:
        return

    assisted_polygon_points.append(point)
    update_assisted_polygon_display()

def on_canvas_mousewheel(event):
    global display_zoom

    if current_display_frame is None:
        return

    old_zoom = display_zoom

    # Cursorposition im Canvas-Koordinatensystem vor dem Zoom
    old_canvas_x = image_canvas.canvasx(event.x)
    old_canvas_y = image_canvas.canvasy(event.y)

    # Entsprechender Originalbild-Punkt unter dem Cursor
    old_u = old_canvas_x / display_scale
    old_v = old_canvas_y / display_scale

    # Zoom ändern
    if event.delta > 0:
        display_zoom *= 1.15
    else:
        display_zoom /= 1.15

    display_zoom = max(
        MIN_DISPLAY_ZOOM,
        min(display_zoom, MAX_DISPLAY_ZOOM)
    )

    # Wenn Zoom-Grenze erreicht ist, nichts neu zeichnen
    if display_zoom == old_zoom:
        return

    # Bild mit neuem Zoom neu zeichnen
    show_current_display_frame()

    # Nach dem Neuzeichnen soll derselbe Originalbild-Punkt
    # wieder unter dem Cursor liegen
    new_canvas_x = old_u * display_scale
    new_canvas_y = old_v * display_scale

    target_left = new_canvas_x - event.x
    target_top = new_canvas_y - event.y

    canvas_w = max(image_canvas.winfo_width(), 1)
    canvas_h = max(image_canvas.winfo_height(), 1)

    max_left = max(display_image_w - canvas_w, 0)
    max_top = max(display_image_h - canvas_h, 0)

    target_left = max(0, min(target_left, max_left))
    target_top = max(0, min(target_top, max_top))

    # Wichtig:
    # xview_moveto/yview_moveto erwarten Anteil an der gesamten Scrollregion,
    # nicht am maximal scrollbaren Bereich.
    image_canvas.xview_moveto(
        target_left / max(display_image_w, 1)
    )

    image_canvas.yview_moveto(
        target_top / max(display_image_h, 1)
    )

def assisted_on_confirm(event=None):

    if len(assisted_polygon_points) < 3:
        info_statusmsg.config(text="Status: Mindestens 3 Punkte für ein Polygon setzen.")
        return
    
    polygon_pixels = np.array(
        assisted_polygon_points,
        dtype=np.float64
    )

    if not ask_plate_thickness():
        return

    exit_assisted_polygon_mode()

    startVisionPipeline(
        "assisted",
        assisted_polygon_pixels = polygon_pixels,
        ask_thickness=False
    )

def assisted_on_cancel(event=None):
    exit_assisted_polygon_mode()

    if current_full_frame is not None:
        set_display_frame(current_full_frame, reset_zoom=True, resize_window=True)

    if current_full_frame is not None and calibration_file is not None:
        set_analyze_buttons_state("normal")

    info_statusmsg.config(text="Status: Assistierter Modus abgebrochen")

def start_assisted_polygon_mode():
    global assisted_mode_active, assisted_base_frame, assisted_polygon_points

    calib_data = np.load(calibration_file) # Temporäres Laden der Kalibrierparameter
    assisted_base_frame = undistortFrame(current_full_frame, calib_data["camera_matrix"], calib_data["dist_coeffs"])

    if assisted_base_frame is None:
        return

    assisted_polygon_points = []
    assisted_mode_active = True

    image_canvas.config(cursor="crosshair")
    assist_hint_label.config(text="Assistierter Modus: Linksklick = Punkt setzen | Rechtsklick/Enter = bestätigen | Escape = abbrechen | Mausrad = Zoom | Shift + Linksklick = Pan")

    image_canvas.bind("<Button-1>", assisted_on_left_click) # Linksklick um Punkt zu erzeugen
    image_canvas.bind("<Button-3>", assisted_on_confirm) # Rechtsklick um Auswahl zu bestätigen

    root.bind("<Return>", assisted_on_confirm) # Enter zum bestätigen drücken
    root.bind("<Escape>", assisted_on_cancel) # Esc zum Abbrechen drücken

    set_analyze_buttons_state("disabled")

    info_statusmsg.config(text="Assistierter Modus - Linksklick Punkte setzen, Rechtsklick/Enter bestätigen, Escape abbrechen")

    update_preview_base_width()

    frame_with_overlay = draw_assisted_polygon_overlay(
        assisted_base_frame,
        assisted_polygon_points
    )

    set_display_frame(
        frame_with_overlay,
        reset_zoom=True,
        resize_window=True
    )

    info_statusmsg.config(
        text="Status: Assistierter Modus - 0 Punkte gesetzt"
    )

def exit_assisted_polygon_mode():
    global assisted_mode_active

    assisted_mode_active = False

    image_canvas.config(cursor="")
    assist_hint_label.config(text="Mausrad = Zoom | Shift + Linksklick = Pan")

    image_canvas.unbind("<Button-1>")
    image_canvas.unbind("<Button-3>")
    
    root.unbind("<Return>")
    root.unbind("<Escape>")

def exportCADandClose():

    if last_cad_data is None:
        messagebox.showerror(
            "Keine CAD-Daten",
            "Es sind keine CAD-Daten vorhanden. Bitte zuerst Auto- oder Assistierten Modus ausführen."
        )
        return

    try: 
        with open(DATA_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(last_cad_data, f, indent=4)

        print(f"CAD-Daten gespeichert: {DATA_OUTPUT_PATH}")
        close_gui() # Schließt das Fenster
    
    except Exception as e:
        messagebox.showerror(
            "Exportfehler",
            f"CAD-Daten konnten nicht gespeichert werden:\n{e}"
        )

########### Tkinter-Fenster ###########

root = tk.Tk() # Erstellt Hauptfenster
root.title("Plattenerkennung WAAM") # Fenstertitel
root.geometry("900x500") # Fenstergröße
root.minsize(300,200) # Minimale Fenstergröße

# Optional: Fenster-Icon
#if CALIB_ICON_PATH.exists():
    #root.iconbitmap(str(CALIB_ICON_PATH)) # Setzt das Fenstericon, wenn die Datei existiert

# Dark-Mode aktivieren, falls default in Windows
if darkdetect.isDark():
    app_theme = "dark"
else:
    app_theme = "light"
sv_ttk.set_theme(app_theme)

load_pipeline_button_icons(app_theme)

### Layout ###

#### Main-Frame
main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill="both", expand=True) # fill="both" füllt das Fenster vertikal und horizontal, expand=True erlaubt, dass der Frame mitwachsen darf, wenn man die Größe des Fensters verändert
# 2 Reihen: 1. gui_frame 2. CAD-Export 3. image_frame - image_frame wird erst sichtbar, wenn ein Bild angezeigt wird
main_frame.rowconfigure(0, weight=0) # Steuerbereich bekommt weniger Platz
main_frame.rowconfigure(1, weight=0)
main_frame.rowconfigure(2, weight=1) # Steuerbereich bekommt mehr Platz
main_frame.columnconfigure(0, weight=1) # 1 Spalte

### CAD-Import ###
cad_frame = ttk.LabelFrame(main_frame, text="CAD-Import", padding=10)
cad_frame.grid(row=1, column=0, sticky="nsew")

cad_button = ttk.Button(
    cad_frame,
    text="Kontur --> CAD",
    width = 25,
    state="disabled", 
    command=exportCADandClose
)
cad_button.pack()

### GUI-Frame - hier sind alles Einstellungen und Buttons drin
# 2 Reihen, 2 Spalten - in jeden Quadranten kommt ein neuer Frame
gui_frame = ttk.LabelFrame(main_frame, text="Steuerung", padding=10)
gui_frame.grid(row=0, column=0, sticky="nsew")

gui_frame.rowconfigure(0, weight=2)
gui_frame.rowconfigure(1, weight=1)
gui_frame.columnconfigure(0, weight=2)
gui_frame.columnconfigure(1, weight=1)

## Kamerawahl, Kalibrierung etc
camconfig_frame = ttk.Frame(gui_frame, padding=10)
camconfig_frame.configure(relief="solid", borderwidth=1)
camconfig_frame.grid(row=0, column=0, sticky="nsew")

# Kamerawahl
camera_row = ttk.Frame(camconfig_frame)
camera_row.pack(fill="x")
camera_row.columnconfigure(0, weight=1)
camera_row.columnconfigure(1, weight=0)

camera_combo = ttk.Combobox(
    camera_row,
    values = [],
    state="readonly",
    width=35
)
camera_combo.grid(row=0, column=0, sticky="ew")
camera_combo.bind("<<ComboboxSelected>>", on_camera_selected)

camRefreshButton = ttk.Button(
    camera_row,
    text = "⟳",
    width = 3,
    state = "normal",
    command = refresh_camera_list
)
camRefreshButton.grid(row=0, column=1, sticky="e", padx=(5, 0))

# Kamerakalibrierung starten
camCalibButton = ttk.Button(
    camconfig_frame,
    text="Starte Kamerakalibrierung",
    width=25,
    state="disabled",
    command=open_calibration_gui
)
camCalibButton.pack(fill="x", pady=(5, 0))

## Kamerainfos
caminfo_frame = ttk.Frame(gui_frame, padding=10)
caminfo_frame.configure(relief="solid", borderwidth=1)
caminfo_frame.grid(row=0, column=1, sticky="nsew")

labels = ["Max. Auflösung:", "Autofokus:", "Backend:", "Kalibrierdatei:", "Kalibriert am:"]
caminfo_res_val = ttk.Label(caminfo_frame, text="-")
caminfo_af_val = ttk.Label(caminfo_frame, text="-")
caminfo_backend_val = ttk.Label(caminfo_frame, text="-")
caminfo_calib_val = ttk.Label(caminfo_frame, text="-", wraplength=200)
caminfo_calibdate_val = ttk.Label(caminfo_frame, text="-")

vals = [caminfo_res_val, caminfo_af_val, caminfo_backend_val, caminfo_calib_val, caminfo_calibdate_val]

for i, (text, val) in enumerate(zip(labels, vals)):
    ttk.Label(caminfo_frame, text=text).grid(row=i, column=0, sticky="nw", padx=(0, 10))
    val.grid(row=i, column=1, sticky="nw")



## Erkennungsinfos - Infos wie wieviele Spanneisen erkannt wurden, Größe der nutzbaren Schweißfläche
info_frame = ttk.Frame(gui_frame, padding=10)
info_frame.configure(relief="solid", borderwidth=1)
info_frame.grid(row=1, column=0, sticky="nsew")
# Info-Frame
info_plattenerkennung = ttk.Label(info_frame, text="Platte erkannt: -")
info_spanneisen = ttk.Label(info_frame, text="Spanneisen erkannt: -", font=("TkDefaultFont", 11))
info_statusmsg = ttk.Label(
    info_frame, 
    text="Nimm ein Bild auf", 
    padding=10, 
    font=("TkDefaultFont", 11, "bold"), 
    wraplength=500, 
    justify="left", 
    anchor="w"
    )

info_plattenerkennung.pack(anchor="w", fill="x")
info_spanneisen.pack(anchor="w", fill="x")
info_statusmsg.pack(anchor="w", fill="x")


## Buttons
button_frame = ttk.Frame(gui_frame, padding=(20, 10))
button_frame.configure(relief="solid", borderwidth=1)
button_frame.grid(row=1, column=1, sticky="nsew")

button_frame.configure(width=260, height=180)
button_frame.grid_propagate(False)

button_frame.columnconfigure(0, weight=1, uniform="pipeline_buttons")
button_frame.columnconfigure(1, weight=1, uniform="pipeline_buttons")
button_frame.rowconfigure(0, weight=0)
button_frame.rowconfigure(1, weight=1)

capture_button = ttk.Button(
    button_frame,
    text="Bild aufnehmen ⛶",
    state="disabled",
    command=capture_image
)
capture_button.grid(
    row=0, 
    column=0, 
    columnspan=2, 
    sticky="ew", 
    pady=(0, 8)
)

assisted_analyze_button = ttk.Button(
    button_frame,
    text="Assistierter Modus",
    image=assisted_pipeline_icon,
    compound="top",
    state="disabled",
    command=start_assisted_polygon_mode
)
assisted_analyze_button.grid(
    row=1,
    column=0,
    sticky="nsew",
    padx=(0, 5),
    pady=(0, 0)
)

auto_analyze_button = ttk.Button(
    button_frame,
    text="Auto Modus",
    image=auto_pipeline_icon,
    compound="top",
    state="disabled",
    command= lambda: startVisionPipeline("auto")
)
auto_analyze_button.grid(
    row=1,
    column=1,
    sticky="nsew",
    padx=(5, 0),
    pady=(0, 0)
)

### Image-Frame - hier werden Bilder angezeigt

image_frame = ttk.LabelFrame(main_frame, text="Bildvorschau", padding=10)
image_frame.grid(row=2, column=0, sticky="nsew")

assist_hint_label = ttk.Label(
    image_frame,
    text="Mausrad = Zoom | Shift + Linksklick = Pan",
    padding=(5, 3),
    font=("TkDefaultFont", 10, "bold")
)
assist_hint_label.pack(anchor="w", fill="x")

#image_label = ttk.Label(image_frame, text="Kein Bild", anchor="center")
#image_label.pack(fill="both", expand=True)

canvas_container = ttk.Frame(image_frame)
canvas_container.pack(fill="both", expand=True)

image_canvas = tk.Canvas(
    canvas_container,
    background="black",
    highlightthickness=0
)
image_canvas.grid(row=0, column=0, sticky="nsew")

canvas_container.rowconfigure(0, weight=1)
canvas_container.columnconfigure(0, weight=1)

image_canvas.bind("<MouseWheel>", on_canvas_mousewheel)
image_canvas.bind("<ButtonPress-2>", on_canvas_pan_start)
image_canvas.bind("<B2-Motion>", on_canvas_pan_move)
image_canvas.bind("<Shift-ButtonPress-1>", on_canvas_pan_start)
image_canvas.bind("<Shift-B1-Motion>", on_canvas_pan_move)

# DEBUG
#ttk.Label(camconfig_frame, text="camconfig_frame").pack()
#ttk.Label(caminfo_frame, text="caminfo_frame").pack()
#ttk.Label(info_frame, text="info_frame").pack()







##### Start-Logik #####

# Holen der verfügbaren Kameras
refresh_camera_list()


# Markierung unten links im Fenster, fürs Resizen
sizegrip = ttk.Sizegrip(root)
sizegrip.place(relx=1.0, rely=1.0, anchor="se")

root.protocol("WM_DELETE_WINDOW", close_gui) # Schließen des Fensters

root.mainloop() # Startet die Tkinter-Event-Schleife