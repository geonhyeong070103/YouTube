# -*- coding: utf-8 -*-

class DialogueNode:
    def __init__(self, text, choices=None):
        self.text = text
        self.choices = choices or []  # [{"text": "...", "next": node_id 또는 None, "action": callable}]


class NPC:
    def __init__(self, npc_id, name, role, dialogue_tree=None):
        self.npc_id = npc_id
        self.name = name
        self.role = role  # merchant/blacksmith/alchemist/guildmaster/quest_giver
        self.dialogue_tree = dialogue_tree or {"start": DialogueNode(f"{name}: 어서 오세요.")}

    def get_node(self, node_id="start") -> DialogueNode:
        return self.dialogue_tree.get(node_id)


class Merchant(NPC):
    def __init__(self, npc_id, name, shop):
        super().__init__(npc_id, name, "merchant")
        self.shop = shop


class Blacksmith(NPC):
    """장비 강화/제작 담당"""
    def __init__(self, npc_id, name):
        super().__init__(npc_id, name, "blacksmith")

    def enhance(self, equipment):
        from .items import enhance_item
        return enhance_item(equipment)


class Alchemist(NPC):
    """포션 제작/재료 조합 담당"""
    def __init__(self, npc_id, name):
        super().__init__(npc_id, name, "alchemist")


class GuildMaster(NPC):
    def __init__(self, npc_id, name, guild_name):
        super().__init__(npc_id, name, "guildmaster")
        self.guild_name = guild_name


class QuestGiver(NPC):
    def __init__(self, npc_id, name, quest_ids):
        super().__init__(npc_id, name, "quest_giver")
        self.quest_ids = quest_ids
