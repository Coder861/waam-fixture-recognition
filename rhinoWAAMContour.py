import subprocess
import json
import os
import System
import math # NumPy funktioniert in Rhino nicht
import rhinoscriptsyntax as rs
import Eto.Forms as Forms
import Eto.Drawing as Drawing

# Rhino Makro-Befehl:
# ! -_ScriptEditor _Run "<PFAD\ZUM\ROOT\ORDNER>\rhinoWAAMContour.py"

# Skriptname: rhinoWAAMContour.py

# Speicherorte der externen Skripte (relative Pfade):
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
EXTERNAL_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "mainGUI.py")
DATA_DIR = os.path.join(SCRIPT_DIR, "data.json")

# Manuelle Skriptpfade (absolute Pfade)
# PYTHON_DIR = r"<PFAD\ZUM\ROOT\ORDNER>\.venv\Scripts\python.exe"
# EXTERNAL_SCRIPT_DIR = r"<PFAD\ZUM\ROOT\ORDNER>\mainGUI.py"
# DATA_DIR = r"<PFAD\ZUM\ROOT\ORDNER>\data.json"
# SCRIPT_DIR = r"<PFAD\ZUM\ROOT\ORDNER>" # Z.B. r"C:\Users\User\WAAM\Skript-Plattenerkennung"

external_process = None
show_ref_img = True # False eingeben, wenn kein Foto importiert werden soll

LOCK_SIM_GEOMETRY = False
LOCK_REFERENCE_IMAGE = True 

MW_LAYER_STOCK = "MW Stock"
MW_LAYER_WORKPIECE = "MW Workpiece"
MW_LAYER_FIXTURE = "MW Fixture"
WAAM_LAYER_REFERENCE = "WAAM Reference"

### LOOKUP-Tabelle für Spanneisen ###

ARUCO_MARKER_WIDTH_MM = 30.0 # Breite der ArUco Marker auf den Spanneisen (nicht den weißen Rand mit messen!)
CLAMP_EXTRUSION_HEIGHT_MM = 20.0

# Koordinaten sind marker-normalisiert.
# (0,0) = Marker-Ecke 0, (1,1) = gegenüberliegende Marker-Ecke.
POLY_SPANNEISEN_14x100_NORM = [
    [-5/30, 35/30], # Ecke unten links
    [-5/30, -42/30], # Ecke oben links 
    [0.25, -65/30], # Ecke ganz oben links
    [0.75, -65/30], # Ecke ganz oben rechts
    [35/30, -42/30], # Ecke oben rechts
    [35/30, 35/30] # Ecke unten rechts
]
POLY_SPANNEISEN_14x125_NORM = [
    [-5/30, 35/30],
    [-5/30, -2.3],
    [0.25, -3],
    [0.75, -3],
    [35/30, -2.3],
    [35/30, 35/30]
]
POLY_SPANNEISEN_14x160_NORM = [
    [-5/30, 35/30],
    [-5/30, -103/30],
    [0.25, -125/30],
    [0.75, -125/30],
    [35/30, -103/30],
    [35/30, 35/30]
]

# Wandelt normierte Spanneisen Koordinaten in lokale mm-Koordinaten um (im ArUco-KS)
# 1 normierte Einheit entspricht der ArUco-Breite
# (0, 0) liegt an Marker-Ecke 0
# (1, 1) liegt an der gegenüberliegenden Marker-Ecke
# Funktion transformiert die normierten Koordinaten zu echten Koordinaten, bezogen auf die Marker-Mitte statt die Marker-Ecke
def marker_norm_to_centered_mm(poly_norm, marker_width_mm=ARUCO_MARKER_WIDTH_MM):
    contour_mm = [] # Hier wird das fertige Polygon gespeichert

    for u_norm, v_norm in poly_norm:
        x_mm = (float(u_norm) - 0.5) * marker_width_mm # -0.5 verschiebt alle Koordinaten zur Marker-Mitte hin
        y_mm = (float(v_norm) - 0.5) * marker_width_mm
        contour_mm.append([x_mm, y_mm])

    return contour_mm

# Speichert für jeweilige ArUco-IDs die normierten Konturen und gibt ggf. einen Offset an falls ein Marker falsch gedreht drauf geklebt wurde
def make_clamp_definition(name, poly_norm, angle_offset_deg=0.0):
    return {
        "name": name,
        "angle_offset_deg": float(angle_offset_deg),
        "contour_mm": marker_norm_to_centered_mm(poly_norm)
    }

CLAMP_CONTOURS = {
    60: make_clamp_definition("Spanneisen_14x100", POLY_SPANNEISEN_14x100_NORM, 180.0),
    61: make_clamp_definition("Spanneisen_14x125", POLY_SPANNEISEN_14x125_NORM, 180.0),
    62: make_clamp_definition("Spanneisen_14x160", POLY_SPANNEISEN_14x160_NORM, 180.0),
}

# DEFAULT_CLAMP_CONTOUR = make_clamp_definition("Spanneisen_default", POLY_SPANNEISEN_14x125_NORM)

def start_process(form, status_label):
    global external_process

    status_label.Text = "Starte visuelle Erkennung..."

    # Alte Ergebnisdatei überschreiben
    if os.path.exists(DATA_DIR):
        os.remove(DATA_DIR)

    # Start des externen GUI
    if os.path.exists(EXTERNAL_SCRIPT_DIR):
        #external_process = subprocess.Popen([PYTHON_DIR, EXTERNAL_SCRIPT_DIR])

    # Verhindert, dass Rhino CPython-Umgebung die externe venv beeinflusst
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONUSERBASE", None)
        env["PYTHONNOUSERSITE"] = "1"

        external_process = subprocess.Popen(
            [PYTHON_DIR, "-E", EXTERNAL_SCRIPT_DIR],
            cwd=SCRIPT_DIR,
            env=env
        )

        poll_timer = Forms.UITimer()
        poll_timer.Interval = 0.5

        def on_poll(sender, e):
            check_external_gui(form, status_label, poll_timer)

        poll_timer.Elapsed += on_poll
        poll_timer.Start()
    else:
        status_label.Text = "Externes Skript nicht gefunden. Beende Prozess"
        error_timer = Forms.UITimer()
        error_timer.Interval = 3

        def close_after_error(sender, e):
            error_timer.Stop()
            form.Close()

        error_timer.Elapsed += close_after_error
        error_timer.Start()


def check_external_gui(form, status_label, poll_timer):
    global external_process

    if external_process.poll() is None:
        status_label.Text = "Visuelle Erkennung läuft..."
        return

    poll_timer.Stop()

    return_code = external_process.returncode

    if return_code != 0:
        status_label.Text = "Externes Skript Fehlercode: " + str(return_code)
        return

    status_label.Text = "Externe Erkennung beendet"
    # Starte Rhino Geometrie-Erstellung
    createRhinoGeometry(form, status_label)


def createRhinoGeometry(form, status_label):
    status_label.Text = "Lese Polygondaten..."

    if not os.path.exists(DATA_DIR):
        status_label.Text = "Fehler: Polygondaten nicht gefunden. Beende Prozess"
        error_timer = Forms.UITimer()
        error_timer.Interval = 3.0

        def close_after_error(sender, e):
            error_timer.Stop()
            form.Close()

        error_timer.Elapsed += close_after_error
        error_timer.Start()
        return
    
    ## JSON-Parser...
    with open(DATA_DIR, "r") as f:
        data = json.load(f)
    
    ## Rhino Befehle um das Polygon zu erstellen

    unit = data.get("unit", "m") #  Schaut, in welcher Einheit die Daten gespeichert wurden
    
    if unit != "m":
        status_label.Text = "Fehler: JSON-Maßeinheit wird nicht unterstützt" + str(unit)
        return
    
    # Laden der Daten aus der JSON-Datei
    plate_thickness_mm = float(data["plate_thickness_mm"])
    z_weld_surface_mm = m_to_mm(data["z_weld_surface"])

    polygon_data = data["weldable_polygon"]
    clamp_data = data.get("spanneisen_positions", [])
    clamp_extrusion_height_mm = float(
        data.get(
            "clamp_extrusion_height_mm",
            CLAMP_EXTRUSION_HEIGHT_MM
        )
    )

    # Schweißplattenpolygon aus JSON aufbauen
    weldplate_points3d = []

    for point in polygon_data:
        x_mm = m_to_mm(point["X"])
        y_mm = m_to_mm(point["Y"])

        # Polygon liegt auf der Oberseite der Schweißplatte (und wird nach unten extrudiert)
        weldplate_points3d.append([
            x_mm,
            y_mm,
            z_weld_surface_mm
        ])

    status_label.Text = "Erstelle Schweißplatte in Rhino..."

    # Schweißplatte nach unten extrudieren:
    # Oberseite liegt bei: z_weld_surface_mm
    # Unterseite liegt bei: z_weld_surface_mm - plate_thickness_mm
    weldplate_solid_id = add_extruded_polygon(
        weldplate_points3d,
        -plate_thickness_mm
    )

    # Sperren des Volumenkörpers, damit diese nicht aus Versehen bewegt werden können
    setup_imported_object(
        weldplate_solid_id,
        "WAAM_InitialStock",
        MW_LAYER_STOCK,
        lock_object=LOCK_SIM_GEOMETRY
    )

    status_label.Text = "Erstelle Spanneisen in Rhino..."

    for clamp in clamp_data:
        aruco_id = int(clamp["aruco_id"])

        # Holt die Standardkontur des jeweiligen Spanneisens aus der Lookuptabelle
        clamp_def = CLAMP_CONTOURS.get(aruco_id)

        if clamp_def is None:
            print(
                "Spanneisen übersprungen: "
                "keine Geometrie für ArUco ID " + str(aruco_id)
            )

        # Wo der Mittelpunkt des Markers liegt
        center_x_mm = m_to_mm(clamp["X"])
        center_y_mm = m_to_mm(clamp["Y"])

        marker_angle_deg = float(clamp.get("angle_z_deg", 0.0))
        angle_deg = marker_angle_deg + float(clamp_def.get("angle_offset_deg", 0.0)) # Falls der Marker falsch gedreht an den Marker geklebt wurde

        # Drehen und Verschieben der Eckkoordinaten der Spanneisenkontur in das Werkobjekt-KS
        clamp_points3d = transform_local_contour_to_world(
            center_x = center_x_mm,
            center_y = center_y_mm,
            z = z_weld_surface_mm,
            angle_deg = angle_deg,
            contour_2d = clamp_def["contour_mm"]
        )

        clamp_solid_id = add_extruded_polygon(
            clamp_points3d,
            clamp_extrusion_height_mm
        )
        # Gibt dem erstellen Volumenkörper einen Namen, der das Spanneisen beschreibt
        if clamp_solid_id:
            rs.ObjectName(
                clamp_solid_id,
                clamp_def["name"] + "_Aruco_" + str(aruco_id)
            )
        
        if clamp_solid_id:
            setup_imported_object(
                clamp_solid_id,
                "WAAM_Fixture_" + clamp_def["name"] + "_Aruco_" + str(aruco_id),
                MW_LAYER_FIXTURE,
                lock_object=LOCK_SIM_GEOMETRY
            )

    status_label.Text = "Füge Referenzbild ein..."

    reference_image = data.get("reference_image", None)

    if show_ref_img and reference_image is not None:
        try:
            picture_id = addWorkplaneReferenceImage(reference_image)

            if picture_id:
                setup_imported_object(
                    picture_id,
                    "WAAM_Referenzbild_Orthofoto",
                    WAAM_LAYER_REFERENCE,
                    lock_object=LOCK_REFERENCE_IMAGE
                )

        except Exception as e:
            print("Referenzbild konnte nicht eingefügt werden:", e)
    
    status_label.Text = "Fertig: Schweißplatte und Spanneisen erstellt"

    close_timer = Forms.UITimer()
    close_timer.Interval = 1.5

    def close_after_done(sender, e):
        close_timer.Stop()
        form.Close()

    close_timer.Elapsed += close_after_done
    close_timer.Start()


### HILFSFUNKTIONEN ###

def addWorkplaneReferenceImage(reference_image):
    if reference_image is None: 
        return None

    image_path = reference_image.get("path", None)

    if not image_path:
        return None
    
    # falls nur dateiname übergeben wurde, suche relativ zum Skriptordner
    if not os.path.isabs(image_path):
        image_path = os.path.join(SCRIPT_DIR, image_path)

    image_path = os.path.abspath(os.path.normpath(image_path))

    print("Referenzbild-Pfad:", image_path)
    print("Existiert:", os.path.exists(image_path))

    if not os.path.exists(image_path):
        print("Referenzbild nicht gefunden:", image_path)
        return None
    
    unit = reference_image.get("unit", "m")

    if unit != "m":
        return None
    
    x_min_mm = m_to_mm(reference_image["x_min"])
    x_max_mm = m_to_mm(reference_image["x_max"])
    y_min_mm = m_to_mm(reference_image["y_min"])
    y_max_mm = m_to_mm(reference_image["y_max"])

    # Auf welche Z-Ebene das Bild hinsoll
    z_mm = m_to_mm(reference_image["z"]) + 0.01 

    width_mm = x_max_mm - x_min_mm
    height_mm = y_max_mm - y_min_mm

    if width_mm <= 0 or height_mm <= 0:
        return None

    plane = rs.PlaneFromFrame(
        [x_min_mm, y_min_mm, z_mm],
        [1, 0, 0],
        [0, 1, 0]
    )

    image_path = os.path.abspath(os.path.normpath(image_path))
    image_path = image_path.strip('"')

    print("Referenzbild-Pfad:", image_path)
    print("os.path.exists:", os.path.exists(image_path))
    print("System.IO.File.Exists:", System.IO.File.Exists(System.String(image_path)))

    image_path_net = System.String(image_path)

    picture_id = rs.AddPictureFrame(
        plane,
        image_path_net,
        width_mm,
        height_mm,
        True,   # self illumination
        True,   # embed image
        False   # use alpha
    )

    if picture_id:
        rs.ObjectName(picture_id, "Referenzbild_Orthofoto_Werkebene")
        
        if LOCK_REFERENCE_IMAGE:
            rs.LockObject(picture_id)

    return picture_id

def m_to_mm(value_m):
    return float(value_m) * 1000.0

# Falls die erste und letzte Koordinate nicht übereinstimmt, wird diese nochmal eingefügt
def closePolylinePoints(points):
    if points and points[0] != points[-1]:
        points.append(points[0])
    return points

# Allgemeine Funktion, die Polygon in Rhino extrudiert
def add_extruded_polygon(points3d, dz_mm):

    # Polygon schließen - Zur Sicherheit überprüfen ob erster und letzter Eintrag, derselbe ist, damit das Polygon geschlossen ist
    # Denn points[0] und points[-1] (letzter Eintrag) sollten identisch sein für den Rhino-Befehl
    points3d = closePolylinePoints(points3d)

    # Erstellt Polygonlinie in Rhino als Skizze
    polyline_id = rs.AddPolyline(points3d) # Fügt die Polyline hinzu und gibt die ID zurück

    if not polyline_id:
        return None

    # Aus der geschlossenen Polyline eine Flaeche erstellen
    surface_ids = rs.AddPlanarSrf(polyline_id) # Erstellt eine Flaeche aus der Polyline und gibt deren ID zurück

    if not surface_ids:
        rs.DeleteObject(polyline_id)
        return None
    
    surface_id = surface_ids[0]

    if abs(dz_mm) < 1e-9:
        if polyline_id:
            rs.DeleteObject(polyline_id)

        return surface_id
    
    # Um eine Flaeche in Rhino zu extrudieren, braucht man einen Pfad, in diesem Fall die Normale der Flaeche:
    path_id = rs.AddLine(
        [0, 0, 0],
        [0, 0, dz_mm]
    )
    # Erstellen des Volumenkörpers:
    solid_id = rs.ExtrudeSurface(
        surface_id, 
        path_id, 
        cap=True
    ) # cap=True schließt den Volumenkörper

    # Hilfsgeometrien löschen, damit kein Artefakte in die Simulation gelangen können
    if polyline_id:
        rs.DeleteObject(polyline_id)

    if surface_id:
        rs.DeleteObject(surface_id)

    if path_id:
        rs.DeleteObject(path_id)

        

    return solid_id

# Dreht eine beliebige Spanneisenkontur um den Mittelpunkt des ArUco-Markers und gibt die neuen Koordinaten im Werkobjekt-KS an
def transform_local_contour_to_world(center_x, center_y, z, angle_deg, contour_2d):
    angle_rad = math.radians(angle_deg)

    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)

    points3d = []

    for local_x, local_y in contour_2d:
        world_x = center_x + local_x * ca - local_y * sa
        world_y = center_y + local_x * sa + local_y * ca

        points3d.append([world_x, world_y, z])

    return points3d

def ensure_layer(layer_name):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name)


def setup_imported_object(obj_id, object_name, layer_name, lock_object=False):
    if not obj_id:
        return

    ensure_layer(layer_name)

    rs.ObjectName(obj_id, object_name)
    rs.ObjectLayer(obj_id, layer_name)

    if lock_object:
        rs.LockObject(obj_id)

### HILFSFUNKTIONEN ###


# Start des Tkinter-Fensters
def main():
    # Fenstertitel zusammenstellen
    form_title = f"Schweißplattenerkennung"

    form = Forms.Dialog()
    form.Title = form_title
    form.ClientSize = Drawing.Size(320, 100)

    status_label = Forms.Label()
    status_label.Text = "Prozess wird vorbereitet..."

    layout = Forms.DynamicLayout()
    layout.Spacing = Drawing.Size(5, 5)
    layout.Padding = Drawing.Padding(10)
    layout.AddRow(status_label)

    form.Content = layout

    form.Shown += lambda sender, e: start_process(form, status_label)

    form.ShowModal()

# Das Skript wird nur ausgeführt, wenn es direkt aufgerufen wird, nicht wenn es importiert wird
if __name__ == "__main__":
    main()


