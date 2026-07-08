# -*- coding: utf-8 -*-
import random

from .enums import ElementType, ELEMENT_ADVANTAGE, StatusEffect


def element_multiplier(attacker_elem: ElementType, defender_elem: ElementType) -> float:
    if attacker_elem == ElementType.NONE or defender_elem == ElementType.NONE:
        return 1.0
    if ELEMENT_ADVANTAGE.get(attacker_elem) == defender_elem:
        return 1.5
    if ELEMENT_ADVANTAGE.get(defender_elem) == attacker_elem:
        return 0.67
    return 1.0


class Battle:
    """플레이어 대 몬스터(1~N) 턴제 전투. 날씨/시간대 보정치는 weather_time 모듈에서 주입 가능."""

    def __init__(self, player, monsters, weather_combat_mod=None):
        self.player = player
        self.monsters = monsters  # list[Monster]
        self.log = []
        self.turn = 0
        self.weather_combat_mod = weather_combat_mod or {}  # 예: {"element_boost": ElementType.WATER}
        self.finished = False
        self.result = None  # "win" | "lose" | "flee"

    def _log(self, msg):
        self.log.append(msg)

    def _crit_chance(self, actor_luck):
        return min(0.05 + actor_luck * 0.01, 0.6)

    def _dodge_chance(self, target_agi):
        return min(0.03 + target_agi * 0.008, 0.45)

    def player_normal_attack(self, target_index=0):
        target = self.monsters[target_index]
        stats = self.player.total_stats()
        if random.random() <= self._dodge_chance(target.agi):
            self._log(f"{target.name}이(가) 공격을 회피했습니다!")
            return self._end_player_turn()

        dmg = max(1, int(stats["atk"] - target.defense * 0.5))
        is_crit = random.random() <= self._crit_chance(stats.get("luck", 0))
        if is_crit:
            dmg = int(dmg * 1.8)
        target.take_damage(dmg)
        crit_txt = " (치명타!)" if is_crit else ""
        self._log(f"{self.player.name}의 공격! {target.name}에게 {dmg} 피해{crit_txt}")
        if not target.is_alive():
            self._log(f"{target.name}을(를) 쓰러뜨렸습니다!")
        return self._end_player_turn()

    def player_use_skill(self, skill, target_index=0):
        if self.player.mp < skill["mp_cost"]:
            self._log("MP가 부족합니다.")
            return False
        self.player.mp -= skill["mp_cost"]
        stats = self.player.total_stats()

        if "heal" in skill:
            heal_amt = int(stats["max_hp"] * (skill["heal"] - 1) * 0.3 + 20)
            self.player.heal(heal_amt)
            self._log(f"{skill['name']}! {self.player.name}이(가) {heal_amt} 회복했습니다.")
            return self._end_player_turn()

        targets = [self.monsters[target_index]] if target_index is not None else self.monsters
        hits = skill.get("hits", 1)
        for _ in range(hits):
            for target in targets:
                if not target.is_alive():
                    continue
                elem = skill.get("element", ElementType.NONE)
                mult = element_multiplier(elem, target.element)
                dmg = max(1, int(stats["atk"] * skill.get("power", 1.0) * mult - target.defense * 0.4))
                is_crit = random.random() <= self._crit_chance(stats.get("luck", 0)) + skill.get("crit_bonus", 0)
                if is_crit:
                    dmg = int(dmg * 1.8)
                target.take_damage(dmg)
                elem_txt = f" [{elem.value} 상성 x{mult}]" if elem != ElementType.NONE else ""
                self._log(f"{skill['name']}! {target.name}에게 {dmg} 피해{elem_txt}")
                if "status" in skill and random.random() <= 0.5:
                    target.status_effects[StatusEffect[skill["status"]]] = 3
                    self._log(f"{target.name}에게 {StatusEffect[skill['status']].value} 상태이상 부여!")
                if not target.is_alive():
                    self._log(f"{target.name}을(를) 쓰러뜨렸습니다!")
        return self._end_player_turn()

    def player_use_item(self, consumable):
        if consumable.effect_type == "heal_hp":
            self.player.heal(consumable.effect_value)
            self._log(f"{consumable.name} 사용! HP {consumable.effect_value} 회복")
        elif consumable.effect_type == "heal_mp":
            self.player.mp = min(self.player.max_mp, self.player.mp + consumable.effect_value)
            self._log(f"{consumable.name} 사용! MP {consumable.effect_value} 회복")
        elif consumable.effect_type == "cure_status":
            self.player.status_effects.clear()
            self._log(f"{consumable.name} 사용! 상태이상이 모두 치료되었습니다.")
        self.player.inventory.remove_item(consumable.uid)
        return self._end_player_turn()

    def player_flee(self):
        chance = 0.5 + self.player.agi * 0.01
        if random.random() <= chance:
            self._log("전투에서 도망쳤습니다.")
            self.finished = True
            self.result = "flee"
            return True
        self._log("도망에 실패했습니다!")
        return self._end_player_turn()

    def _end_player_turn(self):
        if all(not m.is_alive() for m in self.monsters):
            self.finished = True
            self.result = "win"
            return True
        return self._monster_turn()

    def _monster_turn(self):
        self.turn += 1
        status_logs = self.player.tick_status_effects()
        self.log.extend(status_logs)
        if not self.player.is_alive():
            self.finished = True
            self.result = "lose"
            return True

        if self.player.is_stunned() or self.player.is_frozen():
            self._log(f"{self.player.name}은(는) 움직일 수 없습니다!")
        for m in self.monsters:
            if not m.is_alive():
                continue
            if random.random() <= self._dodge_chance(self.player.agi):
                self._log(f"{self.player.name}이(가) {m.name}의 공격을 회피했습니다!")
                continue
            dmg = max(1, int(m.atk - self.player.total_stats()["def_"] * 0.5))
            self.player.take_damage(dmg)
            self._log(f"{m.name}의 공격! {self.player.name}이(가) {dmg} 피해를 입었습니다.")

        if not self.player.is_alive():
            self.finished = True
            self.result = "lose"
        return self.finished
