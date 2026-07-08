# -*- coding: utf-8 -*-
import random


class RandomEventSystem:
    EVENT_WEIGHTS = {
        "raid": 0.2,
        "treasure_chest": 0.25,
        "luck_event": 0.2,
        "mystery_merchant": 0.15,
        "hidden_dungeon_discovery": 0.1,
        "none": 0.1,
    }

    def __init__(self, item_db, monster_db):
        self.item_db = item_db
        self.monster_db = monster_db

    def maybe_trigger(self, probability=0.25):
        if random.random() > probability:
            return None
        events = list(self.EVENT_WEIGHTS.keys())
        weights = list(self.EVENT_WEIGHTS.values())
        chosen = random.choices(events, weights=weights, k=1)[0]
        return chosen if chosen != "none" else None

    def resolve(self, event_type, player, current_location=None):
        if event_type == "raid":
            return self._raid(player, current_location)
        elif event_type == "treasure_chest":
            return self._treasure_chest(player)
        elif event_type == "luck_event":
            return self._luck_event(player)
        elif event_type == "mystery_merchant":
            return self._mystery_merchant()
        elif event_type == "hidden_dungeon_discovery":
            return self._hidden_dungeon()
        return ["아무 일도 일어나지 않았습니다."]

    def _raid(self, player, current_location):
        pool = current_location.monster_pool if (current_location and current_location.monster_pool) else None
        if not pool:
            return ["몬스터 무리가 습격하려 했지만, 이 지역은 안전합니다."], None
        monster = self.monster_db.random_from_pool(pool, level_scale=1.3)
        return [f"몬스터 무리의 습격! {monster.name}이(가) 나타났습니다!"], monster

    def _treasure_chest(self, player):
        gold = random.randint(20, 150)
        player.gold += gold
        return [f"보물상자를 발견했습니다! 골드 +{gold}"]

    def _luck_event(self, player):
        player.luck += 1
        return ["행운의 여신이 미소 지었습니다. 행운 스탯 +1 (영구)"]

    def _mystery_merchant(self):
        return ["안개 속에서 신비한 상인이 나타났습니다..."], "spawn_secret_merchant"

    def _hidden_dungeon(self):
        return ["지도에 없는 숨겨진 던전 입구를 발견했습니다!"], "unlock_hidden_dungeon"
