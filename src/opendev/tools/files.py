import os

from .base import ToolResult


class Files:
    def __init__(self, policy, root):
        self.policy = policy
        self.root = root

    def _p(self, path):
        return os.path.join(self.root, path)

    def list_files(self, path="."):
        d = self.policy.check_read(path)
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        full = self._p(path)
        if not os.path.isdir(full):
            return ToolResult(False, f"{path!r} is not a folder")
        names = sorted(os.listdir(full))
        return ToolResult(True, "\n".join(names) if names else "(empty)")

    def read_file(self, path):
        d = self.policy.check_read(path)
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        full = self._p(path)
        if not os.path.isfile(full):
            return ToolResult(False, f"no such file: {path!r}")
        if full.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                text = "\n".join(p.extract_text() or "" for p in PdfReader(full).pages)
            except ImportError:
                return ToolResult(False, "PDF support needs: pip install pypdf")
        else:
            with open(full, encoding="utf-8", errors="replace") as f:
                text = f.read()
        return ToolResult(True, text[:6000])

    def write_file(self, path, content):
        d = self.policy.check_write(path)
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        full = self._p(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(str(content))
        return ToolResult(True, f"wrote {len(str(content))} characters to {path}", evidence=[full])
