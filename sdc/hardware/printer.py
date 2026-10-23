"""Moonraker motion interface; M400 barrier for completed commands."""
import requests

class Printer:
    def __init__(self, url, geometry, travel_feed=300, work_feed=100, settle_seconds=5, nudge_mm=.005):
        self.url=url.rstrip('/')
        self.geometry=geometry
        self.travel_feed=travel_feed
        self.work_feed=work_feed
        self.settle_seconds=settle_seconds
        self.nudge_mm=nudge_mm
        self.last_contact_z=None
        self.last_clearance_z=None

    def check(self):
        response=requests.get(self.url+'/server/info',timeout=3)
        response.raise_for_status()
        return True

    def gcode(self, script, wait=True):
        response=requests.post(self.url+'/printer/gcode/script', params={'script':script},timeout=30)
        response.raise_for_status()
        if wait:
            r=requests.post(self.url+'/printer/gcode/script', params={'script':'M400'},timeout=120)
            r.raise_for_status()

    def travel(self,x,y,plane):
        px,py,clearance,contact=self.geometry.physical(x,y,plane)
        # Retract vertically before a horizontal move: do not combine XYZ into one diagonal traverse.
        # The controller tracks the max clearance observed for these grid points.
        if self.last_clearance_z is not None:
            self.gcode(f'G90\nG0 Z{max(clearance,self.last_clearance_z):.3f} F{self.travel_feed}')
        else:
            self.gcode(f'G90\nG0 Z{clearance:.3f} F{self.travel_feed}')
        self.gcode(f'G90\nG0 X{px:.3f} Y{py:.3f} F{self.travel_feed}')
        self.last_clearance_z=clearance
        return contact

    def descend(self,z):
        self.gcode(f'G90\nG1 Z{z:.4f} F{self.work_feed}\nG4 P{int(self.settle_seconds*1000)}')
        self.last_contact_z=z

    def nudge(self):
        if self.last_contact_z is None: raise RuntimeError('No known contact Z')
        self.descend(self.last_contact_z-self.nudge_mm)
        return self.last_contact_z

    def retract(self):
        if self.last_clearance_z is None: return
        self.gcode(f'G90\nG0 Z{self.last_clearance_z:.3f} F{self.travel_feed}')
        self.last_contact_z=None
