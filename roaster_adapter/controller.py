"""Roaster state and the rules for who may change it.

All methods run on the asyncio event loop. Command sources:
  'artisan' - WebSocket commands from Artisan
  'touch'   - the LCD UI
  'preheat' - the preheat sequence
  'system'  - internal safety actions (watchdog, link reset)

Rules (CLAUDE.md):
- While preheating only the preheat sequence and the LCD E-STOP act; E-STOP ends preheat.
- Otherwise Artisan commands always act. LCD controls act only while Artisan is polling,
  except E-STOP and starting preheat.
- No getData from Artisan for `artisan_watchdog` seconds -> OFF (not during preheat).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .arduino import Reading
from .config import Settings

log = logging.getLogger(__name__)

# Seconds a commanded heater/fan value wins over READ replies (> command_settle + read_interval).
OUTPUT_GRACE = 2.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def round5(v: float) -> int:
    """The roaster ignores heater/fan duties that are not multiples of 5."""
    return max(0, min(100, int(round(v / 5.0)) * 5))


@dataclass
class RoasterState:
    arduino_connected: bool = False
    temp_c: float | None = None          # latest temperature from the Arduino
    temp_time: float = float('-inf')     # monotonic time of temp_c
    display_temp_c: float | None = None  # what Artisan's BT LCD shows (see on_artisan_poll)
    heater: int = 0
    fan: int = 0
    drum: bool = False
    cooling: bool = False
    filter: int = 0
    artisan_last_poll: float = float('-inf')
    watchdog_armed: bool = False
    watchdog_tripped: bool = False
    charge_time: float | None = None     # monotonic time of CHARGE, None if not charged
    drop_time: float | None = None
    preheat_phase: str | None = None     # None when not preheating
    preheat_detail: str = ''
    message: str = ''                    # short status line for the LCD
    message_time: float = float('-inf')
    listeners: list = field(default_factory=list)


class Controller:
    def __init__(self, settings: Settings, send: Callable[..., None],
                 clock: Callable[[], float] = time.monotonic):
        self.s = settings
        self.state = RoasterState()
        self._send = send                  # ArduinoLink.send
        self._clock = clock
        self._push: list[Callable[[dict], None]] = []
        self._reading_event = asyncio.Event()
        self._preheat_task: asyncio.Task | None = None
        self._changed = asyncio.Event()
        self._output_cmd_time = float('-inf')

    # -- observers --

    def add_push_listener(self, fn: Callable[[dict], None]) -> None:
        """fn receives Artisan push messages such as {'pushMessage': 'startRoasting'}."""
        self._push.append(fn)

    def _notify(self) -> None:
        self._changed.set()

    def consume_changed(self) -> bool:
        """True if the state changed since the last call (used by the UI to redraw)."""
        changed = self._changed.is_set()
        self._changed.clear()
        return changed

    def say(self, text: str) -> None:
        log.info('message: %s', text)
        self.state.message = text
        self.state.message_time = self._clock()
        self._notify()

    # -- derived state --

    @property
    def preheating(self) -> bool:
        return self._preheat_task is not None and not self._preheat_task.done()

    def artisan_alive(self) -> bool:
        return self._clock() - self.state.artisan_last_poll <= self.s.artisan_watchdog

    def temp_fresh(self) -> bool:
        return self._clock() - self.state.temp_time <= self.s.reading_stale

    def _allowed(self, source: str, action: str) -> bool:
        if self.preheating:
            if source == 'preheat' or (source == 'touch' and action == 'estop'):
                return True
            if source == 'touch':
                self.say('Preheating: only E-STOP works')
            return False
        if source in ('artisan', 'system'):
            return True
        if source == 'touch':
            if action in ('estop', 'preheat'):
                return True
            if self.artisan_alive():
                return True
            self.say('Artisan not connected')
            return False
        return False

    # -- input from the Arduino link (already on the event loop) --

    def on_connection(self, connected: bool) -> None:
        self.state.arduino_connected = connected
        if connected:
            # SkyCommand may keep outputs from before this program (re)started, or have
            # reset them. Start from a known state.
            self._send('OFF')
            self._zero_outputs()
        self._notify()

    def on_reading(self, r: Reading) -> None:
        st = self.state
        st.temp_c = round(f_to_c(r.temp_f), 2)
        st.temp_time = r.time
        # READ reports the duties SkyCommand is sending. Right after a change the reply may
        # still carry the old value, so keep the commanded value for a moment.
        if r.time - self._output_cmd_time > OUTPUT_GRACE:
            st.heater, st.fan = r.heater, r.fan
        if not self.artisan_alive():
            st.display_temp_c = st.temp_c
        self._reading_event.set()
        self._notify()

    async def next_reading(self, timeout: float) -> bool:
        self._reading_event.clear()
        try:
            await asyncio.wait_for(self._reading_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # -- input from Artisan --

    def on_artisan_poll(self) -> dict:
        """getData. Returns the data node for the reply."""
        st = self.state
        st.artisan_last_poll = self._clock()
        st.watchdog_armed = True
        if st.watchdog_tripped:
            st.watchdog_tripped = False
            self.say('Artisan connected')
        # With the shipped Artisan settings (no dropDuplicates/minmaxLimits/dropSpikes,
        # no symbolic formula) Artisan's LCD shows exactly the value sent here as '%.1f'.
        # Showing the same number keeps the two displays identical.
        data = {}
        if st.temp_c is not None and self.temp_fresh():
            data = {'BT': st.temp_c, 'ET': st.temp_c}
            st.display_temp_c = st.temp_c
        else:
            st.display_temp_c = None
        data.update({'heater': st.heater, 'fan': st.fan})
        self._notify()
        return data

    def on_artisan_command(self, msg: dict) -> None:
        cmd = msg.get('command')
        value = msg.get('value')
        handlers = {
            'setHeater': lambda: self.set_heater(value, 'artisan'),
            'setFan': lambda: self.set_fan(value, 'artisan'),
            'setDrum': lambda: self.set_drum(value, 'artisan'),
            'setCooling': lambda: self.set_cooling(value, 'artisan'),
            'setFilter': lambda: self.set_filter(value, 'artisan'),
            'estop': lambda: self.estop('artisan'),
            'off': lambda: self.off('artisan'),
            'charge': lambda: self.charge('artisan'),
            'drop': lambda: self.drop('artisan'),
        }
        handler = handlers.get(cmd)
        if handler is None:
            log.warning('unknown Artisan command %r', msg)
            return
        try:
            handler()
        except (TypeError, ValueError) as e:
            log.warning('bad Artisan command %r: %s', msg, e)

    # -- actions --

    def set_heater(self, value, source: str) -> bool:
        if not self._allowed(source, 'heater'):
            return False
        self.state.heater = round5(float(value))
        self._send('OT1', self.state.heater)
        self._output_cmd_time = self._clock()
        self._notify()
        return True

    def set_fan(self, value, source: str) -> bool:
        if not self._allowed(source, 'fan'):
            return False
        self.state.fan = round5(float(value))
        self._send('OT2', self.state.fan)
        self._output_cmd_time = self._clock()
        self._notify()
        return True

    def set_drum(self, on, source: str) -> bool:
        if not self._allowed(source, 'drum'):
            return False
        self.state.drum = bool(int(float(on)))
        self._send('DRUM', 100 if self.state.drum else 0)
        self._notify()
        return True

    def set_cooling(self, on, source: str) -> bool:
        if not self._allowed(source, 'cooling'):
            return False
        self.state.cooling = bool(int(float(on)))
        self._send('COOL', 100 if self.state.cooling else 0)
        self._notify()
        return True

    def set_filter(self, value, source: str) -> bool:
        if not self._allowed(source, 'filter'):
            return False
        self.state.filter = max(0, min(4, int(float(value))))
        self._send('FILTER', self.state.filter)
        self._notify()
        return True

    def estop(self, source: str) -> bool:
        if not self._allowed(source, 'estop'):
            return False
        self._send('ESTOP')
        self.state.heater, self.state.fan = 0, 100
        self._output_cmd_time = self._clock()
        if self.preheating:
            self._preheat_task.cancel()
        self.say('E-STOP')
        return True

    def off(self, source: str) -> bool:
        if not self._allowed(source, 'off'):
            return False
        self._send('OFF')
        self._zero_outputs()
        self._notify()
        return True

    def _zero_outputs(self) -> None:
        st = self.state
        st.heater = st.fan = st.filter = 0
        st.drum = st.cooling = False
        self._output_cmd_time = self._clock()

    def charge(self, source: str) -> bool:
        if not self._allowed(source, 'charge'):
            return False
        self.state.charge_time = self._clock()
        self.state.drop_time = None
        if source == 'touch':
            self._push_message({'pushMessage': 'startRoasting'})
        self._notify()
        return True

    def drop(self, source: str) -> bool:
        if not self._allowed(source, 'drop'):
            return False
        self.state.drop_time = self._clock()
        if source == 'touch':
            self._push_message({'pushMessage': 'endRoasting'})
        # project.md: on DROP the heater goes off, fan 80 %, bean cooling on.
        self.set_heater(0, source)
        self.set_fan(self.s.drop_fan, source)
        self.set_cooling(1, source)
        self._notify()
        return True

    def _push_message(self, msg: dict) -> None:
        for fn in self._push:
            fn(msg)

    # -- preheat --

    def start_preheat(self) -> bool:
        if self.preheating or not self._allowed('touch', 'preheat'):
            return False
        if not (self.state.arduino_connected and self.temp_fresh()):
            self.say('No temperature from Arduino')
            return False
        from .preheat import run_preheat
        self._preheat_task = asyncio.get_running_loop().create_task(run_preheat(self))
        self._preheat_task.add_done_callback(self._preheat_finished)
        self._notify()
        return True

    def _preheat_finished(self, task: asyncio.Task) -> None:
        st = self.state
        st.preheat_phase = None
        st.preheat_detail = ''
        if not task.cancelled() and task.exception() is not None:
            log.error('preheat failed', exc_info=task.exception())
        # The Artisan watchdog resumes, counting from now.
        st.artisan_last_poll = max(st.artisan_last_poll, self._clock())
        st.watchdog_armed = True
        self._notify()

    def set_preheat_status(self, phase: str, detail: str = '') -> None:
        self.state.preheat_phase = phase
        self.state.preheat_detail = detail
        self._notify()

    # -- watchdog --

    def check_watchdog(self) -> None:
        st = self.state
        if self.preheating or not st.watchdog_armed:
            return
        if self._clock() - st.artisan_last_poll > self.s.artisan_watchdog:
            st.watchdog_armed = False
            st.watchdog_tripped = True
            self._send('OFF')
            self._zero_outputs()
            self.say('Artisan lost: roaster OFF')

    async def run_watchdog(self) -> None:
        while True:
            self.check_watchdog()
            await asyncio.sleep(0.5)
