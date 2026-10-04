import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from opendev.runtime import run_task
from test_e2e import TASK, adversarial_agent, good_agent
from scripted import ScriptedLLM

name = sys.argv[1] if len(sys.argv) > 1 else "replay"
which = adversarial_agent if name == "guardrails" else good_agent
res, run_dir = run_task(ROOT, ScriptedLLM(which), TASK, run_name=name, record_video=True)
print(res.finished, sum(c.passed for c in res.checks), len(res.checks))
print(run_dir)
