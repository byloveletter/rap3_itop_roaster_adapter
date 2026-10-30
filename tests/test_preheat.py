import asyncio
import time

from roaster_adapter.arduino import Reading
from roaster_adapter.config import Settings
from roaster_adapter.controller import Controller


def fast_settings(**kw):
    return Settings(**{'preheat_hold': 0.3, 'preheat_heating_timeout': 5.0, 'reading_stale': 1.0, **kw})


async def feed(ctl, temps, period=0.02):
    """Deliver readings (Celsius) like the Arduino link would."""
    for t in temps:
        ctl.on_reading(Reading(temp_f=t * 9 / 5 + 32, heater=ctl.state.heater, fan=ctl.state.fan,
                               time=time.monotonic()))
        await asyncio.sleep(period)


def outputs(sent):
    return [c for c in sent if c[0] in ('OT1', 'OT2', 'DRUM', 'OFF', 'ESTOP')]


def test_full_sequence():
    async def scenario():
        sent = []
        ctl = Controller(fast_settings(), send=lambda *a: sent.append(a))
        ctl.on_connection(True)
        await feed(ctl, [100])
        assert ctl.start_preheat()
        ramp = [150, 179, 181, 182, 183]          # reaches target after 3 samples >= 180
        hot = [185] * 40                          # keep readings coming through hold + ramp 2
        await feed(ctl, ramp + hot)
        await asyncio.wait_for(ctl._preheat_task, 3)
        return sent, ctl

    sent, ctl = asyncio.run(scenario())
    assert outputs(sent) == [
        ('OFF',),                                  # on_connection
        ('DRUM', 0), ('OT1', 80), ('OT2', 10),     # steps 2-3
        ('OT1', 0), ('OT2', 0),                    # step 5
        ('OT1', 75), ('OT2', 20), ('DRUM', 100),   # step 6
        ('OT1', 0), ('OT2', 0), ('DRUM', 0),       # step 8
    ]
    assert not ctl.preheating and ctl.state.message == 'Preheat finished'


def test_only_touch_estop_acts_and_ends_preheat():
    async def scenario():
        sent = []
        ctl = Controller(fast_settings(), send=lambda *a: sent.append(a))
        ctl.on_connection(True)
        ctl.on_artisan_poll()
        await feed(ctl, [100])
        ctl.start_preheat()
        await feed(ctl, [120])
        assert not ctl.set_heater(30, 'touch')
        ctl.on_artisan_command({'command': 'estop'})       # ignored during preheat
        ctl.on_artisan_command({'command': 'setFan', 'value': 50})
        assert ('ESTOP',) not in sent and ('OT2', 50) not in sent
        assert ctl.estop('touch')
        await asyncio.sleep(0.05)
        return sent, ctl

    sent, ctl = asyncio.run(scenario())
    assert sent[-1] == ('ESTOP',)
    assert not ctl.preheating and ctl.state.preheat_phase is None


def test_stale_temperature_aborts_with_off():
    async def scenario():
        sent = []
        ctl = Controller(fast_settings(), send=lambda *a: sent.append(a))
        ctl.on_connection(True)
        await feed(ctl, [100])
        ctl.start_preheat()
        await asyncio.wait_for(ctl._preheat_task, 3)      # no more readings arrive
        return sent, ctl

    sent, ctl = asyncio.run(scenario())
    assert sent[-1] == ('OFF',)
    assert 'no temperature' in ctl.state.message


def test_heating_timeout_aborts_with_off():
    async def scenario():
        sent = []
        ctl = Controller(fast_settings(preheat_heating_timeout=0.3), send=lambda *a: sent.append(a))
        ctl.on_connection(True)
        await feed(ctl, [100])
        ctl.start_preheat()
        await feed(ctl, [120] * 30)
        await asyncio.wait_for(ctl._preheat_task, 3)
        return sent, ctl

    sent, ctl = asyncio.run(scenario())
    assert sent[-1] == ('OFF',)
    assert 'not reached' in ctl.state.message


def test_watchdog_paused_during_preheat_and_restarts_after():
    async def scenario():
        sent = []
        ctl = Controller(fast_settings(artisan_watchdog=0.2), send=lambda *a: sent.append(a))
        ctl.on_connection(True)
        ctl.on_artisan_poll()
        await feed(ctl, [100])
        ctl.start_preheat()
        await feed(ctl, [120] * 20)               # 0.4 s without getData
        ctl.check_watchdog()
        assert ('OFF',) not in sent[1:]
        ctl.estop('touch')
        await asyncio.sleep(0.05)
        ctl.check_watchdog()
        assert sent[-1] == ('ESTOP',)              # 10 s (here 0.2 s) counted from preheat end
        await asyncio.sleep(0.25)
        ctl.check_watchdog()
        return sent

    sent = asyncio.run(scenario())
    assert sent[-1] == ('OFF',)
