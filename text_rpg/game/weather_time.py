# -*- coding: utf-8 -*-
import random

WEATHER_TYPES = ["맑음", "비", "눈", "폭풍"]
SEASONS = ["봄", "여름", "가을", "겨울"]

# 날씨별 전투 보정 (원소 위력 배율, 회피율 보정 등)
WEATHER_COMBAT_EFFECTS = {
    "맑음": {},
    "비": {"element_boost": "물", "boost_mult": 1.2, "fire_penalty": 0.8},
    "눈": {"element_boost": "물", "agi_penalty": 0.9},
    "폭풍": {"element_boost": "번개", "boost_mult": 1.3, "dodge_penalty": 0.85},
}


class WeatherSystem:
    def __init__(self):
        self.current = "맑음"

    def cycle(self):
        self.current = random.choices(
            WEATHER_TYPES, weights=[0.5, 0.25, 0.15, 0.10], k=1
        )[0]
        return self.current

    def combat_modifiers(self):
        return WEATHER_COMBAT_EFFECTS.get(self.current, {})


class TimeSystem:
    """게임 내 시간: 1턴(필드 이동)마다 1시간씩 흐른다고 가정"""
    def __init__(self):
        self.hour = 8
        self.day = 1
        self.season_index = 0

    @property
    def season(self):
        return SEASONS[self.season_index % 4]

    @property
    def is_night(self):
        return self.hour >= 20 or self.hour < 6

    def advance(self, hours=1):
        self.hour = (self.hour + hours) % 24
        if self.hour < hours:  # 자정 넘어감 -> 하루 증가
            self.day += 1
            if self.day % 30 == 0:
                self.season_index += 1
        return self.hour

    def time_based_event(self):
        """특정 시간대 이벤트 훅 (예: 자정에만 나타나는 몬스터 등)"""
        if self.hour == 0:
            return "midnight_special_spawn"
        if self.hour == 12:
            return "noon_market_rush"
        return None
