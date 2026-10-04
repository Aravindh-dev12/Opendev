import json
import os
import threading
from datetime import date
from flask import Flask, redirect, render_template_string, request, url_for, jsonify, abort

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "seed.json")
LOCK = threading.Lock()

BASE = """
<!doctype html><html><head><meta charset="utf-8"><title>{{ title }} | Northwind ERP</title>
<style>body{font-family:system-ui;margin:0}nav{background:#12263f;padding:10px 20px}nav a{color:#fff;margin-right:18px;text-decoration:none}
main{padding:20px 28px;max-width:900px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:6px 10px;text-align:left}
label{display:block;margin:10px 0 2px}button{padding:6px 12px;margin:6px 6px 0 0}.flash{background:#e8f6e8;padding:8px;margin-bottom:12px}</style></head>
<body><nav><a href="/">Home</a><a href="/vendors">Vendors</a><a href="/purchase-orders">Purchase orders</a><a href="/invoices">Invoices</a><a href="/invoices/new">New invoice</a></nav>
<main>{% if msg %}<div class="flash">{{ msg }}</div>{% endif %}<h1>{{ title }}</h1>{% block body %}{% endblock %}</main></body></html>
"""


def create_app(state_path=None):
    app = Flask(__name__)
    path = state_path or os.environ.get("ERP_STATE", os.path.join(HERE, "state.json"))

    def load():
        if not os.path.exists(path):
            with open(SEED) as f, open(path, "w") as g:
                g.write(f.read())
        with open(path) as f:
            return json.load(f)

    def save(db):
        with open(path, "w") as f:
            json.dump(db, f, indent=2)

    def page(title, body, **ctx):
        tpl = BASE.replace("{% block body %}{% endblock %}", body)
        return render_template_string(tpl, title=title, msg=request.args.get("msg"), **ctx)

    def money(v):
        return f"{float(v):,.2f}"

    app.jinja_env.filters["money"] = money

    @app.get("/")
    def home():
        db = load()
        counts = {}
        for i in db["invoices"]:
            counts[i["status"]] = counts.get(i["status"], 0) + 1
        return page("Accounts Payable", "<p>Invoices by status:</p><ul>{% for k,v in counts.items() %}<li>{{k}}: {{v}}</li>{% endfor %}</ul>", counts=counts)

    @app.get("/vendors")
    def vendors():
        db = load()
        body = "<table><tr><th>ID</th><th>Name</th><th>Status</th></tr>{% for v in vs %}<tr><td>{{v.id}}</td><td>{{v.name}}</td><td>Status: {{v.status}}</td></tr>{% endfor %}</table>"
        return page("Vendors", body, vs=db["vendors"])

    @app.get("/purchase-orders")
    def pos():
        db = load()
        body = "<table><tr><th>PO</th><th>Vendor</th><th>Total</th><th>Status</th></tr>{% for p in ps %}<tr><td><a href='/purchase-orders/{{p.number}}'>{{p.number}}</a></td><td>{{p.vendor_id}}</td><td>{{p.total|money}}</td><td>{{p.status}}</td></tr>{% endfor %}</table>"
        return page("Purchase orders", body, ps=db["purchase_orders"])

    @app.get("/purchase-orders/<number>")
    def po(number):
        db = load()
        p = next((x for x in db["purchase_orders"] if x["number"] == number), None)
        if not p:
            abort(404)
        v = next((x for x in db["vendors"] if x["id"] == p["vendor_id"]), {"name": "?"})
        body = "<p>Vendor: {{v.name}} ({{p.vendor_id}})</p><p>PO total: {{p.total|money}}</p><p>PO status: {{p.status}}</p>"
        return page("Purchase order " + number, body, p=p, v=v)

    @app.get("/invoices")
    def invoices():
        db = load()
        vn = {v["id"]: v["name"] for v in db["vendors"]}
        body = ("<table><tr><th>ID</th><th>Vendor</th><th>Invoice no</th><th>PO</th><th>Amount</th><th>Status</th></tr>"
                "{% for i in ins %}<tr><td><a href='/invoices/{{i.id}}'>{{i.id}}</a></td><td>{{vn[i.vendor_id]}}</td><td>{{i.invoice_no}}</td><td>{{i.po_number}}</td><td>{{i.amount|money}}</td><td>{{i.status}}</td></tr>{% endfor %}</table>")
        return page("Invoices", body, ins=db["invoices"], vn=vn)

    @app.get("/invoices/new")
    def invoice_form():
        db = load()
        body = """<form method="post" action="/invoices/new">
<label for="vendor_id">Vendor</label><select id="vendor_id" name="vendor_id"><option value="">choose</option>{% for v in vs %}<option value="{{v.id}}">{{v.name}}</option>{% endfor %}</select>
<label for="invoice_no">Invoice number</label><input id="invoice_no" name="invoice_no">
<label for="po_number">PO number</label><input id="po_number" name="po_number">
<label for="amount">Amount</label><input id="amount" name="amount">
<label for="date">Invoice date</label><input id="date" name="date" placeholder="YYYY-MM-DD">
<button type="submit">Save invoice</button></form>"""
        return page("New invoice", body, vs=db["vendors"])

    @app.post("/invoices/new")
    def invoice_create():
        with LOCK:
            db = load()
            f = request.form
            try:
                amount = float(f["amount"].replace(",", ""))
            except Exception:
                return redirect(url_for("invoice_form", msg="Amount is not a number"))
            if not f.get("vendor_id") or not f.get("invoice_no"):
                return redirect(url_for("invoice_form", msg="Vendor and invoice number are required"))
            nid = f"INV-{len(db['invoices']) + 1:04d}"
            db["invoices"].append({"id": nid, "vendor_id": f["vendor_id"], "invoice_no": f["invoice_no"], "po_number": f.get("po_number", ""),
                                   "amount": amount, "date": f.get("date") or str(date.today()), "status": "Entered", "comment": ""})
            save(db)
        return redirect(url_for("invoice_detail", inv_id=nid, msg="Invoice saved"))

    @app.get("/invoices/<inv_id>")
    def invoice_detail(inv_id):
        db = load()
        i = next((x for x in db["invoices"] if x["id"] == inv_id), None)
        if not i:
            abort(404)
        v = next((x for x in db["vendors"] if x["id"] == i["vendor_id"]), {"name": "?"})
        body = """<p>Vendor: {{v.name}}</p><p>Invoice number: {{i.invoice_no}}</p><p>PO number: {{i.po_number}}</p>
<p>Amount: {{i.amount|money}}</p><p>Invoice date: {{i.date}}</p><p>Status: {{i.status}}</p><p>Comment: {{i.comment}}</p>
{% if i.status == 'Entered' %}<form method="post" action="/invoices/{{i.id}}/act"><label for="comment">Comment</label><textarea id="comment" name="comment"></textarea>
<button name="action" value="approve">Approve invoice</button><button name="action" value="manager">Submit for manager approval</button><button name="action" value="hold">Put on hold</button></form>{% endif %}"""
        return page("Invoice " + inv_id, body, i=i, v=v)

    @app.post("/invoices/<inv_id>/act")
    def invoice_act(inv_id):
        with LOCK:
            db = load()
            i = next((x for x in db["invoices"] if x["id"] == inv_id), None)
            if not i:
                abort(404)
            a = request.form.get("action")
            status = {"approve": "Approved", "manager": "Pending Manager", "hold": "On Hold"}.get(a)
            if not status:
                abort(400)
            i["status"] = status
            i["comment"] = request.form.get("comment", "")
            save(db)
        return redirect(url_for("invoice_detail", inv_id=inv_id, msg="Invoice updated"))

    @app.get("/api/state")
    def api_state():
        return jsonify(load())

    @app.post("/api/reset")
    def api_reset():
        with open(SEED) as f:
            data = json.load(f)
        save(data)
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    port = int(os.environ.get("ERP_PORT", "5055"))
    create_app().run(host="127.0.0.1", port=port, debug=False)
