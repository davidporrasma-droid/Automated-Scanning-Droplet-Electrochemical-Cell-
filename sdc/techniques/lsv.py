"""Original single-forward-sweep CV-backed BioLogic implementation."""
from collections import namedtuple
from easy_biologic import BiologicProgram
from easy_biologic.lib import technique_fields as tfs
from easy_biologic.lib import data_parser as dp
from easy_biologic.lib import ec_lib as ecl

def _set_defaults(params, defaults, channels):
    """Mirror of easy_biologic's internal set_defaults helper."""
    if channels is None:
        # single-channel dict keyed by 0
        merged = {**defaults, **params}
        return {0: merged}
    result = {}
    for ch in channels:
        ch_params = params.get(ch, params)   # per-channel or shared
        result[ch] = {**defaults, **ch_params}
    return result


def _map_hardware_params(ch_params, by_channel=False):
    """
    Passes through hardware-level params (I_Range, E_Range, Bandwidth …)
    if present in ch_params.  Matches the blp helper signature.
    """
    hw_keys = ('I_Range', 'E_Range', 'Bandwidth')
    return {k: ch_params[k] for k in hw_keys if k in ch_params}


class LSV(BiologicProgram):
    """
    Linear Sweep Voltammetry using the BioLogic 'cv' technique backend.

    A single forward sweep from ``start`` (Ei) to ``end`` (Ef) is
    performed.  No return leg is executed (Scan_number = 1, N_Cycles = 0).

    Parameters
    ----------
    device  : BiologicDevice
    params  : dict
        start   — Initial potential in V          [default: 0]
        end     — Final potential in V            [default: 0.5]
        rate    — Scan rate in V/s                [default: 0.05]
        step    — Record every <step> V           [default: 0.001]
        average — Average over dE step            [default: False]
    **kwargs : passed to BiologicProgram (e.g. channels=[0])
    """

    def __init__(self, device, params, **kwargs):
        defaults = {
            'vs_initial':        False,
            'start':             0,
            'end':               0.5,
            'step':              0.001,
            'rate':              0.05,
            'average':           False,
            'Begin_measuring_I': 0.5,
            'End_measuring_I':   1.0,
        }

        channels = kwargs.get('channels', None)
        params = _set_defaults(params, defaults, channels)

        super().__init__(device, params, **kwargs)
        self.params = params
        print("merged_params:", params)
        print("self.params after super().__init__:", self.params)
        # Use the CV technique file — LSV is a degenerate CV
        self._techniques       = ['cv']
        self._parameter_types  = tfs.CV
        self._data_fields      = (
            dp.SP300_Fields.CV
            if ecl.is_in_SP300_family(self.device.kind) else
            dp.VMP3_Fields.CV
        )

        self.field_titles = ['Voltage [V]', 'Current [A]', 'Time [s]', 'Power [W]']
        self._fields      = namedtuple('LSV_Datum', ['voltage', 'current', 'time', 'power'])

        self._field_values = lambda datum, segment: (
            datum.voltage,
            datum.current,
            dp.calculate_time(datum.t_high, datum.t_low, segment.info, segment.values),
            datum.voltage * datum.current,
        )

    def run(self, retrieve_data=True):
        """
        Build a one-way voltage profile and run the cv technique.

        The BioLogic cv technique expects exactly 5 voltage steps; for LSV
        we set them all to the endpoint so the instrument stays there after
        the sweep completes.
        """
        params = {}
        for ch, ch_params in self.params.items():
            start = ch_params['start']
            end   = ch_params['end']

            # 5-point profile required by the cv technique kernel.
            # Steps 0→1 perform the sweep; steps 2-4 hold at end.
            voltage_profile = [start, end, end, end, end]

            params[ch] = {
                'vs_initial':        [ch_params['vs_initial']] * 5,
                'Voltage_step':      voltage_profile,
                'Scan_Rate':         [ch_params['rate']] * 5,
                'Scan_number':       1,          # one leg only → LSV
                'Record_every_dE':   ch_params['step'],
                'Average_over_dE':   ch_params['average'],
                'N_Cycles':          0,          # no repeat cycles
                'Begin_measuring_I': ch_params['Begin_measuring_I'],
                'End_measuring_I':   ch_params['End_measuring_I'],
            }
            params[ch].update(_map_hardware_params(ch_params, by_channel=False))

        self._run('cv', params, retrieve_data=retrieve_data)

