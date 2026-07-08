# -*- coding: utf-8 -*-
"""
직업 데이터. 새 직업을 추가하려면 JOB_DATA에 항목만 추가하면 됨(모드 친화적 구조).
"""
from .enums import JobType, ElementType

JOB_DATA = {
    JobType.WARRIOR: {
        "base_stats": {"hp": 120, "mp": 20, "atk": 14, "def": 12, "agi": 8, "luck": 6},
        "growth": {"hp": 14, "mp": 2, "atk": 2.2, "def": 2.0, "agi": 1.0, "luck": 0.6},
        "element": ElementType.NONE,
        "skills": {
            2: {"name": "강타", "mp_cost": 5, "power": 1.6, "element": ElementType.NONE},
            5: {"name": "방패치기", "mp_cost": 8, "power": 1.2, "status": "STUN"},
            10: {"name": "회전베기", "mp_cost": 14, "power": 1.4, "hits": 2},
        },
    },
    JobType.MAGE: {
        "base_stats": {"hp": 80, "mp": 60, "atk": 8, "def": 6, "agi": 9, "luck": 8},
        "growth": {"hp": 8, "mp": 6, "atk": 1.2, "def": 0.8, "agi": 1.1, "luck": 0.9},
        "element": ElementType.FIRE,
        "skills": {
            2: {"name": "파이어볼", "mp_cost": 10, "power": 1.8, "element": ElementType.FIRE},
            5: {"name": "아이스니들", "mp_cost": 14, "power": 1.5, "element": ElementType.WATER, "status": "FREEZE"},
            10: {"name": "라이트닝체인", "mp_cost": 22, "power": 2.2, "element": ElementType.LIGHTNING},
        },
    },
    JobType.ARCHER: {
        "base_stats": {"hp": 95, "mp": 30, "atk": 13, "def": 7, "agi": 14, "luck": 9},
        "growth": {"hp": 10, "mp": 3, "atk": 1.8, "def": 0.9, "agi": 1.6, "luck": 0.8},
        "element": ElementType.WIND,
        "skills": {
            2: {"name": "연사", "mp_cost": 8, "power": 1.3, "hits": 2},
            5: {"name": "관통사격", "mp_cost": 12, "power": 1.9, "element": ElementType.WIND},
            10: {"name": "출혈화살", "mp_cost": 16, "power": 1.4, "status": "BLEED"},
        },
    },
    JobType.ROGUE: {
        "base_stats": {"hp": 90, "mp": 25, "atk": 12, "def": 7, "agi": 16, "luck": 12},
        "growth": {"hp": 9, "mp": 2.5, "atk": 1.7, "def": 0.8, "agi": 1.8, "luck": 1.2},
        "element": ElementType.DARK,
        "skills": {
            2: {"name": "기습", "mp_cost": 6, "power": 1.7, "crit_bonus": 0.25},
            5: {"name": "독침", "mp_cost": 9, "power": 1.1, "status": "POISON"},
            10: {"name": "그림자베기", "mp_cost": 18, "power": 2.0, "element": ElementType.DARK},
        },
    },
    JobType.PRIEST: {
        "base_stats": {"hp": 100, "mp": 55, "atk": 7, "def": 9, "agi": 8, "luck": 10},
        "growth": {"hp": 11, "mp": 5, "atk": 0.9, "def": 1.2, "agi": 0.9, "luck": 1.0},
        "element": ElementType.LIGHT,
        "skills": {
            2: {"name": "힐", "mp_cost": 10, "heal": 1.5},
            5: {"name": "홀리스매시", "mp_cost": 14, "power": 1.6, "element": ElementType.LIGHT},
            10: {"name": "신의가호", "mp_cost": 20, "buff": {"def": 1.5, "duration": 3}},
        },
    },
}

# 전직(상위 직업) 트리: 레벨/조건 충족 시 전직 가능
ADVANCED_JOB_TREE = {
    JobType.WARRIOR: {"advanced": JobType.PALADIN, "min_level": 20, "quest_id": "q_paladin_trial"},
    JobType.MAGE: {"advanced": JobType.ARCHMAGE, "min_level": 20, "quest_id": "q_archmage_trial"},
    JobType.ROGUE: {"advanced": JobType.ASSASSIN, "min_level": 20, "quest_id": "q_assassin_trial"},
}

# 히든 직업(추가 요소): 특정 조건 만족 시 숨겨진 전직 해금 (예시 스텁)
HIDDEN_JOBS = {
    "chrono_walker": {
        "condition": "defeat_hidden_boss:time_wyrm",
        "unlocks_job": "시간술사",
    }
}


def get_base_stats(job: JobType) -> dict:
    return dict(JOB_DATA[job]["base_stats"])


def get_growth(job: JobType) -> dict:
    return dict(JOB_DATA[job]["growth"])


def get_skills_for_job(job: JobType) -> dict:
    return JOB_DATA[job]["skills"]
