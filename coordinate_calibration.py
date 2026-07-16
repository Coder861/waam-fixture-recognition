import numpy as np
from math import sin, cos, radians, degrees, atan2, sqrt

''' 
KI Notiz: Mathematische Grundlage wurde recherchiert und per Hand durchgerechnet. 
Auf Basis dessen und Angaben zu den Rahmenbedingungen der Kalibrierung (wie die Punkte gemessen werden, wie der Offset im bisherigen Pipeline-Skript verarbeitet wird),
wurde ein Entwurfs-Skript per KI entworfen. 
Jede Zeile wurde händisch überprüft, in vielen Teilen angepasst, zusätzlich kommentiert und nicht ungeprüft übernommen. 
'''
##### GLOBALE VARIABLEN #####

## Eingabewerte ##

# Angenommene Offset-Werte zwischen ChArUco-KS und Werkobjekt-KS (Augenmaß)
OLD_OFFSETS = {
    "OFFSET_X": -0.254044617, # in Meter
    "OFFSET_Y": 0.249578168, # in Meter
    "OFFSET_Z": 0.0225, # in Meter
    "OFFSET_Y_DEG": 180.0, # in Grad
    "OFFSET_Z_DEG": 55.144294937 # in Grad
}

# Punkkoordinaten aus der Robotersteuerung

# p_i Soll-Punkt: Koordinate die einprogrammiert wurde und anschließend automatisch mit dem Roboterarm angefahren wurde
SOLL_POINTS_MM = [
    [163.611, 157.083],
    [156.114, -167.404],
    [-167.617, -160.326],
    [-212.396, 91.199],
    [-57.67, 313.395],
]

# q_i Ist-Punkt: Der Punkt der manuell angefahren werden musste, um mit dem TCP direkt über den Referenzpunkt zu stehen

IST_POINTS_MM = [
    [163.97, 157.48],
    [156.32, -167.12],
    [-167.63, -159.48],
    [-212.03, 91.06],
    [-57.1, 312.44],
]

# Umrechnung von mm in Meter:
MILI_TO_METER = 0.001

# Rotationsreihefolge (wichtig, weil erst Z dann Y ist anders als Y dann Z)
# In der Pipeline ist so: R_work_to_charuco = Ry @ Rz, also wird erst um Y gedreht, dann um Z
ROTATION_ORDER = "Y_THEN_Z" # 

# Falls Korrektur in die falsche Richtung zeigt auf TRUE setzen
USE_INVERSE_DELTA = False

SHOW_INPUT_TABLE = True

##### GLOBALE VARIABLEN #####





def run_calibration():

    # 1. Berechnet aus Soll-/Ist-Punkte die ebene Delta-Transformation

    # 2. Baut aus den bisherigen Pipeline-Offsets die alte Transformation für ChArUco

    # 3. Verkettet die Transformationsmatrizen um die Koordinatensystem mathematisch ordentlich zu verketten

    # 4. Extrahiert aus der neuen Transformationmatrix die Offsetwerte, die so ins Pipeline-Skript kopiert werden können

    #################

    if SHOW_INPUT_TABLE:
        print_input_point_table(SOLL_POINTS_MM, IST_POINTS_MM)


    # 1. Berechnet dx, dy, und dRot_Z aus den korrespondierenden Soll- und Ist-Punkten
    delta_result = estimate_planar_delta_from_points(
        SOLL_POINTS_MM,
        IST_POINTS_MM
    )

    # 2. Baut 4x4 Trawnsformationmatrix aus den jetzigen Offset-Werten aus der Pipeline, wird später mit der Kalibrier-Transformationsmatrix verrechnet
    T_old = build_transform_from_pipeline_offsets(
        OLD_OFFSETS["OFFSET_X"],
        OLD_OFFSETS["OFFSET_Y"],
        OLD_OFFSETS["OFFSET_Z"],
        OLD_OFFSETS["OFFSET_Y_DEG"],
        OLD_OFFSETS["OFFSET_Z_DEG"],
        rotation_order = ROTATION_ORDER
    )

    # Translationsoffset in Meter umwandeln
    dx_m = delta_result["dx"] * MILI_TO_METER
    dy_m = delta_result["dy"] * MILI_TO_METER

    # Erstellt die Transformationsmatrix zwischen dem angenäherten Werkobjekt-KS W0 und dem realen Werkobjekt-KS Wr
    T_delta = build_delta_transform(
        dx_m,
        dy_m,
        delta_result["drot_z_deg"]
    )

    # Falls der Offset falsch herum ist
    if USE_INVERSE_DELTA:
        T_delta_used = np.linalg.inv(T_delta)
    else:
        T_delta_used = T_delta

    # Neue Transformationmatrix vom ChArUco-KS ins reale Werkobjekt-KS Wr
    T_new = T_old @ np.linalg.inv(T_delta_used)

    # Extrahieren der einzelnen Offsets aus der neuen Transformationsmatrix
    new_offsets = extract_pipeline_offsets_from_transform(
        T_new,
        rotation_order=ROTATION_ORDER
    )

    # Anzeigen der Kalibrierergebnisse in der Konsole
    print_calibration_result(
        delta_result,
        new_offsets
    )

    return {
        "delta": delta_result,
        "old_offsets": OLD_OFFSETS,
        "new_offsets": new_offsets,
        "T_old": T_old,
        "T_delta": T_delta,
        "T_new": T_new
    }

# Berechnet dx, dy, und dRot_Z aus den korrespondierenden Soll- und Ist-Punkten
def estimate_planar_delta_from_points(soll_points, ist_points):
    # Also mathematisch: 
    # q_i = Rz(theta) * p_i + t

    # mit:
    # p_i = Sollpunkt
    # q_i = Istpunkt
    # t = [dx, dy]

    # Ergebnis ist dx, dy in gleicher Einheit wie die Eingabepunkte (in Meter)
    # dRot_Z in Grad
    # RMS Fehelr in gleicher Einheit wie die Eingabepunkte (in Meter)
    # Maximalfehler in gleicher Einheit wie die Eingabepunkte (in Meter)

    # Umwandlen der Punkte in homogene Vektoren
    P, Q = prepare_points(soll_points, ist_points)
    
    # Mittelwerte berechnen
    p_mean = np.mean(P, axis=0)
    q_mean = np.mean(Q, axis=0)

    # Punkte wo die Translation raus ist und so die Rotation sichtbar wird
    P_centered = P - p_mean
    Q_centered = Q - q_mean

    C = 0.0
    S = 0.0

    for p, q in zip(P_centered, Q_centered):
        px, py = p
        qx, qy = q

        # Sume der Skalarprodukte
        C += px * qx + py * qy

        # Sume der Z-Komponenten der 2D-Kreuzprodukte
        S += px * qy - py * qx

    # Berechnung der Z-Rotation
    drot_z_rad = atan2(S, C)
    drot_z_deg = degrees(drot_z_rad)

    R2 = rot_2d(drot_z_rad) # Rotation als 2D Rotationsmatrix ausgedrückt
    
    # Berechnung der Translation, welche sich durch die Verschiebung der Mittelpunkten ergibt
    t2 = q_mean - R2 @ p_mean


    # Residual Berechnungen (Einzelfehler, RMS, Max)

    # Verschiebung der Punkte, mit der berechneten Transformationsmatrix
    q_pred = transform_points_2d(P, R2, t2)
    
    # Abweichungen berechnen (Ist-Punkte mit den korrigierten Soll-Punkten subtrahieren um die Abweichung zu erhalten)
    residuals = Q - q_pred
    point_errors = np.linalg.norm(residuals, axis=1)

    rms_error = sqrt(np.mean(point_errors ** 2)) # ** 2 ist hoch 2
    max_error = float(np.max(point_errors))

    return {
        "dx": float(t2[0]),
        "dy": float(t2[1]),
        "drot_z_deg": float(drot_z_deg),
        "drot_z_rad": float(drot_z_rad),
        "rms_error": float(rms_error),
        "max_error": max_error,
        "predicted_ist_points": q_pred,
        "residuals": residuals,
        "point_errors": point_errors,
        "p_mean": p_mean,
        "q_mean": q_mean
    }




## HILFSFUNKTIONEN
def prepare_points(soll_points, ist_points):

    P = np.asarray(soll_points, dtype=np.float64)
    Q = np.asarray(ist_points, dtype=np.float64)

    # Verschiedene Checks, ob die Punkte das richtige Format haben
    if P.shape != Q.shape:
        raise ValueError("Soll- und Ist-Punkte müssen die gleiche Anzahl und Dimension haben")
    
    if P.ndim != 2 or P.shape[1] != 2:
        raise ValueError("Punkte müssen als Nx2-Liste angegeben werden")
    
    if P.shape[0] < 2:
        raise ValueError("Mindestens zwei Punktpaare erforderlich. Besser sind vier")

    return P, Q

# Erstellt eine Rotationsmatrix mit einem beliebigen Winkel angle_rad
def rot_2d(angle_rad):

    c = cos(angle_rad)
    s = sin(angle_rad)

    rot_matrix = np.array([
        [c, -s],
        [s, c]
    ])

    '''
    [cos(a), -sin(a)]
    [sin(a), cos(a)]
    
    '''

    return rot_matrix

# Wendet q_hat = R * p + t auf eine Punktliste an: q_hat sind die korrigierten Punkte
def transform_points_2d(points, R, t):

    P = np.asarray(points, dtype=np.float64)

    return (R @ P.T).T + t

# 3D-Rotation um die Y-Achse
def rot_y(angle_deg):

    a = radians(angle_deg)
    c = cos(a)
    s = sin(a)

    rot_matrix_y = np.array([
        [c, 0.0, s],
        [0.0, 1.0, 0.0],
        [-s, 0.0, c]
    ], dtype=np.float64)

    '''
    [cos(a), 0.0, sin(a)],
    [0.0, 1.0, 0.0],
    [-sin(a), 0.0, cos(a)]
    '''

    return rot_matrix_y

# 3D-Rotation um die Z-Achse
def rot_z(angle_deg):

    a = radians(angle_deg)
    c = cos(a)
    s = sin(a)

    rot_matrix_z = np.array([
        [c, -s, 0.0],
        [s, c, 0.0],
        [0.0, 0.0, 1.0]
    ])

    '''
    [cos(a), -sin(a), 0.0],
    [sin(a), cos(a), 0.0],
    [0.0, 0.0, 1.0]
    '''

    return rot_matrix_z

# Baut 4x4 Transformationmatrix aus den jetzigen Offset-Werten aus der Pipeline, wird später mit der Kalibrier-Transformationsmatrix verrechnet
def build_transform_from_pipeline_offsets(x, y, z, deg_y, deg_z, rotation_order="Y_THEN_Z"):
    
    if rotation_order == "Y_THEN_Z":
        R = rot_z(deg_z) @ rot_y(deg_y)

    elif rotation_order == "Z_THEN_Y":
        R = rot_y(deg_y) @ rot_z(deg_z)

    else: 
        raise ValueError("Unbekannte Rotationsreihenfolge")
    
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = np.array([x, y, z], dtype=np.float64)

    return T

# Baut die Delta-Transformatin vom angenäherten Werkobjekt-KS W0 zum realen Werkobjekt-KS Wr
def build_delta_transform(dx_m, dy_m, drot_z_deg):

    # Mathematisch: q_i = Rz(d_rot_z) * p_i + [dx, dy]

    T = np.eye(4, dtype=np.float64)

    T[:3, :3] = rot_z(drot_z_deg)
    T[:3, 3] = np.array([dx_m, dy_m, 0.0], dtype=np.float64)

    return T

def print_calibration_result(delta_result, new_offsets):

    print("\n==============================")
    print("Kalibrier-Delta aus Punktpaaren")
    print("==============================")
    print(f"dx:          {delta_result['dx']:.6f} mm")
    print(f"dy:          {delta_result['dy']:.6f} mm")
    print(f"dRotZ:       {delta_result['drot_z_deg']:.6f} °")
    print(f"RMS-Fehler:  {delta_result['rms_error']:.6f} mm")
    print(f"Max-Fehler:  {delta_result['max_error']:.6f} mm")

    print("\nPunktfehler:")
    for i, error in enumerate(delta_result["point_errors"], start=1):
        ex, ey = delta_result["residuals"][i - 1]
        print(f"Punkt {i}: ex={ex: .6f} mm, ey={ey: .6f} mm, Betrag={error:.6f} mm")

    print("\n==============================================")
    print("Neue Offsetwerte für das Pipeline-Skript")
    print("==============================================")
    print(f"WORK_ORIGIN_OFFSET_X = {new_offsets['OFFSET_X']:.9f}")
    print(f"WORK_ORIGIN_OFFSET_Y = {new_offsets['OFFSET_Y']:.9f}")
    print(f"WORK_ORIGIN_OFFSET_Z = {new_offsets['OFFSET_Z']:.9f}")
    print(f"WORK_ROTATION_Y_DEG  = {new_offsets['OFFSET_Y_DEG']:.9f}")
    print(f"WORK_ROTATION_Z_DEG  = {new_offsets['OFFSET_Z_DEG']:.9f}")

    return


def print_input_point_table(soll_points, ist_points):

    P, Q = prepare_points(soll_points, ist_points)

    print("\n==============================================")
    print("Eingegebene Soll- und Ist-Punkte")
    print("Einheit: mm")
    print("==============================================")

    header = (
        f"{'Punkt':>5} | "
        f"{'Soll X':>10} {'Soll Y':>10} | "
        f"{'Ist X':>10} {'Ist Y':>10} | "
        f"{'dX roh':>10} {'dY roh':>10} {'Abstand':>10}"
    )

    print(header)
    print("-" * len(header))

    for i, (p, q) in enumerate(zip(P, Q), start=1):
        dx = q[0] - p[0]
        dy = q[1] - p[1]
        dist = np.linalg.norm(q - p)

        print(
            f"{i:5d} | "
            f"{p[0]:10.3f} {p[1]:10.3f} | "
            f"{q[0]:10.3f} {q[1]:10.3f} | "
            f"{dx:10.3f} {dy:10.3f} {dist:10.3f}"
        )

    print()

    return


# Konvertierung in Offsetwerte für das Pipeline-Skript

# Zerpflückt die neue Transformationsmatrix in die einzelnen Offset-Werte die man in das Pipeline-Skript reinkopieren kann
def extract_pipeline_offsets_from_transform(T, rotation_order="Y_THEN_Z"):
    
    '''
    Offsets:
    WORK_ORIGIN_OFFSET_X
    WORK_ORIGIN_OFFSET_Y
    WORK_ORIGIN_OFFSET_Z
    WORK_ROTATION_Y_DEG
    WORK_ROTATION_Z_DEG

    Diese müssen unbedingt in der richtigen Rotationsreihenfolge geholt werden, sonst wird in die falsche Richtung um Z rotiert
    
    '''

    R = T[:3, :3] # Schneidet die Rotationsmatrix heraus (3x3)
    t = T[:3, 3] # Schneidet den Translationsvektor heraus (dritte Spalte)
    
    x = float(t[0]) # Holt X aus t
    y = float(t[1]) # Holt Y aus t
    z = float(t[2]) # Holt Z aus t (Offset bleibt hier erhalten)

    if rotation_order == "Y_THEN_Z":
        '''
        Für: R = Rz(z) @ Ry(y)
        Matrixform soll: 
        [cos(z)*cos(y)  -sin(z) cos(z)*sin(y)]
        [sin(z)*cos(y)  cos(z)  sin(z)*sin(y)]
        [-sin(y)        0       cos(y)]
        '''

        deg_y = degrees(atan2(-R[2, 0], R[2, 2]))
        deg_z = degrees(atan2(-R[0, 1], R[1, 1]))

    elif rotation_order == "Z_THEN_Y":
        '''
        Für: R = Ry(y) @ Rz(z)
        Matrixform soll: 
        [cos(z)*cos(y)  -sin(z) cos(z)*sin(y)]
        [sin(z)*cos(y)  cos(z)  sin(z)*sin(y)]
        [-sin(y)        0       cos(y)]
        '''

        deg_y = degrees(atan2(-R[0, 2], R[2, 2]))
        deg_z = degrees(atan2(-R[1, 0], R[1, 1]))

    else:
        raise ValueError("Unbekannte Rotationsreihenfolge")

    return {
        "OFFSET_X": x,
        "OFFSET_Y": y,
        "OFFSET_Z": z,
        "OFFSET_Y_DEG": float(deg_y),
        "OFFSET_Z_DEG": float(deg_z)
    }


if __name__ == "__main__":
    result = run_calibration()
