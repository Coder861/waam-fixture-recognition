import cv2
import numpy as np
from pathlib import Path
import os
import time
import matplotlib.pyplot as plt

aruco = cv2.aruco

##### Globale Variablen #####

# Cam-Daten
calib_data = None # Kalibrierdatei
camera_matrix = None
dist_coeffs = None

cam_id = None
cam_name = None
resolution_width = None
resolution_height = None

# ChArUco / ArUco Variablen
charuco_rvec = None # Pose vom ChArUco Board
charuco_tvec = None # Pose vom ChArUco Board
spanneisen_positions = []

# Homographie
H_plane_to_image = None
H_image_to_plane = None

# Plate
SPANNPLATTE_HEIGHT = 0.020 # 20mm dicke Aufspannplatte über dem Werkobjekt-KS
plate_thickness = 0.0 # in Milimeter
plate_thickness_m = 0.0 # Umwandlung in Meter
z_weld_surface = 0.0 # Die Höhe über dem Werkobjekt-KS auf dem die Ebene für die Homographie aufgespannt wird

# Bild
img_og = None
img_cpy = None
img_undistort = None
img_charuco = None
img_aruco = None

REF_IMAGE_PATH = Path(__file__).parent / "spannsituation_ortho.png"

##### Auto-Pipeline & Maskierung #####

# Aufspannplatte im ChArUco-Koordinatensystem [m]
# Annahme:
# Board sitzt an der oberen rechten Ecke der Aufspannplatte.
# +X zeigt von der Platte weg.
# +Y zeigt entlang der Platte nach vorne/unten.
SPANNPLATTE_POLY_CHARUCO_M = np.array([
    [ 0.000, 0.000, 0.000],
    [-0.500, 0.000, 0.000],
    [-0.500, 0.500, 0.000],
    [ 0.000, 0.500, 0.000],
], dtype=np.float64)

# Dilate für ArUco-Filterung, damit Marker nahe an der Plattenkante nicht verworfen werden
SPANNPLATTE_ARUCO_DILATE_PX = 80

# Dilate für Spanneisenmaske, um Schatten / Unterlegscheiben mit auszublenden
SPANNEISEN_MASK_DILATE_PX = 45

# Abstand zum Rand der Aufspannplattenmaske, der für die automatische
# Kantenerkennung nicht berücksichtigt wird.
AUTO_EDGE_MASK_ERODE_RADIUS_PX = 30

# Auto-Pipeline Parameter aus 2_Preprocessing.py
AUTO_CANNY_MIN = 30
AUTO_CANNY_MAX = 255

AUTO_HOUGH_THRESHOLD = 200
AUTO_HOUGH_MIN_LINE_LENGTH = 50
AUTO_HOUGH_MAX_LINE_GAP = 60

AUTO_CLUSTER_ANGLE_TOL_DEG = 5
AUTO_CLUSTER_RHO_TOL_PX = 20
AUTO_MIN_CLUSTER_TOTAL_LENGTH = 120
AUTO_ORTHOGONAL_TOL_DEG = 10

ARUCO_MARKER_WIDTH_M = 0.03

##### Auto-Pipeline / Maskierung #####

## Spanneisen-Lookup-Table

# Normierte Spanneisenkonturen.
# (0,0) = Marker-Ecke 0, (1,1) = gegenüberliegende Marker-Ecke.
POLY_SPANNEISEN_14x100_NORM = np.array([
    [-5/30, 35/30],
    [-5/30, -42/30],
    [0.25, -65/30],
    [0.75, -65/30],
    [35/30, -42/30],
    [35/30, 35/30]
], dtype=np.float64)

POLY_SPANNEISEN_14x125_NORM = np.array([
    [-5/30, 35/30],
    [-5/30, -2.3],
    [0.25, -3],
    [0.75, -3],
    [35/30, -2.3],
    [35/30, 35/30]
], dtype=np.float64)

POLY_SPANNEISEN_14x160_NORM = np.array([
    [-5/30, 35/30],
    [-5/30, -103/30],
    [0.25, -125/30],
    [0.75, -125/30],
    [35/30, -103/30],
    [35/30, 35/30]
], dtype=np.float64)

CLAMP_POLYGON_LUT = {
    60: {"poly_norm": POLY_SPANNEISEN_14x100_NORM, "angle_offset_deg": 180.0},
    61: {"poly_norm": POLY_SPANNEISEN_14x125_NORM, "angle_offset_deg": 180.0},
    62: {"poly_norm": POLY_SPANNEISEN_14x160_NORM, "angle_offset_deg": 180.0},
}

#DEFAULT_CLAMP_POLYGON = {
    #"poly_norm": POLY_SPANNEISEN_14x125_NORM,
    #"angle_offset_deg": 180.0
#}


## ChArUco - Werkobjekt Koordinatensystemoffset
WORK_ORIGIN_OFFSET_X = -0.253819483 # in Meter
WORK_ORIGIN_OFFSET_Y = 0.249764114 # in Meter
WORK_ORIGIN_OFFSET_Z = 0.022500000 # in Meter - 20mm unterhalb des Charuco Board, weil das interne Werkobjektkoordiantensystem im CAD auf dem runden Tisch liegt, und auf diesem runden Tisch wurde die viereckige Spannplatte gespannt. Und darauf dann erst die Schweißplatte und das Charuco Board ist auf einer 3D gedruckten Platte die 2,5mm dick ist
WORK_ROTATION_Y_DEG = 180 # in Grad - Das Charuco Koordinatensystem hat die Z-Achse immer nach unten zeigend, deswegen muss das Koordinatensystem umgedreht werden. 
WORK_ROTATION_Z_DEG = 55.124312838 # in Grad


# Offset des Werkobjektkoordinatensystems in ChArUco-Koordinaten
WORK_ORIGIN_IN_CHARUCO = np.array([
    WORK_ORIGIN_OFFSET_X,
    WORK_ORIGIN_OFFSET_Y,
    WORK_ORIGIN_OFFSET_Z
], dtype=np.float64)


# Erkennt ArUco-Marker und das ChArUco-Board und zeichnet die Achsen der Marker in ein Bild ein
def getCharucoPose():

    ### ChArUco Variablen ###
    charuco_dict = aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50) # Dict fürs ChArUco Board

    CHARUCO_SQUARES_X = 3
    CHARUCO_SQUARES_Y = 8
    CHARUCO_SQUARE_LENGTH = 0.03 # in Meter
    CHARUCO_MARKER_LENGTH = 0.0225 # in Meter

    # Wie das ChArUco Board aussieht:
    CHARUCO_BOARD = aruco.CharucoBoard(
        (CHARUCO_SQUARES_X, CHARUCO_SQUARES_Y),
        CHARUCO_SQUARE_LENGTH,
        CHARUCO_MARKER_LENGTH,
        charuco_dict
    )
    charuco_detector = aruco.CharucoDetector(CHARUCO_BOARD)

    ### ChArUco-Erkennung ###
    global charuco_rvec, charuco_tvec

    ### 2. ChArUco und ArUco erkennen --> GGF. ZWEITE FUNKTION HINZUFÜGEN UM ZWEI UNTERSCHIEDLICHE DICTIONARIES ERKENNEN ZU KÖNNEN (FÜRS BOARD UND DIE SPANNEISEN)
    
    ## ChArUco Erkennung
    charuco_corners, charuco_ids, marker_corners, marker_ids = charuco_detector.detectBoard(img_undistort)

    if charuco_corners is None or charuco_ids is None or len(charuco_ids) < 4:
        raise RuntimeError("Zu wenige ChArUco-Punkte erkannt.")

    # Zeichnen der ChArUco Ecken
    charuco_img = aruco.drawDetectedCornersCharuco(img_undistort, charuco_corners, charuco_ids)
    #charuco_img = aruco.drawDetectedMarkers(charuco_img, marker_ids, marker_corners)
  
    ## 3. Korrespondenzen zwischen ChArUco Koordinaten und Bildkoordinaten herstellen (für den PnP-Algorithmus)
    objPoints, imgPoints = CHARUCO_BOARD.matchImagePoints(charuco_corners, charuco_ids)

    ## 4. Perspective and Point Algorithmus um die 6D-Pose des ChArUco Boards im Raum zu erhalten
    retval, charuco_rvec, charuco_tvec = cv2.solvePnP(
        objPoints,
        imgPoints,
        camera_matrix, # Muss hier auch übergeben werden, da Brennweite/Zoom und Bildmitte gleichbleibt und nicht mit cv2.undistort "entfernt" wurde
        None # Da das Bild schon entzerrt wurde, nicht nochmal dist_coeffs übergeben, sonst wird doppelt entzerrt!
    ) # rvec und tvec sind die gesuchten Kamera-Extrinsics (rvec = Rotation (Rodriguez-Vektor), tvec= Translation (Vektor))

    if not retval:
        raise RuntimeError("solvePnP konnte keine Pose ermitteln.")
    
    # Zeichnen der ChArUco Pose (Koordinatenachsen)
    cv2.drawFrameAxes(
        charuco_img,
        camera_matrix,
        None, # charuco_img ist bereits entzerrt
        charuco_rvec,
        charuco_tvec,
        0.1, # length
        3 # thickness
    )
    return charuco_img

def detect_aruco(charuco_frame, valid_mask=None):
    global spanneisen_positions

    # ArUco-Dictionary der Spanneisen
    aruco_dict = aruco.getPredefinedDictionary(
        cv2.aruco.DICT_5X5_100
    )
    aruco_params = aruco.DetectorParameters()

    # Marker im Bild erkennen
    aruco_corners, aruco_ids, aruco_rejected = aruco.detectMarkers(
        charuco_frame,
        aruco_dict,
        parameters=aruco_params
    )

    # Unveränderte Kopie für die spätere Ergebnisdarstellung
    frame_aruco = charuco_frame.copy()

    if aruco_ids is None:
        print("Keine ArUco-Marker der Spanneisen erkannt.")
        return frame_aruco

    # Nur akzeptierte Marker werden später eingezeichnet
    accepted_corners = []
    accepted_ids = []

    for i, marker_id in enumerate(aruco_ids.flatten()):
        marker_id = int(marker_id)

        if marker_id not in CLAMP_POLYGON_LUT:
            print(
                f"ArUco ID {marker_id} verworfen: "
                "keine Spanneisengeometrie hinterlegt."
            )
            continue
        
        corners = aruco_corners[i].reshape(4, 2)

        # Mittelpunkt des Markers im Bild
        u_middle = float(corners[:, 0].mean())
        v_middle = float(corners[:, 1].mean())

        # Marker außerhalb der erweiterten Aufspannplattenmaske verwerfen
        if valid_mask is not None:
            u_i = int(round(u_middle))
            v_i = int(round(v_middle))

            if (
                u_i < 0
                or v_i < 0
                or u_i >= valid_mask.shape[1]
                or v_i >= valid_mask.shape[0]
                or valid_mask[v_i, u_i] == 0
            ):
                print(
                    f"ArUco ID {int(marker_id)} verworfen: "
                    "Mittelpunkt außerhalb der Aufspannplattenmaske"
                )
                continue

        # Erst nach erfolgreicher Maskenprüfung als akzeptiert speichern
        accepted_corners.append(aruco_corners[i])
        accepted_ids.append([int(marker_id)])

        # Lokale X-Richtung des Markers aus Ecke 0 und Ecke 1 bestimmen
        p0_3d = pixel_to_3dplane(
            float(corners[0, 0]),
            float(corners[0, 1]),
            z_weld_surface
        )

        p1_3d = pixel_to_3dplane(
            float(corners[1, 0]),
            float(corners[1, 1]),
            z_weld_surface
        )

        marker_vec = p1_3d - p0_3d

        # Orientierung des Markers um die Z-Achse im Werkobjekt-KS
        angle_z_rad = np.atan2(
            marker_vec[1],
            marker_vec[0]
        )
        angle_z_deg = np.rad2deg(angle_z_rad)

        # Mittelpunkt in Werkobjektkoordinaten transformieren
        point_3d = pixel_to_3dplane(
            u_middle,
            v_middle,
            z_weld_surface
        )

        spanneisen_positions.append({
            "aruco_id": int(marker_id),
            "aruco_corners": aruco_corners[i],
            "u_middle": u_middle,
            "v_middle": v_middle,
            "point3d": point_3d,
            "angle_z_rad": float(angle_z_rad),
            "angle_z_deg": float(angle_z_deg)
        })

        cv2.circle(
            frame_aruco,
            (int(round(u_middle)), int(round(v_middle))),
            5,
            (0, 255, 0),
            -1
        )

        print(
            f"ArUco ID erkannt: {int(marker_id)} - "
            f"Bildkoordinaten: u={u_middle:.1f}, v={v_middle:.1f} - "
            f"Raumkoordinaten: "
            f"X={point_3d[0]:.4f}, "
            f"Y={point_3d[1]:.4f}, "
            f"Z={point_3d[2]:.4f} - "
            f"Winkel Z={angle_z_deg:.1f}°"
        )

    # Nur Marker innerhalb der gültigen Maske darstellen
    if accepted_corners:
        cv2.aruco.drawDetectedMarkers(
            frame_aruco,
            accepted_corners,
            np.asarray(accepted_ids, dtype=np.int32)
        )

    return frame_aruco


def getPlaneHomography():
    ## Homographie des ChArUco-Boards bauen --> zieht eine virtuelle Ebene auf dem ChArUco-Board auf

    # Erstellen der Homographie Welt zu Bild: H_zh = K * [r_1 r_2 (t + z_h*r_3)]
    # 1. rvec (Rodriguez-Vektor) in eine 3x3 Matrix umwandeln
    R, _ = cv2.Rodrigues(charuco_rvec) # Wandelt den 3x1 Rodriguez-Rotationsvektor in eine 3x3 Rotationsmatrix um

    # 2. Rotationsmatrix aufteilen in die einzelnen Spalten r1, r2, r3
    r1 = R[:, 0] # Gibt die Spalte in flacher Form zurück: (3,)
    r2 = R[:, 1]
    r3 = R[:, 2]

    # Matrixmultiplikation: A @ b - elementweise Multiplikation: A * b

    # 3. Dritte Spalte anpassen:
    t = charuco_tvec.reshape(3) # Wandelt tvec von einem (3,1) Vektor zu (3,) um
    r3_new = t + plate_thickness_m * r3

    # 4. Rotationsmatrix neu kombinieren zu r1, r2, (t+z_h*r3)
    Rt = np.column_stack((r1, r2, r3_new))

    # 5. Mit Kameramatrix multiplizieren und als Homographie speichern
    H_plane_to_image = camera_matrix @ Rt
    
    return H_plane_to_image

def getWorkPlaneHomography():
    # Erstellt direkt die Homographie:
    # Werkobjekt-KS auf Ebene Z = z_h --> Pixelkoordianten

    # 1. Extrinsics aus der Charuco Erkennung (Rotation + Translation zwischen Charuco und Kamera)
    R_charuco_to_camera, _ = cv2.Rodrigues(charuco_rvec) # Rotationsmatrix vom ChArUco-KS in Kamerakoordinaten
    t_charuco_to_camera = charuco_tvec.reshape(3) # Translation vom ChArUco-KS in Kamerakoordinaten
    
    # 2. Extrinsics zwischen Werkobjekt-KS und Charuco-KS (manueller Offset Rotation + Translation)
    R_work_to_charuco = None # Rotationsmatrix vom Werkobjekt-KS in ChArUco-Koordinaten
    t_work_to_charuco = WORK_ORIGIN_IN_CHARUCO.reshape(3) # Translation vom Werkobjekt-KS in ChArUco-Koordinaten

    # 2.1 Rotationsmatrizen um Y und Z aufstellen

    # Rotationsmatrix um die Y-Achse (180° damit Z nach oben zeigt)
    theta_y = np.deg2rad(WORK_ROTATION_Y_DEG)
    cy = np.cos(theta_y)
    sy = np.sin(theta_y)

    Ry_work_to_charuco = np.array([
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy]
    ], dtype=np.float64)

    # Rotationsmatrix um die Z-Achse
    theta_z = np.deg2rad(WORK_ROTATION_Z_DEG)
    cz = np.cos(theta_z)
    sz = np.sin(theta_z)

    Rz_work_to_charuco = np.array([
        [cz, -sz, 0.0],
        [sz, cz, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)    

    # Erst Y-Flip, dann Z-Drehung
    R_work_to_charuco = Rz_work_to_charuco @ Ry_work_to_charuco


    # 3. Pose des Werkobjekt-KS in Kamerakoordinaten

    R_work_to_camera = R_charuco_to_camera @ R_work_to_charuco
    t_work_to_camera = R_charuco_to_camera @ t_work_to_charuco + t_charuco_to_camera

    # 4. Homographie für Ebene Z = z_plane_work im Werkobjekt-KS
    # Formel: H = K * [r1 r2 (t + z*r3)] - K: Kameramatrix; r1 r2 r3: Rotationsmatrix R_work_to_camera; t: t_work_to_camera

    # Zerlegen der Rotationsmatrix
    r1 = R_work_to_camera[:, 0]
    r2 = R_work_to_camera[:, 1]
    r3 = R_work_to_camera[:, 2]

    # Dritte Spalte anpassen (t + z*r3) mit t: t_work_to_camera; z: Abstand vom Ursprung zur Schweißplattenoberfläche; r3: dritte Spalte der Rotationsmatrix
    r3_new = t_work_to_camera + z_weld_surface * r3

    # Rotations-Translationsmatrix neu kombinieren R*t (zu r1, r2, (t+z_h*r3))
    Rt_plane = np.column_stack((r1, r2, r3_new))

    # Multiplikation mit der Kameramatrix = Homographie, um von Kamerakoordinaten auf Pixelkoordinaten zu kommen

    H_plane_to_image = camera_matrix @ Rt_plane # Matrixmultiplikation: A @ b - elementweise Multiplikation: A * b
    H_image_to_plane = np.linalg.inv(H_plane_to_image)

    return H_plane_to_image, H_image_to_plane

def draw_work_axes(frame, axis_length=0.05):
    # Werkobjekt-Koordinatensystempunkte in 3D 
    p0_3d = np.array([0.0, 0.0, 0.0]) # Ursprung des Werkobjektkoordinatensystems
    px_3d = np.array([axis_length, 0.0, 0.0]) # X-Achse
    py_3d = np.array([0.0, axis_length, 0.0]) # Y-Achse
    pz_3d = np.array([0.0, 0.0, axis_length]) # Z-Achse

    # Umrechnen der 3D-Koordinaten in Bildkoordinaten
    p0 = point3d_to_pixel(p0_3d)
    px = point3d_to_pixel(px_3d)
    py = point3d_to_pixel(py_3d)
    pz = point3d_to_pixel(pz_3d)

    # Zeichnen der Achsen in das Bild
    cv2.circle(frame, p0, 7, (0, 255, 255), -1) # Ursprung in Gelb
    cv2.putText(frame, "WKS", (p0[0] + 10, p0[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2) # Beschriftung des Ursprungs mit Offset zum Ursprungspunkt

    cv2.arrowedLine(frame, p0, px, (0, 0, 255), 3) # X-Achse in Rot
    cv2.arrowedLine(frame, p0, py, (0, 255, 0), 3) # Y-Achse in Grün
    cv2.arrowedLine(frame, p0, pz, (255, 0, 0), 3) # Z-Achse in Blau

    cv2.putText(frame, "Xw", px, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2) # Beschriftung der X-Achse
    cv2.putText(frame, "Yw", py, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2) # Beschriftung der Y-Achse
    cv2.putText(frame, "Zw", pz, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2) # Beschriftung der Z-Achse

    return frame


# Rechnet mithilfe der inversen Homographie des ChArUco Boards die 2D-Bildkoordinaten in 3D-Raumkoordinaten um
def pixel_to_3dplane(u, v, z_h):
    global H_image_to_plane

    if H_image_to_plane is None:
        raise ValueError("H_image_to_plane ist nicht initialisiert. Bitte zuerst die Homographie berechnen.")

    ## Pixelkoordinate umrechnen in Raumkoordinaten: 
    
    # Bildpixelkoordinaten als homogener Vektor:
    x_pixel = np.array([u, v, 1.0])

    # Umrechnen der Bildkoordinate in Raumkoordinate
    X_plane = H_image_to_plane @ x_pixel

    # Aufteilen der berechneten Koordinaten um diese homogenisieren zu können
    X_prime = X_plane[0]
    Y_prime = X_plane[1]
    lambda_ = X_plane[2]

    if abs(lambda_) < 1e-12:
        raise ValueError("Homogener Skalierungsfaktor lambda_ ist zu klein.")

    X = X_prime / lambda_
    Y = Y_prime / lambda_
    Z = z_h # Z-Koordinate in Werkobjektkoordinaten umrechnen

    return np.array([X,Y,Z])

# Projiziert einen 3D-Punkt in das Bild, an der perspektivisch richtigen Stelle
def plane_to_pixel(point_3d, expected_z):

    if H_plane_to_image is None:
        raise ValueError("H_plane_to_image ist nicht initialisiert. Bitte zuerst die Homographie berechnen.")
    
    point_3d = np.asarray(point_3d, dtype=np.float64).reshape(3) # Sicherstellen, dass point_3d ein 3D-Vektor ist

    X = point_3d[0]
    Y = point_3d[1]
    Z = point_3d[2]

    # Check, dass die Z-Koordinate innerhalb einer Toleranz zum erwarteten Z-Wert liegt (auf der Ebene für die Charuco-Homographie)
    if expected_z is not None and abs(Z - expected_z) > 1e-6:
        raise ValueError(f"Der Punkt liegt nicht auf der erwarteten Ebene. Erwartetes Z: {expected_z}, tatsächliches Z: {Z}")
    
    # Löschen des Z-Wertes, da wir nur die 2D-Ebene betrachten
    p_plane = np.array([X, Y, 1.0])
    # Umwandlung der 3D-Koordinaten in Bildkoordinaten
    p_image = H_plane_to_image @ p_plane

    if abs(p_image[2]) < 1e-12:
        raise ValueError("Homogener Skalierungsfaktor ist zu klein.")
    
    u = p_image[0] / p_image[2] # Umwandlung in Pixelkoordinaten
    v = p_image[1] / p_image[2]

    return int(round(u)), int(round(v))

def point3d_to_pixel(point_work):
    point_charuco = work_to_charuco(point_work) # Wandelt den Punkt vom Werkobjekt-KS in das ChArUco-KS um

    image_points, _ = cv2.projectPoints(
        point_charuco.reshape(1, 3),
        charuco_rvec,
        charuco_tvec,
        camera_matrix,
        None # Verzerrung ist bereits im Bild korrigiert, daher None
    )

    u, v = image_points.reshape(2)

    return int(round(u)), int(round(v))


# Wandelt einen 3D-Punkt aus dem Werkobjekt-KS ins ChArUco-KS um
def work_to_charuco(point_work):

    point_work = np.asarray(point_work, dtype=np.float64).reshape(3)

    # Rotation um Y
    theta_y = np.deg2rad(WORK_ROTATION_Y_DEG)
    cy = np.cos(theta_y)
    sy = np.sin(theta_y)

    Ry_work_to_charuco = np.array([
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy]
    ], dtype=np.float64)

    # Rotation um Z
    theta_z = np.deg2rad(WORK_ROTATION_Z_DEG)
    cz = np.cos(theta_z)
    sz = np.sin(theta_z)  # wichtig: sin, nicht cos

    Rz_work_to_charuco = np.array([
        [cz, -sz, 0.0],
        [sz,  cz, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    # Erst Y-Flip, dann Z-Drehung
    R_work_to_charuco = Rz_work_to_charuco @ Ry_work_to_charuco

    t_work_to_charuco = WORK_ORIGIN_IN_CHARUCO.reshape(3)

    point_charuco = R_work_to_charuco @ point_work + t_work_to_charuco

    return point_charuco

# Erstellt aus einem im ChArUco-Koordinatensystem definierten Rechteck eine Binärmaske der Aufspannplatte im Bild.
def createSpannplatteMask(frame_shape):
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    image_points, _ = cv2.projectPoints(
        SPANNPLATTE_POLY_CHARUCO_M.reshape(-1, 1, 3),
        charuco_rvec,
        charuco_tvec,
        camera_matrix,
        None
    )

    pts = np.round(image_points.reshape(-1, 2)).astype(np.int32)
    cv2.fillPoly(mask, [pts], 255)

    return mask

# Erstellt aus den erkannten ArUco-Spanneisenpositionen eine Maske der Störobjekte.
# Die normierten Spanneisenkonturen werden in reale Werkobjektkoordinaten transformiert und anschließend ins Bild projiziert.
def createSpanneisenMask(frame_shape):
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    for clamp in spanneisen_positions:
        aruco_id = int(clamp["aruco_id"])
        clamp_def = CLAMP_POLYGON_LUT.get(aruco_id)

        if clamp_def is None: 
            print(
                f"Spanneisenmaske übersprungen: "
                f"unbekannte ArUco ID {aruco_id}"
            )

        poly_norm = clamp_def["poly_norm"]
        angle_deg = float(clamp["angle_z_deg"]) + float(clamp_def["angle_offset_deg"])
        angle_rad = np.deg2rad(angle_deg)

        ca = np.cos(angle_rad)
        sa = np.sin(angle_rad)

        center_3d = np.asarray(clamp["point3d"], dtype=np.float64).reshape(3)
        center_x = float(center_3d[0])
        center_y = float(center_3d[1])

        poly_px = []

        for u_norm, v_norm in poly_norm:
            local_x = (float(u_norm) - 0.5) * ARUCO_MARKER_WIDTH_M
            local_y = (float(v_norm) - 0.5) * ARUCO_MARKER_WIDTH_M

            world_x = center_x + local_x * ca - local_y * sa
            world_y = center_y + local_x * sa + local_y * ca

            try:
                u_px, v_px = plane_to_pixel(
                    np.array([world_x, world_y, z_weld_surface], dtype=np.float64),
                    z_weld_surface
                )
                poly_px.append([u_px, v_px])
            except Exception as exc:
                print(f"Spanneisenmaske: ID {aruco_id} konnte nicht projiziert werden: {exc}")

        if len(poly_px) >= 3:
            cv2.fillPoly(mask, [np.array(poly_px, dtype=np.int32)], 255)

    if SPANNEISEN_MASK_DILATE_PX > 0:
        k = int(SPANNEISEN_MASK_DILATE_PX)

        if k % 2 == 0:
            k += 1

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.dilate(mask, kernel, iterations=1)

    return mask

# Berechnet den Linienwinkel im Bildkoordinatensystem im Bereich 0 bis 180 Grad.
def getLineAngleDeg(line):
    x1, y1, x2, y2 = line

    dx = x2 - x1
    dy = y2 - y1

    angle = np.degrees(np.arctan2(dy, dx))

    return angle % 180


# Berechnet die kleinste Winkeldifferenz zweier ungerichteter Linien.
def getAngleDiffDeg(a, b):
    diff = abs(a - b) % 180

    return min(diff, 180 - diff)


# Berechnet den Schnittpunkt zweier reduzierter Linien, behandelt diese dabei als unendliche Geraden.
def getLineIntersection(line_a, line_b):
    x1, y1 = line_a["p1"]
    x2, y2 = line_a["p2"]
    x3, y3 = line_b["p1"]
    x4, y4 = line_b["p2"]

    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

    if abs(den) < 1e-9:
        return None

    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / den

    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / den

    return np.array([px, py], dtype=np.float64)


# Sortiert vier Polygonpunkte um ihren Mittelpunkt, damit ein geschlossenes Viereck gezeichnet werden kann.
def sortPolygonPoints(points):
    pts = np.asarray(points, dtype=np.float64)
    center = pts.mean(axis=0)

    angles = np.arctan2(
        pts[:, 1] - center[1],
        pts[:, 0] - center[0]
    )

    return pts[np.argsort(angles)]

# Versucht aus reduzierten Hough-Linien ein plausibles viereckiges Polygon zu bilden.
def buildPolygonFromHoughLines(cluster_lines, valid_mask):
    # Plausibilitätsprüfung:
    # Die automatische Pipeline nimmt an, dass die Substratplatte in der Bildebene als
    # rechteckiges Viereck erscheint. Die Orientierung dieses Vierecks ist dabei frei
    # und muss nicht mit der Aufspannplatte übereinstimmen.
    # Aus den reduzierten Hough-Linien werden deshalb parallele Linienpaare in zwei
    # ungefähr orthogonalen Hauptrichtungen gesucht. Aus deren Schnittpunkten wird ein
    # Viereck gebildet. Dieses Viereck wird verworfen, wenn es außerhalb des Bildbereichs
    # liegt, zu klein ist, nicht konvex ist oder nur unzureichend mit der gültigen
    # Suchmaske überlappt. Unter mehreren Kandidaten wird derjenige bevorzugt, dessen
    # Kanten durch lange Liniencluster gestützt werden und der gut innerhalb des
    # erlaubten Suchbereichs liegt.
    
    if len(cluster_lines) < 4:
        return None

    best_polygon = None
    best_score = -1.0

    height, width = valid_mask.shape[:2]

    for i in range(len(cluster_lines)):
        for j in range(i + 1, len(cluster_lines)):
            a = cluster_lines[i]
            b = cluster_lines[j]

            diff = getAngleDiffDeg(a["angle"], b["angle"])

            if abs(diff - 90.0) > AUTO_ORTHOGONAL_TOL_DEG:
                continue

            group_a = [
                line for line in cluster_lines
                if getAngleDiffDeg(line["angle"], a["angle"]) < AUTO_ORTHOGONAL_TOL_DEG
            ]

            group_b = [
                line for line in cluster_lines
                if getAngleDiffDeg(line["angle"], b["angle"]) < AUTO_ORTHOGONAL_TOL_DEG
            ]

            if len(group_a) < 2 or len(group_b) < 2:
                continue

            group_a = sorted(group_a, key=lambda line: line["rho"])
            group_b = sorted(group_b, key=lambda line: line["rho"])

            a1 = group_a[0]
            a2 = group_a[-1]
            b1 = group_b[0]
            b2 = group_b[-1]

            intersections = [
                getLineIntersection(a1, b1),
                getLineIntersection(a1, b2),
                getLineIntersection(a2, b2),
                getLineIntersection(a2, b1),
            ]

            if any(p is None for p in intersections):
                continue

            polygon = sortPolygonPoints(intersections)

            margin = 200

            if np.any(polygon[:, 0] < -margin) or np.any(polygon[:, 0] > width + margin):
                continue

            if np.any(polygon[:, 1] < -margin) or np.any(polygon[:, 1] > height + margin):
                continue

            polygon_i = np.round(polygon).astype(np.int32)
            area = abs(cv2.contourArea(polygon_i))

            if area < 1000:
                continue

            poly_mask = np.zeros_like(valid_mask)
            cv2.fillPoly(poly_mask, [polygon_i], 255)

            overlap = cv2.countNonZero(
                cv2.bitwise_and(poly_mask, valid_mask)
            )

            poly_area_px = max(cv2.countNonZero(poly_mask), 1)
            overlap_ratio = overlap / poly_area_px

            if overlap_ratio < 0.25:
                continue

            score = (
                float(
                    a1["total_length"]
                    + a2["total_length"]
                    + b1["total_length"]
                    + b2["total_length"]
                )
                + 0.001 * area
                + 1000.0 * overlap_ratio
            )

            if score > best_score:
                best_score = score
                best_polygon = polygon

    return best_polygon

# Bestimmt aus einem maskierten Debugbild den sichtbaren Bildausschnitt für die Matplotlib-Anzeige.
# Dieser Crop betrifft nur die Anzeige, nicht die eigentliche Bildverarbeitung.
def getDebugCropFromMask(img, margin_px=90):
    if img is None:
        return None

    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    ys, xs = np.where(gray > 0)

    if len(xs) == 0 or len(ys) == 0:
        return None

    h, w = gray.shape[:2]

    x0 = max(int(xs.min()) - margin_px, 0)
    x1 = min(int(xs.max()) + margin_px, w - 1)
    y0 = max(int(ys.min()) - margin_px, 0)
    y1 = min(int(ys.max()) + margin_px, h - 1)

    if x1 <= x0 or y1 <= y0:
        return None

    return x0, y0, x1, y1


# Zeigt die Zwischenschritte der automatischen Pipeline in einem Matplotlib-Fenster.
# Die Anzeige wird auf die Masken-ROI zugeschnitten, damit die Platte größer sichtbar ist.
def showAutoPipelinePanel(debug_steps):
    if not debug_steps:
        return

    import matplotlib.pyplot as plt

    plt.close("Auto-Pipeline Debug")

    crop_box = None

    for _, img in debug_steps:
        crop_box = getDebugCropFromMask(img, margin_px=90)

        if crop_box is not None:
            break

    n = len(debug_steps)
    cols = 4
    rows = int(np.ceil(n / cols))

    fig = plt.figure(
        "Auto-Pipeline Debug",
        figsize=(20, 10)
    )

    for i, (title, img) in enumerate(debug_steps, start=1):
        ax = plt.subplot(rows, cols, i)

        if img is None:
            ax.set_title(str(title), fontsize=10)
            ax.axis("off")
            continue

        display_img = img

        if crop_box is not None:
            x0, y0, x1, y1 = crop_box
            display_img = display_img[y0:y1 + 1, x0:x1 + 1]

        if display_img.ndim == 2:
            ax.imshow(display_img, cmap="gray")
        else:
            ax.imshow(cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB))

        ax.set_title(str(title), fontsize=10)
        ax.axis("off")

    crop_info = "ohne Crop"

    if crop_box is not None:
        x0, y0, x1, y1 = crop_box
        crop_info = f"Crop: x={x0}:{x1}, y={y0}:{y1}"

    fig.suptitle(
        "Auto-Pipeline Debug | Anzeige gecroppt, Verarbeitung in Vollauflösung | " + crop_info,
        fontsize=12
    )

    plt.tight_layout()

    print("Auto-Pipeline Debugfenster geöffnet. Anzeige ist gecroppt, Verarbeitung bleibt Vollauflösung.")
    plt.show()

# Führt die automatische Konturerkennung aus:
# Maske -> Canny -> HoughLinesP -> Liniencluster -> reduzierte Linien -> Polygonbildung.
def runAutoPipeline(corrected_gray, valid_mask, preview_base_bgr, show_debug=True):
    debug_steps = []

    # 0. Eingangsprüfungen um sicherzustellen dass alle benötigten Komponenten vorhanden sind
    if corrected_gray is None or valid_mask is None:
        raise ValueError("Auto-Pipeline: corrected_gray oder valid_mask fehlt.")

    if corrected_gray.shape[:2] != valid_mask.shape[:2]:
        raise ValueError(
            "Auto-Pipeline: corrected_gray und valid_mask haben unterschiedliche Größen: "
            f"{corrected_gray.shape[:2]} vs. {valid_mask.shape[:2]}"
        )

    if preview_base_bgr.shape[:2] != corrected_gray.shape[:2]:
        raise ValueError(
            "Auto-Pipeline: preview_base_bgr und corrected_gray haben unterschiedliche Größen: "
            f"{preview_base_bgr.shape[:2]} vs. {corrected_gray.shape[:2]}"
        )

    print(
        "Auto-Pipeline Vollauflösung: "
        f"{corrected_gray.shape[1]} x {corrected_gray.shape[0]} px"
    )

    # 1. ROI nur für Anzeige/Debug. Canny läuft wie im alten Skript auf dem korrigierten Vollbild.
    corrected_roi = cv2.bitwise_and(
        corrected_gray,
        corrected_gray,
        mask=valid_mask
    )

    debug_steps.append(("01 ROI / Maske", corrected_roi))

    img_canny = corrected_gray.copy()
    debug_steps.append(("02 Canny Input", corrected_roi))

    # 2. Canny-Kantendetektion
    edges = cv2.Canny(
        img_canny,
        AUTO_CANNY_MIN,
        AUTO_CANNY_MAX
    )
    edges[valid_mask == 0] = 0

    debug_steps.append(("03 Canny", edges))

    # 3. Probalistische Hough-Transformation - Aus der Canny-Kantenmaske werden Liniensegmente extrahiert
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=AUTO_HOUGH_THRESHOLD,
        minLineLength=AUTO_HOUGH_MIN_LINE_LENGTH,
        maxLineGap=AUTO_HOUGH_MAX_LINE_GAP
    )

    hough_img = cv2.cvtColor(corrected_roi, cv2.COLOR_GRAY2BGR)
    line_count = 0

    if lines is not None:
        line_count = len(lines)

        for line in lines:
            x1, y1, x2, y2 = line[0]

            cv2.line(
                hough_img,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

    cv2.putText(
        hough_img,
        f"Hough-Linien: {line_count}",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 255, 0),
        3,
        cv2.LINE_AA
    )

    debug_steps.append(("04 HoughLinesP", hough_img))
    preview_current = hough_img.copy()

    if lines is None or len(lines) == 0:
        return {
            "contour_pixels": None,
            "preview_frame": preview_current,
            "debug_steps": debug_steps,
            "status": "Auto-Pipeline abgebrochen: keine Hough-Linien erkannt",
            "line_count": 0,
            "cluster_count": 0,
        }

    # 4. Linienparameter für jede Hough-Linie berechnen. 
    detected_lines = []

    for line in lines:
        x1, y1, x2, y2 = line[0]

        length = float(np.hypot(x2 - x1, y2 - y1))
        angle = float(getLineAngleDeg((x1, y1, x2, y2)))

        phi = np.radians((angle + 90.0) % 180.0)
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0

        rho = float(
            mx * np.cos(phi)
            + my * np.sin(phi)
        )

        detected_lines.append({
            "pts": (int(x1), int(y1), int(x2), int(y2)),
            "length": length,
            "angle": angle,
            "rho": rho,
        })

    detected_lines = sorted(
        detected_lines,
        key=lambda item: item["length"],
        reverse=True
    )

    # 5. Kolineare Linien clustern - Linien mit ähnlichem Winkel und ähnlichem Abstand zum Ursprung
    # werden einem Gruppen-Cluster zugewiesen

    clusters = []

    for det in detected_lines:
        added = False

        for cluster in clusters:
            ref = cluster[0]

            same_angle = getAngleDiffDeg(det["angle"], ref["angle"]) < AUTO_CLUSTER_ANGLE_TOL_DEG
            same_rho = abs(det["rho"] - ref["rho"]) < AUTO_CLUSTER_RHO_TOL_PX

            if same_angle and same_rho:
                cluster.append(det)
                added = True
                break

        if not added:
            clusters.append([det])

    cluster_img = cv2.cvtColor(corrected_roi, cv2.COLOR_GRAY2BGR)
    cluster_reduced_img = cv2.cvtColor(corrected_roi, cv2.COLOR_GRAY2BGR)

    # 6. Cluster auf jeweils eine repräsentative Linie reduzieren
    # Aus allen Linien eines Clusters wird eine mittlere Linie bestimmt
    cluster_lines = []

    for cluster_idx, cluster in enumerate(clusters):
        total_length = float(
            sum(det["length"] for det in cluster)
        )

        if total_length < AUTO_MIN_CLUSTER_TOTAL_LENGTH:
            continue

        hue = int((cluster_idx * 37) % 180)
        hsv_color = np.uint8([[[hue, 255, 255]]])

        cluster_color = tuple(
            int(c) for c in cv2.cvtColor(
                hsv_color,
                cv2.COLOR_HSV2BGR
            )[0, 0]
        )

        cluster_points = []

        for det in cluster:
            x1, y1, x2, y2 = det["pts"]

            cv2.line(
                cluster_img,
                (x1, y1),
                (x2, y2),
                cluster_color,
                2
            )

            cluster_points.append([x1, y1])
            cluster_points.append([x2, y2])

        cluster_points = np.array(cluster_points, dtype=np.float32)

        vx, vy, x0, y0 = cv2.fitLine(
            cluster_points,
            cv2.DIST_L2,
            0,
            0.01,
            0.01
        )

        vx = float(vx[0])
        vy = float(vy[0])
        x0 = float(x0[0])
        y0 = float(y0[0])

        line_dir = np.array([vx, vy], dtype=np.float64)
        line_point = np.array([x0, y0], dtype=np.float64)

        t_values = [
            float(np.dot(p - line_point, line_dir))
            for p in cluster_points
        ]

        p1 = line_point + min(t_values) * line_dir
        p2 = line_point + max(t_values) * line_dir

        p1_i = tuple(np.round(p1).astype(int))
        p2_i = tuple(np.round(p2).astype(int))

        reduced_angle = float(
            getLineAngleDeg(
                (p1_i[0], p1_i[1], p2_i[0], p2_i[1])
            )
        )

        reduced_length = float(
            np.hypot(
                p2_i[0] - p1_i[0],
                p2_i[1] - p1_i[1]
            )
        )

        mx = (p1_i[0] + p2_i[0]) / 2.0
        my = (p1_i[1] + p2_i[1]) / 2.0

        phi = np.radians((reduced_angle + 90.0) % 180.0)

        reduced_rho = float(
            mx * np.cos(phi)
            + my * np.sin(phi)
        )

        line_data = {
            "cluster_idx": cluster_idx,
            "p1": p1_i,
            "p2": p2_i,
            "angle": reduced_angle,
            "length": reduced_length,
            "rho": reduced_rho,
            "color": cluster_color,
            "total_length": total_length,
        }

        cluster_lines.append(line_data)

        cv2.line(
            cluster_reduced_img,
            p1_i,
            p2_i,
            cluster_color,
            3
        )

        label_pos = (
            int((p1_i[0] + p2_i[0]) / 2),
            int((p1_i[1] + p2_i[1]) / 2)
        )

        cv2.putText(
            cluster_reduced_img,
            str(cluster_idx),
            label_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            4,
            cv2.LINE_AA
        )

        cv2.putText(
            cluster_reduced_img,
            str(cluster_idx),
            label_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
            cv2.LINE_AA
        )

    debug_steps.append(("05 Cluster", cluster_img))
    debug_steps.append(("06 reduzierte Linien", cluster_reduced_img))

    preview_current = cluster_reduced_img.copy()

    if len(cluster_lines) < 4:
        return {
            "contour_pixels": None,
            "preview_frame": preview_current,
            "debug_steps": debug_steps,
            "status": f"Auto-Pipeline abgebrochen: nur {len(cluster_lines)} reduzierte Linien",
            "line_count": line_count,
            "cluster_count": len(cluster_lines),
        }

    # 7. Orthogonale Linienpaare suchen:
    # Da die Substratplatte meist rechteckig ist, werden Linienpaare gesucht, deren Winkel ungefähr
    # 90° voneinander abweichen. 
    orthogonal_img = cluster_reduced_img.copy()
    orthogonal_pairs = []

    for i in range(len(cluster_lines)):
        for j in range(i + 1, len(cluster_lines)):
            a = cluster_lines[i]
            b = cluster_lines[j]

            diff = getAngleDiffDeg(a["angle"], b["angle"])

            if abs(diff - 90.0) < AUTO_ORTHOGONAL_TOL_DEG:
                orthogonal_pairs.append({
                    "score": a["total_length"] + b["total_length"],
                    "diff": diff,
                    "line_a": a,
                    "line_b": b,
                })

    orthogonal_pairs = sorted(
        orthogonal_pairs,
        key=lambda item: item["score"],
        reverse=True
    )

    for rank, pair in enumerate(orthogonal_pairs[:5], start=1):
        a = pair["line_a"]
        b = pair["line_b"]
        diff = pair["diff"]

        cv2.line(orthogonal_img, a["p1"], a["p2"], (255, 255, 255), 7)
        cv2.line(orthogonal_img, b["p1"], b["p2"], (255, 255, 255), 7)

        cv2.line(orthogonal_img, a["p1"], a["p2"], a["color"], 3)
        cv2.line(orthogonal_img, b["p1"], b["p2"], b["color"], 3)

        cv2.putText(
            orthogonal_img,
            f"#{rank}: {diff:.1f} deg",
            (30, 50 + 40 * rank),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            4,
            cv2.LINE_AA
        )

        cv2.putText(
            orthogonal_img,
            f"#{rank}: {diff:.1f} deg",
            (30, 50 + 40 * rank),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 0),
            2,
            cv2.LINE_AA
        )

    debug_steps.append(("07 orthogonale Paare", orthogonal_img))

    # 8. Polygonbildung aus reduzierten Linien
    # Aus zwei parallelen Linien je Hauptrichtung werden vier Geraden gebildet. 
    # Die Schnittpunkte werden ermittelt und ein Polygon erstellt
    # Plausibilität wird geprüft indem... 
    polygon = buildPolygonFromHoughLines(
        cluster_lines,
        valid_mask
    )

    # 9. Ergebnisvisualisierung - Erstellen des Ergebnisbildes. 
    result_img = preview_base_bgr.copy()

    mask_overlay = result_img.copy()
    mask_overlay[valid_mask > 0] = (0, 80, 0)

    result_img = cv2.addWeighted(
        result_img,
        0.85,
        mask_overlay,
        0.15,
        0
    )

    # 10a. Falls kein plausibles Polygon gefunden wurde, wird das Bild mit den erkannten Linien zurückgegeben
    if polygon is None:
        for line in cluster_lines:
            cv2.line(
                result_img,
                line["p1"],
                line["p2"],
                line["color"],
                3
            )

        debug_steps.append(("08 Ergebnis: kein Polygon", result_img))

        return {
            "contour_pixels": None,
            "preview_frame": result_img,
            "debug_steps": debug_steps,
            "status": "Auto-Pipeline abgebrochen: aus Linien konnte kein plausibles Viereck gebildet werden",
            "line_count": line_count,
            "cluster_count": len(cluster_lines),
        }

    # 10b. Das erkannte Polygon wird in Pixelkoordinaten zurückgegeben. 
    # Die Umrechnung in Werkobjektkoordinaten wird im Auto-Zweig von runVisionPipeline() gemacht
    polygon_i = np.round(polygon).astype(np.int32)

    cv2.polylines(
        result_img,
        [polygon_i.reshape(-1, 1, 2)],
        isClosed=True,
        color=(0, 180, 255),
        thickness=4
    )

    # Eckpunkte wie im assistierten Modus zusätzlich als Kreise darstellen
    for idx, p in enumerate(polygon_i, start=1):
        p_tuple = (int(p[0]), int(p[1]))

        cv2.circle(
            result_img,
            p_tuple,
            8,
            (0, 255, 255),
            2
        )

        cv2.putText(
            result_img,
            f"P{idx}",
            (p_tuple[0] + 10, p_tuple[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            3,
            cv2.LINE_AA
        )

    debug_steps.append(("08 Ergebnis: Polygon", result_img))

    return {
        "contour_pixels": polygon.astype(np.float64),
        "preview_frame": result_img,
        "debug_steps": debug_steps,
        "status": f"Auto-Pipeline erfolgreich: Polygon aus {len(cluster_lines)} Linienclustern gebildet",
        "line_count": line_count,
        "cluster_count": len(cluster_lines),
    }

def undistortFrame(frame, camera_mat, distortion):

    if frame is None:
        print("Kein Bild zum Entzerren vorhanden.")
        return None

    ### 1. Entzerren des Bildes (mit intrinsischen Kameraparametern)
    if camera_mat is not None and distortion is not None:
        undistort = cv2.undistort(frame, camera_mat, distortion) # Begradigt alle nichtlineare Verzerrung im Bild. Lineare Verzerrung die durch die Brennweite/Zoom Bildmitte entsteht bleibt erhalten
    else:
        print("Kalibrierdaten unvollständig!")
        return None

    return undistort

def createCADPositions(polygon_points_3d, pipeline_mode, reference_image_data=None):

    # Speichern aller Spanneisenpositionen in Raumkoordinaten
    clamp_positions_cad = []

    for clamp in spanneisen_positions:
        point3d = np.asarray(clamp["point3d"], dtype=np.float64).reshape(3)

        clamp_positions_cad.append({
            "aruco_id": int(clamp["aruco_id"]),
            "X": float(point3d[0]),
            "Y": float(point3d[1]),
            "Z": float(z_weld_surface),
            "angle_z_deg": float(clamp["angle_z_deg"]),
            "angle_offset_deg": 0.0 # Manuell ändern, falls der Marker falsch gedreht ist
        })

    # Speichern aller Polygonpunkte in Raumkoordinaten
    polygon_cad = []

    for i, point3d in enumerate(polygon_points_3d, start=1):

        polygon_cad.append({
            "point_id": int(i),
            "X": float(point3d[0]),
            "Y": float(point3d[1]),
            "Z": float(z_weld_surface)
        })

    cad_data = {
        "unit": "m",
        "pipeline_mode": pipeline_mode,
        "plate_thickness_mm": float(plate_thickness),
        "z_weld_surface": float(z_weld_surface),
        "clamp_extrusion_height_mm": 20.0,
        "spanneisen_positions": clamp_positions_cad,
        "weldable_polygon": polygon_cad,
    }

    if reference_image_data is not None:
        cad_data["reference_image"] = reference_image_data

    '''
    Format von cad_data: 
    {
        "unit": "m",
        "pipeline_mode": "assisted",
        "z_weld_surface": 0.024,
        "spanneisen_positions": [
            {"aruco_id": 12, "x": 0.123, "y": 0.456}
        ],
        "weldable_polygon": [
            {"point_id": 1, "x": 0.100, "y": 0.200},
            {"point_id": 2, "x": 0.300, "y": 0.200}
        ]
    }
    '''

    return cad_data

def createWorkplaneOrthoPhoto(
    image_bgr,
    H_plane_to_image,
    x_min_m,
    x_max_m,
    y_min_m,
    y_max_m,
    pixel_size_m,
    output_path
):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width_px = int(round((x_max_m - x_min_m) / pixel_size_m))
    height_px = int(round((y_max_m - y_min_m) / pixel_size_m))

    # Vier Eckpunkte des gewünschten Ausschnitts im Werkobjekt-KS
    work_corners = np.array([
        [x_min_m, y_min_m, 1.0],
        [x_max_m, y_min_m, 1.0],
        [x_max_m, y_max_m, 1.0],
        [x_min_m, y_max_m, 1.0]
    ], dtype=np.float64)

    image_corners = []

    for p_work in work_corners:
        p_img = H_plane_to_image @ p_work

        u = p_img[0] / p_img[2]
        v = p_img[1] / p_img[2]

        image_corners.append([u, v])

    src_pts = np.array(image_corners, dtype=np.float32)

    # Zielbild: Draufsicht
    # Achtung: Bildkoordinaten haben y nach unten
    dst_pts = np.array([
        [0, height_px - 1],
        [width_px - 1, height_px - 1],
        [width_px - 1, 0],
        [0, 0]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)

    ortho = cv2.warpPerspective(
        image_bgr,
        M,
        (width_px, height_px),
        flags=cv2.INTER_LINEAR
    )

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_ok = cv2.imwrite(str(output_path), ortho)

    # Fallback, falls cv2.imwrite unter Windows/Pfadproblemen still fehlschlägt
    if not write_ok or not output_path.exists():
        encode_ok, buffer = cv2.imencode(".png", ortho)

        if not encode_ok:
            raise RuntimeError("Referenzbild konnte nicht als PNG kodiert werden.")

        with open(output_path, "wb") as f:
            f.write(buffer.tobytes())

    if not output_path.exists():
        raise RuntimeError(f"Referenzbild wurde nicht gespeichert: {output_path}")

    print(f"Referenzbild gespeichert: {output_path}")

    return {
        "path": output_path.name,
        "type": "workplane_orthophoto",
        "unit": "m",
        "x_min": float(x_min_m),
        "x_max": float(x_max_m),
        "y_min": float(y_min_m),
        "y_max": float(y_max_m),
        "z": float(z_weld_surface),
        "pixel_size_m": float(pixel_size_m)
    }



def draw_point_coordinate_label(frame, u, v, point3d, point_name="P"):
    u_int = int(round(u))
    v_int = int(round(v))

    x_mm = point3d[0] * 1000.0
    y_mm = point3d[1] * 1000.0
    z_mm = point3d[2] * 1000.0

    text = f"{point_name}: X={x_mm:.1f} Y={y_mm:.1f} Z={z_mm:.1f} mm"

    cv2.circle(
        frame,
        (u_int, v_int),
        8,
        (0, 255, 255),
        -1
    )

    # Offset zum Punkt für den Text
    text_x = u_int + 12
    text_y = v_int -12

    text_x = max(10, min(text_x, frame.shape[1] - 420))
    text_y = max(10, min(text_y, frame.shape[0] - 10))

    cv2.putText(
        frame,
        text,
        (text_x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0, 255, 255),
        2, 
        cv2.LINE_AA
    )


def runVisionPipeline(frame, camera_info, calibration_file, plate_mm, pipeline_mode, assisted_polygon_pixels=None):
    global calib_data, camera_matrix, dist_coeffs, cam_id, cam_name, resolution_width, resolution_height
    global img_og, img_cpy, img_undistort, img_charuco, img_aruco
    global H_image_to_plane, H_plane_to_image
    global plate_thickness, plate_thickness_m, z_weld_surface
    global spanneisen_positions

    # Laden der Kalibrierdaten
    calib_data = np.load(calibration_file)
    camera_matrix = calib_data["camera_matrix"]
    dist_coeffs = calib_data["dist_coeffs"]

    # Laden des Bilds und der Kameradaten
    img_og = frame
    cam_id = camera_info["camera_id"]
    cam_name = camera_info["camera_name"]
    resolution_width = camera_info["resolution_width"]
    resolution_height = camera_info["resolution_height"]

    plate_thickness = plate_mm
    plate_thickness_m = plate_thickness / 1000.0 # Umwandlung in Meter
    z_weld_surface = SPANNPLATTE_HEIGHT + plate_thickness_m # Die Höhe über dem Werkobjekt-KS auf dem die Ebene für die Homographie aufgespannt wird


    print(camera_matrix)
    print(dist_coeffs)
    print(cam_id)
    print(cam_name)
    print(resolution_width)
    print(resolution_height)

    contour_pixels = None
    points3d = []
    auto_status = None
    auto_line_count = 0
    auto_cluster_count = 0

    if img_og is None:
        raise FileNotFoundError("Bild konnte nicht geladen werden.")

    img_cpy = img_og.copy()

    img_undistort = undistortFrame(img_cpy, camera_matrix, dist_coeffs)




    ##### START VISION PIPELINE #####

    #### ArUco, ChArUco Detection und Extrinsics/Homography Berechnung ####

    img_charuco = getCharucoPose()

    #### COORDINATE TRANSFORM ####

    # Offset des Werkobjektkoordinatensystems in die Homographie einbeziehen (inkl. Rotation und Translation des Koordinatensystems (auch in Z))
    H_plane_to_image, H_image_to_plane = getWorkPlaneHomography()

    #### COORDINATE TRANSFORM ####

    ### Erstellen des Ortho Fotos für Referenz im CAD
    # Vorher Beleuchtungskorrektur für gute Sicht

    # Graubild
    img_gray = cv2.cvtColor(img_undistort, cv2.COLOR_BGR2GRAY)

    # Beleuchtungskorrektur - 1. Starken Blur aufs Bild anwenden 2. Vom Graubild abziehen --> normalisiert alle Beleuchtungsunterschiede in der Szene
    # Starker Blur um die diffuse Beleuchtung zu bekommen
    illumination = cv2.GaussianBlur(img_gray, (151, 151), 0)
    # Beleuchtung abziehen und mittleren Grauwert wieder addieren
    img_light_corrected = cv2.addWeighted(img_gray, 1.0, illumination, -1.0, 128)

    img_light_corrected_bgr = cv2.cvtColor(img_light_corrected, cv2.COLOR_GRAY2BGR)

    reference_image_data = createWorkplaneOrthoPhoto(
        image_bgr=img_light_corrected_bgr,
        H_plane_to_image=H_plane_to_image,
        x_min_m=-0.35,
        x_max_m=0.35,
        y_min_m=-0.35,
        y_max_m=0.35,
        pixel_size_m=0.001, #  Das bestimmt nur, wie pixelig das Bild später im CAD sein wird, es hat keinen Einfluss auf die Skalierung des Bildes
        output_path=Path(__file__).parent / "spannsituation_ortho.png"
    )

    #### Masken für Aufspannplatte und Spanneisen ####

    # 1. Aufspannplattenmaske erzeugen:
    # Vom ChArUco-Board aus, wird die Aufspannplatte maskiert, damit alle Kanten außerhalb nicht mit einbezogen werden
    spannplatte_mask = createSpannplatteMask(img_undistort.shape)

    # 2. Aufspannplattenmaske für die ArUco-Filterung erweitern:
    # Falls ein Spanneisen über der Kante hängt wird dieser auch noch erkannt
    # Spanneisen die unten gelagert werden, sollten aber ignoriert werden
    aruco_filter_mask = spannplatte_mask.copy()

    if SPANNPLATTE_ARUCO_DILATE_PX > 0:
        k = int(SPANNPLATTE_ARUCO_DILATE_PX)

        if k % 2 == 0:
            k += 1

        aruco_filter_mask = cv2.dilate(
            aruco_filter_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)),
            iterations=1
        )

    #### Erkennen und Maskieren der ArUco-Spanneisen ####

    # 3. ArUco-Marker der Spanneisen erkennen
    # Es werden nur die ArUco-Marker genommen die innerhalb der aruco_filter_mask liegen
    spanneisen_positions = []

    img_aruco = detect_aruco(
        img_charuco,
        valid_mask=aruco_filter_mask
    )
    # Die Maskierung der Spanneisen wird ebenfalls erweitert (dilatiert) um Schattierungen und alle Kanten der Spanneisen für die Konturerkennung auszuschließen
    spanneisen_mask = createSpanneisenMask(img_undistort.shape)

    # 4. Aufspannplattenmaske für die automatische Kantenerkennung
    # Suchbereich der automatischen Kantenerkennung nach innen verkleinern.
    # Dadurch werden die Randkante der Aufspannplatte sowie schmale, nahe am
    # Plattenrand liegende Strukturen nicht an Canny und HoughLinesP übergeben.
    spannplatte_edge_mask = spannplatte_mask.copy()

    if AUTO_EDGE_MASK_ERODE_RADIUS_PX > 0:
        radius = int(AUTO_EDGE_MASK_ERODE_RADIUS_PX)
        kernel_size = 2 * radius + 1

        erode_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (kernel_size, kernel_size)
        )

        spannplatte_edge_mask = cv2.erode(
            spannplatte_edge_mask,
            erode_kernel,
            iterations=1
        )

    # 5. Gültigen Suchbereich für die Substratplattenerkennung bilden:
    # erodierter Innenbereich der Aufspannplatte minus dilatierte Spanneisenmaske.
    # Die Spanneisenmaske wird hierbei nicht weiter verändert.
    auto_edge_mask = cv2.bitwise_and(
        spannplatte_edge_mask,
        cv2.bitwise_not(spanneisen_mask)
    )



    # 6. Bild vorbereiten zur Visualisierung
    # Zeichnet ArUco & ChArUco-Informationen ein zur Anzeige in der Bildvorschau
    img_work = draw_work_axes(img_aruco, axis_length=0.05)

    contour_pixels = None
    points3d = []

    ##### Auto-Pipeline #####
    if pipeline_mode == "auto":

        ### Automatische Kantenerkennung ###

        ## 7. Start der Auto-Pipeline
        # Nutzt das beleuchtungskorrigierte Graubild und die erstellten Masken
        auto_result = runAutoPipeline(
            corrected_gray=img_light_corrected,
            valid_mask=auto_edge_mask,
            preview_base_bgr=img_work,
            show_debug=True
        )

        # 8. Debug-Panel anzeigen. Zeigt alle Schritte der Pipeline zur Betrachtung durch den Nutzer
        if auto_result.get("debug_steps") is not None:
            showAutoPipelinePanel(auto_result["debug_steps"])

        # 9. Ergebnis der Auto-Pipeline. contour_pixels ist None wenn kein plausibles Polygon gefunden werden konnte
        contour_pixels = auto_result.get("contour_pixels", None)

        if contour_pixels is None:
            img_work = auto_result["preview_frame"].copy()
            points3d = []

        else:
            contour_pixels = np.asarray(contour_pixels, dtype=np.float64)

            pts_draw = np.round(contour_pixels).astype(np.int32).reshape(-1, 1, 2)

            cv2.polylines(
                img_work,
                [pts_draw],
                isClosed=True,
                color=(0, 180, 255),
                thickness=4
            )

            # Pixelkoordinaten des Polygons in Werkobjektkoordinaten transformieren
            for u, v in contour_pixels:
                point3d = pixel_to_3dplane(
                    float(u),
                    float(v),
                    z_weld_surface
                )
                points3d.append(point3d)

            # Einzeichnen und beschriften der Eckpunkte des Polygons
            for i, ((u, v), point3d) in enumerate(zip(contour_pixels, points3d), start=1):
                # Eckpunkte als Kreise wie im assistierten Modus
                cv2.circle(
                    img_work,
                    (int(round(u)), int(round(v))),
                    8,
                    (0, 255, 255),
                    2
                )

                draw_point_coordinate_label(
                    img_work,
                    u,
                    v,
                    point3d,
                    point_name=f"P{i}"
                )
        # Statusdaten für GUI
        auto_status = auto_result.get("status", "Auto-Pipeline ausgeführt")
        auto_line_count = auto_result.get("line_count", 0)
        auto_cluster_count = auto_result.get("cluster_count", 0)

    # Falls assistierter Modus, wird Kantenerkennung übersprungen
    elif pipeline_mode == "assisted":
        if assisted_polygon_pixels is None:
            raise ValueError("Assistierter Modus gestartet, aber keine Polygonpunkte übergeben.")
        
        contour_pixels = np.asarray(
            assisted_polygon_pixels,
            dtype=np.float64
        )

        if contour_pixels.ndim != 2 or contour_pixels.shape[1] != 2:
            raise ValueError("Polygonpunkte müssen die Form (n, 2) haben")
        
        if len(contour_pixels) < 3:
            raise ValueError("Das assistierte Polygon benötigt mindestens 3 Punkte.")
        
        # Umrechnung von Pixelpunkten in Raumpunkte
        for u, v in contour_pixels:
            point3d = pixel_to_3dplane(
                float(u),
                float(v),
                z_weld_surface
            )
            points3d.append(point3d)

        pts_draw = np.round(contour_pixels).astype(np.int32).reshape(-1, 1, 2)

        cv2.polylines(
            img_work,
            [pts_draw],
            isClosed=True,
            color=(0, 180, 255),
            thickness=3
        )

        for i, ((u, v), point3d) in enumerate(zip(contour_pixels, points3d), start=1):
            draw_point_coordinate_label(
                img_work,
                u,
                v,
                point3d,
                point_name=f"P{i}"
            )


        


    ##### ÜBERGABE DER ERGEBNISSE #####

    processed_frame = img_work.copy()

    # Konturkoordinaten, Spanneisenpositionen
    
    cad_data = createCADPositions(
        polygon_points_3d=points3d,
        pipeline_mode=pipeline_mode,
        reference_image_data=reference_image_data
    )
    


    if pipeline_mode == "auto" and auto_status is not None:
        status_text = (
            f"{auto_status}\n"
            f"Polygon: {len(points3d)} Punkte | "
            f"Spanneisen: {len(spanneisen_positions)}\n"
            f"Hough-Linien: {auto_line_count} | "
            f"Liniencluster: {auto_cluster_count}"
        )
    else:
        status_text = (
            "VisionPipeline erfolgreich\n"
            f"Polygon: {len(points3d)} Punkte | "
            f"Spanneisen: {len(spanneisen_positions)}"
        )

    msg = {
        "plate_detected": len(points3d) >= 3,
        "clamp_count": len(spanneisen_positions),
        "status": status_text
    }
    
    return processed_frame, msg, cad_data