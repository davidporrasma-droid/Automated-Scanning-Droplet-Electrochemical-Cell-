"""PEIS (potentiostatic EIS) based on OCV_PEISAuromated.ipynb.

Important: voltage (V vs instrument reference) must be explicitly supplied,
usually from the measured OCV at the SAME grid point.
"""
import math
import easy_biologic as ebl
import easy_biologic.base_programs as blp
from .common import require_keys, saved_ok

KEYS = ('initial_frequency', 'final_frequency', 'amplitude_voltage',
        'frequency_number', 'duration', 'repeat', 'wait')

def run_eis(address, channel, params, save_path, sanity_check=True,
            *, bias_voltage=None):
    require_keys(params, KEYS)
    if bias_voltage is None:
        bias_voltage = params.get('voltage')
    if bias_voltage is None or not math.isfinite(float(bias_voltage)):
        raise ValueError('PEIS requires a measured OCV bias or an explicit eis_params["voltage"].')
    if not (params['initial_frequency'] > params['final_frequency'] > 0):
        raise ValueError('PEIS frequency bounds must satisfy initial > final > 0')
    if params['amplitude_voltage'] <= 0 or params['frequency_number'] < 2:
        raise ValueError('PEIS amplitude must be positive and frequency_number >= 2')
    hardware_params = dict(params)
    hardware_params['voltage'] = float(bias_voltage)
    device = ebl.BiologicDevice(address)
    program = blp.PEIS(device, hardware_params, channels=[channel])
    print(f'[eis] PEIS bias={bias_voltage:.5f} V; '
          f'{params["initial_frequency"]} -> {params["final_frequency"]} Hz', flush=True)
    program.run('data')
    program.save_data(str(save_path))
    return saved_ok(save_path, sanity_check)
