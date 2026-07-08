# -*- coding: utf-8 -*-
from .enums import RARITY_ORDER


class Inventory:
    def __init__(self, capacity=100):
        self.capacity = capacity
        self.items = []
        self.warehouse = []  # 창고(별도 무제한에 가까운 보관함)

    def add_item(self, item):
        if len(self.items) >= self.capacity:
            return False, "인벤토리가 가득 찼습니다."
        self.items.append(item)
        return True, f"{item.name} 획득"

    def remove_item(self, uid):
        for i, it in enumerate(self.items):
            if it.uid == uid:
                return self.items.pop(i)
        return None

    def sort_items(self, by="rarity"):
        if by == "rarity":
            self.items.sort(key=lambda it: RARITY_ORDER.index(it.rarity), reverse=True)
        elif by == "name":
            self.items.sort(key=lambda it: it.name)
        elif by == "type":
            self.items.sort(key=lambda it: it.to_dict().get("type", ""))
        return self.items

    def auto_organize(self):
        """희귀도 -> 종류 -> 이름 순으로 자동 정렬"""
        self.items.sort(key=lambda it: (
            -RARITY_ORDER.index(it.rarity),
            it.to_dict().get("type", ""),
            it.name,
        ))
        return self.items

    def move_to_warehouse(self, uid):
        item = self.remove_item(uid)
        if item:
            self.warehouse.append(item)
        return item

    def move_from_warehouse(self, uid):
        for i, it in enumerate(self.warehouse):
            if it.uid == uid:
                item = self.warehouse.pop(i)
                self.add_item(item)
                return item
        return None

    @staticmethod
    def compare_equipment(current_eq, candidate_eq):
        """장착중인 장비와 후보 장비의 스탯 차이 비교 딕셔너리 반환"""
        cur_stats = current_eq.effective_stats() if current_eq else {}
        new_stats = candidate_eq.effective_stats()
        keys = set(cur_stats) | set(new_stats)
        return {k: round(new_stats.get(k, 0) - cur_stats.get(k, 0), 1) for k in keys}
