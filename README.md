# Scanning Droplet Cell (SDC) — Modular Python Control System

A Python-based control architecture for automated, spatially resolved electrochemical characterization using a **Scanning Droplet Cell (SDC)**. The platform integrates motion control, electrolyte delivery, electrochemical measurements, sample-surface leveling, and experimental data logging in a single workflow, configured from JupyterLab.

## Hardware and software platform

| Component | Hardware / implementation | Role |
| --- | --- | --- |
| **Motion platform** | **Creality K1C 3D printer** | Positions the SDC head over a programmed sample grid; controlled through Klipper/Moonraker commands |
| **Potentiostat** | **BioLogic SP-50e** | Performs electrochemical measurements |
| **Electrochemical control software** | **BioLogic EC-Lab Developer Package**, accessed via the **`easy_biologic` Python library** | Provides the Python interface used to configure, execute, and retrieve BioLogic measurements |
| **Electrolyte delivery** | **Harvard Apparatus syringe pump** | Controls liquid infusion through a serial connection |
| **Experiment interface** | **Python + JupyterLab (Anaconda)** | Configures experiments, launches workflows, and displays progress |

> **Project status:** Research software for a laboratory-specific SDC assembly. The control scripts can command real motion, fluidics, and electrical hardware. Review and validate each subsystem, coordinate convention, and emergency-stop behavior on the target setup before use. Do not run unattended without independently verified safeguards.

## Overview

The SDC enables position-dependent electrochemical measurements by bringing a confined electrolyte contact into contact with selected locations on a sample. This project organizes the laboratory automation into reusable modules rather than maintaining separate monolithic notebooks for each measurement technique.

At each selected grid point, the controller can coordinate:

1. Safe retraction and X–Y positioning using the modified Creality K1C.
2. Electrolyte infusion using the Harvard Apparatus pump.
3. Droplet stabilization and controlled Z movement to a calibrated contact position.
4. A user-selected sequence of electrochemical techniques using the BioLogic SP-50e.
5. Data export, per-technique status logging, and retraction before moving to the next point.

### Supported techniques

The modular technique library is designed to support:

| Technique | Abbreviation | Typical purpose |
| --- | --- | --- |
| Open-circuit voltage / potential | OCV | Monitor open-circuit potential |
| Linear sweep voltammetry | LSV | Polarization measurements |
| Cyclic voltammetry | CV | Redox behavior and electrochemical cycling |
| Chronoamperometry | CA | Current response under a potential program |
| Chronopotentiometry | CP | Potential response under a current program |
| Potentiostatic electrochemical impedance spectroscopy | PEIS / EIS | Frequency-dependent impedance measurements |

The initial architecture was developed around **OCV → LSV** and subsequently extended with CV, CA, CP, and PEIS modules. The exact techniques available in a checkout depend on which modules and controller configuration have been included and verified. The LSV implementation originally used a BioLogic CV backend to produce a forward sweep; its waveform should be verified on the instrument.

## Software architecture

```text
JupyterLab experiment notebook
          |
          v
Experiment controller (sdc/core/)
          |
          +-- Motion and coordinate handling (sdc/hardware/, sdc/calibration/)
          +-- Syringe-pump control (sdc/hardware/)
          +-- Electrochemical technique runners (sdc/techniques/)
          +-- Experiment logs and measurement files
```

### Repository layout

```text
SDC_Control/
├── sdc/
│   ├── hardware/          # Printer/Moonraker and syringe-pump communication
│   ├── calibration/       # Four-corner plane fitting and coordinate transforms
│   ├── techniques/        # OCV, LSV, and additional electrochemical routines
│   ├── core/              # Grid, experiment sequencing, recovery, and run control
│   └── config.py          # Experiment and hardware configuration
├── notebooks/             # Jupyter-based configuration and experiment entry points
├── tests/                 # Hardware-free checks
├── pyproject.toml
└── README.md
```

**Separation of responsibilities:** notebooks specify what to measure; the controller determines the sequence; hardware modules handle device communication; technique modules encapsulate BioLogic acquisition; calibration handles the sample geometry. This makes it possible to extend the technique library without rewriting the grid-movement workflow.

## Setup (Windows / Anaconda)

Use a dedicated Conda environment. The following is an example; dependencies and versions should be matched to the instrument's known-working configuration.

```powershell
conda create -n sdc-control python=3.11 -y
conda activate sdc-control
conda install numpy requests pyserial jupyterlab ipykernel pytest -y
python -m pip install easy-biologic
python -m pip install -e .
python -m ipykernel install --user --name sdc-control --display-name "Python (SDC Control)"
```

Launch JupyterLab and select the **Python (SDC Control)** kernel:

```powershell
jupyter lab
```

The code imports `easy_biologic` and `easy_biologic.lib`. It does **not** ordinarily require copying standalone `kbio` or `lib` folders into this repository. The appropriate BioLogic native libraries, firmware-compatible technique files, and drivers still need to be installed or discoverable as required by the particular `easy_biologic` setup. Some versions of `easy_biologic` require the legacy `pkg_resources` module; if that import fails, use a compatible `setuptools` version in the Conda environment.

**Jupyter event-loop note:** Some `easy_biologic` methods use `asyncio.run()` internally, which can conflict with the running Jupyter event loop. The working SDC architecture uses a dedicated worker-thread wrapper for electrochemical acquisition. Avoid applying `nest_asyncio` globally unless explicitly validated against the Jupyter/IPython version.

## Example: configure and run an experiment

The example below assumes a checkout containing `cfg.techniques`, the grid API, and the technique modules named above. Parameter keys should match the installed version of `sdc/config.py`.

```python
from pathlib import Path
from sdc.config import Config
from sdc.core.grid import Grid
from sdc.core.experiment import Experiment

cfg = Config()
cfg.techniques = ["OCV", "LSV"]

# Sample and output naming
sample_name = "Sample01"
cfg.file_prefix = sample_name
cfg.data_dir = Path("SDC_Data") / sample_name / "Run01"

# 5 x 5 measurement grid, 2 mm spacing
cfg.grid = Grid(
    mode="grid", rows=5, columns=5,
    spacing_x=2.0, spacing_y=2.0,
    start_x=0.0, start_y=0.0,
)

# OCV acquisition
cfg.ocv_params["time"] = 15.0
cfg.ocv_params["time_interval"] = 0.5

# Stabilization delays
cfg.droplet_stabilize_seconds = 1.0
cfg.settle_seconds = 1.0

# Check hardware configuration, travel limits, sample origin,
# and safe contact/retraction before enabling a real experiment.
experiment = Experiment(cfg)
# experiment.run()  # COMMANDS LIVE HARDWARE
```

When corner calibration is enabled, the experiment guides the operator through four sample-corner contacts. The fitted plane estimates a contact height for each grid coordinate. Disabling calibration requires supplying a previously verified plane explicitly.

## Calibration and motion control

- **Four-corner leveling:** fits a least-squares plane, `z = a*x + b*y + c`, from measured corner positions.
- **Position-dependent contact height:** uses the fitted plane instead of a single constant Z reference.
- **Travel clearance:** computes a clearance target for the measurement grid to reduce the risk of surface contact during X–Y translation; this is **not** collision-proof and does not account automatically for all fixtures.
- **Motion synchronization:** uses `M400` to wait for queued Klipper moves before depending on their completion.

Calibration coefficients and the recorded corner positions can be written to `calibration.json` with the experiment data.

## Data and traceability

A typical experiment output directory contains:

```text
SDC_Data/Sample01/Run01/
├── experiment_metadata.json
├── calibration.json
├── experiment_log.csv
├── experiment_progress.log
├── dataocv/
│   └── Sample01_x0.0_y0.0.csv
└── datalsv/
    └── Sample01_x0.0_y0.0.csv
```

Additional technique folders (for example `datacv`, `dataca`, `datacp`, and `dataeis`) are created when their runners are selected and present. Individual measurement files are associated with their measurement coordinates. The experiment status log and human-readable progress log support troubleshooting and data provenance. A successfully written file is **not**, by itself, proof of a valid electrochemical contact or measurement.

## Testing and validation

Run hardware-free tests from the project root:

```powershell
python -m pytest tests
python -m compileall -q sdc
```

Before live experiments, verify:

- Printer axes, workspace boundaries, Z direction, clearance, and motion completion.
- The physical coordinate origin and grid-to-sample transformation.
- Four-corner leveling residuals and safe contact heights over the entire sample.
- Pump serial settings, infuse commands, response parsing, and timeout handling.
- BioLogic SP-50e connection, channel selection, applied waveform/current ranges, technique stopping, and data export.
- Recovery behavior, live progress reporting, and hardware shutdown after errors.

**Limitations:** The original implementation has operator-driven recovery and does not guarantee an automatic safe potentiostat output-off or restart-from-checkpoint procedure after failures. Do not rely on a notebook interrupt as an emergency stop. Validate the installed version of this project against the real hardware before unattended operation.

## Publishing this repository

Before pushing a public version to GitHub:

- Remove or replace private IP addresses, COM-port identifiers tied to your setup, user-specific Windows paths, credentials, access tokens, and internal network details.
- Exclude experimental datasets, instrument logs, notebook outputs containing sensitive paths, virtual environments, and proprietary BioLogic developer-package files or DLLs unless redistribution is explicitly permitted.
- Add a `.gitignore`, choose a license for **your own code** (without purporting to license third-party vendor components), and document versions required to reproduce the software environment.
- Keep third-party dependencies as installation prerequisites rather than copying vendor packages into the repository.

## Project origin

The software started as a refactor of `OCV_LSVMeshLvl.ipynb` and `sdc_mesh_leveling.py` into hardware, calibration, technique, and experiment-control modules. Its purpose is to support repeatable, grid-based electrochemical characterization and further development of a flexible scanning droplet cell automation platform.
