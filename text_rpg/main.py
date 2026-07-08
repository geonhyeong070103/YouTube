
# -*- coding: utf-8 -*-
"""
텍스트 그래픽 RPG - 메인 진입점
실행: python main.py

방향키(위/아래)로 메뉴 이동, Enter로 선택.
캐릭터 생성 시에는 이름을 타이핑 후 좌/우로 직업 선택, Enter로 시작.
"""
import os
import sys
import pygame

sys.path.insert(0, os.path.dirname(__file__))

from game.constants import (SCREEN_WIDTH, SCREEN_HEIGHT, FPS, BLACK, WHITE, GOLD, RED, GREEN,
                             FONT_PATH_KR, FONT_SIZE, LINE_HEIGHT, AUTOSAVE_INTERVAL_SEC)
from game.enums import GameState, JobType, EquipSlot
from game.character import Character
from game.jobs import JOB_DATA
from game.items import ItemDatabase, Equipment, Consumable
from game.monsters import MonsterDatabase, MonsterCodex
from game.combat import Battle
from game.shop import Shop, SecretMerchant
from game.quests import QuestLog
from game.world import WorldMap
from game.events_random import RandomEventSystem
from game.weather_time import WeatherSystem, TimeSystem
from game.reputation import ReputationSystem
from game.titles import TitleManager
from game.ethics import AlignmentSystem
from game.mods import ModLoader
from game.save_load import save_game, load_game, AutoSaver
from game.ui import TextUI, load_font


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("텍스트 RPG (Pygame)")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = load_font(FONT_PATH_KR, FONT_SIZE)
        self.ui = TextUI(self.screen, self.font)

        self.state = GameState.MAIN_MENU
        self.running = True
        self.menu_index = 0
        self.message_log = ["텍스트 RPG에 오신 것을 환영합니다."]

        # 데이터베이스 & 시스템
        self.item_db = ItemDatabase()
        self.monster_db = MonsterDatabase()
        self.world_map = WorldMap()
        self.quest_log = QuestLog()
        self.random_events = RandomEventSystem(self.item_db, self.monster_db)
        self.weather = WeatherSystem()
        self.time_system = TimeSystem()
        self.reputation = ReputationSystem()
        self.titles = TitleManager()
        self.alignment = AlignmentSystem()
        self.monster_codex = MonsterCodex()

        self.player = None
        self.current_location_id = "town"
        self.current_battle = None
        self.current_shop = None
        self.pending_name = ""
        self.pending_job_index = 0

        self.autosaver = AutoSaver(AUTOSAVE_INTERVAL_SEC, self._collect_save_state)

        # 모드 로더: game/ 코드를 건드리지 않고 mods/ 폴더로 기능 확장
        self.mod_loader = ModLoader()
        self.game_context = {"world_map": self.world_map, "quest_log": self.quest_log}
        self.mod_loader.load_all(self.game_context)

    def _collect_save_state(self):
        extra = {"current_location_id": self.current_location_id}
        return self.player, extra

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event)
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
            if self.player:
                self.autosaver.tick()
        pygame.quit()

    def handle_key(self, event):
        if self.state == GameState.MAIN_MENU:
            self._handle_main_menu(event)
        elif self.state == GameState.CHAR_CREATE:
            self._handle_char_create(event)
        elif self.state == GameState.TOWN:
            self._handle_town(event)
        elif self.state == GameState.FIELD:
            self._handle_field(event)
        elif self.state == GameState.BATTLE:
            self._handle_battle(event)
        elif self.state == GameState.SHOP:
            self._handle_shop(event)
        elif self.state == GameState.INVENTORY:
            self._handle_inventory(event)
        elif self.state == GameState.QUEST_LOG:
            self._handle_quest_log(event)
        elif self.state == GameState.GAME_OVER:
            if event.key == pygame.K_RETURN:
                self.state = GameState.MAIN_MENU

    def _nav(self, event, length):
        if length <= 0:
            return
        if event.key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % length
        elif event.key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % length

    def _handle_main_menu(self, event):
        options = ["새 게임", "이어하기", "종료"]
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            if self.menu_index == 0:
                self.state = GameState.CHAR_CREATE
                self.pending_name = ""
                self.menu_index = 0
            elif self.menu_index == 1:
                data = load_game("autosave")
                if data:
                    self._load_from_dict(data)
                    self.state = GameState.TOWN
                else:
                    self.message_log.append("저장된 게임이 없습니다.")
            elif self.menu_index == 2:
                self.running = False

    def _handle_char_create(self, event):
        jobs = list(JobType)[:5]
        if event.key == pygame.K_RETURN:
            if self.pending_name.strip():
                job = jobs[self.pending_job_index]
                self.player = Character(self.pending_name.strip(), job)
                self.message_log = [f"{self.player.name}({job.value})의 모험이 시작됩니다!"]
                self.quest_log.accept("q_main_1")
                self.state = GameState.TOWN
                self.menu_index = 0
        elif event.key == pygame.K_BACKSPACE:
            self.pending_name = self.pending_name[:-1]
        elif event.key == pygame.K_LEFT:
            self.pending_job_index = (self.pending_job_index - 1) % len(jobs)
        elif event.key == pygame.K_RIGHT:
            self.pending_job_index = (self.pending_job_index + 1) % len(jobs)
        elif event.unicode and event.unicode.isprintable() and len(self.pending_name) < 12:
            self.pending_name += event.unicode

    def _town_options(self):
        return ["필드로 이동", "상점", "인벤토리", "퀘스트 목록", "스탯 분배", "저장하기", "메인 메뉴로"]

    def _handle_town(self, event):
        options = self._town_options()
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            choice = options[self.menu_index]
            if choice == "필드로 이동":
                self.state = GameState.FIELD
                self.menu_index = 0
            elif choice == "상점":
                stock = {"potion_small": 20, "potion_large": 60, "mana_potion": 25,
                         "antidote": 15, "iron_sword": 150, "iron_armor": 160}
                self.current_shop = Shop("마을 상점", stock, self.item_db)
                self.current_shop.fluctuate_prices()
                self.state = GameState.SHOP
                self.menu_index = 0
            elif choice == "인벤토리":
                self.state = GameState.INVENTORY
                self.menu_index = 0
            elif choice == "퀘스트 목록":
                self.state = GameState.QUEST_LOG
                self.menu_index = 0
            elif choice == "스탯 분배":
                if self.player.unspent_stat_points > 0:
                    ok, msg = self.player.allocate_stat("atk", 1)
                    self.message_log.append(msg)
                else:
                    self.message_log.append("분배 가능한 스탯 포인트가 없습니다.")
            elif choice == "저장하기":
                save_game(self.player, {"current_location_id": self.current_location_id}, "autosave")
                self.message_log.append("게임을 저장했습니다.")
            elif choice == "메인 메뉴로":
                self.state = GameState.MAIN_MENU
                self.menu_index = 0

    def _handle_field(self, event):
        loc = self.world_map.get(self.current_location_id)
        options = [self.world_map.get(cid).name for cid in loc.connections] + ["마을로 복귀", "탐색하기"]
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            choice_index = self.menu_index
            if choice_index < len(loc.connections):
                self.current_location_id = loc.connections[choice_index]
                self.time_system.advance(1)
                self.weather.cycle()
                self.menu_index = 0
            elif options[choice_index] == "마을로 복귀":
                self.current_location_id = "town"
                self.state = GameState.TOWN
                self.menu_index = 0
            elif options[choice_index] == "탐색하기":
                self._explore()

    def _explore(self):
        loc = self.world_map.get(self.current_location_id)
        event_type = self.random_events.maybe_trigger(0.3)
        if event_type == "raid":
            logs, monster = self.random_events.resolve("raid", self.player, loc)
            self.message_log.extend(logs)
            if monster:
                self._start_battle([monster])
            return
        elif event_type:
            result = self.random_events.resolve(event_type, self.player, loc)
            logs = result[0] if isinstance(result, tuple) else result
            self.message_log.extend(logs)
            return
        if loc.monster_pool:
            monster = self.monster_db.random_from_pool(loc.monster_pool)
            self.monster_codex.record_encounter(monster.monster_id)
            self._start_battle([monster])
        else:
            self.message_log.append("이 지역에서는 몬스터가 나타나지 않습니다.")

    def _start_battle(self, monsters):
        self.current_battle = Battle(self.player, monsters, self.weather.combat_modifiers())
        self.state = GameState.BATTLE
        self.menu_index = 0

    def _battle_options(self):
        return ["일반 공격", "스킬 사용", "아이템 사용", "도망"]

    def _handle_battle(self, event):
        battle = self.current_battle
        if battle.finished:
            if event.key == pygame.K_RETURN:
                self._resolve_battle_end()
            return
        options = self._battle_options()
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            choice = options[self.menu_index]
            if choice == "일반 공격":
                battle.player_normal_attack(0)
            elif choice == "스킬 사용":
                if self.player.skills:
                    battle.player_use_skill(self.player.skills[0], 0)
                else:
                    battle.log.append("사용 가능한 스킬이 없습니다.")
            elif choice == "아이템 사용":
                consumables = [it for it in self.player.inventory.items if hasattr(it, "effect_type")]
                if consumables:
                    battle.player_use_item(consumables[0])
                else:
                    battle.log.append("사용 가능한 아이템이 없습니다.")
            elif choice == "도망":
                battle.player_flee()

    def _resolve_battle_end(self):
        battle = self.current_battle
        if battle.result == "win":
            total_exp = sum(m.exp_reward for m in battle.monsters)
            total_gold = sum(m.gold_reward for m in battle.monsters)
            self.player.gold += total_gold
            logs = self.player.gain_exp(total_exp)
            self.message_log = logs + [f"골드 +{total_gold}"]
            for m in battle.monsters:
                self.monster_codex.record_defeat(m.monster_id)
                self.titles.increment(f"{m.monster_id}_kills")
                drops = m.roll_drops(self.item_db)
                for it in drops:
                    self.player.inventory.add_item(it)
                    self.message_log.append(f"드롭: {it.name}")
                self.quest_log.notify_event("defeat", m.monster_id)
            unlocked = self.titles.check_achievements(self.player)
            for t in unlocked:
                self.message_log.append(f"업적 달성! 칭호 '{t}' 획득")
        elif battle.result == "lose":
            self.message_log = ["패배했습니다... 마을에서 다시 시작합니다."]
            self.player.hp = self.player.max_hp
            self.current_location_id = "town"
        else:
            self.message_log = ["전투에서 벗어났습니다."]
        self.current_battle = None
        self.state = GameState.TOWN if self.current_location_id == "town" else GameState.FIELD
        self.menu_index = 0

    def _handle_shop(self, event):
        item_ids = list(self.current_shop.stock.keys())
        options = [f"{self.item_db.defs[i]['name']} - {self.current_shop.get_price(i)}G" for i in item_ids] + ["나가기"]
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            if self.menu_index == len(options) - 1:
                self.state = GameState.TOWN
                self.menu_index = 0
            else:
                item_id = item_ids[self.menu_index]
                ok, msg = self.current_shop.buy(self.player, item_id)
                self.message_log.append(msg)

    def _handle_inventory(self, event):
        items = self.player.inventory.items
        options = [it.name for it in items] + ["자동 정리", "나가기"]
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            if self.menu_index == len(options) - 1:
                self.state = GameState.TOWN
                self.menu_index = 0
            elif self.menu_index == len(options) - 2:
                self.player.inventory.auto_organize()
                self.message_log.append("인벤토리를 정리했습니다.")
            else:
                item = items[self.menu_index]
                if isinstance(item, Equipment):
                    old = self.player.equip(item)
                    self.message_log.append(f"{item.name} 장착!" + (f" ({old.name} 해제)" if old else ""))
                elif isinstance(item, Consumable):
                    if item.effect_type == "heal_hp":
                        self.player.heal(item.effect_value)
                    self.message_log.append(f"{item.name} 사용")
                    self.player.inventory.remove_item(item.uid)

    def _handle_quest_log(self, event):
        quest_ids = list(self.quest_log.active.keys())
        options = quest_ids + ["나가기"]
        self._nav(event, len(options))
        if event.key == pygame.K_RETURN:
            if self.menu_index == len(options) - 1:
                self.state = GameState.TOWN
                self.menu_index = 0
            else:
                qid = quest_ids[self.menu_index]
                ok, result = self.quest_log.turn_in(qid, self.player)
                if ok:
                    self.message_log.extend(result)
                else:
                    self.message_log.append(result)

    def _load_from_dict(self, data):
        pd = data["player"]
        self.player = Character(pd["name"], JobType[pd["job"]])
        self.player.level = pd["level"]
        self.player.exp = pd["exp"]
        self.player.exp_to_next = pd["exp_to_next"]
        self.player.max_hp = pd["max_hp"]
        self.player.hp = pd["hp"]
        self.player.max_mp = pd["max_mp"]
        self.player.mp = pd["mp"]
        self.player.atk = pd["atk"]
        self.player.def_ = pd["def_"]
        self.player.agi = pd["agi"]
        self.player.luck = pd["luck"]
        self.player.unspent_stat_points = pd["unspent_stat_points"]
        self.player.skills = pd["skills"]
        self.player.gold = pd["gold"]
        self.player.karma = pd.get("karma", 0)
        self.player.titles = pd.get("titles", [])
        for item_data in pd.get("inventory", []):
            try:
                self.player.inventory.add_item(self.item_db.create(item_data["item_id"]))
            except KeyError:
                continue
        self.current_location_id = data.get("extra", {}).get("current_location_id", "town")

    def draw(self):
        self.screen.fill(BLACK)
        if self.state == GameState.MAIN_MENU:
            self._draw_main_menu()
        elif self.state == GameState.CHAR_CREATE:
            self._draw_char_create()
        elif self.state == GameState.TOWN:
            self._draw_town()
        elif self.state == GameState.FIELD:
            self._draw_field()
        elif self.state == GameState.BATTLE:
            self._draw_battle()
        elif self.state == GameState.SHOP:
            self._draw_shop()
        elif self.state == GameState.INVENTORY:
            self._draw_inventory()
        elif self.state == GameState.QUEST_LOG:
            self._draw_quest_log()
        elif self.state == GameState.GAME_OVER:
            self.ui.draw_text("GAME OVER", 400, 300, RED)

    def _draw_main_menu(self):
        self.ui.draw_text("텍스트 RPG", 380, 100, GOLD)
        self.ui.draw_menu("메인 메뉴", ["새 게임", "이어하기", "종료"], 400, 250, self.menu_index)

    def _draw_char_create(self):
        jobs = list(JobType)[:5]
        job = jobs[self.pending_job_index]
        self.ui.draw_text("캐릭터 생성", 380, 60, GOLD)
        self.ui.draw_text(f"이름: {self.pending_name}_", 200, 150, WHITE)
        self.ui.draw_text(f"직업(<- ->로 변경): {job.value}", 200, 190, WHITE)
        base = JOB_DATA[job]["base_stats"]
        self.ui.draw_text(
            f"HP {base['hp']} MP {base['mp']} ATK {base['atk']} DEF {base['def']} AGI {base['agi']} LUK {base['luck']}",
            200, 230, GREEN)
        self.ui.draw_text("Enter로 시작", 200, 280, GOLD)

    def _draw_town(self):
        self.ui.draw_status_window(self.player, 20, 20)
        loc = self.world_map.get(self.current_location_id)
        self.ui.draw_text(f"[{loc.name}] 날씨: {self.weather.current} "
                           f"시간: {self.time_system.hour}시 ({self.time_system.season})", 20, 130, GOLD)
        self.ui.draw_menu("행동 선택", self._town_options(), 20, 180, self.menu_index)
        self.ui.draw_lines(self.message_log, 20, 420, WHITE, max_lines=8)

    def _draw_field(self):
        loc = self.world_map.get(self.current_location_id)
        self.ui.draw_status_window(self.player, 20, 20)
        self.ui.draw_minimap_text(loc, self.world_map, 20, 130)
        options = [self.world_map.get(cid).name for cid in loc.connections] + ["마을로 복귀", "탐색하기"]
        self.ui.draw_menu("이동/행동", options, 20, 250, self.menu_index)
        self.ui.draw_lines(self.message_log, 20, 460, WHITE, max_lines=6)

    def _draw_battle(self):
        battle = self.current_battle
        self.ui.draw_status_window(self.player, 20, 20)
        y = 130
        for m in battle.monsters:
            color = GREEN if m.is_alive() else GOLD
            self.ui.draw_text(f"{m.name}  HP {m.hp}/{m.max_hp}", 20, y, color)
            y += LINE_HEIGHT
        if not battle.finished:
            self.ui.draw_menu("전투 행동", self._battle_options(), 20, y + 20, self.menu_index)
        else:
            result_txt = {"win": "승리!", "lose": "패배...", "flee": "도망 성공"}[battle.result]
            self.ui.draw_text(f"{result_txt} (Enter로 계속)", 20, y + 20, GOLD)
        self.ui.draw_battle_log(battle.log, 20, y + 70, max_lines=8)

    def _draw_shop(self):
        self.ui.draw_text(f"{self.current_shop.name} (보유 골드: {self.player.gold})", 20, 20, GOLD)
        item_ids = list(self.current_shop.stock.keys())
        options = [f"{self.item_db.defs[i]['name']} - {self.current_shop.get_price(i)}G" for i in item_ids] + ["나가기"]
        self.ui.draw_menu("구매할 아이템", options, 20, 70, self.menu_index)
        self.ui.draw_lines(self.message_log, 20, 420, WHITE, max_lines=6)

    def _draw_inventory(self):
        self.ui.draw_text(f"인벤토리 ({len(self.player.inventory.items)}/{self.player.inventory.capacity})", 20, 20, GOLD)
        items = self.player.inventory.items
        options = [it.name for it in items] + ["자동 정리", "나가기"]
        self.ui.draw_menu("아이템", options, 20, 70, self.menu_index)
        self.ui.draw_lines(self.message_log, 20, 460, WHITE, max_lines=6)

    def _draw_quest_log(self):
        self.ui.draw_text("퀘스트 목록 (Enter: 완료 시도)", 20, 20, GOLD)
        quest_ids = list(self.quest_log.active.keys())
        options = []
        for qid in quest_ids:
            q = self.quest_log.active[qid]
            obj_txt = ", ".join(f"{o['target']} {o['progress']}/{o['count']}" for o in q.objectives)
            options.append(f"{q.title} [{obj_txt}]")
        options.append("나가기")
        self.ui.draw_menu("진행중인 퀘스트", options, 20, 70, self.menu_index)


def main():
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
