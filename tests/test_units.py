import os

from opendev.audit import AuditLog
from opendev.knowledge import Knowledge
from opendev.llm import parse_action
from opendev.policy import Policy
from opendev.packs.ap_invoices import expected, parse_invoice

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def policy():
    return Policy.load(os.path.join(ROOT, "company", "policy.yaml"), ROOT)


def test_url_policy(policy):
    assert policy.check_url("http://127.0.0.1:5055/invoices").allowed
    assert not policy.check_url("http://127.0.0.1:5055/api/state").allowed
    assert not policy.check_url("https://evil.example.com/").allowed
    assert not policy.check_url("file:///etc/passwd").allowed


def test_file_policy_blocks_traversal(policy):
    assert policy.check_read("tasks/inbox/x.txt").allowed
    assert not policy.check_read("../secrets.txt").allowed
    assert not policy.check_read("tasks/../../etc/passwd").allowed
    assert not policy.check_write("company/policy.yaml").allowed
    assert policy.check_write("workspace/notes.md").allowed


def test_click_guards(policy):
    over = "Amount: 4,800.00\nStatus: Entered"
    under = "Amount: 1,200.00"
    assert not policy.check_click("Approve invoice", over).allowed
    assert policy.check_click("Approve invoice", under).allowed
    assert policy.check_click("Submit for manager approval", over).allowed
    assert not policy.check_click("Approve invoice", "no amount here").allowed
    assert not policy.check_click("Delete vendor", "").allowed
    assert not policy.check_fill("bank_account").allowed


def test_audit_chain_detects_tampering(tmp_path):
    p = str(tmp_path / "a.jsonl")
    a = AuditLog(p)
    for i in range(4):
        a.write("step", i=i)
    assert AuditLog.verify(p)
    text = open(p).read().replace('"i": 2', '"i": 9')
    open(p, "w").write(text)
    assert not AuditLog.verify(p)


def test_knowledge_finds_the_right_sop():
    k = Knowledge(os.path.join(ROOT, "company", "sops"))
    top = k.search("invoice total above limit needs manager approval", 3)
    assert any("ap_invoice" in h["source"] and "Enter and route" in h["text"] for h in top)
    assert k.search("zzzz qqqq", 1) == []


def test_parse_action_handles_noise():
    assert parse_action('```json\n{"tool":"goto","args":{"url":"/x"}}\n```')["tool"] == "goto"
    assert parse_action('Sure! {"thought":"a {b}","tool":"read_page"} done')["args"] == {}
    for bad in ("no json", '{"tool":', '{"x":1}'):
        with pytest.raises(ValueError):
            parse_action(bad)


def test_expected_dispositions():
    db = {"vendors": [{"id": "V1", "name": "A", "status": "Active"}, {"id": "V2", "name": "B", "status": "Blocked"}],
          "purchase_orders": [{"number": "P1", "vendor_id": "V1", "total": 1000, "status": "Open"}],
          "invoices": [{"vendor_id": "V1", "invoice_no": "D"}]}
    mk = lambda **k: dict(dict(vendor="A", invoice_no="N", po="P1", amount=1000.0), **k)
    assert expected(mk(), db, 2500)[0] == "approved"
    assert expected(mk(amount=1019.0), db, 2500)[0] == "approved"
    assert expected(mk(amount=1021.0), db, 2500)[0] == "on_hold"
    assert expected(mk(invoice_no="D"), db, 2500)[0] == "duplicate"
    assert expected(mk(vendor="B"), db, 2500)[0] == "escalated"
    assert expected(mk(vendor="Z"), db, 2500)[0] == "escalated"
    assert expected(mk(po=""), db, 2500)[0] == "escalated"
    assert expected(mk(amount=3000.0), {**db, "purchase_orders": [{"number": "P1", "vendor_id": "V1", "total": 3000, "status": "Open"}]}, 2500)[0] == "pending_manager"


def test_parse_invoice():
    d = parse_invoice("From: Acme\nInvoice No: X1\nPO Number: P\nTotal: 1,200.50\n")
    assert d["amount"] == 1200.5 and d["po"] == "P"
