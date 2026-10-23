"""CV measurement; parameters directly match uploaded notebook CV_PARAMS."""
import easy_biologic as ebl
import easy_biologic.base_programs as blp
from .common import require_keys, saved_ok

def run_cv(address, channel, params, save_path, sanity_check=True):
    require_keys(params, ['start', 'end', 'E2', 'Ef', 'rate', 'step', 'N_Cycles'])

    if params['rate'] <= 0 or params['step'] <= 0 or params['N_Cycles'] < 1:
        raise ValueError('CV rate, step and N_Cycles must be positive')
    device = ebl.BiologicDevice(address)
    program = blp.CV(device, dict(params), channels=[channel])
    print(f'[{cv}] Starting CV', flush=True)
    program.run('data')
    program.save_data(str(save_path))
    return saved_ok(save_path, sanity_check)
