import json
import re


class ScriptedLLM:
    model = "scripted-test-double"

    def __init__(self, gen_factory):
        self.gen = gen_factory()
        self.started = False
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        obs = messages[-1]["content"]
        action = next(self.gen) if not self.started else self.gen.send(obs)
        self.started = True
        return json.dumps(action)


def el(obs, pattern):
    for m in re.finditer(r"^\[(\d+)\] (\S+) '([^']*)'", obs, re.M):
        if re.search(pattern, m.group(3)):
            return int(m.group(1))
    raise AssertionError(f"element {pattern!r} not in observation:\n{obs[:800]}")


def act(tool, **args):
    return {"thought": f"calling {tool}", "tool": tool, "args": args}
