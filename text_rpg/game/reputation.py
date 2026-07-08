# -*- coding: utf-8 -*-

class ReputationSystem:
    def __init__(self):
        self.city_rep = {}   # {city_id: value(-100~100)}
        self.guild_rep = {}  # {guild_id: value}
        self.npc_affinity = {}  # {npc_id: value(0~100)}

    def change_city_rep(self, city_id, amount):
        self.city_rep[city_id] = max(-100, min(100, self.city_rep.get(city_id, 0) + amount))
        return self.city_rep[city_id]

    def change_guild_rep(self, guild_id, amount):
        self.guild_rep[guild_id] = max(-100, min(100, self.guild_rep.get(guild_id, 0) + amount))
        return self.guild_rep[guild_id]

    def change_npc_affinity(self, npc_id, amount):
        self.npc_affinity[npc_id] = max(0, min(100, self.npc_affinity.get(npc_id, 0) + amount))
        return self.npc_affinity[npc_id]

    def city_rank(self, city_id):
        rep = self.city_rep.get(city_id, 0)
        if rep >= 80:
            return "영웅"
        if rep >= 40:
            return "친애"
        if rep >= 0:
            return "중립"
        if rep >= -40:
            return "불신"
        return "적대"
