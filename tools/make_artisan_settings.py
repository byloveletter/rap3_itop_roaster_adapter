"""Build the Artisan settings file for the Raspberry Pi WebSocket bridge.

Starts from ref/skywalker-rpi-bt.aset, the Artisan settings used before with the
Arduino connected directly (TC4 serial device). Display settings (Celsius, axes,
event graph, buttons, sliders) are kept; only the device is changed to Artisan's
WebSocket device and the serial commands are translated to WebSocket commands.

Action numbers are stored differently per place (Artisan main.py: eventactionx(),
fireslideraction_internal(), recordextraevent()); all of these end up as internal
action 22 = WebSocket Command:
  default/ON/OFF buttons: 21   extra event buttons: 22   sliders: 18
Commands use send(dict(...)) instead of a JSON literal because Artisan runs
str.format() over slider and extra-button command strings, which breaks on '{'.

Usage: python3 tools/make_artisan_settings.py [--host 172.20.30.181] [--port 8080]
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'ref/skywalker-rpi-bt.aset'
OUTPUT = ROOT / 'artisan/skywalker-rpi-websocket.aset'

BUTTON_WS, EXTRA_WS, SLIDER_WS = 21, 22, 18


def ws(command: str, value=None) -> str:
    args = f"command='{command}'" if value is None else f"command='{command}',value={value}"
    return f'"send(dict({args}))"'


def ini_list(items) -> str:
    return ', '.join(str(i) for i in items)


def changes(host: str, port: int) -> dict[str, dict[str, str]]:
    # Extra event buttons of the template, in order: serial command -> WebSocket command.
    # Labels, colours and event types stay as in the template.
    extra = [
        ws('setFilter', 1),     # Filter Fan On   (FILTER;1)
        ws('setFilter', 0),     # Filter Fan OFF  (FILTER;0)
        ws('setDrum', 1),       # Drum On         (DRUM;100)
        ws('setDrum', 0),       # Drum Off        (DRUM;0)
        ws('off'),              # E STOP          (OFF, all outputs 0)
    ]
    return {
        'General': {
            'Delay': '1000',
            # The roaster has one probe; the bridge reports it as both BT and ET.
            'ETcurve': 'false',
            'ETlcd': 'false',
            'recentRoasts': '@Invalid()',   # file history of the PC the template came from
        },
        'Device': {'id': '111'},
        'WebSocket': {
            'host': host,
            'port': str(port),
            'path': 'WebSocket',
            'STARTonCHARGE': 'true',
            'OFFonDROP': 'false',
            'channel_nodes': ini_list(['BT', 'ET'] + [''] * 8),
            'channel_modes': ini_list([1, 1] + [0] * 8),   # 1 = Celsius
        },
        'Sliders': {
            'slideractions': ini_list([SLIDER_WS, 0, 0, SLIDER_WS]),
            'slidercommands': ini_list([ws('setFan', '{}'), '', '', ws('setHeater', '{}')]),
        },
        'DefaultButtons': {
            # CHARGE, DRY END, FCs, FCe, SCs, SCe, DROP, COOL END
            # The bridge itself sets heater 0, fan 80 and bean cooling on at DROP.
            'buttonactions': ini_list([BUTTON_WS, 0, 0, 0, 0, 0, BUTTON_WS, BUTTON_WS]),
            'buttonactionstrings': ini_list([ws('charge'), '', '', '', '', '', ws('drop'),
                                             ws('setCooling', 0)]),
            # ON (DRUM;100), OFF (OFF), SAMPLE
            'extrabuttonactions': ini_list([BUTTON_WS, BUTTON_WS, 0]),
            'extrabuttonactionstrings': ini_list([ws('setDrum', 1), ws('off'), '']),
        },
        'ExtraEventButtons': {
            'extraeventsactions': ini_list([EXTRA_WS] * len(extra)),
            'extraeventsactionstrings': ini_list(extra),
        },
    }


def apply(text: str, edits: dict[str, dict[str, str]]) -> str:
    out, section, seen = [], None, set()
    for line in text.split('\n'):
        m = re.match(r'^\[(.+)\]$', line)
        if m:
            section = m.group(1)
        elif section in edits and '=' in line:
            key = line.split('=', 1)[0]
            if key in edits[section]:
                line = f'{key}={edits[section][key]}'
                seen.add((section, key))
        out.append(line)
    missing = [(s, k) for s, keys in edits.items() for k in keys if (s, k) not in seen]
    if missing:
        raise SystemExit(f'keys not found in template: {missing}')
    return '\n'.join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='172.20.30.181', help='Raspberry Pi address')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--output', type=Path, default=OUTPUT)
    args = ap.parse_args()
    text = apply(TEMPLATE.read_text(encoding='latin-1'), changes(args.host, args.port))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='latin-1')
    print(f'wrote {args.output}')


if __name__ == '__main__':
    main()
