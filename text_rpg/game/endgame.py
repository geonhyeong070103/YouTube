# -*- coding: utf-8 -*-
import json
import os
import time


class InfiniteDungeon:
    """층이 끝없이 이어지며 난이도가 계속 상승하는 엔드 콘텐츠"""
    def __init__(self):
        self.current_floor = 0
        self.best_floor = 0

    def next_floor(self):
        self.current_floor += 1
        self.best_floor = max(self.best_floor, self.current_floor)
        level_scale = 1.0 + self.current_floor * 0.08
        return self.current_floor, level_scale

    def reset_on_death(self):
        self.current_floor = 0


class TowerOfTrials:
    """고정된 층 수, 층마다 강력한 단일 보스 + 제한시간/버프 없음 등의 룰"""
    TOTAL_FLOORS = 100

    def __init__(self):
        self.cleared_floor = 0

    def attempt_floor(self, floor_num):
        if floor_num != self.cleared_floor + 1:
            return False, "이전 층부터 순서대로 도전해야 합니다."
        return True, "도전 시작"

    def clear_floor(self, floor_num):
        self.cleared_floor = max(self.cleared_floor, floor_num)


class HardMode:
    """난이도 배율 토글: 몬스터 강화, 보상 증가"""
    def __init__(self, enabled=False, monster_mult=1.6, reward_mult=1.5):
        self.enabled = enabled
        self.monster_mult = monster_mult
        self.reward_mult = reward_mult

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled


class SeasonContent:
    """시즌제 콘텐츠: 시즌 종료 시 랭킹 보상 후 초기화되는 별도 진행도"""
    def __init__(self, season_id="season_1", duration_days=60):
        self.season_id = season_id
        self.duration_days = duration_days
        self.started_at = time.time()
        self.season_points = 0

    def is_active(self):
        elapsed_days = (time.time() - self.started_at) / 86400
        return elapsed_days < self.duration_days

    def add_points(self, amount):
        self.season_points += amount


class RankingBoard:
    """로컬 랭킹 스텁 (온라인 연동 시 서버 API로 교체 - mods.py 참고)"""
    def __init__(self, path=os.path.join("data", "ranking.json")):
        self.path = path
        self.entries = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)

    def submit_score(self, name, score, category="infinite_dungeon"):
        self.entries.append({"name": name, "score": score, "category": category})
        self.entries.sort(key=lambda e: e["score"], reverse=True)
        self.entries = self.entries[:100]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def top(self, category="infinite_dungeon", n=10):
        return [e for e in self.entries if e["category"] == category][:n]
