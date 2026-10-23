"""Defaults transcribed from OCV_LSVMeshLvl.ipynb; override for each run."""
from dataclasses import dataclass, field
from pathlib import Path
from .core.grid import Grid
from .calibration.coordinates import Geometry

@dataclass
class Config:
    data_dir:Path=Path('data/TestTEST')
    file_prefix:str='HRL_EC_ECH_MnFeCoCuNi_Test01'
    printer_url:str='http://10.45.205.84:4409'
    biologic_address:str='192.109.209.128'
    biologic_channel:int=0
    pump_port:str='COM3'
    pump_baud:int=115200
    infusion_every:int=1
    infusion_rate_ul_min:float=10.0
    infusion_volume_ul:float=0.5
    droplet_stabilize_seconds:float=3.0
    settle_seconds:float=5.0
    travel_feed:int=300
    work_feed:int=100
    nudge_mm:float=.005
    sanity_check:bool=True
    max_recovery_attempts:int=5
    calibrate_corners:bool=True
    # A verified plane can be passed explicitly if calibration is disabled.
    grid:Grid=field(default_factory=Grid)
    geometry:Geometry=field(default_factory=lambda:Geometry(103.624,104.431,109.484,10.0))
    techniques:list[str]=field(default_factory=lambda: ['OCV', 'LSV'])
    cv_params:dict=field(default_factory=lambda: {
        'start':0.0, 'end':0.4, 'E2':-0.6, 'Ef':0.0,
        'rate':0.01, 'step':0.001, 'N_Cycles':2})
    ca_params:dict=field(default_factory=lambda: {
        'voltages':[1.0], 'durations':[10.0], 'vs_initial':False,
        'time_interval':0.1, 'current_interval':0.0001})
    cp_params:dict=field(default_factory=lambda: {
        'currents':[-20e-6], 'durations':[100.0], 'vs_initial':False,
        'time_interval':0.05, 'voltage_interval':1})
    eis_params:dict=field(default_factory=lambda: {
        'initial_frequency':100000.0, 'final_frequency':0.1,
        'amplitude_voltage':0.01, 'frequency_number':51,
        'duration':0, 'repeat':20, 'wait':0.1})
    ocv_params:dict=field(default_factory=lambda: {'time':180.0,'time_interval':.5,'voltage_interval':1000})
    lsv_params:dict=field(default_factory=lambda: {'start':0.0,'end':-1.0,'rate':.005,'step':.001,'average':False})
