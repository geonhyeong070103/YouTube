# -*- coding: utf-8 -*-
from enum import Enum, auto


class JobType(str, Enum):
    WARRIOR = "전사"
    MAGE = "마법사"
    ARCHER = "궁수"
    ROGUE = "도적"
    PRIEST = "사제"
    # 상위 직업(전직) 예시 - jobs.py의 ADVANCED_JOB_TREE 참고
    PALADIN = "성기사"
    ARCHMAGE = "대마법사"
    ASSASSIN = "암살자"


class ElementType(str, Enum):
    NONE = "무속성"
    FIRE = "불"
    WATER = "물"
    WIND = "바람"
    LIGHTNING = "번개"
    DARK = "암흑"
    LIGHT = "빛"


# 속성 상성표: key가 value에 강함(1.5배 데미지), 반대는 0.67배
ELEMENT_ADVANTAGE = {
    ElementType.FIRE: ElementType.WIND,
    ElementType.WIND: ElementType.LIGHTNING,
    ElementType.LIGHTNING: ElementType.WATER,
    ElementType.WATER: ElementType.FIRE,
    ElementType.LIGHT: ElementType.DARK,
    ElementType.DARK: ElementType.LIGHT,
}


class StatusEffect(str, Enum):
    POISON = "독"
    BURN = "화상"
    FREEZE = "빙결"
    STUN = "기절"
    BLEED = "출혈"


class Rarity(str, Enum):
    COMMON = "일반"
    UNCOMMON = "고급"
    RARE = "희귀"
    EPIC = "영웅"
    LEGENDARY = "전설"
    MYTHIC = "신화"


RARITY_ORDER = [Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.EPIC, Rarity.LEGENDARY, Rarity.MYTHIC]

RARITY_STAT_MULTIPLIER = {
    Rarity.COMMON: 1.0,
    Rarity.UNCOMMON: 1.15,
    Rarity.RARE: 1.35,
    Rarity.EPIC: 1.6,
    Rarity.LEGENDARY: 2.0,
    Rarity.MYTHIC: 2.6,
}


class EquipSlot(str, Enum):
    WEAPON = "무기"
    ARMOR = "방어구"
    ACCESSORY = "장신구"


class MonsterTier(str, Enum):
    NORMAL = "일반"
    ELITE = "엘리트"
    BOSS = "보스"
    WORLD_BOSS = "월드보스"


class GameState(Enum):
    MAIN_MENU = auto()
    CHAR_CREATE = auto()
    TOWN = auto()
    FIELD = auto()
    BATTLE = auto()
    SHOP = auto()
    INVENTORY = auto()
    QUEST_LOG = auto()
    MONSTER_CODEX = auto()
    GAME_OVER = auto()
