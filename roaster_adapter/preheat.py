"""Preheat sequence from project.md.

1. Check the Arduino is answering with temperatures (Controller.start_preheat).
2-3. Drum off, heater 80 %, fan 10 %.
4. Wait for the target temperature.
5. Heater and fan off, wait 5 minutes.
6. Heater 75 %, fan 20 %, drum on.
7. Wait for the target temperature.
8. Heater, fan and drum off, wait 5 minutes.
9. Announce the end.

Only the LCD E-STOP interrupts it (it cancels this task). Two safety aborts send OFF:
a heating phase that exceeds `preheat_heating_timeout`, and no temperature from the
Arduino for `reading_stale` seconds.
"""

import asyncio
import logging

log = logging.getLogger(__name__)

SOURCE = 'preheat'


class PreheatAbort(Exception):
    pass


async def _heat_to_target(ctl, step: str) -> None:
    s = ctl.s
    target = s.preheat_target
    loop = asyncio.get_running_loop()
    deadline = loop.time() + s.preheat_heating_timeout
    hits = 0
    ctl.set_preheat_status(step, f'heating to {target:.0f}°C')
    while hits < s.preheat_reach_samples:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise PreheatAbort(f'{target:.0f}°C not reached in {s.preheat_heating_timeout / 60:.0f} min')
        if not await ctl.next_reading(min(s.reading_stale, remaining)):
            if not ctl.temp_fresh():
                raise PreheatAbort('no temperature from Arduino')
            continue
        temp = ctl.state.temp_c
        hits = hits + 1 if temp >= target else 0
        ctl.set_preheat_status(step, f'heating to {target:.0f}°C')


async def _hold(ctl, step: str) -> None:
    s = ctl.s
    loop = asyncio.get_running_loop()
    end = loop.time() + s.preheat_hold
    while True:
        remaining = end - loop.time()
        if remaining <= 0:
            return
        m, sec = divmod(int(remaining + 0.999), 60)
        ctl.set_preheat_status(step, f'hold {m}:{sec:02d}')
        # The temperature still has to keep arriving; a dead link aborts here as well.
        if not await ctl.next_reading(min(1.0, remaining)) and not ctl.temp_fresh():
            raise PreheatAbort('no temperature from Arduino')


async def run_preheat(ctl) -> None:
    s = ctl.s
    log.info('preheat started')
    ctl.say('Preheat started')
    try:
        ctl.set_drum(0, SOURCE)
        ctl.set_heater(s.preheat_heater_1, SOURCE)
        ctl.set_fan(s.preheat_fan_1, SOURCE)
        await _heat_to_target(ctl, '1/4')

        ctl.set_heater(0, SOURCE)
        ctl.set_fan(0, SOURCE)
        await _hold(ctl, '2/4')

        ctl.set_heater(s.preheat_heater_2, SOURCE)
        ctl.set_fan(s.preheat_fan_2, SOURCE)
        ctl.set_drum(1, SOURCE)
        await _heat_to_target(ctl, '3/4')

        ctl.set_heater(0, SOURCE)
        ctl.set_fan(0, SOURCE)
        ctl.set_drum(0, SOURCE)
        await _hold(ctl, '4/4')
    except PreheatAbort as e:
        log.warning('preheat aborted: %s', e)
        ctl.off(SOURCE)
        ctl.say(f'Preheat aborted: {e}')
        return
    except asyncio.CancelledError:
        log.info('preheat cancelled (E-STOP)')
        raise
    log.info('preheat finished')
    ctl.say('Preheat finished')
