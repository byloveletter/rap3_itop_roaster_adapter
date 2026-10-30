"""Serial link to the Arduino running SkyCommand.ino.

SkyCommand reads its serial port once per loop() with Serial.readString() and parses
only up to the first ';'. Two commands that land in the same read are both ignored,
so this link never has more than one command in flight:

- READ is answered immediately, so the next write may follow the reply.
- Other commands have no reply. After one, nothing is written for
  `command_settle` seconds, which covers the longest SkyCommand loop
  (send ~120 ms + roaster read timeout 500 ms + readString timeout 100 ms).

The link runs in its own thread because pyserial is blocking. Callbacks are invoked
from that thread; the caller is responsible for handing them over to its event loop.
"""

import glob
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

import serial

from .config import Settings

log = logging.getLogger(__name__)

# Commands that override everything still waiting to be sent.
PRIORITY_COMMANDS = ('ESTOP', 'OFF')


@dataclass
class Reading:
    temp_f: float   # roaster temperature as reported by SkyCommand (Fahrenheit)
    heater: int     # heater duty currently sent to the roaster
    fan: int        # fan (vent) duty currently sent to the roaster
    time: float     # time.monotonic() when the reply arrived


def parse_read_reply(line: str) -> tuple[float, int, int] | None:
    """Parse '0.0,<temp>,<temp>,<heat>,<vent>,0'. Returns (temp_f, heater, fan)."""
    parts = line.strip().split(',')
    if len(parts) < 5:
        return None
    try:
        return float(parts[1]), int(float(parts[3])), int(float(parts[4]))
    except ValueError:
        return None


def format_command(name: str, value: int | None = None) -> str:
    return name if value is None else f'{name};{value}'


def resolve_port(port: str) -> str | None:
    if port != 'auto':
        return port
    candidates = sorted(glob.glob('/dev/ttyACM*')) + sorted(glob.glob('/dev/ttyUSB*'))
    return candidates[0] if candidates else None


class ArduinoLink(threading.Thread):
    def __init__(self, settings: Settings,
                 on_reading: Callable[[Reading], None],
                 on_connection: Callable[[bool], None],
                 open_serial: Callable[..., serial.Serial] = serial.Serial,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(name='arduino-link', daemon=True)
        self._s = settings
        self._on_reading = on_reading
        self._on_connection = on_connection
        self._open_serial = open_serial
        self._clock = clock
        self._pending: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._connected = False

    # -- called from any thread --

    def send(self, name: str, value: int | None = None) -> None:
        """Queue a command. A newer command with the same name replaces an older one."""
        with self._lock:
            if name in PRIORITY_COMMANDS:
                self._pending.clear()
            self._pending.pop(name, None)
            self._pending[name] = format_command(name, value)
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    # -- link thread --

    def _pop_command(self) -> str | None:
        with self._lock:
            if not self._pending:
                return None
            _, line = self._pending.popitem(last=False)
            return line

    def _set_connected(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            log.info('Arduino %s', 'connected' if connected else 'disconnected')
            self._on_connection(connected)

    def _write(self, port: serial.Serial, line: str) -> None:
        log.debug('-> %s', line)
        port.write((line + '\n').encode('ascii'))
        port.flush()

    def _read_reply(self, port: serial.Serial) -> tuple[float, int, int] | None:
        deadline = self._clock() + self._s.read_timeout
        buf = b''
        while self._clock() < deadline and not self._stop.is_set():
            chunk = port.readline()
            if not chunk:
                continue
            buf += chunk
            if not buf.endswith(b'\n'):
                continue
            line = buf.decode('ascii', errors='replace').strip()
            buf = b''
            log.debug('<- %s', line)
            if not line or line.startswith('#'):
                continue
            reply = parse_read_reply(line)
            if reply is not None:
                return reply
        return None

    def _session(self, port: serial.Serial) -> None:
        last_read = float('-inf')
        while not self._stop.is_set():
            line = self._pop_command()
            if line is not None:
                self._write(port, line)
                # Quiet time so the next write is not read together with this one.
                self._stop.wait(self._s.command_settle)
                continue
            wait = last_read + self._s.read_interval - self._clock()
            if wait > 0:
                self._wake.wait(wait)
                self._wake.clear()
                continue
            self._write(port, 'READ')
            last_read = self._clock()
            reply = self._read_reply(port)
            if reply is None:
                self._set_connected(False)
                continue
            self._set_connected(True)
            temp_f, heater, fan = reply
            self._on_reading(Reading(temp_f, heater, fan, self._clock()))

    def run(self) -> None:
        while not self._stop.is_set():
            name = resolve_port(self._s.serial_port)
            if name is None:
                self._set_connected(False)
                self._stop.wait(2.0)
                continue
            try:
                with self._open_serial(name, self._s.serial_baud, timeout=0.1) as port:
                    log.info('opened %s', name)
                    self._stop.wait(self._s.serial_open_delay)
                    port.reset_input_buffer()
                    self._session(port)
            except (serial.SerialException, OSError) as e:
                log.warning('serial %s: %s', name, e)
            self._set_connected(False)
            self._stop.wait(2.0)
