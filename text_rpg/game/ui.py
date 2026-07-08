# -*- coding: utf-8 -*-
import pygame

from .constants import WHITE, GRAY, GOLD, DARK_GRAY, CYAN, LINE_HEIGHT, FONT_SIZE


class TextUI:
    def __init__(self, screen, font):
        self.screen = screen
        self.font = font

    def draw_text(self, text, x, y, color=WHITE):
        surf = self.font.render(text, True, color)
        self.screen.blit(surf, (x, y))
        return surf.get_height()

    def draw_lines(self, lines, x, y, color=WHITE, max_lines=None):
        shown = lines[-max_lines:] if max_lines else lines
        for i, line in enumerate(shown):
            self.draw_text(line, x, y + i * LINE_HEIGHT, color)

    def draw_menu(self, title, options, x, y, selected_index=0):
        self.draw_text(title, x, y, GOLD)
        for i, opt in enumerate(options):
            color = CYAN if i == selected_index else WHITE
            prefix = "> " if i == selected_index else "  "
            self.draw_text(f"{prefix}{opt}", x, y + LINE_HEIGHT * (i + 1), color)

    def draw_status_window(self, player, x, y):
        stats = player.total_stats()
        lines = [
            f"{player.name} Lv.{player.level} [{player.job.value}]",
            f"HP {player.hp}/{int(stats['max_hp'])}  MP {player.mp}/{int(stats['max_mp'])}",
            f"ATK {stats['atk']:.0f} DEF {stats.get('def_', 0):.0f} AGI {stats['agi']:.0f} LUK {stats['luck']:.0f}",
            f"EXP {player.exp}/{player.exp_to_next}  GOLD {player.gold}",
        ]
        for i, line in enumerate(lines):
            self.draw_text(line, x, y + i * LINE_HEIGHT, WHITE)

    def draw_battle_log(self, log, x, y, max_lines=8):
        self.draw_lines(log, x, y, WHITE, max_lines)

    def draw_minimap_text(self, current_loc, world_map, x, y):
        self.draw_text(f"[현재 위치: {current_loc.name}]", x, y, GOLD)
        for i, conn_id in enumerate(current_loc.connections):
            conn = world_map.get(conn_id)
            if conn:
                self.draw_text(f" -> {conn.name}", x, y + LINE_HEIGHT * (i + 1), GRAY)


def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if font.size(test)[0] > max_width:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def load_font(path, size=FONT_SIZE):
    """한글 폰트가 시스템에 있으면 사용, 없으면 pygame 기본 폰트로 폴백"""
    try:
        if path:
            return pygame.font.Font(path, size)
    except Exception:
        pass
    try:
        return pygame.font.SysFont("malgungothic,applesdgothicneo,notosanscjkkr,dejavusans", size)
    except Exception:
        return pygame.font.Font(None, size)
