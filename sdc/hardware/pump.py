"""Serial syringe-pump adapter, preserving original pump commands."""
import time

class Pump:
    def __init__(self,port,baud,rate_ul_min,volume_ul,timeout=120):
        self.port,self.baud=port,baud
        self.rate_ul_min,self.volume_ul=rate_ul_min,volume_ul
        self.timeout=timeout
        self.ser=None
    def __enter__(self):
        import serial
        self.ser=serial.Serial(self.port,self.baud,timeout=1)
        self.command(f'irate {self.rate_ul_min/1000:.6f} m/m')
        self.command(f'tvolume {self.volume_ul/1000:.6f} ml')
        return self
    def command(self,cmd):
        self.ser.write((cmd+'\r').encode())
        time.sleep(.1)
        return self.ser.read_all().decode(errors='replace')
    def infuse(self):
        self.command('civolume')
        self.command('irun')
        start=time.monotonic()
        while time.monotonic()-start < self.timeout:
            time.sleep(.5)
            status=self.command('status')
            if 'Stalled' in status: raise RuntimeError('Pump stalled')
            if 'Target' in status or 'T*' in status: return
        raise TimeoutError('Pump target volume not confirmed')
    def __exit__(self,*exc):
        if self.ser is not None:
            self.ser.close()
