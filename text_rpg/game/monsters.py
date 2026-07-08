# -*- coding: utf-8 -*-
import json
import os
import random

from .enums import MonsterTier, ElementType


class Monster:
    def __init__(self, monster_id, name, level, hp, atk, defense, agi, element=ElementType.NONE,
                 tier=MonsterTier.NORMAL, drop_table=None, exp_reward=10, gold_reward=5, skills=None):
        self.monster_id = monster_id
        self.name = name
        self.level = level
        self.max_hp = hp
        self.hp = hp
        self.atk = atk
        self.defense = defense
        self.agi = agi
        self.element = element
        self.tier = tier
        self.drop_table = drop_table or []  # [{"item_id":..., "chance":0.3, "rare": bool}]
        self.exp_reward = exp_reward
        self.gold_reward = gold_reward
        self.skills = skills or []
        self.status_effects = {}

    def is_alive(self):
        return self.hp > 0

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        return self.hp

    def roll_drops(self, item_db):
        dropped = []
        for entry in self.drop_table:
            if random.random() <= entry["chance"]:
                try:
                    dropped.append(item_db.create(entry["item_id"]))
                except KeyError:
                    continue
        return dropped


class MonsterCodex:
    """몬스터 도감: 조우/처치 기록"""
    def __init__(self):
        self.encountered = set()
        self.defeated_count = {}

    def record_encounter(self, monster_id):
        self.encountered.add(monster_id)

    def record_defeat(self, monster_id):
        self.defeated_count[monster_id] = self.defeated_count.get(monster_id, 0) + 1

    def completion_rate(self, total_known):
        if total_known == 0:
            return 0
        return round(len(self.encountered) / total_known * 100, 1)


class MonsterDatabase:
    def __init__(self, path=os.path.join("data", "monsters.json")):
        self.path = path
        self.defs = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.defs = json.load(f)

    def spawn(self, monster_id, level_scale=1.0) -> Monster:
        d = self.defs[monster_id]
        return Monster(
            monster_id=monster_id, name=d["name"], level=int(d["level"] * level_scale),
            hp=int(d["hp"] * level_scale), atk=int(d["atk"] * level_scale),
            defense=int(d["def"] * level_scale), agi=d["agi"],
            element=ElementType[d.get("element", "NONE")], tier=MonsterTier[d.get("tier", "NORMAL")],
            drop_table=d.get("drop_table", []), exp_reward=int(d.get("exp_reward", 10) * level_scale),
            gold_reward=int(d.get("gold_reward", 5) * level_scale), skills=d.get("skills", []),
        )

    def all_ids(self):
        return list(self.defs.keys())

    def random_from_pool(self, pool_ids, level_scale=1.0):
        return self.spawn(random.choice(pool_ids), level_scale)
