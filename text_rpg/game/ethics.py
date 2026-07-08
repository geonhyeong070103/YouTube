# -*- coding: utf-8 -*-
import random


class AlignmentSystem:
    """카르마 값에 따라 상인 반응, 비밀 길드 접근, 감옥/현상금 시스템이 변화"""

    def __init__(self):
        self.bounty = 0
        self.imprisoned = False
        self.prison_days_left = 0

    def steal(self, player, shop, item_id, success_rate=0.5):
        if random.random() <= success_rate:
            item = shop.item_db.create(item_id)
            ok, msg = player.inventory.add_item(item)
            player.karma -= 5
            return True, f"{item.name}을(를) 훔쳤습니다. (카르마 -5)"
        else:
            self.bounty += 50
            player.karma -= 2
            return False, f"도둑질에 실패했습니다! 현상금 +50 (현재 {self.bounty})"

    def get_bounty(self):
        return self.bounty

    def get_arrested(self, days=3):
        self.imprisoned = True
        self.prison_days_left = days
        self.bounty = 0
        return f"체포되었습니다. {days}일간 감옥에 수감됩니다."

    def serve_day(self):
        if self.imprisoned:
            self.prison_days_left -= 1
            if self.prison_days_left <= 0:
                self.imprisoned = False
                return "출소했습니다."
        return None

    def secret_guild_access(self, player, threshold=-30):
        """카르마가 낮을수록(악행) 비밀 도적 길드 접근 가능 - 반대로 높은 카르마는 성기사단 등 접근"""
        if player.karma <= threshold:
            return "dark_guild"
        elif player.karma >= abs(threshold):
            return "holy_order"
        return None
