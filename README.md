# Vision-based fixture recognition for WAAM substrate plates

**English** | [Deutsch](README_DE.md)

Research prototype for camera-assisted setup of a Wire Arc Additive Manufacturing (WAAM) cell. The software determines a usable substrate-plate area in work-object coordinates, detects marked clamps, and transfers the resulting geometry to Rhino for CAD/CAM planning.

> **Project status:** The assisted contour workflow is the recommended and validated operating mode. The automatic edge-based contour detection is included as an experimental development path and is not sufficiently robust for unrestricted use.

<p align="center">
  <img src="media/graphical_abstract.png" alt="WAAM setup-recognition workflow" width="850">
</p>

## Purpose

The software supports a setup process in which substrate plates and clamps can be positioned variably on a WAAM fixture plate. A monocular camera records the scene. ChArUco and ArUco fiducials provide the geometric reference required to transform image points into the work-object coordinate system.

The workflow covers:

* intrinsic camera calibration through the integrated calibration window;
* ChArUco-based camera-pose estimation;
* transformation from image coordinates to a planar work-object coordinate system;
* assisted polygon definition of the usable welding area;
* experimental automatic contour detection based on Canny edges and probabilistic Hough lines;
* detection and orientation estimation of ArUco-marked clamps;
* JSON export and generation of CAD geometry in Rhino;
* creation of an orthorectified reference image for visual verification in CAD.

## Tested environment and requirements

The implementation is intended for Windows because camera enumeration and acquisition use DirectShow/Media Foundation and `pygrabber`.

Required components:

* 64-bit CPython compatible with the package versions in `requirements.txt`;
* a camera accessible through OpenCV;
* the printed ChArUco reference board and ArUco clamp markers matching the dimensions used in the source code;
* Rhino 8 for the integrated CAD-import workflow;
* the relevant CAM plug-in only when its layer conventions and machine simulation are used.

Rhino, ModuleWorks, and other third-party CAM components are not part of this repository.

## Installation

Clone the repository and run the installation script:

```bat
git clone https://github.com/Coder861/waam-fixture-recognition.git
cd waam-fixture-recognition
install_requirements.bat
```

The script creates a local virtual environment in `.venv` and installs the external Python dependencies.

Manual installation:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Starting the software

### Stand-alone vision workflow

```bat
.venv\Scripts\python.exe mainGUI.py
```

### Rhino-integrated workflow

Open `rhinoWAAMContour.py` in the Rhino ScriptEditor or assign the following command to a Rhino button or alias:

```text
! _-ScriptEditor _Run "C:\path\to\waam-fixture-recognition\rhinoWAAMContour.py"
```

The Rhino script starts the external vision GUI with the repository-local virtual environment. When the GUI exports the result, Rhino reads `data.json` and creates the substrate-plate and clamp geometry.

## Operating workflow

1. Select the camera in the main window.
2. Check whether a matching intrinsic calibration file is detected for the selected camera and resolution.
3. When no suitable calibration is available, start the integrated camera-calibration window, record the required ChArUco views, review the reprojection error, and save the result.
4. Refresh or reselect the camera when the newly saved calibration is not detected immediately.
5. Capture the current setup image.
6. Choose the **assisted mode** and mark the usable welding-area polygon. The automatic mode may be used for experiments under the tested image conditions.
7. Enter the substrate-plate thickness.
8. Review the detected coordinate axes, polygon points, and clamp markers.
9. Select **Kontur → CAD** to write the JSON data and continue the Rhino import.

## Calibration and geometric reference

Two different ChArUco boards are used by the current implementation and must not be confused:

| Purpose                           | Squares | Square length | Marker length | Dictionary    |
| --------------------------------- | ------: | ------------: | ------------: | ------------- |
| Intrinsic camera calibration      |   9 × 6 |         15 mm |         11 mm | `DICT_4X4_50` |
| Scene pose / work-plane reference |   3 × 8 |         30 mm |       22.5 mm | `DICT_4X4_50` |

Intrinsic calibration is integrated into the GUI and is specific to the camera, resolution, focus, and optical setup.

The relation between the ChArUco coordinate system and the WAAM work-object coordinate system is installation-specific. The current values in `visionPipeline.py` represent the investigated WAAM cell. `coordinate_calibration.py` estimates a planar correction from corresponding nominal and measured robot points and is intended for the initial referencing of another installation or after a relevant mechanical change.

The included `.npz` file documents the tested EMEET SmartCam Nova 4K setup. It is not a universal calibration file and should not be reused with another camera, resolution, focus setting, or mounting geometry.

## Output

The vision application creates:

* `data.json`: geometry and metadata exchanged with Rhino;
* `spannsituation_ortho.png`: orthorectified reference image of the work plane.

The current JSON uses metres for geometric coordinates and contains:

* the selected pipeline mode;
* substrate-plate thickness and welding-surface height;
* ArUco ID, position, and orientation of each detected clamp;
* polygon vertices of the usable welding area;
* placement information for the orthorectified reference image.

A current-format example is provided in `examples/example_output.json`.

## Repository structure

| File or directory           | Purpose                                                                           |
| --------------------------- | --------------------------------------------------------------------------------- |
| `mainGUI.py`                | Main user interface, camera selection, acquisition, and assisted polygon input    |
| `cameraCalibration.py`      | Integrated intrinsic ChArUco camera calibration                                   |
| `visionPipeline.py`         | Pose estimation, transformations, marker detection, masks, and contour processing |
| `coordinate_calibration.py` | Initial planar correction of the work-object reference                            |
| `rhinoWAAMContour.py`       | Starts the external GUI and creates Rhino geometry from the JSON result           |
| `requirements.txt`          | External Python dependencies                                                      |
| `install_requirements.bat`  | Creation and installation of the local virtual environment                        |
| `icons/`                    | Required GUI icons                                                                |
| `media/`                    | README media, including the workflow picture                                      |
| `examples/`                 | Small example data that do not contain confidential production information        |

## Known limitations

* The automatic contour pipeline is parameterised for the investigated 4K setup and remains experimental.
* The assisted mode requires the operator to define a valid, non-self-intersecting polygon.
* The planar transformation assumes that the selected contour lies on the entered substrate-surface plane.
* Clamp geometry is reconstructed from marker positions and a lookup table. Marker placement, marker height, clamp dimensions, and ID assignment must match the implementation.
* Unknown or incorrectly assigned marker IDs can produce incorrect fixture geometry and must be rejected or checked before use.
* The work-object offsets in the source code are specific to the investigated cell.
* Camera properties depend on the camera driver and may not accept all requested values.
* The software has not been developed or certified as a safety component.

## Safety notice

This repository contains a research prototype. Generated coordinates and CAD objects must be checked before CAM programming, robot motion, welding, or collision assessment. The software does not replace machine safeguarding, validated robot programs, process supervision, or a safety-rated collision-prevention system.

## Citation

Citation metadata are provided in `CITATION.cff`. A Zenodo DOI will be added after publication of the first archived GitHub release.

The related bachelor thesis will receive a separate institutional URN. That URN should later be listed under a “Related thesis” entry; it does not replace the software DOI.

## License

The software is distributed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
