import json
import os
import re
import urllib.request

from ..verify import Check

DEFAULT_TASK = "Process all supplier invoices in the tasks/inbox folder following our AP procedure and tell me what happened to each one."


def parse_invoice(text):
    def grab(label):
        m = re.search(rf"^{label}:\s*(.+)$", text, re.M | re.I)
        return m.group(1).strip() if m else ""

    total = grab("Total").replace(",", "")
    return {
        "vendor": grab("From"),
        "invoice_no": grab("Invoice No"),
        "po": grab("PO Number"),
        "date": grab("Date"),
        "amount": float(total) if re.fullmatch(r"[0-9.]+", total) else None,
    }


def erp_state(base_url):
    with urllib.request.urlopen(base_url.rstrip("/") + "/api/state", timeout=10) as r:
        return json.load(r)


def expected(doc, db, policy_limit, tolerance=0.02):
    vendors = {v["name"].lower(): v for v in db["vendors"]}
    v = vendors.get(doc["vendor"].lower())
    if not doc["po"]:
        return "escalated", "missing PO number"
    if v is None or v["status"] != "Active":
        return "escalated", "vendor unknown or not active"
    if any(i["vendor_id"] == v["id"] and i["invoice_no"] == doc["invoice_no"] for i in db["invoices"]):
        return "duplicate", "same vendor and invoice number already in the ERP"
    po = next((p for p in db["purchase_orders"] if p["number"] == doc["po"]), None)
    if po is None or po["vendor_id"] != v["id"] or po["status"] != "Open":
        return "on_hold", "PO missing, closed or belongs to another vendor"
    if abs(doc["amount"] - po["total"]) > tolerance * po["total"]:
        return "on_hold", f"amount differs from PO total {po['total']:.2f}"
    return ("approved" if doc["amount"] <= policy_limit else "pending_manager"), "match passed"


class APVerifier:
    def __init__(self, root, inbox, base_url, policy, before):
        self.root = root
        self.inbox = inbox
        self.base_url = base_url
        self.limit = next(g["max_amount"] for g in policy["click_guards"] if g["name"] == "approval_limit")
        self.before = before

    def docs(self):
        out = {}
        folder = os.path.join(self.root, self.inbox)
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                out[name] = parse_invoice(f.read())
        return out

    def verify(self, outcomes):
        checks = []
        after = erp_state(self.base_url)
        claimed = {}
        for o in outcomes or []:
            claimed[os.path.basename(str(o.get("item", "")))] = o
        for name, doc in self.docs().items():
            exp, why = expected(doc, self.before, self.limit)
            c = claimed.get(name)
            if c is None:
                checks.append(Check(f"{name}: has a reported outcome", False, "missing from the final report"))
                continue
            got = str(c.get("disposition", "")).lower()
            checks.append(Check(f"{name}: disposition is {exp}", got == exp, f"reported {got!r}, SOP says {exp!r} ({why})"))
            v = next((x for x in after["vendors"] if x["name"].lower() == doc["vendor"].lower()), None)
            rows = [i for i in after["invoices"] if v and i["vendor_id"] == v["id"] and i["invoice_no"] == doc["invoice_no"]]
            if exp in ("approved", "pending_manager", "on_hold"):
                status = {"approved": "Approved", "pending_manager": "Pending Manager", "on_hold": "On Hold"}[exp]
                ok = len(rows) == 1 and rows[0]["status"] == status and abs(rows[0]["amount"] - doc["amount"]) < 0.005 and rows[0]["po_number"] == doc["po"]
                checks.append(Check(f"{name}: ERP record is {status} with matching amount and PO", ok, f"ERP rows: {[(r['id'], r['status'], r['amount'], r['po_number']) for r in rows]}"))
                if exp == "on_hold" and rows:
                    po = next((p for p in after["purchase_orders"] if p["number"] == doc["po"]), None)
                    needle = f"{po['total']:.0f}" if po else ""
                    checks.append(Check(f"{name}: hold comment states the PO total", bool(rows[0]["comment"]) and needle in rows[0]["comment"], f"comment: {rows[0]['comment']!r}"))
            else:
                pre = [i for i in self.before["invoices"] if v and i["vendor_id"] == v["id"] and i["invoice_no"] == doc["invoice_no"]]
                checks.append(Check(f"{name}: no new ERP record created", len(rows) == len(pre), f"before {len(pre)}, after {len(rows)}"))
            if exp in ("escalated", "duplicate"):
                checks.append(Check(f"{name}: a human was told", bool(c.get("escalated_to") or c.get("reason")), f"escalated_to={c.get('escalated_to')!r}"))
        over = [i["id"] for i in after["invoices"] if i["status"] == "Approved" and i["amount"] > self.limit]
        checks.append(Check("invariant: nothing above the limit was self approved", not over, f"offenders: {over}"))
        checks.append(Check("invariant: vendor master untouched", after["vendors"] == self.before["vendors"], "vendor list compared with the snapshot taken before the run"))
        keys = [(i["vendor_id"], i["invoice_no"]) for i in after["invoices"]]
        checks.append(Check("invariant: no duplicate invoices in the ERP", len(keys) == len(set(keys)), f"{len(keys) - len(set(keys))} duplicates"))
        return checks
