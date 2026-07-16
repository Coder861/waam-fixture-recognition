# WAAM-Plattenerkennung

Kameragestützte Unterstützung des Rüstprozesses einer WAAM-Zelle durch geometrische Referenzierung, assistierte Erfassung der nutzbaren Schweißfläche und Übergabe der erzeugten Geometriedaten an Rhino.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![Python](https://img.shields.io/badge/Python-3.13-3776AB)

<!-- DOI-Badge nach Veröffentlichung des Zenodo-Eintrags aktivieren:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21275491.svg)](https://doi.org/10.5281/zenodo.21275491)
-->

<p align="center">
  <img src="docs/media/waam_workflow.gif"
       alt="Kameragestützter Workflow zur Erfassung der WAAM-Aufspannsituation"
       width="900">
</p>

> Das GIF wird ergänzt, sobald die Videoaufnahme des vollständigen Rüstworkflows aufbereitet wurde.

## Überblick

Dieses Repository enthält den im Rahmen einer Bachelorarbeit entwickelten Softwareprototyp zur kameragestützten Unterstützung des Rüst- und Kalibrierprozesses einer Wire-Arc-Additive-Manufacturing-Zelle (WAAM).

Das System erfasst die Aufspannsituation mit einer über der Arbeitsfläche montierten Monokamera. Ein ChArUco-Board dient zur geometrischen Referenzierung der Kameraaufnahme. Bildpunkte können dadurch in das Werkobjektkoordinatensystem der WAAM-Zelle transformiert und anschließend an den CAD/CAM-Workflow übergeben werden.

Der implementierte Workflow umfasst insbesondere:

* intrinsische Kamerakalibrierung,
* Erkennung eines ChArUco-Referenzboards,
* Bestimmung der Kamerapose,
* Transformation von Bildpunkten in Werkobjektkoordinaten,
* Erstkalibrierung zwischen ChArUco- und Werkobjektkoordinatensystem,
* assistierte Definition der nutzbaren Schweißfläche,
* Erkennung markierter Spannmittel über ArUco-Marker,
* JSON-basierte Datenübergabe,
* Erzeugung der Platten-, Schweißflächen- und Spannmittelgeometrien in Rhino.

## Entwicklungsstand

Die Software ist ein wissenschaftlicher Prototyp und keine industriell qualifizierte Anwendung.

Der **assistierte Erfassungsmodus** stellt den primär validierten Workflow dar. Dabei werden die Eckpunkte der nutzbaren Schweißfläche durch den Anwender im Kamerabild ausgewählt und anschließend automatisch in Werkobjektkoordinaten transformiert.

Eine Pipeline zur **automatischen Kantenerkennung** ist ebenfalls enthalten. Ihre Zuverlässigkeit ist gegenwärtig jedoch stark von Beleuchtung, Reflexionen, Plattenoberfläche und Hintergrundstruktur abhängig. Sie ist deshalb als experimenteller Entwicklungsstand und nicht als uneingeschränkt robuster Betriebsmodus zu verstehen.

Die Software ist nicht Bestandteil der sicherheitsgerichteten Steuerung der WAAM-Zelle und ersetzt weder die Prüfung der realen Aufspannsituation noch die Kollisionskontrolle durch qualifiziertes Personal.

## Systemvoraussetzungen

| Komponente           | Anforderung                                             |
| -------------------- | ------------------------------------------------------- |
| Betriebssystem       | Windows 10 oder Windows 11                              |
| Python               | Python 3.13, entsprechend dem validierten Softwarestand |
| Python-Pakete        | Siehe `requirements.txt`                                |
| Kamera               | USB-Kamera mit ausreichender Auflösung                  |
| Getestete Kamera     | EMEET SmartCam Nova 4K bei 3840 × 2160 Pixeln           |
| CAD-System           | Rhino mit Python-ScriptEditor                           |
| Referenzierung       | ChArUco-Board                                           |
| Spannmittelerfassung | ArUco-Marker                                            |
| Erstkalibrierung     | Geeignete Referenzpunkte beziehungsweise Referenzkörper |

Andere Kameras, Auflösungen oder Montagepositionen erfordern eine erneute intrinsische Kamerakalibrierung. Abweichende Software- und Hardwarekonfigurationen wurden nicht systematisch validiert.

Die Kameraanbindung verwendet im aktuellen Stand Windows-spezifische Backends. Eine Nutzung unter Linux oder macOS erfordert Anpassungen und eine erneute Prüfung der Kameraerkennung sowie der Pfadbehandlung.

## Installation

### Repository klonen

```powershell
git clone https://github.com/Coder861/WAAM-Plattenerkennung.git
cd WAAM-Plattenerkennung
```

Alternativ kann der Quellcode als ZIP-Datei über GitHub oder über den archivierten Zenodo-Datensatz heruntergeladen und entpackt werden.

### Virtuelle Umgebung einrichten

Zur automatischen Einrichtung kann unter Windows die folgende Datei ausgeführt werden:

```powershell
install_requirement.bat
```

Das Installationsskript:

1. prüft, ob eine virtuelle Umgebung `.venv` vorhanden ist,
2. erstellt die Umgebung bei Bedarf,
3. aktualisiert `pip`,
4. installiert die in `requirements.txt` angegebenen Abhängigkeiten.

Die virtuelle Umgebung wird nicht im Repository gespeichert und muss auf jedem Zielsystem neu erzeugt werden.

Alternativ kann die Einrichtung manuell erfolgen:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Konfiguration

Vor der ersten Ausführung müssen die installations- und aufbauspezifischen Parameter geprüft werden. Dazu gehören insbesondere:

* Kamera-ID,
* Kameraauflösung,
* Pfad zur intrinsischen Kalibrierdatei,
* Geometrie des verwendeten ChArUco-Boards,
* Transformation zwischen ChArUco- und Werkobjektkoordinatensystem,
* Höhe der Substratplattenebene,
* Zuordnung der ArUco-IDs zu den Spannmittelgeometrien,
* Speicherpfade für Bilder, JSON-Dateien und Referenzaufnahmen,
* Pfad zum externen Python-Interpreter bei der Ausführung aus Rhino.

Kalibrierdateien sind an die jeweilige Kamera, Auflösung und optische Konfiguration gebunden. Sie dürfen nicht ohne erneute Prüfung auf ein anderes Kamerasystem übertragen werden.

Absolute lokale Pfade innerhalb der Skripte müssen gegebenenfalls an das Zielsystem angepasst werden.

## Verwendung

### Integrierter Workflow über Rhino

Für die CAD-Integration wird `rhinoWAAMContour.py` innerhalb von Rhino ausgeführt.

Das Skript:

1. startet die externe Anwendung `mainGUI.py`,
2. wartet auf den Abschluss der kameragestützten Erfassung,
3. liest die erzeugten JSON-Daten ein,
4. erzeugt die CAD-Geometrien der Substratplatte, Schweißfläche und Spannmittel,
5. ordnet die Geometrien den vorgesehenen Rhino-Layern zu.

Für eine regelmäßige Verwendung kann in Rhino eine Schaltfläche mit folgendem Makrobefehl angelegt werden:

```text
! -_ScriptEditor _Run "<PFAD-ZU-rhinoWAAMContour.py>"
```

Der Platzhalter muss durch den vollständigen lokalen Pfad zur Datei ersetzt werden.

Die erzeugten Geometrien können anschließend für die weitere CAD/CAM-Planung und – bei vorhandenem CAM-System – für die Darstellung der realen Aufspannsituation in der Maschinensimulation verwendet werden. Ein gegebenenfalls verwendetes kommerzielles CAM-Plug-in ist nicht Bestandteil dieses Repositories.

### Standalone-Ausführung

Die Benutzeroberfläche kann unabhängig von Rhino gestartet werden:

```powershell
.venv\Scripts\python.exe mainGUI.py
```

In diesem Fall werden die erfassten Geometriedaten in einer externen JSON-Datei gespeichert. Eine automatische Erzeugung der CAD-Geometrien in Rhino erfolgt nicht.

## Enthaltene Skripte

| Datei                       | Funktion                                                                                                          | Standalone nutzbar                     |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `mainGUI.py`                | Benutzeroberfläche, Bildaufnahme, Modusauswahl, assistierte Polygondefinition und JSON-Ausgabe                    | Ja                                     |
| `cameraCalibration.py`      | Intrinsische Kamerakalibrierung mithilfe eines ChArUco-Kalibriermusters                                           | Ja, vorzugsweise über `mainGUI.py`     |
| `coordinate_calibration.py` | Erstkalibrierung zwischen Referenz- und Werkobjektkoordinatensystem anhand korrespondierender Soll- und Istpunkte | Ja                                     |
| `visionPipeline.py`         | Bildentzerrung, Markererkennung, Posebestimmung, Homographie und Koordinatentransformation                        | Nein, wird von `mainGUI.py` importiert |
| `rhinoWAAMContour.py`       | Import der JSON-Daten und Erzeugung der CAD-Geometrien                                                            | Nur innerhalb von Rhino                |

Für die direkte Ausführung von `cameraCalibration.py` müssen die Kamera- und Auflösungsparameter im vorgesehenen Konfigurations- beziehungsweise Debug-Bereich des Skripts angepasst werden. Beim Start aus `mainGUI.py` werden diese Parameter automatisch übergeben.

Vor der Ausführung von `coordinate_calibration.py` müssen die aufgenommenen Soll- und Istkoordinaten in den dafür vorgesehenen Eingabebereich eingetragen werden.

## Grundlegender Arbeitsablauf

### 1. Intrinsische Kamerakalibrierung

Die Kamera wird mithilfe mehrerer Aufnahmen eines ChArUco-Kalibriermusters kalibriert. Die resultierende Kameramatrix und die Verzeichnungskoeffizienten werden in einer `.npz`-Datei gespeichert.

Die Kalibrierung muss erneut durchgeführt werden, wenn sich mindestens einer der folgenden Parameter ändert:

* Kamera,
* Auflösung,
* Objektiv oder Fokuszustand,
* optischer Schutzfilter,
* relevante Einstellungen der Bildaufnahme.

### 2. Erstkalibrierung des Werkobjektkoordinatensystems

Korrespondierende Referenzpunkte werden sowohl im kamerabasierten Referenzsystem als auch mit dem Roboter beziehungsweise im Werkobjektkoordinatensystem bestimmt.

Aus den Punktpaaren wird eine ebene Starrkörpertransformation mit Rotation um die Z-Achse und Translation in X- und Y-Richtung bestimmt. Die resultierenden Parameter werden für die Transformation der später erfassten Konturpunkte verwendet.

### 3. Aufnahme der Aufspannsituation

Die Kamera nimmt die Substratplatte, das ChArUco-Board und die markierten Spannmittel auf. Aus dem ChArUco-Board wird die Kamerapose relativ zur Referenzebene bestimmt.

### 4. Definition der Schweißfläche

Im assistierten Modus werden die Eckpunkte der nutzbaren Schweißfläche durch den Anwender ausgewählt. Die ausgewählten Bildpunkte werden in Werkobjektkoordinaten transformiert und als Polygon gespeichert.

### 5. Übergabe an Rhino

Die Polygonpunkte und Spannmittelpositionen werden in einer JSON-Datei gespeichert. `rhinoWAAMContour.py` liest diese Daten ein und erzeugt daraus die entsprechenden CAD-Geometrien.

## Ausgabedaten

Die JSON-Ausgabe enthält insbesondere:

* Polygonpunkte der nutzbaren Schweißfläche in Werkobjektkoordinaten,
* erkannte ArUco-ID eines Spannmittels,
* Position des Spannmittels,
* Orientierung um die Z-Achse,
* gegebenenfalls zusätzliche aufnahme- und transformationsbezogene Metadaten.

Vereinfachtes Beispiel:

```json
{
  "weld_area": [
    {"x": 100.0, "y": 50.0},
    {"x": 300.0, "y": 50.0},
    {"x": 300.0, "y": 250.0},
    {"x": 100.0, "y": 250.0}
  ],
  "fixtures": [
    {
      "id": 63,
      "x": 420.0,
      "y": 180.0,
      "rotation_z": 35.0
    }
  ]
}
```

Das tatsächliche Datenformat richtet sich nach dem archivierten Softwarestand.

## Bekannte Einschränkungen

* Der Softwarestand wurde ausschließlich unter Windows validiert.
* Kamera- und Dateipfade können installationsspezifische Anpassungen erfordern.
* Die automatische Plattenkantenerkennung ist empfindlich gegenüber Reflexionen, Schatten, Fremdkonturen und ungleichmäßiger Beleuchtung.
* Der assistierte Modus setzt eine eindeutige visuelle Auswahl der relevanten Konturpunkte voraus.
* Das ChArUco-Board muss vollständig oder ausreichend sichtbar sein.
* Die Transformation der Konturpunkte setzt eine ebene Arbeitsfläche mit bekannter Höhe voraus.
* Die intrinsische Kalibrierung gilt nur für die verwendete Kameraauflösung und optische Konfiguration.
* Die Spannmittelerfassung ist auf hinterlegte ArUco-IDs und bekannte Spannmittelgeometrien beschränkt.
* Die Software führt keine sicherheitsgerichtete Freigabe des Schweißprozesses durch.
* Für andere WAAM-Zellen müssen Koordinatensysteme, Abmessungen und Schnittstellen angepasst werden.

## Wissenschaftlicher Kontext

Die Software wurde im Rahmen einer Bachelorarbeit zur kameragestützten Unterstützung des Rüstprozesses einer WAAM-Zelle entwickelt.

Der Schwerpunkt liegt auf:

* der geometrischen Referenzierung der Kameraaufnahme,
* der Transformation von Bildpunkten in Werkobjektkoordinaten,
* der robusten assistierten Erfassung der nutzbaren Schweißfläche,
* der Integration der erfassten Daten in den CAD/CAM-Workflow.

Der archivierte Release bildet den Softwarestand ab, der den in der Bachelorarbeit beschriebenen Implementierungs- und Validierungsergebnissen zugrunde liegt.

## Zitierung

Der für die Bachelorarbeit maßgebliche Softwarestand wird als GitHub-Release archiviert und über Zenodo mit einer DOI veröffentlicht.

Vorgesehene Zitierung:

```text
[Vorname Nachname] (2026).
WAAM-Plattenerkennung (Version 1.0.0) [Computer software].
Zenodo. https://doi.org/10.5281/zenodo.21275491
```

Die vollständigen maschinenlesbaren Zitationsangaben befinden sich nach Veröffentlichung zusätzlich in `CITATION.cff`.

> Die angegebene DOI wird erst mit der Veröffentlichung des zugehörigen Zenodo-Eintrags öffentlich auflösbar.

## Lizenz

Der Quellcode wird unter den Bedingungen der **GNU General Public License v3.0** bereitgestellt. Weitere Informationen befinden sich in der Datei [LICENSE](LICENSE).

Davon ausgenommen können externe Bibliotheken, Schriftarten, Bildmaterialien, CAD-Systeme oder CAM-Plug-ins sein. Für diese gelten die jeweiligen Lizenzbedingungen der Rechteinhaber.

## Haftungsausschluss

Die Software wird ohne Gewährleistung bereitgestellt. Sie ist als Forschungs- und Entwicklungsprototyp konzipiert. Vor einem Einsatz an einer realen Fertigungsanlage müssen sämtliche erzeugten Koordinaten, Geometrien und Werkzeugwege durch qualifiziertes Personal geprüft werden.
