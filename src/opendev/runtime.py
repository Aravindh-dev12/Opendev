import os
import socket
import subprocess
import sys
import time
import urllib.request

from .agent import Agent
from .audit import AuditLog
from .human import Human
from .knowledge import Knowledge
from .memory import Memory
from .packs import ap_invoices
from .policy import Policy
from .report import write_report
from .tools.base import Tool, ToolResult
from .tools.browser import Browser
from .tools.files import Files

ROOT_MARKER = "company"


def find_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, ROOT_MARKER)) and os.path.isfile(os.path.join(d, "company", "policy.yaml")):
            return d
        p = os.path.dirname(d)
        if p == d:
            raise SystemExit("run opendev from the project folder (it needs company/policy.yaml)")
        d = p


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ErpServer:
    def __init__(self, root, port=None, state_path=None):
        self.root = root
        self.port = port or free_port()
        self.state_path = state_path
        self.proc = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        env = dict(os.environ, ERP_PORT=str(self.port))
        if self.state_path:
            env["ERP_STATE"] = self.state_path
        self.proc = subprocess.Popen([sys.executable, os.path.join(self.root, "erp", "app.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen(self.url + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("ERP did not start")
        req = urllib.request.Request(self.url + "/api/reset", method="POST")
        urllib.request.urlopen(req, timeout=5)

    def stop(self):
        if self.proc:
            self.proc.terminate()


def build_tools(browser, files, knowledge, memory, human, plan_sink):
    def plan(steps):
        plan_sink.append(steps)
        return ToolResult(True, "plan recorded")

    def sop_search(query):
        hits = knowledge.search(query, k=3)
        return ToolResult(True, "\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits) or "no matching procedure")

    def remember(note):
        memory.add(note)
        return ToolResult(True, "saved to company memory")

    def ask_human(question, context=""):
        return ToolResult(True, human.ask(question, context))

    return [
        Tool("plan", "record your plan before acting", {"steps": "list of strings"}, plan),
        Tool("sop_search", "search company procedures", {"query": "string"}, sop_search),
        Tool("list_files", "list a folder", {"path": "string"}, files.list_files),
        Tool("read_file", "read a text or pdf file", {"path": "string"}, files.read_file),
        Tool("write_file", "write a note or export into the workspace folder", {"path": "string", "content": "string"}, files.write_file),
        Tool("goto", "open a URL or a path like /invoices in the ERP browser", {"url": "string"}, browser.goto),
        Tool("read_page", "re-read the current page and its numbered elements", {}, browser.read),
        Tool("click", "click an element by number", {"element": "number"}, browser.click),
        Tool("fill", "type text into an input by number", {"element": "number", "text": "string"}, browser.fill),
        Tool("select_option", "choose an option in a dropdown by number", {"element": "number", "option": "visible text"}, browser.select_option),
        Tool("remember", "store a durable lesson for future runs", {"note": "string"}, remember),
        Tool("ask_human", "escalate a specific question to a person", {"question": "string", "context": "string"}, ask_human),
        Tool("finish", "end the run with the final outcomes", {"summary": "string", "outcomes": "list of objects"}, lambda **k: ToolResult(True, "")),
    ]


def run_task(root, llm, task, pack="ap_invoices", headless=True, human_mode="batch", answers=None, on_step=None, erp_url=None, run_name=None, record_video=False):
    from .llm import LLMError
    stamp = run_name or time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(root, "runs", stamp)
    os.makedirs(os.path.join(run_dir, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(root, "workspace"), exist_ok=True)
    policy = Policy.load(os.path.join(root, "company", "policy.yaml"), root)
    audit = AuditLog(os.path.join(run_dir, "audit.jsonl"))
    knowledge = Knowledge(os.path.join(root, "company", "sops"))
    memory = Memory(os.path.join(root, "workspace", "memory.jsonl"))
    human = Human(human_mode, answers)
    server = None
    if erp_url is None:
        server = ErpServer(root)
        server.start()
        erp_url = server.url
    browser = Browser(policy, os.path.join(run_dir, "evidence"), erp_url, headless=headless, record_video=record_video)
    try:
        browser.start()
        before = ap_invoices.erp_state(erp_url)
        verifier = ap_invoices.APVerifier(root, "tasks/inbox", erp_url, policy, before)
        files = Files(policy, root)
        tools = build_tools(browser, files, knowledge, memory, human, [])
        agent = Agent(llm, tools, policy, audit, knowledge, memory, human, verifier=verifier, on_step=on_step)
        res = agent.run(task + f"\n\n(ERP address: {erp_url})")
        ok = AuditLog.verify(os.path.join(run_dir, "audit.jsonl"))
        write_report(run_dir, task, res, human, ok, getattr(llm, "model", "?"))
        return res, run_dir
    finally:
        browser.close()
        if server:
            server.stop()
