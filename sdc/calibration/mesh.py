"""
SDC Mesh Step — 4-Point Plane Leveling
=======================================
Interactive Jupyter-friendly routine that asks the user to jog the printer
head to the 4 corners of the sample, records the physical (X, Y, Z) contact
position at each corner, fits a best-fit plane through those 4 points, and
returns a function `get_contact_z(x, y)` that gives the leveled contact Z
for any (X, Y) in the grid -- replacing the constant `REF_Z` assumption in
the original `_phys()` helper.

This is meant to be run as ONE Jupyter cell, before the main `run()` loop.
It depends only on `requests` and talks to the same Moonraker HTTP API
already used in the main script (`PRINTER_URL`).

Math
----
Given 4 corner points P1..P4 = (x_i, y_i, z_i), we fit a plane:

    z = a*x + b*y + c

via least-squares (using numpy.linalg.lstsq). With exactly 4 points this
is an over-determined 3-unknown system, so if the 4 corners aren't
perfectly coplanar (very likely for a real sample / printer bed), the fit
finds the plane that minimizes total squared Z error across all 4 -- this
is more robust than just using 3 of the 4 points and ignoring the 4th.

The fitted (a, b, c) let you compute the *leveled* contact Z at any
(grid_x, grid_y) point during the main mesh-grid routine, the same way
bed-leveling mesh works on a 3D printer.

Usage
-----
    from sdc_mesh_leveling import run_corner_calibration

    plane = run_corner_calibration(PRINTER_URL)
    # plane.get_z(x, y) -> leveled contact Z at that physical (x, y)
    # plane.a, plane.b, plane.c -> raw fit coefficients
    # plane.corners -> the 4 recorded (x, y, z) tuples
    # plane.max_residual -> worst point's deviation from the fit (mm),
    #                        a quick sanity check on how "flat" the sample is

Then inside `_phys()`, replace:
    phys_z_contact = REF_Z
with:
    phys_z_contact = plane.get_z(phys_x, phys_y)
"""

import time
from dataclasses import dataclass, field

import numpy as np
import requests


# ============================================================
# SETTINGS (mirror the conventions in the main automation script)
# ============================================================

CORNER_NAMES = [
    "Corner 1 (e.g. front-left)",
    "Corner 2 (e.g. front-right)",
    "Corner 3 (e.g. back-right)",
    "Corner 4 (e.g. back-left)",
]

# Small relative move after jogging, in mm, used by the fine-jog helper
FINE_JOG_STEP_MM = 0.05


# ============================================================
# MOONRAKER HELPERS (same pattern as the main script)
# ============================================================
def _get_bed_mesh_status(url: str) -> dict:
    """Query current bed_mesh state (active profile, if any)."""
    r = requests.get(f"{url}/printer/objects/query?bed_mesh", timeout=3)
    r.raise_for_status()
    return r.json()["result"]["status"]["bed_mesh"]


def _clear_bed_mesh(url: str) -> None:
    """
    Disable Klipper's active bed mesh Z-compensation.

    The SDC plane-fit calibration is meant to be the sole source of Z
    correction for this workflow. If a bed_mesh profile is loaded,
    toolhead.position already includes Klipper's own mesh-corrected Z,
    which will silently stack with our FittedPlane correction and throw
    off every contact height. Clear it before calibrating.
    """
    _send_gcode(url, "BED_MESH_CLEAR")
    _wait_for_moves(url)
    
def _get_toolhead_position(url: str) -> tuple:
    """Query Moonraker for the current physical (X, Y, Z) toolhead position."""
    r = requests.get(f"{url}/printer/objects/query?toolhead", timeout=3)
    r.raise_for_status()
    pos = r.json()["result"]["status"]["toolhead"]["position"]
    return float(pos[0]), float(pos[1]), float(pos[2])


def _send_gcode(url: str, cmd: str) -> None:
    r = requests.post(
        f"{url}/printer/gcode/script",
        params={"script": cmd},
        timeout=30,
    )
    r.raise_for_status()
def _wait_for_moves(url: str) -> None:
    """
    Block until Klipper's motion queue is fully drained.
 
    `toolhead.position` reflects the live, print-time-interpolated
    position -- it is NOT a "final target" value that only updates once
    a move is physically finished. Querying it while a G0/G1 is still
    executing returns wherever the head happens to be *at that instant*
    (a partial/interpolated position along the move), not the commanded
    endpoint. M400 blocks further gcode processing until all queued
    moves have actually completed, so it must be sent (and its response
    awaited) before any position read that needs to be trustworthy.
    """
    _send_gcode(url, "M400")

def _jog_relative(url: str, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
                   feed: int = 200) -> None:
    """Small relative nudge, used during fine positioning at each corner."""
    _send_gcode(url, f"G91\nG0 X{dx:.4f} Y{dy:.4f} Z{dz:.4f} F{feed}\nG90")


# ============================================================
# PLANE FIT
# ============================================================

@dataclass
class FittedPlane:
    a: float
    b: float
    c: float
    corners: list = field(default_factory=list)   # [(x, y, z), ...] x4
    max_residual: float = 0.0

    def get_z(self, x: float, y: float) -> float:
        """Leveled contact Z for any physical (x, y), per the fitted plane."""
        return self.a * x + self.b * y + self.c


def fit_plane(points: list) -> FittedPlane:
    """
    Least-squares plane fit z = a*x + b*y + c through N >= 3 points.

    points : list of (x, y, z) tuples
    """
    pts = np.array(points, dtype=float)
    xs, ys, zs = pts[:, 0], pts[:, 1], pts[:, 2]

    # Design matrix for [a, b, c] solving A @ [a,b,c]^T = z
    A = np.column_stack([xs, ys, np.ones_like(xs)])
    coeffs, _, _, _ = np.linalg.lstsq(A, zs, rcond=None)
    a, b, c = coeffs

    residuals = np.abs(A @ coeffs - zs)
    max_residual = float(np.max(residuals))

    return FittedPlane(a=float(a), b=float(b), c=float(c),
                        corners=list(points), max_residual=max_residual)


# ============================================================
# INTERACTIVE CORNER CALIBRATION
# ============================================================

def _prompt_fine_jog(url: str, corner_label: str) -> tuple:
    """
    Lets the user fine-jog with simple text commands before accepting a
    corner point. Returns the final (x, y, z) once accepted.
    """
    print(f"\n  [mesh] {corner_label}")
    print("  [mesh] Jog the nozzle in Klipper's UI (or Moonraker) to make light")
    print("         contact with the sample surface at this corner.")
    print("  [mesh] Optional fine-jog here (each press moves "
          f"{FINE_JOG_STEP_MM:.3f} mm):")
    print("         w/s = Z up/down   a/d = X-/X+   q/e = Y-/Y+   "
          "ENTER = accept point")

    while True:
        try:
            key = input("  > ").strip().lower()
        except EOFError:
            key = ""

        if key == "":
            _wait_for_moves(url)
            x, y, z = _get_toolhead_position(url)
            print(f"  [mesh] Accepted {corner_label} at "
                  f"X={x:.4f} Y={y:.4f} Z={z:.4f}")
            return x, y, z
        elif key == "w":
            _jog_relative(url, dz=FINE_JOG_STEP_MM)
        elif key == "s":
            _jog_relative(url, dz=-FINE_JOG_STEP_MM)
        elif key == "a":
            _jog_relative(url, dx=-FINE_JOG_STEP_MM)
        elif key == "d":
            _jog_relative(url, dx=FINE_JOG_STEP_MM)
        elif key == "q":
            _jog_relative(url, dy=-FINE_JOG_STEP_MM)
        elif key == "e":
            _jog_relative(url, dy=FINE_JOG_STEP_MM)
        else:
            print("  [mesh] Unrecognised input -- use w/a/s/d/q/e or ENTER.")


def run_corner_calibration(url: str, clearance_z: float = 10.0,
                            travel_feed: int = 300) -> FittedPlane:
    """
    Interactive 4-point mesh/plane calibration.

    For each of the 4 corners:
      1. Retract to clearance height (safe travel)
      2. Prompt user to position via Klipper UI / fine-jog keys
      3. Record the physical (X, Y, Z) on ENTER

    After all 4 points are collected, fits a best-fit plane and reports
    the max residual (a quick flatness/tilt sanity check).

    Returns
    -------
    FittedPlane
        Use `plane.get_z(x, y)` in place of a constant REF_Z.
    """
    print("\n[mesh] Starting 4-point plane calibration.")

    mesh_status = _get_bed_mesh_status(url)
    active_profile = mesh_status.get("profile_name", "")
    if active_profile:
        print(f"[mesh] Active bed_mesh profile detected: '{active_profile}'. "
              "Clearing it -- this calibration's FittedPlane will be the "
              "sole Z-compensation source for the SDC routine.")
        _clear_bed_mesh(url)
    else:
        print("[mesh] No active bed_mesh profile -- toolhead.position "
              "should already match nominal G-code Z.")

    print("[mesh] You will be asked to contact each of the 4 corners of "
          "the sample in turn.\n")

    corners = []

    for i, label in enumerate(CORNER_NAMES):
        if i > 0:
            # Retract to clearance height before moving to the next corner
            x, y, z = _get_toolhead_position(url)
            print(f"  [mesh] Retracting to clearance height before next corner ...")
            _send_gcode(url, f"G90\nG0 Z{z + clearance_z:.3f} F{travel_feed}")
            _wait_for_moves(url)
            
        point = _prompt_fine_jog(url, label)
        corners.append(point)

    plane = fit_plane(corners)

    print("\n[mesh] Calibration complete.")
    print(f"[mesh] Fitted plane: z = {plane.a:.6f}*x + {plane.b:.6f}*y + {plane.c:.6f}")
    print(f"[mesh] Max residual across corners: {plane.max_residual:.4f} mm")
    if plane.max_residual > 0.05:
        print("[mesh] WARNING: residual is fairly large -- sample may be "
              "significantly warped, or a corner was mis-jogged. Consider "
              "re-running calibration or re-checking each point.")

    print("\n[mesh] Corner points used:")
    for label, (x, y, z) in zip(CORNER_NAMES, corners):
        print(f"    {label:32s}  X={x:.4f}  Y={y:.4f}  Z={z:.4f}")

    return plane


# ============================================================
# QUICK SELF-TEST (does NOT touch hardware) -- run this cell to sanity
# check the plane-fit math itself before trusting it on real hardware
# ============================================================

def _selftest() -> None:
    # Perfectly flat plane (z = 5 everywhere) -> residual should be ~0
    flat_pts = [(0, 0, 5.0), (100, 0, 5.0), (100, 100, 5.0), (0, 100, 5.0)]
    flat_plane = fit_plane(flat_pts)
    assert abs(flat_plane.get_z(50, 50) - 5.0) < 1e-9
    assert flat_plane.max_residual < 1e-9

    # Tilted plane: z = 0.001*x + 0.002*y + 1.0
    tilted_pts = [
        (0, 0,   1.0),
        (100, 0, 1.1),
        (100, 100, 1.3),
        (0, 100, 1.2),
    ]
    tilted_plane = fit_plane(tilted_pts)
    z_center = tilted_plane.get_z(50, 50)
    print(f"[selftest] Flat plane center Z:   {flat_plane.get_z(50,50):.4f} "
          f"(expected 5.0000)")
    print(f"[selftest] Tilted plane center Z: {z_center:.4f}")
    print(f"[selftest] Tilted plane max residual: {tilted_plane.max_residual:.4f} mm")
    print("[selftest] OK")


if __name__ == "__main__":
    _selftest()