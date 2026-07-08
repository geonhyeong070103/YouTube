# -*- coding: utf-8 -*-

TITLE_DEFINITIONS = {
    "slime_slayer": {
        "name": "슬라임 학살자", "condition": lambda p, ctx: ctx.get("slime_kills", 0) >= 50,
        "stat_bonus": {"atk": 3},
    },
    "dungeon_master": {
        "name": "던전 정복자", "condition": lambda p, ctx: ctx.get("dungeons_cleared", 0) >= 10,
        "stat_bonus": {"def_": 5},
    },
    "wealthy": {
        "name": "황금손", "condition": lambda p, ctx: p.gold >= 10000,
        "stat_bonus": {"luck": 5},
    },
    "max_level": {
        "name": "전설의 모험가", "condition": lambda p, ctx: p.level >= 50,
        "stat_bonus": {"max_hp": 50, "max_mp": 30},
    },
}


class TitleManager:
    def __init__(self):
        self.context = {}  # 업적 조건 판단용 누적 카운터 (예: slime_kills)

    def increment(self, key, amount=1):
        self.context[key] = self.context.get(key, 0) + amount

    def check_achievements(self, player):
        newly_unlocked = []
        for title_id, d in TITLE_DEFINITIONS.items():
            if title_id in player.titles:
                continue
            if d["condition"](player, self.context):
                player.titles.append(title_id)
                newly_unlocked.append(d["name"])
        return newly_unlocked

    def equip_title(self, player, title_id):
        if title_id not in player.titles:
            return False, "보유하지 않은 칭호입니다."
        player.active_title_bonus = dict(TITLE_DEFINITIONS[title_id]["stat_bonus"])
        return True, f"칭호 '{TITLE_DEFINITIONS[title_id]['name']}' 장착"
