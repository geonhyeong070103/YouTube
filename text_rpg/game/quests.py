# -*- coding: utf-8 -*-
import json
import os


class Quest:
    def __init__(self, quest_id, title, quest_type, objectives, rewards, description=""):
        self.quest_id = quest_id
        self.title = title
        self.quest_type = quest_type  # "main" | "sub" | "daily" | "repeat" | "achievement"
        self.objectives = objectives  # [{"type":"defeat","target":"slime","count":5,"progress":0}]
        self.rewards = rewards  # {"exp":100,"gold":50,"items":[...]}
        self.description = description
        self.status = "active"  # active | completed | turned_in

    def update_progress(self, obj_type, target, amount=1):
        for obj in self.objectives:
            if obj["type"] == obj_type and obj["target"] == target:
                obj["progress"] = min(obj["count"], obj["progress"] + amount)
        if all(o["progress"] >= o["count"] for o in self.objectives):
            self.status = "completed"

    def is_complete(self):
        return self.status in ("completed", "turned_in")


class QuestLog:
    def __init__(self, path=os.path.join("data", "quests.json")):
        self.path = path
        self.definitions = {}
        self.active = {}
        self.completed = {}
        self.load_definitions()

    def load_definitions(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.definitions = json.load(f)

    def accept(self, quest_id):
        if quest_id in self.active or quest_id in self.completed:
            return None
        d = self.definitions[quest_id]
        q = Quest(quest_id, d["title"], d["type"],
                   [dict(o) for o in d["objectives"]], d["rewards"], d.get("description", ""))
        self.active[quest_id] = q
        return q

    def notify_event(self, obj_type, target, amount=1):
        """전투/채집 등 이벤트 발생 시 호출하여 모든 활성 퀘스트 진행도 갱신"""
        completed_now = []
        for qid, q in self.active.items():
            q.update_progress(obj_type, target, amount)
            if q.is_complete():
                completed_now.append(qid)
        return completed_now

    def turn_in(self, quest_id, player):
        q = self.active.get(quest_id)
        if not q or not q.is_complete():
            return False, "완료 조건을 충족하지 못했습니다."
        rewards = q.rewards
        logs = player.gain_exp(rewards.get("exp", 0))
        player.gold += rewards.get("gold", 0)
        q.status = "turned_in"
        if q.quest_type not in ("daily", "repeat"):
            self.completed[quest_id] = self.active.pop(quest_id)
        else:
            del self.active[quest_id]  # 반복 퀘스트는 다시 수락 가능하도록 제거만
        logs.append(f"퀘스트 '{q.title}' 완료! 골드 +{rewards.get('gold', 0)}")
        return True, logs
