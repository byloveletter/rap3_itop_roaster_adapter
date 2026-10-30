"""Tunable constants. Times are in seconds, temperatures in Celsius."""

from dataclasses import dataclass


@dataclass
class Settings:
    # Arduino running SkyCommand.ino (unmodified)
    serial_port: str = 'auto'           # 'auto': first /dev/ttyACM* (Leonardo/Micro) or /dev/ttyUSB* (Nano)
    serial_baud: int = 115200
    serial_open_delay: float = 2.0      # boards with auto-reset (Nano) reboot when the port opens
    read_interval: float = 0.5          # READ poll period
    read_timeout: float = 1.5           # no reply to READ within this -> link considered down
    command_settle: float = 0.8         # quiet time after a non-READ command, see arduino.py
    reading_stale: float = 5.0          # no valid temperature for this long -> temperature unknown

    # Artisan WebSocket device
    ws_host: str = '0.0.0.0'
    ws_port: int = 8080
    artisan_watchdog: float = 10.0      # no getData for this long -> send OFF

    # DROP: heater 0, this fan duty, bean cooling on (project.md)
    drop_fan: int = 80

    # Preheat sequence (project.md)
    preheat_target: float = 180.0
    preheat_heater_1: int = 80
    preheat_fan_1: int = 10
    preheat_heater_2: int = 75
    preheat_fan_2: int = 20             # second heating phase also turns the drum on
    preheat_hold: float = 300.0         # wait after each heating phase
    preheat_heating_timeout: float = 900.0
    preheat_reach_samples: int = 3      # consecutive samples at/above target
