# -*- coding: utf-8 -*-
import json
import os
import time

from .constants import SAVE_DIR


def ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)


def save_game(player, extra_state=None, slot="autosave"):
    ensure_save_dir()
    data = {
        "player": player.to_dict(),
        "extra": extra_state or {},
        "saved_at": time.time(),
    }
    path = os.path.join(SAVE_DIR, f"{slot}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_game(slot="autosave"):
    path = os.path.join(SAVE_DIR, f"{slot}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saves():
    ensure_save_dir()
    return [f[:-5] for f in os.listdir(SAVE_DIR) if f.endswith(".json")]


class AutoSaver:
    def __init__(self, interval_sec, get_state_fn):
        self.interval_sec = interval_sec
        self.get_state_fn = get_state_fn
        self._last_save = time.time()

    def tick(self):
        now = time.time()
        if now - self._last_save >= self.interval_sec:
            player, extra = self.get_state_fn()
            save_game(player, extra, slot="autosave")
            self._last_save = now
            return True
        return False
