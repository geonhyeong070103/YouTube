# -*- coding: utf-8 -*-
"""
예시 모드: 마을 입장 시 길드 게시판 알림을 띄우는 간단한 훅.
동료가 이 파일을 복사해서 새로운 모드를 만들면 됩니다.
"""


def register(game_context):
    def on_town_enter(ctx):
        print("[길드 모드] 게시판에 새로운 공지가 붙어있습니다.")

    game_context.setdefault("hooks", {}).setdefault("on_town_enter", []).append(on_town_enter)
    print("[모드] example_guild_mod 로드 완료")
