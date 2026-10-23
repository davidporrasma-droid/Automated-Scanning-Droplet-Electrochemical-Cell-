"""SDC OCV→LSV experiment orchestrator."""
import csv
import json
import time
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from .controller import RunControl
from .recovery import recover
from ..hardware.printer import Printer
from ..hardware.pump import Pump
from ..calibration.mesh import run_corner_calibration
from ..techniques.ocv import run_ocv
from ..techniques.lsv_runner import run_lsv
from ..techniques.worker import run_in_worker

class Experiment:
    def __init__(self, config, *, plane=None, printer=None, pump_factory=None, runners=None):
        self.cfg=config
        self.plane=plane
        self.printer=printer or Printer(config.printer_url,config.geometry,config.travel_feed,config.work_feed,config.settle_seconds,config.nudge_mm)
        self.pump_factory=pump_factory

        self.runners = runners if runners is not None else {
            "OCV": lambda p: run_in_worker(
                run_ocv,
                config.biologic_address,
                config.biologic_channel,
                config.ocv_params,
                p,
                config.sanity_check
            ),
            "LSV": lambda p: run_in_worker(
                run_lsv,
                config.biologic_address,
                config.biologic_channel,
                config.lsv_params,
                p,
                config.sanity_check
            ),
            }
        self.control=RunControl()

    def calibrate(self):
        self.plane=run_corner_calibration(self.cfg.printer_url,clearance_z=self.cfg.geometry.clearance,travel_feed=self.cfg.travel_feed)
        return self.plane

    def _log(self, row):
        path=Path(self.cfg.data_dir)/'experiment_log.csv'
        exists=path.exists()
        with path.open('a',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['row','column','x_mm','y_mm','technique','status','file','contact_z_mm'])
            if not exists:w.writeheader()
            w.writerow(row)

    
    def log_message(self, message):
        """Print progress and save it in a persistent log file."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [SDC] {message}"

        print(formatted_message, flush=True)

        log_path = Path(self.cfg.data_dir) / "experiment_progress.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open("a", encoding="utf-8") as f:
            f.write(formatted_message + "\n")

    
    def run(self):
        cfg = self.cfg

        if cfg.infusion_every < 0:
            raise ValueError("infusion_every must be >= 0")

        data_dir = Path(cfg.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        self.log_message("Starting SDC experiment")
        self.log_message("Checking printer connection")
        self.printer.check()

        if cfg.calibrate_corners:
            self.log_message("Starting mesh calibration")
            self.calibrate()
            self.log_message("Mesh calibration completed")

        if self.plane is None:
            raise RuntimeError(
                "Calibration disabled: supply a verified plane explicitly."
            )

        (data_dir / "experiment_metadata.json").write_text(
            json.dumps(asdict(cfg), default=str, indent=2)
        )

        (data_dir / "calibration.json").write_text(
            json.dumps({
                "a": getattr(self.plane, "a", None),
                "b": getattr(self.plane, "b", None),
                "c": getattr(self.plane, "c", None),
                "corners": getattr(self.plane, "corners", None),
                "max_residual": getattr(self.plane, "max_residual", None)
            }, indent=2)
        )

        self.log_message("Experiment metadata and calibration saved")

        points = cfg.grid.points()

        if not points:
            raise ValueError("Experiment grid contains no points.")

        safe_z = max(
            cfg.geometry.physical(x, y, self.plane)[2]
            for _, _, x, y in points
        )

        self.printer.last_clearance_z = safe_z

        self.log_message(
            f"Grid initialized: {len(points)} measurement points"
        )

        factory = self.pump_factory or (
            lambda: Pump(
                cfg.pump_port,
                cfg.pump_baud,
                cfg.infusion_rate_ul_min,
                cfg.infusion_volume_ul
            )
        )

        ctx = factory() if cfg.infusion_every else nullcontext(None)

        self.log_message("Initializing pump")

        try:
            with ctx as pump:
                for index, (r, c, x, y) in enumerate(points):

                    if self.control.check():
                        self.log_message(
                            "Experiment stopped by user control"
                        )
                        break

                    self.log_message(
                        f"Point {index + 1}/{len(points)} "
                        f"| Row={r}, Column={c} "
                        f"| X={x:.2f}, Y={y:.2f}"
                    )

                    self.log_message("Moving to measurement position")
                    contact = self.printer.travel(x, y, self.plane)

                    try:
                        if (
                            pump is not None
                            and index % cfg.infusion_every == 0
                        ):
                            self.log_message(
                                "Starting electrolyte infusion"
                            )

                            pump.infuse()

                            self.log_message(
                                "Infusion completed; "
                                "stabilizing droplet"
                            )

                            time.sleep(
                                cfg.droplet_stabilize_seconds
                            )

                        self.log_message(
                            "Descending to sample contact"
                        )

                        self.printer.descend(contact)

                        self.log_message(
                            "Contact movement completed"
                        )

                        for label, runner in self.runners.items():

                            self.log_message(
                                f"Starting {label} measurement"
                            )

                            directory = (
                                data_dir / ("data" + label.lower())
                            )
                            directory.mkdir(exist_ok=True)

                            path = directory / (
                                f"{cfg.file_prefix}"
                                f"_x{x:.1f}_y{y:.1f}.csv"
                            )

                            status = "ok"

                            try:
                                valid = runner(path)

                                if cfg.sanity_check and not valid:
                                    self.log_message(
                                        f"{label} validation failed; "
                                        "starting recovery"
                                    )

                                    valid = recover(
                                        label,
                                        self.printer,
                                        pump,
                                        runner,
                                        path,
                                        cfg.max_recovery_attempts,
                                        cfg.droplet_stabilize_seconds
                                    )

                                if not valid:
                                    status = "skipped"

                            except Exception as exc:
                                status = "error"

                                self.log_message(
                                    f"ERROR during {label}: "
                                    f"{type(exc).__name__}: {exc}"
                                )

                                self._log(dict(
                                    row=r,
                                    column=c,
                                    x_mm=x,
                                    y_mm=y,
                                    technique=label,
                                    status=status,
                                    file=str(path),
                                    contact_z_mm=(
                                        self.printer.last_contact_z
                                    )
                                ))

                                raise

                            self._log(dict(
                                row=r,
                                column=c,
                                x_mm=x,
                                y_mm=y,
                                technique=label,
                                status=status,
                                file=str(path),
                                contact_z_mm=(
                                    self.printer.last_contact_z
                                )
                            ))

                            self.log_message(
                                f"{label} completed: {status}"
                            )

                            if status == "skipped":
                                self.log_message(
                                    f"Skipping remaining techniques "
                                    f"at point {index + 1}"
                                )
                                break

                    finally:
                        self.log_message("Retracting SDC head")
                        self.printer.retract()
                        self.log_message("Retraction completed")

                    self.log_message(
                        f"Point {index + 1}/{len(points)} finished"
                    )

            self.log_message(
                "Experiment sequence completed"
            )

        except Exception as exc:
            self.log_message(
                f"EXPERIMENT INTERRUPTED: "
                f"{type(exc).__name__}: {exc}"
            )
            raise
