import json
import re

import httpx


class LLMError(RuntimeError):
    pass


THINK = re.compile(r"<think>.*?</think>", re.S)


class LocalLLM:
    def __init__(self, base_url="http://localhost:11434/v1", model="qwen3.5", temperature=0.2, timeout=300.0, api_key="local", num_ctx=16384):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.api_key = api_key
        self.num_ctx = num_ctx

    def chat(self, messages):
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
            "response_format": {"type": "json_object"},
            "options": {"num_ctx": self.num_ctx},
        }
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"cannot reach the model at {self.base_url}: {e}") from e
        text = r.json()["choices"][0]["message"].get("content") or ""
        return THINK.sub("", text).strip()

    def models(self):
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=10, headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        except httpx.HTTPError as e:
            raise LLMError(str(e)) from e


def parse_action(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = json.loads(text[start:i + 1])
                if not isinstance(obj, dict) or "tool" not in obj:
                    raise ValueError("JSON has no 'tool' field")
                obj.setdefault("args", {})
                if not isinstance(obj["args"], dict):
                    raise ValueError("'args' must be an object")
                return obj
    raise ValueError("unterminated JSON object")
