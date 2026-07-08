# -*- coding: utf-8 -*-
import random


class Shop:
    def __init__(self, name, stock: dict, item_db, is_secret=False):
        """stock: {item_id: base_price}"""
        self.name = name
        self.stock = stock
        self.item_db = item_db
        self.is_secret = is_secret
        self.price_modifier = 1.0  # 시세 변동
        self.discount_active = False

    def fluctuate_prices(self):
        self.price_modifier = round(random.uniform(0.85, 1.2), 2)
        return self.price_modifier

    def start_discount_event(self, rate=0.3):
        self.discount_active = True
        self.discount_rate = rate

    def end_discount_event(self):
        self.discount_active = False

    def get_price(self, item_id):
        base = self.stock[item_id]
        price = base * self.price_modifier
        if self.discount_active:
            price *= (1 - getattr(self, "discount_rate", 0))
        return int(price)

    def buy(self, player, item_id):
        if item_id not in self.stock:
            return False, "판매하지 않는 아이템입니다."
        price = self.get_price(item_id)
        if player.gold < price:
            return False, "골드가 부족합니다."
        player.gold -= price
        item = self.item_db.create(item_id)
        ok, msg = player.inventory.add_item(item)
        if not ok:
            player.gold += price
            return False, msg
        return True, f"{item.name}을(를) {price}골드에 구매했습니다."

    def sell(self, player, item_uid, sell_rate=0.4):
        item = player.inventory.remove_item(item_uid)
        if not item:
            return False, "인벤토리에 없는 아이템입니다."
        base_price = self.stock.get(item.item_id, 20)
        price = int(base_price * sell_rate)
        player.gold += price
        return True, f"{item.name}을(를) {price}골드에 판매했습니다."


class SecretMerchant(Shop):
    """랜덤 이벤트로 등장하는 희귀 아이템 판매 비밀 상인"""
    def __init__(self, item_db, rare_item_ids):
        stock = {iid: random.randint(500, 3000) for iid in rare_item_ids}
        super().__init__("??? 비밀 상인", stock, item_db, is_secret=True)
