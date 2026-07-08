# -*- coding: utf-8 -*-
"""전역 상수 정의"""

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 640
FPS = 30

# 색상
BLACK = (15, 15, 20)
WHITE = (235, 235, 235)
GRAY = (120, 120, 130)
DARK_GRAY = (40, 40, 48)
GOLD = (255, 205, 60)
RED = (220, 60, 60)
GREEN = (90, 200, 110)
BLUE = (90, 150, 230)
PURPLE = (170, 100, 230)
CYAN = (90, 220, 220)

RARITY_COLORS = {
    "COMMON": (200, 200, 200),
    "UNCOMMON": (90, 200, 110),
    "RARE": (90, 150, 230),
    "EPIC": (170, 100, 230),
    "LEGENDARY": (255, 180, 40),
    "MYTHIC": (255, 80, 80),
}

FONT_PATH_KR = None  # 시스템 한글 폰트가 없으면 None -> pygame 기본 폰트로 대체(한글 미지원 시 콘솔 로그 병행 권장)
FONT_SIZE = 20
LINE_HEIGHT = 26

SAVE_DIR = "saves"
DATA_DIR = "data"
MODS_DIR = "mods"

AUTOSAVE_INTERVAL_SEC = 120
