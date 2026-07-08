# -*- coding: utf-8 -*-
"""
모드 지원 구조.
동료가 새 시스템(길드/PvP/멀티플레이 등)을 독립적으로 개발할 때,
game/ 코드를 직접 건드리지 않고 mods/ 폴더에 파일을 추가하는 것만으로
기능을 확장할 수 있게 하기 위한 간단한 플러그인 로더입니다.

모드 작성 규칙:
1. mods/ 폴더에 .py 파일을 추가한다.
2. 파일 안에 `def register(game_context): ...` 함수를 정의한다.
3. register 함수는 game_context(딕셔너리 - player, world_map, quest_log 등 핵심 객체 참조)를
   받아 필요한 훅을 등록하거나 데이터를 주입한다.

예시(mods/example_guild_mod.py):

    def register(game_context):
        print("길드 시스템 모드 로드됨")
        game_context["hooks"].setdefault("on_town_enter", []).append(
            lambda ctx: print("길드 게시판이 반짝입니다!")
        )

데이터만 추가하고 싶다면(신규 아이템/몬스터), data/items.json / data/monsters.json 에
새 항목을 추가하는 것만으로도 ItemDatabase / MonsterDatabase 가 자동으로 인식합니다.
"""
import importlib.util
import os

from .constants import MODS_DIR


class ModLoader:
    def __init__(self, mods_dir=MODS_DIR):
        self.mods_dir = mods_dir
        self.loaded_mods = []

    def discover(self):
        if not os.path.isdir(self.mods_dir):
            return []
        return [f for f in os.listdir(self.mods_dir) if f.endswith(".py") and not f.startswith("_")]

    def load_all(self, game_context):
        game_context.setdefault("hooks", {})
        for filename in self.discover():
            path = os.path.join(self.mods_dir, filename)
            mod_name = f"mods.{filename[:-3]}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register"):
                    module.register(game_context)
                    self.loaded_mods.append(filename)
            except Exception as e:
                print(f"[모드 로드 실패] {filename}: {e}")
        return self.loaded_mods

    def run_hook(self, game_context, hook_name, *args, **kwargs):
        for fn in game_context.get("hooks", {}).get(hook_name, []):
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[모드 훅 실행 오류] {hook_name}: {e}")
