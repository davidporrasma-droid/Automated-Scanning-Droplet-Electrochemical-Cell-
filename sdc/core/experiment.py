"""SDC technique-selectable experiment controller."""
import csv
import json
import time
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from .controller import RunControl
from .recovery import recover
from ..hardware.printer import Printer
from ..hardware.pump import Pump
from ..calibration.mesh import run_corner_calibration
from ..techniques.worker import run_in_worker
from ..techniques.ocv import run_ocv
from ..techniques.lsv_runner import run_lsv
from ..techniques.cv import run_cv
from ..techniques.ca import run_ca
from ..techniques.cp import run_cp
from ..techniques.eis import run_eis

class Experiment:
    def __init__(self, config, *, plane=None, printer=None, pump_factory=None, runners=None):
        self.cfg = config
        self.plane = plane
        self.printer = printer or Printer(
            config.printer_url, config.geometry, config.travel_feed,
            config.work_feed, config.settle_seconds, config.nudge_mm)
        self.pump_factory = pump_factory
        self.control = RunControl()
        # Store the OCV potential per point, never reuse a previous location's bias.
        self._point_ocv_bias = None
        self.runners = runners if runners is not None else self._make_runners()

    def _make_runners(self):
        cfg = self.cfg
        def simple(fn, params):
            return lambda p: run_in_worker(
                fn, cfg.biologic_address, cfg.biologic_channel,
                params, p, cfg.sanity_check)

        def ocv(p):
            ok, bias = run_in_worker(
                run_ocv, cfg.biologic_address, cfg.biologic_channel,
                cfg.ocv_params, p, cfg.sanity_check, return_mean=True)
            self._point_ocv_bias = bias if ok else None
            return ok

        def peis(p):
            bias = self._point_ocv_bias
            if bias is None:
                bias = cfg.eis_params.get('voltage')
            # Never silently default to 0 V.
            return run_in_worker(
                run_eis, cfg.biologic_address, cfg.biologic_channel,
                cfg.eis_params, p, cfg.sanity_check, bias_voltage=bias)

        registry = {
            'OCV': ocv,
            'LSV': simple(run_lsv, cfg.lsv_params),
            'CV': simple(run_cv, cfg.cv_params),
            'CA': simple(run_ca, cfg.ca_params),
            'CP': simple(run_cp, cfg.cp_params),
            'EIS': peis,
        }
        labels = list(cfg.techniques)
        if not labels:
            raise ValueError('Specify at least one technique in cfg.techniques')
        if len(labels) != len(set(labels)):
            raise ValueError('Repeated technique labels are not supported in cfg.techniques')
        unknown = set(labels) - registry.keys()
        if unknown:
            raise ValueError(f'Unknown techniques: {sorted(unknown)}')
        if 'EIS' in labels and 'voltage' not in cfg.eis_params:
            if 'OCV' not in labels or labels.index('OCV') >= labels.index('EIS'):
                raise ValueError('EIS requires preceding OCV at every point, or explicit eis_params["voltage"].')
        return {name: registry[name] for name in labels}

    def calibrate(self):
        self.plane = run_corner_calibration(
            self.cfg.printer_url,
            clearance_z=self.cfg.geometry.clearance,
            travel_feed=self.cfg.travel_feed)
        return self.plane

    def log_message(self, message):
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted = f'[{stamp}] [SDC] {message}'
        print(formatted, flush=True)
        p = Path(self.cfg.data_dir) / 'experiment_progress.log'
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('a', encoding='utf-8') as fh:
            fh.write(formatted + '\n')

    def _log(self, row):
        path = Path(self.cfg.data_dir) / 'experiment_log.csv'
        exists = path.exists()
        with path.open('a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=[
                'row','column','x_mm','y_mm','technique','status',
                'file','contact_z_mm'])
            if not exists:
                w.writeheader()
            w.writerow(row)

    def run(self):
        cfg = self.cfg
        if cfg.infusion_every < 0:
            raise ValueError('infusion_every must be >= 0')
        data_dir = Path(cfg.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.log_message('Starting SDC experiment')
        self.log_message('Checking printer connection')
        self.printer.check()
        if cfg.calibrate_corners:
            self.log_message('Starting mesh calibration')
            self.calibrate()
            self.log_message('Mesh calibration completed')
        if self.plane is None:
            raise RuntimeError('Calibration disabled: supply a verified plane explicitly.')
        (data_dir/'experiment_metadata.json').write_text(
            json.dumps(asdict(cfg), default=str, indent=2))
        (data_dir/'calibration.json').write_text(json.dumps({
            'a':getattr(self.plane,'a',None),
            'b':getattr(self.plane,'b',None),
            'c':getattr(self.plane,'c',None),
            'corners':getattr(self.plane,'corners',None),
            'max_residual':getattr(self.plane,'max_residual',None)},indent=2))
        self.log_message('Experiment metadata and calibration saved')
        points = cfg.grid.points()
        if not points:
            raise ValueError('Experiment grid contains no points')
        safe_z = max(cfg.geometry.physical(x,y,self.plane)[2] for _,_,x,y in points)
        self.printer.last_clearance_z = safe_z
        self.log_message(f'Grid initialized: {len(points)} measurement points')
        factory = self.pump_factory or (lambda: Pump(
            cfg.pump_port,cfg.pump_baud,cfg.infusion_rate_ul_min,cfg.infusion_volume_ul))
        ctx = factory() if cfg.infusion_every else nullcontext(None)
        self.log_message('Initializing pump' if cfg.infusion_every else 'Pump disabled')
        try:
            with ctx as pump:
                stopped = False
                for index,(r,c,x,y) in enumerate(points):
                    if self.control.check():
                        stopped = True
                        self.log_message('Experiment stopped by user control')
                        break
                    self._point_ocv_bias = None
                    self.log_message(f'Point {index+1}/{len(points)} | Row={r}, Column={c} | X={x:.2f}, Y={y:.2f}')
                    self.log_message('Moving to measurement position')
                    contact = self.printer.travel(x,y,self.plane)
                    try:
                        if pump is not None and index % cfg.infusion_every == 0:
                            self.log_message('Starting electrolyte infusion')
                            pump.infuse()
                            self.log_message('Infusion completed; stabilizing droplet')
                            time.sleep(cfg.droplet_stabilize_seconds)
                        self.log_message('Descending to sample contact')
                        self.printer.descend(contact)
                        self.log_message('Contact movement completed')
                        for label,runner in self.runners.items():
                            directory = data_dir / ('data'+label.lower())
                            directory.mkdir(exist_ok=True)
                            path = directory/f'{cfg.file_prefix}_x{x:.1f}_y{y:.1f}.csv'
                            self.log_message(f'Starting {label} measurement')
                            status = 'ok'
                            try:
                                valid = runner(path)
                                if cfg.sanity_check and not valid:
                                    self.log_message(f'{label} validation failed; starting recovery')
                                    valid = recover(label,self.printer,pump,runner,path,
                                                    cfg.max_recovery_attempts,cfg.droplet_stabilize_seconds)
                                if not valid:
                                    status = 'skipped'
                            except Exception as exc:
                                status = 'error'
                                self.log_message(f'ERROR during {label}: {type(exc).__name__}: {exc}')
                                self._log(dict(row=r,column=c,x_mm=x,y_mm=y,
                                    technique=label,status=status,file=str(path),
                                    contact_z_mm=self.printer.last_contact_z))
                                raise
                            self._log(dict(row=r,column=c,x_mm=x,y_mm=y,
                                technique=label,status=status,file=str(path),
                                contact_z_mm=self.printer.last_contact_z))
                            self.log_message(f'{label} completed: {status}')
                            if status == 'skipped':
                                self.log_message(f'Skipping remaining techniques at point {index+1}')
                                break
                    finally:
                        self.log_message('Retracting SDC head')
                        self.printer.retract()
                        self.log_message('Retraction completed')
                    self.log_message(f'Point {index+1}/{len(points)} finished')
                if not stopped:
                    self.log_message('Experiment sequence completed')
        except Exception as exc:
            self.log_message(f'EXPERIMENT INTERRUPTED: {type(exc).__name__}: {exc}')
            raise
