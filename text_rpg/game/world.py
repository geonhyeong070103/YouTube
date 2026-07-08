# -*- coding: utf-8 -*-
import json
import os
import random


class Location:
    def __init__(self, loc_id, name, loc_type, connections=None, monster_pool=None, npcs=None):
        self.loc_id = loc_id
        self.name = name
        self.loc_type = loc_type  # town/forest/cave/desert/snow/volcano/dungeon/castle/hidden
        self.connections = connections or []  # 이동 가능한 다른 loc_id 리스트
        self.monster_pool = monster_pool or []
        self.npcs = npcs or []


class DungeonFloor:
    def __init__(self, floor_num, rooms):
        self.floor_num = floor_num
        self.rooms = rooms  # [{"type": "normal|boss|trap|treasure|secret", "cleared": False}]


class Dungeon(Location):
    def __init__(self, loc_id, name, connections=None, monster_pool=None,
                 num_floors=3, is_random=False, boss_id=None):
        super().__init__(loc_id, name, "dungeon", connections, monster_pool)
        self.num_floors = num_floors
        self.is_random = is_random
        self.boss_id = boss_id
        self.current_floor = 1
        self.floors = self._generate_floors()

    def _generate_floors(self):
        floors = []
        for i in range(1, self.num_floors + 1):
            rooms = []
            room_count = random.randint(3, 6) if self.is_random else 4
            for _ in range(room_count):
                roll = random.random()
                if roll < 0.08:
                    rtype = "treasure"
                elif roll < 0.15:
                    rtype = "trap"
                elif roll < 0.18:
                    rtype = "secret"
                else:
                    rtype = "normal"
                rooms.append({"type": rtype, "cleared": False})
            rooms.append({"type": "boss", "cleared": False})  # 층 마지막은 항상 보스방
            floors.append(DungeonFloor(i, rooms))
        return floors

    def advance_floor(self):
        if self.current_floor < self.num_floors:
            self.current_floor += 1
            return True
        return False

    def is_cleared(self):
        return self.current_floor >= self.num_floors and all(
            r["cleared"] for r in self.floors[-1].rooms)


class WorldMap:
    def __init__(self, path=os.path.join("data", "world.json")):
        self.path = path
        self.locations = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for loc_id, d in data.items():
            if d.get("type") == "dungeon":
                self.locations[loc_id] = Dungeon(
                    loc_id, d["name"], d.get("connections", []), d.get("monster_pool", []),
                    d.get("num_floors", 3), d.get("is_random", False), d.get("boss_id"))
            else:
                self.locations[loc_id] = Location(
                    loc_id, d["name"], d.get("type", "field"), d.get("connections", []),
                    d.get("monster_pool", []), d.get("npcs", []))

    def get(self, loc_id) -> Location:
        return self.locations.get(loc_id)

    def can_travel(self, from_id, to_id):
        loc = self.get(from_id)
        return loc is not None and to_id in loc.connections
