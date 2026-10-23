"""Human-in-the-loop failure recovery as in the original notebook."""
import time

def recover(label, printer, pump, run_measurement, path, attempts=5, stabilize=3):
    for attempt in range(1,attempts+1):
        print(f'[recovery] {label} attempt {attempt}/{attempts}: 1=refill 2=nudge Z 3=skip')
        choice=input('Choice: ').strip()
        if choice=='3':return False
        if choice=='1':
            if pump is None:
                print('[recovery] pump unavailable');continue
            z=printer.last_contact_z
            printer.retract()
            pump.infuse()
            time.sleep(stabilize)
            printer.descend(z)
        elif choice=='2': printer.nudge()
        else:continue
        if run_measurement(path):return True
    return False
