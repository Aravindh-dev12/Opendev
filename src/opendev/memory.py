import json
import os
import time

from .knowledge import tokens


class Memory:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _all(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(x) for x in f if x.strip()]

    def add(self, note, tags=()):
        with open(self.path, "a") as f:
            f.write(json.dumps({"ts": time.time(), "note": note, "tags": list(tags)}) + "\n")

    def recall(self, query, k=5):
        q = set(tokens(query))
        scored = []
        for m in self._all():
            overlap = len(q & set(tokens(m["note"] + " " + " ".join(m["tags"]))))
            if overlap:
                scored.append((overlap, m["ts"], m["note"]))
        scored.sort(reverse=True)
        return [n for _, _, n in scored[:k]]
