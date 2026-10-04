import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import yaml


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


class Policy:
    def __init__(self, data, root):
        self.data = data
        self.root = os.path.realpath(root)

    @classmethod
    def load(cls, path, root):
        with open(path) as f:
            return cls(yaml.safe_load(f), root)

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    def check_url(self, url):
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            return Decision(False, f"scheme {u.scheme!r} is not allowed")
        if u.hostname not in self.data["allowed_hosts"]:
            return Decision(False, f"host {u.hostname!r} is not in the allowed list")
        target = u.path + ("?" + u.query if u.query else "")
        for pat in self.data["deny_url_patterns"]:
            if re.search(pat, target):
                return Decision(False, f"path {u.path!r} is reserved for administrators and systems")
        return Decision(True)

    def _inside(self, path, roots):
        real = os.path.realpath(os.path.join(self.root, path))
        for r in roots:
            base = os.path.realpath(os.path.join(self.root, r))
            if real == base or real.startswith(base + os.sep):
                return True
        return False

    def check_read(self, path):
        if self._inside(path, self.data["file_read_roots"] + self.data["file_write_roots"]):
            return Decision(True)
        return Decision(False, f"{path!r} is outside the readable folders {self.data['file_read_roots']}")

    def check_write(self, path):
        if self._inside(path, self.data["file_write_roots"]):
            return Decision(True)
        return Decision(False, f"{path!r} is outside the writable folders {self.data['file_write_roots']}")

    def check_click(self, label, page_text):
        for g in self.data.get("click_guards", []):
            if not re.search(g["click_text"], label.strip()):
                continue
            if g.get("always_deny"):
                return Decision(False, g["reason"])
            m = re.search(g["page_regex"], page_text or "")
            if not m:
                return Decision(False, f"{g['name']}: cannot read the amount on the page, refusing to act")
            amount = float(m.group(1).replace(",", ""))
            if amount > g["max_amount"]:
                return Decision(False, g["reason"] + f" (amount {amount:,.2f}, limit {g['max_amount']:,.2f})")
        return Decision(True)

    def check_fill(self, field_name):
        for g in self.data.get("fill_guards", []):
            if re.search(g["field_regex"], field_name or ""):
                return Decision(False, g["reason"])
        return Decision(True)
