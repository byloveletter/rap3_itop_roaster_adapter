"""Build the Artisan settings file for the Raspberry Pi WebSocket bridge.

Starts from SkywalkerRoaster/ArtisanConfigs/basic-skitop-artisan-settings.aset (read
only) and changes the device to Artisan's WebSocket device plus the buttons and sliders.

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
TEMPLATE = ROOT / 'SkywalkerRoaster/ArtisanConfigs/basic-skitop-artisan-settings.aset'
OUTPUT = ROOT / 'artisan/skywalker-rpi-websocket.aset'

BUTTON_WS, EXTRA_WS, SLIDER_WS = 21, 22, 18


def ws(command: str, value=None) -> str:
    args = f"command='{command}'" if value is None else f"command='{command}',value={value}"
    return f'"send(dict({args}))"'


def ini_list(items) -> str:
    return ', '.join(str(i) for i in items)


def changes(host: str, port: int) -> dict[str, dict[str, str]]:
    extra = [  # label, command, colour, event type (1 = Drum, 4 = no event)
        (' DRUM ON ', ws('setDrum', 1), '#009202', 1),
        (' DRUM OFF ', ws('setDrum', 0), '#8a1200', 1),
        (' BEAN COOL ON ', ws('setCooling', 1), '#0053bb', 4),
        (' BEAN COOL OFF ', ws('setCooling', 0), '#7e1000', 4),
        (' BOX COOL ON ', ws('setFilter', 1), '#0051b7', 4),
        (' BOX COOL OFF ', ws('setFilter', 0), '#801000', 4),
        ('SHUTDOWN ALL', ws('off'), '#808080', 4),
        (' EMERGENCY STOP ', ws('estop'), '#ff000e', 4),
    ]
    n = len(extra)
    return {
        'General': {
            'Delay': '1000',
            # The roaster has one probe; the bridge reports it as both BT and ET.
            'ETcurve': 'false',
            'ETlcd': 'false',
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
            'buttonactions': ini_list([BUTTON_WS, 0, 0, 0, 0, 0, BUTTON_WS, BUTTON_WS]),
            'buttonactionstrings': ini_list([ws('charge'), '', '', '', '', '', ws('drop'),
                                             ws('setCooling', 0)]),
            # ON, OFF, SAMPLE
            'extrabuttonactions': ini_list([0, BUTTON_WS, 0]),
            'extrabuttonactionstrings': ini_list(['', ws('off'), '']),
        },
        'ExtraEventButtons': {
            'extraeventbuttoncolor': ini_list(c for _, _, c, _ in extra),
            'extraeventbuttontextcolor': ini_list(['white'] * n),
            'extraeventsactions': ini_list([EXTRA_WS] * n),
            'extraeventsactionstrings': ini_list(cmd for _, cmd, _, _ in extra),
            'extraeventsdescriptions': ini_list([''] * n),
            'extraeventslabels': ini_list(f'"{label}"' if label != label.strip() else label
                                          for label, _, _, _ in extra),
            'extraeventstypes': ini_list(t for _, _, _, t in extra),
            'extraeventsvalues': ini_list([0] * n),
            'extraeventsvisibility': ini_list([1] * n),
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
