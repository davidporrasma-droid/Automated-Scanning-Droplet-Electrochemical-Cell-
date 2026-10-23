"""CA measurement; parameters directly match uploaded notebook CA_PARAMS."""
import easy_biologic as ebl
import easy_biologic.base_programs as blp
from .common import require_keys, saved_ok

def run_ca(address, channel, params, save_path, sanity_check=True):
    require_keys(params, ['voltages', 'durations', 'vs_initial', 'time_interval', 'current_interval'])

    if not params['voltages'] or len(params['voltages']) != len(params['durations']):
        raise ValueError('CA voltages and durations must have equal nonzero lengths')
    if any(t <= 0 for t in params['durations']):
        raise ValueError('CA durations must be positive')
    device = ebl.BiologicDevice(address)
    program = blp.CA(device, dict(params), channels=[channel])
    print(f'[{ca}] Starting CA', flush=True)
    program.run('data')
    program.save_data(str(save_path))
    return saved_ok(save_path, sanity_check)
