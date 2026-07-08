# -*- coding: utf-8 -*-

class Companion:
    def __init__(self, companion_id, name, job, base_stats):
        self.companion_id = companion_id
        self.name = name
        self.job = job
        self.level = 1
        self.stats = dict(base_stats)
        self.equipment = {}
        self.skills = []
        self.affinity = 0  # 호감도 (0~100)
        self.recruited = False

    def recruit(self):
        self.recruited = True
        return f"{self.name}이(가) 파티에 합류했습니다."

    def train(self, exp):
        self.level += max(1, exp // 100)
        for k in self.stats:
            self.stats[k] += 1
        return f"{self.name}이(가) 훈련으로 성장했습니다. (Lv.{self.level})"

    def equip(self, slot, item):
        self.equipment[slot] = item

    def raise_affinity(self, amount=1):
        self.affinity = min(100, self.affinity + amount)
        if self.affinity >= 100:
            return f"{self.name}과(와) 완전한 신뢰 관계가 되었습니다!"
        return None


class Pet:
    STAGE_ORDER = ["유생", "성체", "진화체", "최종진화체"]

    def __init__(self, pet_id, name, species, base_stats):
        self.pet_id = pet_id
        self.name = name
        self.species = species
        self.level = 1
        self.stage_index = 0
        self.stats = dict(base_stats)
        self.captured = False
        self.battle_ready = False

    def capture(self, capture_chance=0.3):
        import random
        if random.random() <= capture_chance:
            self.captured = True
            return True, f"{self.species}을(를) 포획했습니다!"
        return False, f"{self.species} 포획에 실패했습니다."

    def grow(self, exp):
        self.level += max(1, exp // 80)
        if self.level >= (self.stage_index + 1) * 15 and self.stage_index < len(self.STAGE_ORDER) - 1:
            self.stage_index += 1
            for k in self.stats:
                self.stats[k] = int(self.stats[k] * 1.5)
            return f"{self.name}이(가) {self.STAGE_ORDER[self.stage_index]}(으)로 진화했습니다!"
        return None

    def set_battle_ready(self, ready=True):
        self.battle_ready = ready
