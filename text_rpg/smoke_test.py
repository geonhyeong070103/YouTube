import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from main import Game

def key(k, unicode=""):
    return pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode)

g = Game()
g.draw()

# 새 게임 선택
g.handle_key(key(pygame.K_RETURN))
g.draw()
assert g.state.name == "CHAR_CREATE"

# 이름 입력
for ch in "테스트":
    g.handle_key(key(pygame.K_a, unicode=ch))
g.handle_key(key(pygame.K_RIGHT))  # 직업 변경
g.handle_key(key(pygame.K_RETURN))  # 시작
g.draw()
assert g.state.name == "TOWN", g.state

# 필드 이동
g.menu_index = 0
g.handle_key(key(pygame.K_RETURN))
g.draw()
assert g.state.name == "FIELD"

# 여러 번 탐색해서 전투/이벤트 유발
import random
random.seed(1)
for _ in range(15):
    loc = g.world_map.get(g.current_location_id)
    explore_index = len(loc.connections) + 1
    g.menu_index = explore_index
    g.handle_key(key(pygame.K_RETURN))
    g.draw()
    if g.state.name == "BATTLE":
        # 전투 진행: 승패 날 때까지 일반 공격
        tries = 0
        while not g.current_battle.finished and tries < 30:
            g.menu_index = 0
            g.handle_key(key(pygame.K_RETURN))
            g.draw()
            tries += 1
        g.handle_key(key(pygame.K_RETURN))  # 결과 확인
        g.draw()
    print("state:", g.state.name, "loc:", g.current_location_id, "hp:", g.player.hp if g.player else None)

# 상점 진입 테스트
g.state = __import__("game.enums", fromlist=["GameState"]).GameState.TOWN
g.menu_index = 1
g.handle_key(key(pygame.K_RETURN))
g.draw()
assert g.state.name == "SHOP"
g.menu_index = 0
g.handle_key(key(pygame.K_RETURN))  # 아이템 구매
g.draw()
print("gold after shop:", g.player.gold)

# 저장/로드 테스트
from game.save_load import save_game, load_game
save_game(g.player, {"current_location_id": g.current_location_id}, "autosave")
data = load_game("autosave")
assert data is not None
print("SAVE/LOAD OK")

print("ALL SMOKE TESTS PASSED")
