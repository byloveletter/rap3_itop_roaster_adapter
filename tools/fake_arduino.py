"""Simulated Arduino running SkyCommand.ino, on a pseudo terminal.

Reproduces the parts of SkyCommand that matter to the Raspberry Pi program:
- loop() timing: the serial port is looked at only between roaster frames;
- Serial.readString() with a 100 ms timeout, parsed up to the first ';' only,
  so two commands read together are both ignored (logged as LOST);
- the READ reply format and the 10 s no-command shutdown;
- a crude thermal model so preheat can be exercised.

Usage: python3 tools/fake_arduino.py [--link /tmp/fake-arduino] [--speed 10]
then run the adapter with --serial /tmp/fake-arduino
"""

import argparse
import os
import random
import select
import time
import tty

AMBIENT_C = 25.0


class SkyCommandSim:
    def __init__(self, speed: float):
        self.speed = speed
        self.temp_c = AMBIENT_C
        self.heat = self.vent = self.drum = self.cool = self.filter = 0
        self.last_event = time.monotonic()

    def step_thermal(self, dt: float) -> None:
        dt *= self.speed
        gain = 0.0176 * self.heat
        loss = (self.temp_c - AMBIENT_C) * (0.004 + 0.0002 * self.vent + (0.001 if self.drum else 0))
        self.temp_c += (gain - loss) * dt

    def shutdown(self) -> None:
        self.heat = self.vent = self.drum = self.cool = self.filter = 0

    def handle(self, text: str) -> str | None:
        text = text.strip()
        split = text.find(';')
        command, value = (text[:split], text[split + 1:]) if split >= 0 else (text, '')
        try:
            v = int(value) if value else 0
        except ValueError:
            v = 0
        if command == 'READ':
            temp_f = self.temp_c * 9 / 5 + 32 + random.uniform(-0.3, 0.3)
            self.last_event = time.monotonic()
            return f'0.00,{temp_f:.2f},{temp_f:.2f},{self.heat},{self.vent},0'
        if command == 'OT1' and v <= 100:
            self.heat = v
        elif command == 'OT2' and v <= 100:
            self.vent = v
        elif command == 'DRUM':
            self.drum = 100 if v else 0
        elif command == 'COOL' and v <= 100:
            self.cool = v
        elif command == 'FILTER' and v <= 100:
            self.filter = v
        elif command == 'OFF':
            self.shutdown()
        elif command == 'ESTOP':
            self.heat, self.vent = 0, 100
        elif command == 'CHAN':
            return '# Active channels set to 0200'
        elif command == 'UNITS':
            pass
        else:
            print(f'LOST/unknown input {text!r}', flush=True)
            return None
        if command in ('OT1', 'OT2', 'DRUM', 'COOL', 'FILTER'):
            self.last_event = time.monotonic()
        print(f'{command:<6} {value:>4}  -> heat={self.heat} vent={self.vent} drum={self.drum} '
              f'cool={self.cool} filter={self.filter} temp={self.temp_c:.1f}C', flush=True)
        return None


def read_string(fd: int) -> str:
    """Serial.readString(): read until 100 ms pass without new data."""
    data = b''
    while True:
        r, _, _ = select.select([fd], [], [], 0.1)
        if not r:
            return data.decode('ascii', errors='replace')
        data += os.read(fd, 1024)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--link', default='/tmp/fake-arduino', help='symlink to the pty slave')
    ap.add_argument('--speed', type=float, default=1.0, help='thermal model speed-up')
    args = ap.parse_args()

    master, slave = os.openpty()
    tty.setraw(slave)
    slave_name = os.ttyname(slave)
    if os.path.islink(args.link):
        os.unlink(args.link)
    os.symlink(slave_name, args.link)
    print(f'SkyCommand simulator on {slave_name} (link {args.link}), speed x{args.speed}', flush=True)

    sim = SkyCommandSim(args.speed)
    last = time.monotonic()
    try:
        while True:
            # failSafeChecks + sendRoasterMessage + getRoasterMessage
            if time.monotonic() - sim.last_event > 10.0 and (sim.heat or sim.vent or sim.drum):
                print('no command for 10 s -> shutdown()', flush=True)
                sim.shutdown()
            time.sleep(0.10 + random.uniform(0.10, 0.25))
            now = time.monotonic()
            sim.step_thermal(now - last)
            last = now
            # getArtisanMessage
            r, _, _ = select.select([master], [], [], 0)
            if r:
                text = read_string(master)
                if text.strip().count('\n') >= 1:
                    print(f'LOST: commands read together {text!r}', flush=True)
                reply = sim.handle(text)
                if reply is not None:
                    os.write(master, (reply + '\r\n').encode('ascii'))
    except KeyboardInterrupt:
        pass
    finally:
        if os.path.islink(args.link):
            os.unlink(args.link)


if __name__ == '__main__':
    main()
