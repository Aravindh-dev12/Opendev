import json
import os

from opendev.audit import AuditLog
from opendev.runtime import run_task

from scripted import ScriptedLLM, act, el

TASK = "Process all supplier invoices in the tasks/inbox folder following our AP procedure."


def enter_invoice(vendor, no, po, amount, date, button):
    obs = yield act("goto", url="/invoices/new")
    yield act("select_option", element=el(obs, "^Vendor$"), option=vendor)
    yield act("fill", element=el(obs, "^Invoice number$"), text=no)
    yield act("fill", element=el(obs, "^PO number$"), text=po)
    yield act("fill", element=el(obs, "^Amount$"), text=amount)
    yield act("fill", element=el(obs, "^Invoice date$"), text=date)
    obs = yield act("click", element=el(obs, "Save invoice"))
    return obs


def good_agent():
    yield act("plan", steps=["read sop", "list inbox", "process each"])
    yield act("sop_search", query="invoice approval limit")
    yield act("list_files", path="tasks/inbox")

    obs = yield from enter_invoice("Acme Paper Co", "AC-1042", "PO-5001", "1200.00", "2026-10-01", "approve")
    page = obs
    yield act("fill", element=el(page, "^Comment$"), text="Auto approved per AP SOP")
    obs = yield act("click", element=el(page, "^Approve invoice$"))

    obs = yield from enter_invoice("Globex Industrial", "GX-8830", "PO-5002", "4800.00", "2026-10-01", "manager")
    page = obs
    yield act("fill", element=el(page, "^Comment$"), text="Over 2,500 limit, routed to manager")
    obs = yield act("click", element=el(page, "Submit for manager approval"))

    obs = yield from enter_invoice("Initech Supplies", "IN-311", "PO-5003", "980.00", "2026-10-02", "hold")
    page = obs
    yield act("fill", element=el(page, "^Comment$"), text="PO total 800.00 vs invoice 980.00, difference 180.00, buyer to confirm")
    obs = yield act("click", element=el(page, "Put on hold"))

    yield act("ask_human", question="Hooli Supplies is not in the vendor master. Procurement, please advise.", context="invoice_hooli_77.txt")
    yield act("finish", summary="Processed six invoices", outcomes=[
        {"item": "invoice_acme_1042.txt", "disposition": "approved", "reason": "1,200.00 matches PO-5001, under 2,500.00", "erp_id": "INV-0002"},
        {"item": "invoice_globex_8830.txt", "disposition": "pending_manager", "reason": "4,800.00 matches PO but is over the 2,500.00 limit", "erp_id": "INV-0003"},
        {"item": "invoice_initech_311.txt", "disposition": "on_hold", "reason": "980.00 vs PO 800.00", "erp_id": "INV-0004"},
        {"item": "invoice_acme_dup.txt", "disposition": "duplicate", "reason": "AP-7781 already entered as INV-0001", "escalated_to": "requester"},
        {"item": "invoice_hooli_77.txt", "disposition": "escalated", "reason": "vendor not in master", "escalated_to": "Procurement"},
        {"item": "invoice_umbrella_5.txt", "disposition": "escalated", "reason": "vendor blocked and no PO number", "escalated_to": "Procurement"},
    ])


def test_full_run_completes_and_verifies(project):
    res, run_dir = run_task(project, ScriptedLLM(good_agent), TASK, run_name="t1")
    assert res.finished, res.stop_reason
    failed = [c.line() for c in res.checks if not c.passed]
    assert not failed, failed
    assert AuditLog.verify(os.path.join(run_dir, "audit.jsonl"))
    shots = os.listdir(os.path.join(run_dir, "evidence"))
    assert len([s for s in shots if s.endswith(".png")]) >= 4
    report = json.load(open(os.path.join(run_dir, "report.json")))
    assert report["finished"] and len(report["outcomes"]) == 6
    assert open(os.path.join(run_dir, "report.md")).read().count("PASS") == len(res.checks)


def adversarial_agent():
    obs = yield act("goto", url="/api/state")
    obs = yield act("goto", url="https://example.com/")
    obs = yield act("read_file", path="../../etc/passwd")
    obs = yield from enter_invoice("Globex Industrial", "GX-8830", "PO-5002", "4800.00", "2026-10-01", "approve")
    obs = yield act("goto", url="/invoices/INV-0002")
    obs = yield act("click", element=el(obs, "^Approve invoice$"))
    final = act("finish", summary="done", outcomes=[{"item": "invoice_globex_8830.txt", "disposition": "approved", "reason": "looked fine"}])
    obs = yield final
    assert "INDEPENDENT VERIFICATION FAILED" in obs
    yield final


def test_policy_blocks_every_unsafe_move_and_verifier_catches_bad_report(project):
    llm = ScriptedLLM(adversarial_agent)
    steps = []
    res, run_dir = run_task(project, llm, TASK, run_name="t2", on_step=steps.append)
    blocked = [s for s in steps if s.blocked]
    assert len(blocked) == 4, [(s.tool, s.observation[:60]) for s in steps]
    assert any("approval_limit" in s.observation or "manager approval" in s.observation for s in blocked)
    failed = [c for c in res.checks if not c.passed]
    assert failed
    assert any("disposition" in c.name for c in failed)
    assert not any("self approved" in c.name for c in failed)
    kinds = [json.loads(line)["kind"] for line in open(os.path.join(run_dir, "audit.jsonl"))]
    assert kinds.count("policy_block") == 4
