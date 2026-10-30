"""WebSocket server for Artisan's WebSocket device (Artisan is the client).

Message formats follow Artisan's defaults in src/artisanlib/wsport.py:
  Artisan -> here : {"command": "getData", "id": N, "roasterID": 0}
  here -> Artisan : {"id": N, "data": {"BT": .., "ET": .., "heater": .., "fan": ..}}
  Artisan -> here : {"command": "setHeater", "value": 55.0, "id": N, ...}  (no reply expected)
  here -> Artisan : {"pushMessage": "startRoasting"} / {"pushMessage": "endRoasting"}
A frame may hold several JSON objects separated by newlines.
"""

import asyncio
import json
import logging

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .controller import Controller

log = logging.getLogger(__name__)


class ArtisanServer:
    def __init__(self, controller: Controller, host: str, port: int):
        self._ctl = controller
        self._host = host
        self._port = port
        self._clients: set[ServerConnection] = set()
        controller.add_push_listener(self.push)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def push(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(',', ':'))
        log.info('push %s to %d client(s)', text, len(self._clients))
        for ws in list(self._clients):
            asyncio.get_running_loop().create_task(self._send(ws, text))

    async def _send(self, ws: ServerConnection, text: str) -> None:
        try:
            await ws.send(text)
        except ConnectionClosed:
            pass

    def handle_message(self, msg: dict) -> dict | None:
        """Returns the reply for requests that need one."""
        if msg.get('command') == 'getData':
            return {'id': msg.get('id'), 'data': self._ctl.on_artisan_poll()}
        if 'command' in msg:
            log.info('Artisan command %s', msg)
            self._ctl.on_artisan_command(msg)
        return None

    async def _handler(self, ws: ServerConnection) -> None:
        peer = ws.remote_address
        log.info('Artisan connected from %s path %s', peer, ws.request.path)
        self._clients.add(ws)
        try:
            async for frame in ws:
                if isinstance(frame, bytes):
                    frame = frame.decode('utf-8', errors='replace')
                for line in frame.strip().split('\n'):
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning('bad JSON from %s: %r', peer, line)
                        continue
                    if not isinstance(msg, dict):
                        continue
                    reply = self.handle_message(msg)
                    if reply is not None:
                        await ws.send(json.dumps(reply, separators=(',', ':')))
        except ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            log.info('Artisan disconnected from %s', peer)

    async def serve_forever(self) -> None:
        async with serve(self._handler, self._host, self._port) as server:
            log.info('WebSocket server on %s:%d', self._host, self._port)
            await server.serve_forever()
