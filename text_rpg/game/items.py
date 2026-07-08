# -*- coding: utf-8 -*-
import json
import os
import random
import uuid

from .enums import Rarity, RARITY_STAT_MULTIPLIER, EquipSlot, ElementType


class Item:
    def __init__(self, item_id, name, rarity=Rarity.COMMON, description=""):
        self.item_id = item_id
        self.uid = str(uuid.uuid4())[:8]  # 개별 인스턴스 식별자(강화치 다른 동일 아이템 구분용)
        self.name = name
        self.rarity = Rarity(rarity) if not isinstance(rarity, Rarity) else rarity
        self.description = description

    def to_dict(self):
        return {"type": "item", "item_id": self.item_id, "uid": self.uid, "name": self.name,
                "rarity": self.rarity.name, "description": self.description}


class Equipment(Item):
    def __init__(self, item_id, name, slot: EquipSlot, base_stats: dict, rarity=Rarity.COMMON,
                 description="", set_name=None, element=ElementType.NONE, max_durability=100):
        super().__init__(item_id, name, rarity, description)
        self.slot = EquipSlot(slot) if not isinstance(slot, EquipSlot) else slot
        self.base_stats = base_stats  # {"atk": 5, "def": 2, ...}
        self.enhancement_level = 0  # +1, +2 ... 강화
        self.durability = max_durability
        self.max_durability = max_durability
        self.set_name = set_name  # 세트 효과 그룹명
        self.element = element
        self.rolled_options = {}  # 랜덤 옵션 부여 결과

    def effective_stats(self):
        """희귀도 배율 + 강화 수치 + 랜덤옵션 반영한 최종 스탯"""
        mult = RARITY_STAT_MULTIPLIER[self.rarity]
        result = {}
        for k, v in self.base_stats.items():
            enhanced = v * mult * (1 + 0.1 * self.enhancement_level)
            result[k] = round(enhanced, 1)
        for k, v in self.rolled_options.items():
            result[k] = result.get(k, 0) + v
        return result

    def to_dict(self):
        d = super().to_dict()
        d.update({"type": "equipment", "slot": self.slot.name, "base_stats": self.base_stats,
                   "enhancement_level": self.enhancement_level, "durability": self.durability,
                   "max_durability": self.max_durability, "set_name": self.set_name,
                   "element": self.element.name, "rolled_options": self.rolled_options})
        return d


class Consumable(Item):
    def __init__(self, item_id, name, effect_type, effect_value, rarity=Rarity.COMMON, description=""):
        super().__init__(item_id, name, rarity, description)
        self.effect_type = effect_type  # "heal_hp" | "heal_mp" | "cure_status" | "buff_atk" ...
        self.effect_value = effect_value

    def to_dict(self):
        d = super().to_dict()
        d.update({"type": "consumable", "effect_type": self.effect_type, "effect_value": self.effect_value})
        return d


class Material(Item):
    """제작 재료 (채집/채광/낚시/벌목으로 획득)"""
    def to_dict(self):
        d = super().to_dict()
        d["type"] = "material"
        return d


class QuestItem(Item):
    def to_dict(self):
        d = super().to_dict()
        d["type"] = "quest_item"
        return d


def enhance_item(equipment: Equipment, success_rate=0.7):
    """강화 시도: 성공 시 +1, 실패 시 낮은 확률로 내구도 손상"""
    roll = random.random()
    if roll <= success_rate:
        equipment.enhancement_level += 1
        return True, f"{equipment.name} 강화 성공! (+{equipment.enhancement_level})"
    else:
        equipment.durability = max(0, equipment.durability - 10)
        return False, f"{equipment.name} 강화 실패... 내구도 감소"


def roll_random_option(equipment: Equipment, possible_stats=("atk", "def", "agi", "luck")):
    """장비 옵션 부여(희귀도가 높을수록 옵션 수 증가)"""
    n_options = {Rarity.COMMON: 0, Rarity.UNCOMMON: 1, Rarity.RARE: 1,
                 Rarity.EPIC: 2, Rarity.LEGENDARY: 3, Rarity.MYTHIC: 4}[equipment.rarity]
    stats = random.sample(possible_stats, min(n_options, len(possible_stats)))
    for s in stats:
        equipment.rolled_options[s] = round(random.uniform(1, 5) * RARITY_STAT_MULTIPLIER[equipment.rarity], 1)
    return equipment


class ItemDatabase:
    """data/items.json 로부터 아이템 정의를 읽어 인스턴스를 생성하는 팩토리 (모드가 json만 추가해도 확장 가능)"""

    def __init__(self, path=os.path.join("data", "items.json")):
        self.path = path
        self.defs = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.defs = json.load(f)

    def create(self, item_id) -> Item:
        d = self.defs.get(item_id)
        if not d:
            raise KeyError(f"알 수 없는 아이템 ID: {item_id}")
        kind = d.get("kind")
        rarity = d.get("rarity", "COMMON")
        if kind == "equipment":
            return Equipment(item_id, d["name"], EquipSlot[d["slot"]], d["base_stats"], Rarity[rarity],
                              d.get("description", ""), d.get("set_name"),
                              ElementType[d.get("element", "NONE")])
        elif kind == "consumable":
            return Consumable(item_id, d["name"], d["effect_type"], d["effect_value"], Rarity[rarity],
                               d.get("description", ""))
        elif kind == "material":
            return Material(item_id, d["name"], Rarity[rarity], d.get("description", ""))
        elif kind == "quest_item":
            return QuestItem(item_id, d["name"], Rarity[rarity], d.get("description", ""))
        raise ValueError(f"알 수 없는 아이템 종류: {kind}")
