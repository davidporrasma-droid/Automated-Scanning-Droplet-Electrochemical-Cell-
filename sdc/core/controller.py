"""Between-point pause/stop requests; Jupyter-friendly (no input thread)."""
class RunControl:
    def __init__(self): self.stop_requested=False;self.pause_requested=False
    def request_stop(self): self.stop_requested=True
    def request_pause(self): self.pause_requested=True
    def check(self):
        if self.pause_requested:
            self.pause_requested=False
            if input('Paused between points. Enter to continue or type stop: ').strip().lower()=='stop':
                self.stop_requested=True
        return self.stop_requested
