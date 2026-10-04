from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    text: str
    blocked: bool = False
    evidence: list = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    args: dict
    fn: Callable[..., Any]

    def spec(self):
        a = ", ".join(f"{k}: {v}" for k, v in self.args.items())
        return f"- {self.name}({a}): {self.description}"
