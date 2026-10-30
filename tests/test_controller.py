import asyncio

import pytest

from roaster_adapter.arduino import Reading
from roaster_adapter.config import Settings
from roaster_adapter.controller import Controller, round5


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    """Controller with a fake clock; returns (controller, sent commands, clock, pushes)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    sent, pushes = [], []
    clock = Clock()
    ctl = Controller(Settings(), send=lambda *a: sent.append(a), clock=clock)
    ctl.add_push_listener(pushes.append)
    yield ctl, sent, clock, pushes
    loop.close()


def test_round5():
    assert [round5(v) for v in (0, 2, 3, 52.4, 57.5, 99, 130, -5)] == [0, 0, 5, 50, 60, 100, 100, 0]


def test_touch_controls_need_artisan(env):
    ctl, sent, clock, _ = env
    assert not ctl.set_heater(50, 'touch')
    assert sent == []
    ctl.on_artisan_poll()
    assert ctl.set_heater(52, 'touch')
    assert sent == [('OT1', 50)]


def test_touch_estop_always_works(env):
    ctl, sent, _, _ = env
    assert ctl.estop('touch')
    assert sent == [('ESTOP',)]
    assert (ctl.state.heater, ctl.state.fan) == (0, 100)


def test_artisan_commands(env):
    ctl, sent, _, _ = env
    ctl.on_artisan_command({'command': 'setHeater', 'value': 55.0, 'id': 1})
    ctl.on_artisan_command({'command': 'setDrum', 'value': 1})
    ctl.on_artisan_command({'command': 'estop'})
    assert sent == [('OT1', 55), ('DRUM', 100), ('ESTOP',)]


def test_get_data_reply_and_display(env):
    ctl, _, clock, _ = env
    assert ctl.on_artisan_poll() == {'heater': 0, 'fan': 0}      # no temperature yet
    ctl.on_reading(Reading(temp_f=392.0, heater=80, fan=10, time=clock.t))
    data = ctl.on_artisan_poll()
    assert data['BT'] == data['ET'] == 200.0
    assert ctl.state.display_temp_c == 200.0
    clock.t += 6                                                   # reading goes stale
    assert 'BT' not in ctl.on_artisan_poll()


def test_watchdog_sends_off_once_after_artisan_stops(env):
    ctl, sent, clock, _ = env
    ctl.check_watchdog()
    assert sent == []                      # never connected -> not armed
    ctl.on_artisan_poll()
    ctl.set_heater(80, 'artisan')
    clock.t += 9.9
    ctl.check_watchdog()
    assert sent == [('OT1', 80)]
    clock.t += 0.2
    ctl.check_watchdog()
    ctl.check_watchdog()
    assert sent == [('OT1', 80), ('OFF',)]
    assert ctl.state.watchdog_tripped and ctl.state.heater == 0
    ctl.on_artisan_poll()
    assert not ctl.state.watchdog_tripped


def test_touch_charge_and_drop_push_to_artisan(env):
    ctl, sent, _, pushes = env
    ctl.on_artisan_poll()
    ctl.charge('touch')
    ctl.drop('touch')
    assert pushes == [{'pushMessage': 'startRoasting'}, {'pushMessage': 'endRoasting'}]
    assert sent == [('OT1', 0), ('OT2', 80), ('COOL', 100)]


def test_artisan_drop_sets_drop_outputs(env):
    ctl, sent, _, pushes = env
    ctl.on_artisan_command({'command': 'drop'})
    assert pushes == []
    assert sent == [('OT1', 0), ('OT2', 80), ('COOL', 100)]


def test_artisan_charge_does_not_echo(env):
    ctl, _, _, pushes = env
    ctl.on_artisan_command({'command': 'charge'})
    assert pushes == [] and ctl.state.charge_time is not None


def test_connection_resets_outputs(env):
    ctl, sent, _, _ = env
    ctl.state.heater, ctl.state.drum = 80, True
    ctl.on_connection(True)
    assert sent == [('OFF',)]
    assert ctl.state.heater == 0 and not ctl.state.drum
