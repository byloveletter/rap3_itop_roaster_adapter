"""Entry point: python3 -m roaster_adapter [options]"""

import argparse
import asyncio
import logging

from .arduino import ArduinoLink
from .config import Settings
from .controller import Controller
from .wsserver import ArtisanServer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='roaster_adapter')
    p.add_argument('--serial', default=Settings.serial_port,
                   help="Arduino serial port, or 'auto' (default)")
    p.add_argument('--ws-port', type=int, default=Settings.ws_port, help='WebSocket port for Artisan')
    p.add_argument('--windowed', action='store_true', help='run in a window instead of fullscreen')
    p.add_argument('--no-ui', action='store_true', help='run without the LCD UI')
    p.add_argument('--preheat-hold', type=float, default=Settings.preheat_hold,
                   help='seconds to wait after each preheat heating phase')
    p.add_argument('-v', '--verbose', action='store_true', help='log every serial line')
    return p.parse_args()


async def main(args: argparse.Namespace) -> None:
    settings = Settings(serial_port=args.serial, ws_port=args.ws_port, preheat_hold=args.preheat_hold)
    loop = asyncio.get_running_loop()

    link: ArduinoLink | None = None
    controller = Controller(settings, send=lambda *a: link.send(*a))
    link = ArduinoLink(
        settings,
        on_reading=lambda r: loop.call_soon_threadsafe(controller.on_reading, r),
        on_connection=lambda c: loop.call_soon_threadsafe(controller.on_connection, c),
    )
    server = ArtisanServer(controller, settings.ws_host, settings.ws_port)

    link.start()
    tasks = [asyncio.create_task(server.serve_forever()),
             asyncio.create_task(controller.run_watchdog())]
    try:
        if args.no_ui:
            await asyncio.gather(*tasks)
        else:
            from .ui import UI
            await UI(controller, fullscreen=not args.windowed).run()
    finally:
        for t in tasks:
            t.cancel()
        link.send('OFF')
        await asyncio.sleep(1.0)    # let the link thread deliver OFF
        link.stop()


if __name__ == '__main__':
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    logging.getLogger('websockets').setLevel(logging.WARNING)
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
