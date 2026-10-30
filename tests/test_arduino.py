import threading
import time

from roaster_adapter.arduino import ArduinoLink, parse_read_reply, resolve_port
from roaster_adapter.config import Settings


def test_parse_read_reply():
    assert parse_read_reply('0.00,392.45,392.45,80,10,0\r\n') == (392.45, 80, 10)
    assert parse_read_reply('# Active channels set to 0200') is None
    assert parse_read_reply('0.0,abc,1,2,3,0') is None


def test_resolve_port_keeps_explicit_name():
    assert resolve_port('/dev/ttyUSB3') == '/dev/ttyUSB3'


def make_link(**overrides):
    s = Settings(read_interval=0.05, read_timeout=0.3, command_settle=0.05, serial_open_delay=0, **overrides)
    return ArduinoLink(s, on_reading=lambda r: None, on_connection=lambda c: None)


def test_newer_command_replaces_older_and_moves_to_end():
    link = make_link()
    link.send('OT1', 50)
    link.send('DRUM', 100)
    link.send('OT1', 60)
    assert [link._pop_command() for _ in range(3)] == ['DRUM;100', 'OT1;60', None]


def test_estop_drops_pending_commands():
    link = make_link()
    link.send('OT1', 80)
    link.send('OT2', 10)
    link.send('ESTOP')
    link.send('OT2', 20)
    assert [link._pop_command() for _ in range(3)] == ['ESTOP', 'OT2;20', None]


class FakePort:
    """Answers READ like SkyCommand and records write times."""

    def __init__(self):
        self.writes: list[tuple[float, str]] = []
        self._reply = b''
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data: bytes):
        line = data.decode().strip()
        self.writes.append((time.monotonic(), line))
        if line == 'READ':
            with self._lock:
                self._reply += b'0.00,212.00,212.00,0,0,0\r\n'

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def readline(self):
        with self._lock:
            if self._reply:
                line, _, rest = self._reply.partition(b'\n')
                self._reply = rest
                return line + b'\n'
        time.sleep(0.01)
        return b''


def test_session_spaces_commands_and_reports_readings():
    port = FakePort()
    readings, connections = [], []
    s = Settings(serial_port='/dev/fake', read_interval=0.05, read_timeout=0.3, command_settle=0.1,
                 serial_open_delay=0)
    link = ArduinoLink(s, on_reading=readings.append, on_connection=connections.append,
                       open_serial=lambda *a, **k: port)
    link.start()
    time.sleep(0.2)
    link.send('OT1', 50)
    link.send('OT2', 20)
    time.sleep(0.5)
    link.stop()
    link.join(1)

    assert connections[0] is True
    assert readings and abs(readings[0].temp_f - 212.0) < 1e-9
    lines = [line for _, line in port.writes]
    assert 'OT1;50' in lines and 'OT2;20' in lines
    # Nothing may be written within command_settle after a non-READ command.
    for (t0, l0), (t1, _) in zip(port.writes, port.writes[1:]):
        if l0 != 'READ':
            assert t1 - t0 >= s.command_settle * 0.95
