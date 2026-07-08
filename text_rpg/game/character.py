# -*- coding: utf-8 -*-
from .enums import JobType, EquipSlot, StatusEffect
from .jobs import get_base_stats, get_growth, get_skills_for_job
from .inventory import Inventory


class Character:
    def __init__(self, name: str, job: JobType):
        self.name = name
        self.job = job
        self.level = 1
        self.exp = 0
        self.exp_to_next = 100

        base = get_base_stats(job)
        self.max_hp = base["hp"]
        self.hp = self.max_hp
        self.max_mp = base["mp"]
        self.mp = self.max_mp
        self.atk = base["atk"]
        self.def_ = base["def"]
        self.agi = base["agi"]
        self.luck = base["luck"]

        self.unspent_stat_points = 0
        self.skills = []  # [{"name":..., "mp_cost":..., ...}]
        self.equipment = {slot: None for slot in EquipSlot}
        self.inventory = Inventory()
        self.gold = 100
        self.status_effects = {}  # {StatusEffect: 남은턴}
        self.titles = []
        self.active_title_bonus = {}
        self.karma = 0  # 윤리/성향 시스템

    # ---------- 레벨/경험치 ----------
    def gain_exp(self, amount: int):
        logs = [f"{self.name}이(가) 경험치 {amount}을(를) 획득했습니다."]
        self.exp += amount
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            logs.extend(self._level_up())
        return logs

    def _level_up(self):
        self.level += 1
        growth = get_growth(self.job)
        self.max_hp += growth["hp"]
        self.max_mp += growth["mp"]
        self.atk += growth["atk"]
        self.def_ += growth["def"]
        self.agi += growth["agi"]
        self.luck += growth["luck"]
        self.hp = self.max_hp
        self.mp = self.max_mp
        self.unspent_stat_points += 5
        self.exp_to_next = int(self.exp_to_next * 1.25)

        logs = [f"레벨업! {self.name}이(가) Lv.{self.level}이 되었습니다. (스탯포인트 +5)"]
        skills = get_skills_for_job(self.job)
        if self.level in skills:
            new_skill = dict(skills[self.level])
            self.skills.append(new_skill)
            logs.append(f"새로운 스킬 습득: {new_skill['name']}")
        return logs

    def allocate_stat(self, stat_name: str, points: int = 1):
        if self.unspent_stat_points < points:
            return False, "스탯 포인트가 부족합니다."
        mapping = {"hp": "max_hp", "mp": "max_mp", "atk": "atk", "def": "def_", "agi": "agi", "luck": "luck"}
        if stat_name not in mapping:
            return False, "알 수 없는 스탯입니다."
        attr = mapping[stat_name]
        increment = {"hp": 8, "mp": 4}.get(stat_name, 1)
        setattr(self, attr, getattr(self, attr) + increment * points)
        if stat_name == "hp":
            self.hp = min(self.hp + increment * points, self.max_hp)
        self.unspent_stat_points -= points
        return True, f"{stat_name} 스탯을 {points}만큼 투자했습니다."

    # ---------- 장비 ----------
    def equip(self, equipment):
        old = self.equipment.get(equipment.slot)
        self.equipment[equipment.slot] = equipment
        if old:
            self.inventory.add_item(old)
        self.inventory.remove_item(equipment.uid)
        return old

    def unequip(self, slot: EquipSlot):
        item = self.equipment.get(slot)
        if item:
            self.equipment[slot] = None
            self.inventory.add_item(item)
        return item

    def total_stats(self):
        """장비/세트효과/칭호 보너스 합산 스탯"""
        stats = {"atk": self.atk, "def_": self.def_, "agi": self.agi, "luck": self.luck,
                  "max_hp": self.max_hp, "max_mp": self.max_mp}
        equipped_sets = {}
        for slot, eq in self.equipment.items():
            if not eq:
                continue
            for k, v in eq.effective_stats().items():
                key = "def_" if k == "def" else k
                stats[key] = stats.get(key, 0) + v
            if eq.set_name:
                equipped_sets[eq.set_name] = equipped_sets.get(eq.set_name, 0) + 1
        # 세트효과: 2피스 이상 착용 시 전체 스탯 +5%(단순 예시, set_effects.json으로 세분화 가능)
        for set_name, count in equipped_sets.items():
            if count >= 2:
                for k in stats:
                    stats[k] = round(stats[k] * 1.05, 1)
        for k, v in self.active_title_bonus.items():
            stats[k] = stats.get(k, 0) + v
        return stats

    # ---------- 전투 관련 ----------
    def take_damage(self, dmg: int):
        self.hp = max(0, self.hp - dmg)
        return self.hp

    def heal(self, amount: int):
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp

    def apply_status(self, status: StatusEffect, duration: int = 3):
        self.status_effects[status] = max(self.status_effects.get(status, 0), duration)

    def tick_status_effects(self):
        """매 턴 상태이상 효과 적용, 반환: 로그 리스트"""
        logs = []
        expired = []
        for status, turns in self.status_effects.items():
            if status == StatusEffect.POISON:
                dmg = max(1, int(self.max_hp * 0.05))
                self.take_damage(dmg)
                logs.append(f"{self.name}이(가) 독 피해 {dmg}을 입었습니다.")
            elif status == StatusEffect.BURN:
                dmg = max(1, int(self.max_hp * 0.07))
                self.take_damage(dmg)
                logs.append(f"{self.name}이(가) 화상 피해 {dmg}을 입었습니다.")
            elif status == StatusEffect.BLEED:
                dmg = max(1, int(self.max_hp * 0.04))
                self.take_damage(dmg)
                logs.append(f"{self.name}이(가) 출혈 피해 {dmg}을 입었습니다.")
            self.status_effects[status] -= 1
            if self.status_effects[status] <= 0:
                expired.append(status)
        for s in expired:
            del self.status_effects[s]
            logs.append(f"{s.value} 효과가 해제되었습니다.")
        return logs

    def is_stunned(self):
        return StatusEffect.STUN in self.status_effects

    def is_frozen(self):
        return StatusEffect.FREEZE in self.status_effects

    def is_alive(self):
        return self.hp > 0

    # ---------- 저장/로드용 직렬화 ----------
    def to_dict(self):
        return {
            "name": self.name, "job": self.job.name, "level": self.level, "exp": self.exp,
            "exp_to_next": self.exp_to_next, "max_hp": self.max_hp, "hp": self.hp,
            "max_mp": self.max_mp, "mp": self.mp, "atk": self.atk, "def_": self.def_,
            "agi": self.agi, "luck": self.luck, "unspent_stat_points": self.unspent_stat_points,
            "skills": self.skills, "gold": self.gold, "karma": self.karma,
            "titles": self.titles,
            "equipment": {slot.name: (eq.to_dict() if eq else None) for slot, eq in self.equipment.items()},
            "inventory": [it.to_dict() for it in self.inventory.items],
        }
