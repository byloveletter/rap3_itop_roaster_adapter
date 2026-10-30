"""Stand-in for Artisan's WebSocket device, for testing without Artisan.

Polls getData like Artisan's sampling loop, prints replies and push messages, and sends
commands typed on stdin:
  heater 55 | fan 20 | drum 1 | cooling 0 | filter 1 | estop | off | charge | drop
  or a raw JSON object, e.g. {"command": "setHeater", "value": 55.0}

Usage: python3 tools/fake_artisan.py [--url ws://127.0.0.1:8080/WebSocket] [--interval 1.0]
       [--script "2:heater 80;5:fan 10"]   (seconds after start : command)
"""

import argparse
import asyncio
import json
import random
import sys

from websockets.asyncio.client import connect

SHORTHAND = {'heater': 'setHeater', 'fan': 'setFan', 'drum': 'setDrum',
             'cooling': 'setCooling', 'filter': 'setFilter'}


def to_message(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith('{'):
        return json.loads(line)
    parts = line.split()
    if parts[0] in SHORTHAND and len(parts) == 2:
        return {'command': SHORTHAND[parts[0]], 'value': float(parts[1])}
    if parts[0] in ('estop', 'off', 'charge', 'drop'):
        return {'command': parts[0]}
    raise ValueError(f'unknown command {line!r}')


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='ws://127.0.0.1:8080/WebSocket')
    ap.add_argument('--interval', type=float, default=1.0, help='getData period (Artisan sampling interval)')
    ap.add_argument('--script', default='', help='timed commands "t:cmd;t:cmd"')
    ap.add_argument('--duration', type=float, default=0, help='exit after this many seconds (0 = never)')
    args = ap.parse_args()

    async with connect(args.url) as ws:
        print(f'connected to {args.url}', flush=True)
        pending: dict[int, float] = {}

        async def send(msg: dict) -> None:
            msg = {**msg, 'id': random.randint(1, 99999), 'roasterID': 0}
            print(f'-> {json.dumps(msg)}', flush=True)
            await ws.send(json.dumps(msg))

        async def poll() -> None:
            loop = asyncio.get_running_loop()
            while True:
                mid = random.randint(1, 99999)
                pending[mid] = loop.time()
                await ws.send(json.dumps({'command': 'getData', 'id': mid, 'roasterID': 0}))
                await asyncio.sleep(args.interval)

        async def receive() -> None:
            loop = asyncio.get_running_loop()
            async for frame in ws:
                msg = json.loads(frame)
                if 'id' in msg and msg['id'] in pending:
                    rtt = (loop.time() - pending.pop(msg['id'])) * 1000
                    print(f'<- data {msg.get("data")}  ({rtt:.0f} ms)', flush=True)
                else:
                    print(f'<- {msg}', flush=True)

        async def stdin_commands() -> None:
            loop = asyncio.get_running_loop()
            reader = asyncio.StreamReader()
            await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
            while line := (await reader.readline()).decode():
                try:
                    msg = to_message(line)
                except ValueError as e:
                    print(e, flush=True)
                    continue
                if msg:
                    await send(msg)

        async def scripted() -> None:
            start = asyncio.get_running_loop().time()
            for item in filter(None, args.script.split(';')):
                t, cmd = item.split(':', 1)
                await asyncio.sleep(max(0.0, start + float(t) - asyncio.get_running_loop().time()))
                await send(to_message(cmd))

        tasks = [poll(), receive(), scripted()]
        if sys.stdin.isatty():
            tasks.append(stdin_commands())
        if args.duration:
            await asyncio.wait_for(asyncio.gather(*tasks), args.duration)
        else:
            await asyncio.gather(*tasks)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.TimeoutError):
        pass
