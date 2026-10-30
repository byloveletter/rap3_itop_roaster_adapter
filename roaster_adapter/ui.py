"""480x320 touch UI.

+------------------------------------------------+
| ARD o  ART o      READY                  03:25 |  status bar
+----------------------+-------------------------+
|  201.5               | HEAT  [-]  75%  [+]     |
|  °C  BT              | FAN   [-]  20%  [+]     |
|  message             | DRUM  [   ON / OFF   ]  |
+----------------------+-------------------------+
| [PREHEAT] [CHARGE] [DROP]        [  E-STOP  ]  |
+------------------------------------------------+
"""

import asyncio
import logging
import os
import time

import pygame

from .controller import Controller
from .widgets import Button, Stepper, Style, draw_text, font

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 480, 320
APP_ID = 'roaster-adapter'
FPS_IDLE = 2        # redraw rate with nothing changing (timer, staleness)
FRAME = 1 / 30      # event polling period
MESSAGE_SECONDS = 5

BG = (18, 20, 24)
PANEL = (28, 31, 36)
TEXT = (235, 235, 235)
DIM = (130, 135, 145)
OK = (60, 190, 90)
BAD = (210, 60, 50)
WARN = (230, 170, 40)
HOT = (255, 140, 60)

STOP_STYLE = Style(bg=(190, 30, 30), pressed_bg=(240, 70, 60), border=(90, 10, 10), font_size=28)
ACTION_STYLE = Style(font_size=20)
PREHEAT_STYLE = Style(bg=(40, 150, 70), active_bg=(25, 105, 45), pressed_bg=(25, 105, 45),
                      border=(15, 60, 25), font_size=20)


class UI:
    def __init__(self, controller: Controller, fullscreen: bool = True):
        self.ctl = controller
        self.fullscreen = fullscreen
        self.running = True
        self.screen: pygame.Surface | None = None
        self._build()

    def _build(self) -> None:
        ctl, st = self.ctl, self.ctl.state
        self.heat = Stepper((200, 34, 276, 60), 'HEAT', lambda: st.heater,
                            lambda v: ctl.set_heater(v, 'touch'))
        self.fan = Stepper((200, 100, 276, 60), 'FAN', lambda: st.fan,
                           lambda v: ctl.set_fan(v, 'touch'))
        self.drum = Button((262, 166, 214, 60), 'DRUM', lambda: ctl.set_drum(not st.drum, 'touch'))
        self.charge = Button((118, 234, 104, 82), 'CHARGE', lambda: ctl.charge('touch'), ACTION_STYLE)
        self.drop = Button((226, 234, 104, 82), 'DROP', lambda: ctl.drop('touch'), ACTION_STYLE)
        self.preheat = Button((4, 234, 110, 82), 'PRE\nHEAT', ctl.start_preheat, PREHEAT_STYLE)
        self.estop = Button((334, 234, 142, 82), 'E-STOP', lambda: ctl.estop('touch'), STOP_STYLE,
                            fire_on_press=True)
        self.widgets = [self.heat, self.fan, self.drum, self.charge, self.drop, self.preheat, self.estop]

    # -- state -> widget enablement --

    def _update_widgets(self) -> None:
        ctl, st = self.ctl, self.ctl.state
        preheating = ctl.preheating
        artisan = ctl.artisan_alive()
        controls = artisan and not preheating
        self.heat.enabled = self.fan.enabled = self.drum.enabled = controls
        self.charge.enabled = controls and st.charge_time is None
        self.drop.enabled = controls and st.charge_time is not None and st.drop_time is None
        self.preheat.enabled = not preheating and st.arduino_connected and ctl.temp_fresh()
        self.preheat.active = preheating
        self.drum.active = st.drum
        self.drum.label = 'DRUM  ON' if st.drum else 'DRUM  OFF'
        self.estop.enabled = True
        for w in self.widgets:
            w.tick()

    # -- drawing --

    def _status_bar(self, surf: pygame.Surface) -> None:
        ctl, st = self.ctl, self.ctl.state
        pygame.draw.rect(surf, PANEL, (0, 0, WIDTH, 30))
        x = 8
        for name, ok in (('ARD', st.arduino_connected), ('ART', ctl.artisan_alive())):
            r = draw_text(surf, name, 14, TEXT, midleft=(x, 15), bold=True)
            pygame.draw.circle(surf, OK if ok else BAD, (r.right + 9, 15), 6)
            x = r.right + 24
        if ctl.preheating:
            mode, color = f'PREHEAT {st.preheat_phase or ""}', WARN
        elif st.watchdog_tripped:
            mode, color = 'ARTISAN LOST', BAD
        elif st.charge_time is not None and st.drop_time is None:
            mode, color = 'ROASTING', HOT
        else:
            mode, color = 'READY', TEXT
        draw_text(surf, mode, 16, color, center=(WIDTH // 2 + 30, 15), bold=True)
        draw_text(surf, self._timer_text(), 18, TEXT, midright=(WIDTH - 8, 15), bold=True)

    def _timer_text(self) -> str:
        st = self.ctl.state
        if st.charge_time is None:
            return '--:--'
        end = st.drop_time if st.drop_time is not None else time.monotonic()
        m, s = divmod(int(end - st.charge_time), 60)
        return f'{m:02d}:{s:02d}'

    def _temp_panel(self, surf: pygame.Surface) -> None:
        ctl, st = self.ctl, self.ctl.state
        pygame.draw.rect(surf, PANEL, (4, 34, 192, 192), border_radius=8)
        temp = st.display_temp_c if ctl.temp_fresh() else None
        text = '%.1f' % temp if temp is not None and -100 < temp < 1000 else '---.-'
        draw_text(surf, text, 54, HOT if temp is not None else DIM, center=(100, 92), bold=True)
        draw_text(surf, '°C  BT', 16, DIM, center=(100, 132))
        if ctl.preheating:
            draw_text(surf, st.preheat_detail, 17, WARN, center=(100, 166), bold=True)
        if st.message and time.monotonic() - st.message_time < MESSAGE_SECONDS:
            self._wrapped(surf, st.message, 14, TEXT, (100, 198), 180)

    def _wrapped(self, surf, text, size, color, center, width) -> None:
        words, lines, line = text.split(), [], ''
        for w in words:
            trial = f'{line} {w}'.strip()
            if font(size).size(trial)[0] > width and line:
                lines.append(line)
                line = w
            else:
                line = trial
        lines.append(line)
        h = font(size).get_linesize()
        top = center[1] - h * len(lines) / 2
        for i, ln in enumerate(lines):
            draw_text(surf, ln, size, color, center=(center[0], int(top + h * (i + 0.5))))

    def draw(self) -> None:
        surf = self.screen
        surf.fill(BG)
        self._status_bar(surf)
        self._temp_panel(surf)
        for w in self.widgets:
            w.draw(surf)
        pygame.display.flip()

    # -- main loop --

    def open(self) -> None:
        os.environ.setdefault('SDL_VIDEODRIVER', 'wayland')
        os.environ.setdefault('SDL_VIDEO_WAYLAND_WMCLASS', APP_ID)
        pygame.display.init()
        pygame.font.init()
        # Fullscreen on the LCD is done by the labwc window rule (deploy/labwc-rc.xml),
        # which moves the window to SPI-1 before making it fullscreen.
        flags = pygame.NOFRAME if self.fullscreen else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.display.set_caption('Roaster Adapter')
        pygame.mouse.set_visible(not self.fullscreen)

    async def run(self) -> None:
        self.open()
        next_idle = 0.0
        try:
            while self.running:
                dirty = False
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not self.fullscreen:
                        self.running = False
                    else:
                        for w in self.widgets:
                            if w.handle(event):
                                dirty = True
                                break
                self._update_widgets()
                now = time.monotonic()
                if self.ctl.consume_changed():
                    dirty = True
                if dirty or now >= next_idle or self._any_pressed():
                    self.draw()
                    next_idle = now + 1 / FPS_IDLE
                await asyncio.sleep(FRAME)
        finally:
            pygame.quit()

    def _any_pressed(self) -> bool:
        buttons = [self.drum, self.charge, self.drop, self.preheat, self.estop,
                   self.heat.minus, self.heat.plus, self.fan.minus, self.fan.plus]
        return any(b._pressed for b in buttons)
