import hashlib
import json
import os
import time


class AuditLog:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.prev = "0" * 64
        self.n = 0

    def write(self, kind, **data):
        self.n += 1
        rec = {"seq": self.n, "ts": round(time.time(), 3), "kind": kind, "data": data, "prev": self.prev}
        body = json.dumps(rec, sort_keys=True, default=str)
        rec["hash"] = hashlib.sha256(body.encode()).hexdigest()
        self.prev = rec["hash"]
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    @staticmethod
    def verify(path):
        prev = "0" * 64
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                h = rec.pop("hash")
                if rec["prev"] != prev:
                    return False
                body = json.dumps(rec, sort_keys=True, default=str)
                if hashlib.sha256(body.encode()).hexdigest() != h:
                    return False
                prev = h
        return True
