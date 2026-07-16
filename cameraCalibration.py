import cv2
import numpy as np
from pathlib import Path
import os
import tkinter as tk # GUI-Toolkit
from tkinter import ttk # Moderne Tkinter-Widgets
from PIL import Image, ImageTk # Für die Anzeige von OpenCV-Bildern in Tkinter
import sv_ttk # Dark-Mode Theme für Tkinter
import darkdetect # Erkennt ob Windows im Dark Mode ist
from datetime import datetime # Funktionen für den Timestamp


### Globale Variablen ###

# Debug Kamera-Info-Dict:
#camera_info = {
    #"camera_id": 1,
    #"camera_name": "EMEET SmartCam Nova 4k",
    #"display_text": "0 - EMEET SmartCam Nova 4k",
    #"resolution_width": 3840,
    #"resolution_height": 2160,
#}

# Globale Variablen - Kamerabild
calib_cap = None
calib_cam_id = None
calib_cam_name = ""
calib_cam_displaytext = ""
calib_cam_res_width = 0
calib_cam_res_height = 0

camera_info = None

latest_raw_frame = None # Variable in die immer der aktuellste unskalierte Frame aus dem Livefeed gespeichert wird

ARUCO_DICT_NAMES = {
    getattr(cv2.aruco, attr): attr
    for attr in dir(cv2.aruco)
    if attr.startswith("DICT_")
}

# Globale Variablen - Kamerakalibierung
CHARUCO_SQUARES_X = 9
CHARUCO_SQUARES_Y = 6
CHARUCO_SQUARE_LENGTH = 0.015 # in Meter oder relativ - WICHTIG IST: Das Verhältnis zwischen Marker-Länge und Rechteck-Länge des Schachbrettmusters, kann also auch z.b 0.75 sein (was 75% der Länge des Rechtecks entsprechen würde)
CHARUCO_MARKER_LENGTH = 0.011
CHARUCO_DICT_ID = cv2.aruco.DICT_4X4_50
CHARUCO_DICT = cv2.aruco.getPredefinedDictionary(CHARUCO_DICT_ID)
CHARUCO_DICT_NAME = ARUCO_DICT_NAMES.get(CHARUCO_DICT_ID)
CHARUCO_BOARD = cv2.aruco.CharucoBoard(
    (CHARUCO_SQUARES_X, CHARUCO_SQUARES_Y),
    CHARUCO_SQUARE_LENGTH,
    CHARUCO_MARKER_LENGTH,
    CHARUCO_DICT
)

patternDisplaytext = f"{CHARUCO_SQUARES_X}x{CHARUCO_SQUARES_Y} ChArUco Board ({CHARUCO_DICT_NAME})"

# Capture der Kalibrierbilder
calibration_images = [] # Liste zum Speichern der aufgenommenen Kalibrierungsbilder
calibration_capture_active = False

CALIBRATION_FILE_PATH = ""
CALIBRATION_TARGET_COUNT = 20

# Globale Variablen - Tkinter
CALIB_ICON_PATH = Path("calibration_icon.ico")  # Pfad zum Icon für das Tkinter-Fenster

# Globale Variablen - Tkinter Widgets
root = None
video_frame = None
video_label = None
active_camera_label2 = None
active_resolution_label2 = None
livefeed_resolution_label2 = None
capture_image_button = None
save_calibration_button = None
calibration_status_label = None
calibration_info_label = None
info_reproj_label = None
info_quality_label = None
file_path_label = None


#### HILFSFUNKTIONEN ####

def get_calibration_file_path():
    return os.path.abspath(CALIBRATION_FILE_PATH)

def generate_calibration_file_path():
    # Dateiname wird anhand des Kameranamens, Auflösung und Datum erstellt
    global CALIBRATION_FILE_PATH

    safe_name = calib_cam_name.replace(" ", "_") # Wandelt die Leerzeichen im Kameranamen in Unterstriche um
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ("_", "-")) # Durchläuft jeden Buchstaben im String und löscht alle Zeichen die nicht alphanumerisch sind

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # Erstellt den Timestamp mit der aktuellen Zeit
    # Zusammengesetzer Dateiname:
    CALIBRATION_FILE_PATH = f"{safe_name}_{calib_cam_res_width}x{calib_cam_res_height}p_{timestamp}.npz" # Z.B. EMEET_SmartCam_Nova_4k_3840x2160p_20260605222652.npz

def cleanup_tmp_calibration():
    tmp_path = Path(get_calibration_file_path() + ".tmp.npz")
    if tmp_path.exists():
        tmp_path.unlink()
        print(f"Temporäre Kalibrierungsdatei gelöscht: {tmp_path}")


#### KAMERA - HARDWARE ####

def create_capture(camera_id):
    # Öffnet die Kamera mit dem besten verfügbaren Backend
    backends_to_try = [
        ("DSHOW", cv2.CAP_DSHOW), # Windows DirectShow
        ("MSMF", cv2.CAP_MSMF), # Windows Media Foundation
    ]

    # Versuch die Kamera mit den verschiedenen Backends zu öffnen
    for backend_name, backend_flag in backends_to_try:
        capture = cv2.VideoCapture(camera_id, backend_flag)

        if capture is not None and capture.isOpened():
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Setzt die Puffergröße auf 1, um die Latenz zu minimieren
            print(f"Kamera {camera_id} mit Backend {backend_name} erfolgreich geöffnet.")
            return capture, backend_name

        if capture is not None:
            capture.release() # Gibt die Kamera frei, falls sie geöffnet wurde, aber nicht funktioniert hat
    
    return None, None # Falls alle Backends fehlschlagen, gibt None zurück



#### KAMERA - LIVEFEED ####

def start_livefeed(camera_id):
    global calib_cap, calib_cam_id, calib_cam_name, calib_cam_displaytext, calib_cam_res_width, calib_cam_res_height

    if calib_cap is not None:
        calib_cap.release() # Gibt die Kamera frei, falls sie bereits geöffnet ist

    new_cap, backend_used = create_capture(camera_id)

    if new_cap is None:
        print(f"Kamera {calib_cam_displaytext} konnte nicht geöffnet werden.\nSchließen die Anwendung und wählen eine andere Kamera aus.")
        return

    calib_cap = new_cap

    # Wenn die Cam-Info gültige Auflösungswerte enthält, wird die KAmera mit diesen geöffnet
    if calib_cam_res_width > 0 and calib_cam_res_height > 0:
        calib_cap.set(cv2.CAP_PROP_FRAME_WIDTH, calib_cam_res_width)
        calib_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, calib_cam_res_height)

    # Lese aktuelle Kamera-Auflösung und FPS aus
    px_width = int(calib_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    px_height = int(calib_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fps = calib_cap.get(cv2.CAP_PROP_FPS)
    fps_str = f"{fps:.1f}" if fps > 0 else "..." # Zeigt "..." an, wenn der Treiber die FPS nicht auslesen kann
    resolution_info = f"{px_width}x{px_height}p @ {fps_str} FPS"

    active_camera_label2.config(text=calib_cam_displaytext) # Aktualisiert die Anzeige der aktiven Kamera im GUI
    active_resolution_label2.config(text=resolution_info) # Aktualisiert die Anzeige der Auflösung im GUI
    
    
    
    print(f"Kamera {calib_cam_displaytext} (ID: {calib_cam_id}) erfolgreich geöffnet.")
    print(f"{resolution_info} (Backend: {backend_used})")

    root.after(30, update_frame)

    return True

def update_frame():
    global calib_cap, latest_raw_frame

    # Kopie des Frames erstellen
    if calib_cap is not None and calib_cap.isOpened():
        ret, frame = calib_cap.read()

        if ret and frame is not None:
            latest_raw_frame = frame.copy() # Speichert den voll aufgelösten Frame für die Kalibrierungsaufnahme
            
            # Skalierung des Bildes auf die Größe des Video-Labels im GUI
            container_width = video_frame.winfo_width() - 24 # Holt aktuelle Breite des Fensters - 24px
            container_height = video_frame.winfo_height() - 24 # Holt aktuelle Höhe des Fensters - 24px

            # Guard: Nur verabeiten wenn der Container bereits gerendet ist
            if container_width > 1 and container_height > 1:
                
                # Seitenverhältnis des Originalbildes beibehalten
                frame_ratio = frame.shape[1] / frame.shape[0] # width/height
                container_ratio = container_width / container_height

                # Proportionale Skalierung basierend auf dem Seitenverhältnis
                if frame_ratio > container_ratio:
                    # Wenn das Label breiter ist als das Bild, skaliere basierend auf der Breite
                    new_width = container_width
                    new_height = int(container_width / frame_ratio)
                else:
                    # Wenn das Label höher ist als das Bild, skaliere basierend auf der Höhe
                    new_height = container_height
                    new_width = int(container_height * frame_ratio)

                if new_width > 0 and new_height > 0:
                    # Schnelleres Downscaling in cv2 statt PIL
                    frame = cv2.resize(
                        frame,
                        (new_width, new_height),
                        interpolation=cv2.INTER_LINEAR
                    )
                
                # Frame für Tkinter umwandeln
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # OpenCV verwendet BGR, Tkinter erwartet RGB
                image = Image.fromarray(frame_rgb) # Konvertiert das NumPy-Array in ein PIL-Image

                photo = ImageTk.PhotoImage(image) # Konvertiert das PIL-Image in ein ImageTk-PhotoImage für die Anzeige in Tkinter
                video_label.config(image=photo, text="") # Aktualisiert das Label mit dem neuen Bild
                video_label.image = photo

            root.after(16, update_frame) # Aktualisiert das Bild alle 16ms (ca. 60 FPS)

            

#### KALIBRIERUNG - AUFNAHME ####

def start_calibration_capture():
    # Startet die Kalibrieraufnahme oder startet diese neu
    global calibration_images, calibration_capture_active

    # Update des UIs - cleared alle Infos von alten Kalibrieraufnahmen
    save_calibration_button.config(state="disabled")
    info_reproj_label.config(text="")
    info_quality_label.config(text="")
    file_path_label.config(text="")

    cleanup_tmp_calibration() # Löscht alte temporäre Kalibrierdateien
    calibration_images = []
    calibration_capture_active = True
    generate_calibration_file_path()
    update_calibration_ui()

    return

def capture_calibration_image():
    # Funktion speichert den aktuellen Rohframe in eine Liste
    global calibration_images, latest_raw_frame, calib_cap, calibration_capture_active

    if latest_raw_frame is None:
        return
    
    if not calibration_capture_active:
        return
    
    if len(calibration_images) >= CALIBRATION_TARGET_COUNT:
        return

    if calib_cap is not None and calib_cap.isOpened():
        calibration_images.append(latest_raw_frame.copy())
        image_count = len(calibration_images)

        update_calibration_ui()

        if image_count == CALIBRATION_TARGET_COUNT:
            calibration_capture_active = False
            
            # UI aktualisieren um 20/20 anzuzeigen, bevor Kalibrierung startet
            update_calibration_ui()

            calibration_success, reproj_error, quality, success_msg = intrinsic_calibration(calibration_images)

            ## Status Angaben

            if calibration_success == False:
                file_path_label.config(
                    text=f"Kalibrierung fehlgeschlagen:\n{success_msg}",
                    foreground="red",
                    font=("TkDefaultFont", 11, "bold")
                )
                info_reproj_label.config(text="")
                info_quality_label.config(text="")
            else:
                file_path_label.config(
                    text=success_msg,
                    foreground="orange",
                    font=("TkDefaultFont", 11, "bold")
                )
                info_reproj_label.config(
                    text=(
                        f"Reprojektionsfehler: {reproj_error:.4f} Pixel"
                    )
                )
                info_quality_label.config(
                    text=quality
                )
                save_calibration_button.config(state="normal")

        # UI nochmal aktualisieren nach der Kalibrierung
        update_calibration_ui()
    else:
        print("Camera Feed not active")


#### KALIBRIERUNG - VERARBEITUNG ####

## Intrinsic calibration. Gibt True bei erfolgreicher Kalibrierung zurück, False bei Fehlern (z.B. zu wenig Bilder)
# Mit Hilfe eines externen Hilfsmittels entworfen, anschließend fachlich geprüft und angepasst.
def intrinsic_calibration(calibration_images):

    # calibrateCameraCharuco() benötigt statt 2D und 3D Punkte, nur die Charuco-Ecken und IDs
    all_charuco_corners = []
    all_charuco_ids = []
    img_size = None # Bildgröße wird ebenfalls für calibrateCameraCharuco() benötigt

    # Prüft zunächst ob genügen / überhaupt Bilder für die Kalibrierung vorhanden sind
    if not calibration_images or len(calibration_images) < CALIBRATION_TARGET_COUNT:
        success_msg = f"Mindestens {CALIBRATION_TARGET_COUNT} Bilder für Kalibrierung erforderlich"
        print(success_msg)
        return False, None, None, success_msg
    
    # calibrateCameraCharuco() berechnet die 3D Punkte und verfeinert die Subpixel (cornerSubPix) direkt intern
    # Erkannte Ecken sind daher direkt schon subpixelgenau
    
    ### Durchläuft alle Bilder um die Ecken zu finden und die 2D- und 3D-Punkte für die Kalibrierung für jedes Bild zu sammeln
    total_images = len(calibration_images)
    for idx, image in enumerate(calibration_images):
        if isinstance(image, str):
            img = cv2.imread(image)
        elif isinstance(image, np.ndarray):
            img = image.copy()
        else:
            print(f"Unbekannter Bildtyp: {type(image)}")
            continue

        if img is None:
            print("Bild konnte nicht geladen werden, überspringe")
            continue

        imgHeight, imgWidth = img.shape[:2] # holt die Bildgröße in px
        img_size = (imgWidth, imgHeight) # Bildgröße wird als Tupel benötigt

        ### Erkennung der ChArUco Features ###
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # konvertiert das Bild in Graustufen für bessere Erkennung der Ecken
        
        # 1. ArUco-Marker im Bild suchen
        detector = cv2.aruco.ArucoDetector(CHARUCO_DICT)
        marker_corners, marker_ids, _ = detector.detectMarkers(gray)

        # Falls weniger als 4 Marker im Bild erkannt werden, wird dieses Bild übersprungen
        if marker_ids is None or len(marker_ids) < 4:
            print(f"Bild {idx+1}: Zu wenig Marker erkannt ({0 if marker_ids is None else len(marker_ids)}), überspringe")
            continue

        # 2. ChArUco-Ecken aus den Markern interpolieren
        ret, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
            marker_corners, 
            marker_ids,
            gray,
            CHARUCO_BOARD
        )

        # Falls weniger als 4 Ecken gefunden wurden, wird dieses Bild übersprungen
        if ret < 4:
            print(f"Bild {idx+1}: Nur {ret} Ecken gefunden, überspringe")
            continue

        all_charuco_corners.append(charuco_corners)
        all_charuco_ids.append(charuco_ids)
        print(f"Bild {idx+1}/{total_images}: {ret} ChArUco-Ecken erkannt")


    valid_images = len(all_charuco_corners)
    total_images = len(calibration_images)
    not_used = total_images - valid_images
    print(f"Gefundene valide Kalibrierungsbilder: {valid_images} / {total_images}")
    print(f"Nicht genutzte Bilder: {not_used}")

    # Checkt ob genügend Bilder mit gefundenen Ecken für die Kalibrierung vorhanden sind, mindestens 5 Bilder werden empfohlen, da calibrateCamera mindestens 5 Bilder benötigt, um eine zuverlässige Kalibrierung durchzuführen
    if valid_images < 10:
        print(f"Zu wenig zusammengeführte Bilder für Kalibrierung: objectPoints={valid_images}, imagePoints={len(all_charuco_corners)}")
        return False, None, None, "Mindestens 10 Bilder mit erkannten Ecken erforderlich"

    if valid_images < 15:
        print("Warnung: Weniger als 15 verwertbare ChArUco-Bilder - Kalibrierungsqualität könnte schlechter sein.")

    ######## KALIBRIERUNG ########
    ret, cameraMatrix, distCoeffs, rvecs, tvecs, stdDeviationsIntrinsics, stdDeviationsExtrinsics, perViewErrors = cv2.aruco.calibrateCameraCharucoExtended(
        all_charuco_corners, 
        all_charuco_ids, 
        CHARUCO_BOARD, 
        img_size, 
        None, None
    )

    # ret ist bereits der RMS Reprojektionsfehler von cv2.calibrateCamera
    mean_reprojection_error = ret

    # perViewErrors auswerten
    per_view_mean = np.mean(perViewErrors)
    per_view_std = np.std(perViewErrors)
    worst_idx = int(np.argmax(perViewErrors.flatten())) # Index des schlechtesten Bildes
    worst_error = float(perViewErrors[worst_idx][0]) # Fehlerwert des schlechtesten Bildes
    bad_images = [i + 1 for i, e in enumerate(perViewErrors.flatten())
                  if e > per_view_mean + per_view_std] # Speichert die Bildnummern mit allen schlechten Bildern unterm Schwellwert (=außerhalb der Standardabweichung in der Normalverteilung)

    print(f"Schlechtestes Bild: Bild {worst_idx + 1} ({worst_error:.4f} Pixel)")
    if bad_images:
        print(f"Auffällige Bilder (>{per_view_mean:.3f} + {per_view_std:.3f}): {bad_images}")



    # Ausgabe der Kalibrierungsergebnisse
    print("Kalibrierungsergebnis:", ret)
    if not ret:
        print("Kalibrierung fehlgeschlagen.")
        return False, None, None, "Kalibrierung fehlgeschlagen."
    print("Kameramatrix:\n", cameraMatrix)
    print("Verzerrungskoeffizienten:\n", distCoeffs)
    print("Rotationsvektoren:\n", rvecs)
    print("Translationsvektoren:\n", tvecs)
    print(f"Mittlerer Reprojektionsfehler: {mean_reprojection_error:.4f} Pixel")
    
    # Bewertung der Kalibrierungsqualität
    if mean_reprojection_error < 0.1:
        quality_msg = "Ausgezeichnet (Reprojektionsfehler < 0.1 Pixel)"
    elif mean_reprojection_error < 0.5:
        quality_msg = "Sehr gut (Reprojektionsfehler < 0.5 Pixel)"
    elif mean_reprojection_error < 1.0:
        quality_msg = "Gut (Reprojektionsfehler < 1.0 Pixel)"
    elif mean_reprojection_error < 2.0:
        quality_msg = "Akzeptabel (Reprojektionsfehler < 2.0 Pixel)"
    else:
        quality_msg = "Schlecht (Reprojektionsfehler >= 2.0 Pixel) - Kalibrierung erneut durchführen"
    
    print(f"Kalibrierungsqualität: {quality_msg}")

    ## Kalibrierungsergebnisse in Datei speichern
    file_path = get_calibration_file_path() + ".tmp.npz"
    if Path(file_path).exists():
        print(f"Überschreibe vorhandene Kalibrierungsdatei: {file_path}")

    np.savez_compressed(
        file_path, 
        camera_matrix=cameraMatrix, 
        dist_coeffs=distCoeffs, 
        rvecs=rvecs, 
        tvecs=tvecs,
        camera_info=np.array([calib_cam_displaytext if calib_cam_displaytext else "unknown"], dtype='U50'),
        reprojection_error=np.array([mean_reprojection_error], dtype=np.float32),
        calibration_quality=np.array([quality_msg], dtype='U100'),
        calibration_images_used=np.array([valid_images], dtype=np.int32),
        calibration_images_total=np.array([total_images], dtype=np.int32),
        per_view_errors=perViewErrors.flatten(),
        resolution=np.array([f"{calib_cam_res_width}x{calib_cam_res_height}"], dtype='U20'),
        timestamp=np.array([datetime.now().strftime("%Y-%m-%d %H:%M:%S")], dtype='U20')
    )

    bad_str = f", auffällige Bilder: {bad_images}" if bad_images else ""
    success_msg = (
        f"Kalibrierung abgeschlossen - bitte Ergebnisse prüfen und speichern. \n"
        f"Schlechtestes Bild: Nr. {worst_idx + 1} ({worst_error:.4f} Pixel) {bad_str}"
    )

    print(f"{success_msg}\nReprojektionsfehler: {mean_reprojection_error:.4f} Pixel\nKalibrierungsqualität: {quality_msg}")
    return True, mean_reprojection_error, quality_msg, success_msg 

def save_npz():

    temp_path = get_calibration_file_path() + ".tmp.npz"
    final_path = get_calibration_file_path()

    if not Path(temp_path).exists():
        file_path_label.config(
            text=("Keine temporären Kalibrierungsdaten zum Speichern vorhanden."),
            foreground="red"
        )
        return
    
    Path(temp_path).rename(final_path) # Umbenennen der temporären Datei zum finalen Pfad

    save_calibration_button.config(state="disabled")
    file_path_label.config(
        text=f"Gespeichert unter:\n{final_path}",
        foreground="green"
    )
    print(f"Kalibrierdatei final gespeichert: {final_path}")

#### GUI - UPDATES ####

def update_calibration_ui():
    # Aktualisiert die Statuszeilen, nach jeden aufgenommenen Frame
    image_count = len(calibration_images)

    # Status-Label
    if calibration_capture_active:
        if image_count < CALIBRATION_TARGET_COUNT:
            # Kalibrier Status Update
            calibration_status_label.config(
                text=(
                    f"Kalibrierbilder: {image_count}/{CALIBRATION_TARGET_COUNT}"
                )
            )
            # Kalibrier Info Update
            calibration_info_label.config(
                text=(
                    "Kalibriermuster neu positionieren und ein neues Bild erfassen"
                )
            )
            # Button Update
            capture_image_button.config(state="normal") # Aktiviert den Capture-Button
        else:
            # Wenn genügend Bilder gemacht wurden
            calibration_status_label.config(
                text=(
                    f"Kalibrierbilder vollständig: {image_count}/{CALIBRATION_TARGET_COUNT}"
                )
            )
            calibration_info_label.config(
                text=(
                    "Alle Kalibrierbilder aufgenommen! Starten Sie jetzt die Kalibrierung"
                )
            )
            capture_image_button.config(state="disabled") # Deaktiviert Caputure-Button da Bilder vollständig
    else:
        if image_count == 0:
            calibration_status_label.config(
                text=(
                    "Noch keine Kalibrieraufnahme aktiv" 
                )
            )
            calibration_info_label.config(
                text=(
                    "Kalibriermuster ins Kamerasichtfeld platzieren"
                )
            )
        else:
            calibration_info_label.config(
                text=(
                    f"Kalibrierbilder gespeichert: {image_count}/{CALIBRATION_TARGET_COUNT}"
                )
            )
        # Deaktivieren des Buttons, nachdem Capture deaktiviert ist
        capture_image_button.config(state="disabled")
        

#### GUI - FENSTER ####

# Funktion zum sauberen Schließen der Anwendung
def on_close():
    
    global calib_cap, calibration_images

    if calib_cap is not None:
        calib_cap.release()
        calib_cap = None

    if root:
        root.destroy()

def on_abort():
    cleanup_tmp_calibration()
    on_close()

# Startfunktion - wird von mainGUI.py aus gestartet
def start_calibration_gui(cam_info=None, return_theme="light"):
    global root, calib_cam_id, calib_cam_name, calib_cam_displaytext, calibration_images, calib_cam_res_width, calib_cam_res_height, CALIBRATION_FILE_PATH

    # Tkinter Widget-Variablen
    global root, video_frame, video_label
    global active_camera_label2, active_resolution_label2, livefeed_resolution_label2
    global capture_image_button, save_calibration_button
    global calibration_status_label, calibration_info_label
    global info_reproj_label, info_quality_label, file_path_label

    if cam_info is not None:
        calib_cam_id = cam_info.get("camera_id", None)
        calib_cam_name = cam_info.get("camera_name", "")
        calib_cam_displaytext = cam_info.get("display_text", "")
        calib_cam_res_width = cam_info.get("resolution_width", 0)
        calib_cam_res_height = cam_info.get("resolution_height", 0)
        # Aktualisieren des Dateinamen
        CALIBRATION_FILE_PATH = f"{calib_cam_name}_{calib_cam_res_width}x{calib_cam_res_height}p_.npz"
    
    calibration_images = [] # Initialisiert die Liste der Kalibrierungsbilder

    ## Tkinter-Initialisierung
    # Schließen des Fensters

    # Check ob das Skript standalone gestartet wird oder von einem anderen skript gestartet wurde
    if tk._default_root is None:
        root = tk.Tk() # Standalone-Start
        standalone = True
    else:
        root = tk.Toplevel() # Aufruf aus MainGui
        standalone = False


    #root = tk.Tk() # Erstellt Hauptfenster, als eigenständiges Fenster
    root.title("Kamerakalibrierung") # Fenstertitel
    root.geometry("1000x900") # Fenstergröße
    root.minsize(850,300) # Minimale Fenstergröße

    # Optional: Fenster-Icon
    #if CALIB_ICON_PATH.exists():
        #root.iconbitmap(str(CALIB_ICON_PATH)) # Setzt das Fenstericon, wenn die Datei existiert

    # Dark-Mode aktivieren, falls default in Windows
    if darkdetect.isDark():
        sv_ttk.set_theme("dark")
    else:
        sv_ttk.set_theme("light")

    ########### Tkinter-Fenster ###########

    ### Layout ###

    # Main-Frame
    main_frame = ttk.Frame(root, padding=10)
    main_frame.pack(fill="both", expand=True) # fill="both" füllt das Fenster vertikal und horizontal, expand=True erlaubt, dass der Frame mitwachsen darf, wenn man die Größe des Fensters verändert
    # 2 Reihen: 1. Livefeed, 2. Steuerbereich
    main_frame.rowconfigure(0, weight=1) # Livefeed bekommt mehr Platz
    main_frame.rowconfigure(1, weight=0) # Steuerbereich bekommt weniger Platz
    main_frame.columnconfigure(0, weight=1) # Eine Spalte, die den gesamten Platz einnimmt

    ## Livefeed-Frame
    video_frame = ttk.LabelFrame(main_frame, text="Live-Feed", padding=10)
    video_frame.grid(row=0, column=0, sticky="nsew")
    video_label = ttk.Label(
        video_frame,
        text= "Live-Feed",
        anchor="center"
    )
    video_label.pack(fill="both", expand=True)

    style = ttk.Style()
    style.configure("Centered.TButton", anchor="center", justify="center") # Zentriert den Text in den Buttons

    ### Steuerbereich ###
    control_frame = ttk.Frame(main_frame, padding=10, height=300)
    control_frame.grid(row=1, column=0, sticky="ew")
    # Spaltenbereich definieren
    control_frame.columnconfigure(0, weight=1) # Statusbereich
    control_frame.columnconfigure(1, weight=0) # Buttonbereich

    ## Statusbereich ##
    status_frame = ttk.LabelFrame(control_frame,text="Status", padding=5)
    status_frame.grid(row=0, column=0, sticky="nsew")

    # Aktive Kamera
    active_camera_label = ttk.Label(status_frame, text=f"Aktive Kamera:")
    active_camera_label2 = ttk.Label(status_frame, text=f"...")
    active_camera_label.grid(row=0, column=0, sticky="w")
    active_camera_label2.grid(row=0, column=1, sticky="e", padx=(50, 0)) # Fügt links einen kleinen Abstand hinzu, damit der Text nicht direkt am Rand klebt

    # Aktive Auflösung
    active_resolution_label = ttk.Label(status_frame, text=f"Aktive Auflösung:")
    active_resolution_label2 = ttk.Label(status_frame, text=f"...")
    active_resolution_label.grid(row=1, column=0, sticky="w")
    active_resolution_label2.grid(row=1, column=1, sticky="e", padx=(50, 0))

    # Livefeed Auflösung
    livefeed_resolution_label = ttk.Label(status_frame, text=f"Livefeed Auflösung:")
    livefeed_resolution_label2 = ttk.Label(status_frame, text=f"...")
    livefeed_resolution_label.grid(row=2, column=0, sticky="w")
    livefeed_resolution_label2.grid(row=2, column=1, sticky="e", padx=(50, 0))

    # Kalibriermuster
    calib_pattern_label = ttk.Label(status_frame, text=f"Aktives Kalibriermuster:")
    calib_pattern_label2 = ttk.Label(status_frame, text=f"{patternDisplaytext}")
    calib_pattern_label.grid(row=3, column=0, sticky="w")
    calib_pattern_label2.grid(row=3, column=1, sticky="e", padx=(50, 0))



    # Info Label
    info_reproj_label = ttk.Label(status_frame, text=f"", font=("TkDefaultFont", 11, "bold"))
    info_quality_label = ttk.Label(status_frame, text=f"", font=("TkDefaultFont", 11, "bold"))
    info_reproj_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(25, 0))
    info_quality_label.grid(row=5, column=0, columnspan=2, sticky="w")

    # Speicherort Label
    file_path_label = ttk.Label(status_frame, text=f"", font=("TkDefaultFont", 11, "bold"), foreground="green")
    file_path_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))



    ## Button Bereich ##
    button_frame = ttk.LabelFrame(control_frame, text="Aktionen", padding=5)
    button_frame.grid(row=0, column=1, sticky="e")

    # Capture Button
    start_capture_button = ttk.Button(
        button_frame,
        text="Kalibrierung starten / neu starten [R]",
        command=start_calibration_capture
    )
    start_capture_button.pack(fill="x", pady=(0, 5))

    # Aktuelles Bild erfassen Button
    capture_image_button = ttk.Button(
        button_frame,
        text="Aktuelles Bild erfassen [Leertaste]",
        command=capture_calibration_image,
        state="disabled"
    )
    capture_image_button.pack(fill="x", pady=(0, 5))

    # Info Message
    calibration_status_label = ttk.Label(button_frame, text="Noch keine Kalibrierungsaufnahme aktiv.")
    calibration_status_label.pack(fill="x", pady=(0, 5))

    # Status Message
    calibration_info_label = ttk.Label(button_frame, text="Kalibriermuster ins Kamerafeld positionieren")
    calibration_info_label.pack(fill="x", pady=(0, 5))

    # Button Container
    button_container = ttk.Frame(button_frame)
    button_container.pack(fill="x", pady=(0, 5))
    button_container.columnconfigure(0, weight=0)
    button_container.columnconfigure(1, weight=0)

    style.configure("Save.TButton", 
                    anchor="center", 
                    justify="center",
                    foreground="green",
                    padding=(0, 5),
                    font=("TkDefaultFont", 11, "bold")
                ) # Macht Text im Button grün

    # Speicher Button
    save_calibration_button = ttk.Button(
        button_container,
        text="Kalibrierungsergebnisse\nspeichern",
        style="Save.TButton",
        width=25,
        state="disabled",
        command=save_npz
    )
    save_calibration_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

    style.configure("Abort.TButton",
                    anchor="center",
                    justify="center", 
                    foreground="red",
                    padding=(0, 11),
                    font=("TkDefaultFont", 11, "bold")
                ) # Macht Text im Button rot

    # Abbruch-Button / Zurück
    abort_button = ttk.Button(
        button_container,
        text="Abbrechen / Zurück",
        style="Abort.TButton",
        width=25,
        command=on_abort
    )
    abort_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))


    # Markierung unten links im Fenster, fürs Resizen
    sizegrip = ttk.Sizegrip(root)
    sizegrip.place(relx=1.0, rely=1.0, anchor="se")

    ## Tkinter Tastenkürzel ##

    root.protocol("WM_DELETE_WINDOW", on_close)

    # R drücken um die Kalibrieraufnahme zu starten
    root.bind("<r>", lambda e: start_calibration_capture())
    # Leertaste drücken um Bild aufzunehmen
    root.bind("<space>", lambda e: capture_calibration_image())

    root.after(100, lambda: start_livefeed(calib_cam_id)) # Startet den Livefeed nach 100ms, um sicherzustellen, dass das GUI bereits initialisiert ist 
    
    if standalone:
        root.mainloop() # Startet die Tkinter-Event-Schleife
        sv_ttk.set_theme(return_theme)


if __name__ == "__main__":
    # Debug Kamera-Info-Dict:
    camera_info = {
        "camera_id": 1,
        "camera_name": "Debugkamera",
        "display_text": "1 - Debugkamera",
        "resolution_width": 3840,
        "resolution_height": 2160,
    }
    start_calibration_gui(camera_info)