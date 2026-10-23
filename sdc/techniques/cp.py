"""CP measurement; parameters directly match uploaded notebook CP_PARAMS."""
import easy_biologic as ebl
import easy_biologic.base_programs as blp
from .common import require_keys, saved_ok

def run_cp(address, channel, params, save_path, sanity_check=True):
    require_keys(params, ['currents', 'durations', 'vs_initial', 'time_interval', 'voltage_interval'])

    if not params['currents'] or len(params['currents']) != len(params['durations']):
        raise ValueError('CP currents and durations must have equal nonzero lengths')
    if any(t <= 0 for t in params['durations']):
        raise ValueError('CP durations must be positive')
    device = ebl.BiologicDevice(address)
    program = blp.CP(device, dict(params), channels=[channel])
    print(f'[{cp}] Starting CP', flush=True)
    program.run('data')
    program.save_data(str(save_path))
    return saved_ok(save_path, sanity_check)
