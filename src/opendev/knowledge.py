import math
import os
import re
from collections import Counter


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class Knowledge:
    def __init__(self, folder):
        self.chunks = []
        for dirpath, _, files in os.walk(folder):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                p = os.path.join(dirpath, name)
                with open(p, encoding="utf-8") as f:
                    text = f.read()
                first = text.strip().splitlines()[0].lstrip("# ").strip() if text.strip() else name
                parts = re.split(r"\n(?=#{1,3} )", text)
                for part in parts:
                    part = part.strip()
                    if part:
                        self.chunks.append({"source": os.path.relpath(p, folder), "text": part, "tf": Counter(tokens(first + " " + part))})
        self.n = len(self.chunks)
        self.avg = sum(sum(c["tf"].values()) for c in self.chunks) / max(self.n, 1)
        self.df = Counter()
        for c in self.chunks:
            for t in c["tf"]:
                self.df[t] += 1

    def search(self, query, k=3):
        q = tokens(query)
        scored = []
        for c in self.chunks:
            dl = sum(c["tf"].values())
            s = 0.0
            for t in q:
                if t not in c["tf"]:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                f = c["tf"][t]
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * dl / self.avg))
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        return [{"source": c["source"], "text": c["text"], "score": round(s, 2)} for s, c in scored[:k]]

    def full(self, source):
        return "\n\n".join(c["text"] for c in self.chunks if c["source"] == source)
