import json
import time
from dataclasses import dataclass, field

from .llm import LLMError, parse_action

SYSTEM = """You are openDev, an autonomous operations employee at {company}. You complete company tasks end to end by operating a web browser, reading files, and following company procedures. You are judged on whether the real outcome is correct and provable, not on how fluent your answer is.

Reply with exactly one JSON object per turn and nothing else:
{{"thought": "short reasoning", "tool": "<tool name>", "args": {{...}}}}

Tools:
{tools}

Working rules:
1. Start with plan(steps). Read the relevant SOP before acting. Procedures decide what is allowed, not your own guess.
2. The browser tools return the page text and numbered elements. Always use element numbers from the latest observation. Numbers change after every page load.
3. Check facts in the real system before you act. Never assume a vendor, PO or amount.
4. If a tool says BLOCKED by policy, do not try to work around it. Follow the SOP route instead or ask a human.
5. An escalation never stops the rest of the batch. Continue with the remaining items.
6. Finish only when every item has a disposition. Call finish with outcomes: a list of objects {{"item": "<file name>", "disposition": "approved|pending_manager|on_hold|duplicate|escalated", "reason": "<one line with the concrete numbers>", "erp_id": "<id or empty>", "escalated_to": "<team or empty>"}}.
7. Your claims are independently verified against the system of record. Do not claim anything you did not do and see.

Company memory from earlier runs:
{memory}
"""


@dataclass
class Step:
    n: int
    thought: str
    tool: str
    args: dict
    ok: bool
    blocked: bool
    observation: str


@dataclass
class RunResult:
    finished: bool
    outcomes: list = field(default_factory=list)
    summary: str = ""
    steps: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    stop_reason: str = ""
    seconds: float = 0.0


class Agent:
    def __init__(self, llm, tools, policy, audit, knowledge, memory, human, verifier=None, max_steps=None, on_step=None):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.policy = policy
        self.audit = audit
        self.knowledge = knowledge
        self.memory = memory
        self.human = human
        self.verifier = verifier
        self.max_steps = max_steps or policy.get("max_steps", 40)
        self.max_repeat = policy.get("max_repeat_action", 3)
        self.on_step = on_step or (lambda s: None)

    def _system(self, task):
        mem = self.memory.recall(task)
        return SYSTEM.format(company=self.policy.get("company", "the company"), tools="\n".join(t.spec() for t in self.tools.values()),
                             memory="\n".join(f"- {m}" for m in mem) or "(none)")

    def _first_user(self, task):
        hits = self.knowledge.search(task, k=4)
        ctx = "\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
        return f"TASK FROM USER:\n{task}\n\nMOST RELEVANT COMPANY PROCEDURES (auto retrieved, call sop_search for more):\n{ctx}"

    def _messages(self, task, history, nudge=None):
        msgs = [{"role": "system", "content": self._system(task)}, {"role": "user", "content": self._first_user(task)}]
        recent = 6
        for i, s in enumerate(history):
            full = i >= len(history) - recent
            msgs.append({"role": "assistant", "content": json.dumps({"thought": s.thought, "tool": s.tool, "args": s.args})})
            obs = s.observation if full else s.observation[:160].replace("\n", " ") + (" ..." if len(s.observation) > 160 else "")
            msgs.append({"role": "user", "content": f"OBSERVATION (step {s.n}, {'ok' if s.ok else 'FAILED'}):\n{obs}"})
        if nudge:
            msgs.append({"role": "user", "content": nudge})
        return msgs

    def run(self, task):
        t0 = time.time()
        res = RunResult(finished=False)
        history = []
        nudge = None
        bad_json = 0
        recent_calls = []
        verify_rounds = 0
        self.audit.write("run_start", task=task, model=getattr(self.llm, "model", "?"))
        for n in range(1, self.max_steps + 1):
            try:
                raw = self.llm.chat(self._messages(task, history, nudge))
            except LLMError as e:
                res.stop_reason = f"model unreachable: {e}"
                self.audit.write("run_abort", reason=res.stop_reason)
                break
            nudge = None
            try:
                act = parse_action(raw)
                bad_json = 0
            except ValueError as e:
                bad_json += 1
                self.audit.write("bad_model_output", n=n, error=str(e), raw=raw[:400])
                if bad_json >= 4:
                    res.stop_reason = "model kept returning invalid JSON"
                    break
                nudge = f"Your last reply was not valid. {e}. Reply with one JSON object: {{\"thought\":..., \"tool\":..., \"args\":{{...}}}}"
                continue
            tool_name, args = act["tool"], act["args"]
            thought = str(act.get("thought", ""))[:300]
            sig = json.dumps([tool_name, args], sort_keys=True)
            recent_calls.append(sig)
            if recent_calls[-self.max_repeat:].count(sig) >= self.max_repeat and len(recent_calls) >= self.max_repeat:
                obs, ok, blocked = f"LOOP GUARD: you repeated {tool_name} with the same arguments {self.max_repeat} times. Change approach, or call ask_human or finish.", False, False
                recent_calls.clear()
            elif tool_name == "finish":
                outcomes = args.get("outcomes", [])
                if self.verifier is not None:
                    checks = self.verifier.verify(outcomes)
                    failed = [c for c in checks if not c.passed]
                    self.audit.write("verification", round=verify_rounds, failed=[c.name for c in failed], total=len(checks))
                    if failed and verify_rounds < 1:
                        verify_rounds += 1
                        obs = "INDEPENDENT VERIFICATION FAILED against the system of record. Fix the real state if it is wrong, or correct your report if the claim was wrong. Then call finish again.\n" + "\n".join(c.line() for c in failed)
                        step = Step(n, thought, tool_name, args, False, False, obs)
                        history.append(step)
                        self.on_step(step)
                        self.audit.write("step", n=n, tool=tool_name, args=args, ok=False, blocked=False, observation=obs[:600])
                        continue
                    res.checks = checks
                res.finished, res.outcomes, res.summary = True, outcomes, str(args.get("summary", ""))
                step = Step(n, thought, tool_name, args, True, False, "run finished")
                history.append(step)
                self.on_step(step)
                self.audit.write("step", n=n, tool=tool_name, args=args, ok=True, blocked=False, observation="finished")
                break
            elif tool_name not in self.tools:
                obs, ok, blocked = f"unknown tool {tool_name!r}. Available: {', '.join(self.tools)}", False, False
            else:
                try:
                    r = self.tools[tool_name].fn(**args)
                    obs, ok, blocked = r.text, r.ok, r.blocked
                    for e in r.evidence:
                        self.audit.write("evidence", n=n, path=e)
                except TypeError as e:
                    obs, ok, blocked = f"bad arguments for {tool_name}: {e}", False, False
                except Exception as e:
                    obs, ok, blocked = f"{tool_name} crashed: {type(e).__name__}: {str(e)[:200]}", False, False
            if blocked:
                self.audit.write("policy_block", n=n, tool=tool_name, args=args, reason=obs)
            step = Step(n, thought, tool_name, args, ok, blocked, obs)
            history.append(step)
            self.on_step(step)
            self.audit.write("step", n=n, tool=tool_name, args=args, ok=ok, blocked=blocked, observation=obs[:600])
        else:
            res.stop_reason = f"step budget of {self.max_steps} exhausted"
        if not res.finished and not res.stop_reason:
            res.stop_reason = "stopped"
        if not res.finished and self.verifier is not None:
            res.checks = self.verifier.verify(res.outcomes)
        res.steps = history
        res.seconds = round(time.time() - t0, 1)
        self.audit.write("run_end", finished=res.finished, stop_reason=res.stop_reason, steps=len(history))
        return res
