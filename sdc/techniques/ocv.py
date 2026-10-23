"""OCV with optional extraction of mean measured potential for PEIS."""
import math
import easy_biologic as ebl
import easy_biologic.base_programs as blp
from .common import saved_ok

def run_ocv(address, channel, params, save_path, sanity_check=True,
            *, return_mean=False):
    device = ebl.BiologicDevice(address)
    program = blp.OCV(device, dict(params), channels=[channel])
    program.run('data')
    program.save_data(str(save_path))
    success = saved_ok(save_path, sanity_check)
    if not return_mean:
        return success
    if not success:
        return False, None
    try:
        values = [float(item.voltage) for item in program.data[channel]]
        values = [v for v in values if math.isfinite(v)]
        mean = sum(values) / len(values) if values else None
    except (AttributeError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        mean = None
    print(f'[ocv] Mean Ewe for PEIS: {mean!r} V', flush=True)
    return success, mean
