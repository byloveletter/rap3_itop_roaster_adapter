"""Minimal pygame widgets for a small resistive touchscreen.

Touch arrives as mouse events (labwc mouseEmulation). Buttons fire on release inside
the button so a slipping finger cancels, except buttons created with fire_on_press
(E-STOP). Buttons with repeat=True keep firing while held.
"""

import functools
import time
from dataclasses import dataclass
from typing import Callable

import pygame

FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

REPEAT_DELAY = 0.5
REPEAT_INTERVAL = 0.15


@functools.lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        return pygame.font.Font(FONT_BOLD if bold else FONT_REGULAR, size)
    except (FileNotFoundError, OSError):
        return pygame.font.SysFont('dejavusans', size, bold=bold)


def draw_text(surface: pygame.Surface, text: str, size: int, color, center=None,
              topleft=None, midleft=None, midright=None, bold: bool = False) -> pygame.Rect:
    img = font(size, bold).render(text, True, color)
    rect = img.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    elif midleft is not None:
        rect.midleft = midleft
    elif midright is not None:
        rect.midright = midright
    surface.blit(img, rect)
    return rect


@dataclass
class Style:
    bg: tuple = (60, 64, 72)
    fg: tuple = (235, 235, 235)
    active_bg: tuple = (40, 120, 200)
    pressed_bg: tuple = (110, 116, 128)
    disabled_bg: tuple = (38, 40, 45)
    disabled_fg: tuple = (95, 98, 105)
    border: tuple = (20, 22, 25)
    font_size: int = 20


class Button:
    def __init__(self, rect: tuple, label: str, on_press: Callable[[], None],
                 style: Style | None = None, fire_on_press: bool = False, repeat: bool = False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_press = on_press
        self.style = style or Style()
        self.fire_on_press = fire_on_press
        self.repeat = repeat
        self.enabled = True
        self.active = False          # highlighted, e.g. a toggle that is on
        self._pressed = False
        self._next_repeat = 0.0

    def handle(self, event: pygame.event.Event) -> bool:
        """Returns True if the event was consumed."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                return False
            if not self.enabled:
                return True
            self._pressed = True
            if self.fire_on_press or self.repeat:
                self.on_press()
                self._next_repeat = time.monotonic() + REPEAT_DELAY
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._pressed:
            self._pressed = False
            if (self.enabled and not self.fire_on_press and not self.repeat
                    and self.rect.collidepoint(event.pos)):
                self.on_press()
            return True
        if event.type == pygame.MOUSEMOTION and self._pressed and not self.rect.collidepoint(event.pos):
            self._pressed = False
        return False

    def tick(self) -> None:
        """Call every frame; drives hold-to-repeat."""
        if self.repeat and self._pressed and self.enabled and time.monotonic() >= self._next_repeat:
            self.on_press()
            self._next_repeat = time.monotonic() + REPEAT_INTERVAL

    def draw(self, surface: pygame.Surface) -> None:
        st = self.style
        if not self.enabled:
            bg, fg = st.disabled_bg, st.disabled_fg
        elif self._pressed:
            bg, fg = st.pressed_bg, st.fg
        elif self.active:
            bg, fg = st.active_bg, st.fg
        else:
            bg, fg = st.bg, st.fg
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, st.border, self.rect, width=2, border_radius=8)
        lines = self.label.split('\n')
        line_h = font(st.font_size, True).get_linesize()
        top = self.rect.centery - line_h * len(lines) / 2
        for i, line in enumerate(lines):
            draw_text(surface, line, st.font_size, fg,
                      center=(self.rect.centerx, int(top + line_h * (i + 0.5))), bold=True)


class Stepper:
    """'LABEL [-] value [+]' with a fixed step; calls on_change(new_value)."""

    def __init__(self, rect: tuple, label: str, get_value: Callable[[], int],
                 on_change: Callable[[int], None], step: int = 5, lo: int = 0, hi: int = 100,
                 unit: str = '%'):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.get_value = get_value
        self.on_change = on_change
        self.step, self.lo, self.hi, self.unit = step, lo, hi, unit
        x, y, w, h = self.rect
        bw = 62
        label_w = 62
        style = Style(font_size=30)
        self.minus = Button((x + label_w, y, bw, h), '-', lambda: self._bump(-1), style, repeat=True)
        self.plus = Button((x + w - bw, y, bw, h), '+', lambda: self._bump(+1), style, repeat=True)
        self._label_rect = pygame.Rect(x, y, label_w, h)
        self._value_rect = pygame.Rect(x + label_w + bw, y, w - label_w - 2 * bw, h)
        self.enabled = True

    def _bump(self, direction: int) -> None:
        v = max(self.lo, min(self.hi, self.get_value() + direction * self.step))
        self.on_change(v)

    def handle(self, event: pygame.event.Event) -> bool:
        return self.minus.handle(event) or self.plus.handle(event)

    def tick(self) -> None:
        self.minus.enabled = self.plus.enabled = self.enabled
        self.minus.tick()
        self.plus.tick()

    def draw(self, surface: pygame.Surface) -> None:
        fg = Style().fg if self.enabled else Style().disabled_fg
        draw_text(surface, self.label, 16, fg, midleft=(self._label_rect.x + 4, self._label_rect.centery), bold=True)
        draw_text(surface, f'{self.get_value()}{self.unit}', 30, fg, center=self._value_rect.center, bold=True)
        self.minus.draw(surface)
        self.plus.draw(surface)
