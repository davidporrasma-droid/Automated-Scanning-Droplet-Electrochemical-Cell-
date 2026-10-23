"""LSV runner using the preserved LSV class."""
from pathlib import Path
import easy_biologic as ebl
from .lsv import LSV

def run_lsv(address, channel, params, save_path, sanity_check=True):
    device = ebl.BiologicDevice(address)
    program = LSV(device, params, channels=[channel])
    program.run('data')
    program.save_data(str(save_path))
    return not sanity_check or (Path(save_path).is_file() and Path(save_path).stat().st_size > 0)
