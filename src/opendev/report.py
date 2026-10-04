import json
import os


def write_report(run_dir, task, res, human, audit_ok, model):
    rows = []
    for o in res.outcomes:
        rows.append(f"| {o.get('item', '')} | {o.get('disposition', '')} | {o.get('erp_id', '') or '-'} | {o.get('reason', '')} |")
    checks = "\n".join(f"- {c.line()}" for c in res.checks) or "- no verifier configured"
    passed = sum(1 for c in res.checks if c.passed)
    esc = "\n".join(f"- {e['question']}" + (f"  (answer: {e['answer']})" if e["answer"] else "  (pending)") for e in human.escalations) or "- none"
    shots = sorted(f for f in os.listdir(os.path.join(run_dir, "evidence")) if f.endswith(".png")) if os.path.isdir(os.path.join(run_dir, "evidence")) else []
    blocked = sum(1 for s in res.steps if s.blocked)
    md = f"""# Run report

Task: {task}

Model: {model}  |  Steps: {len(res.steps)}  |  Time: {res.seconds}s  |  Finished: {res.finished}  |  Policy blocks: {blocked}  |  Audit chain intact: {audit_ok}

{('Stop reason: ' + res.stop_reason) if res.stop_reason else ''}

## Outcomes

| Item | Disposition | ERP record | Reason |
|---|---|---|---|
{chr(10).join(rows)}

## Independent verification ({passed}/{len(res.checks)} checks passed)

{checks}

## Escalations

{esc}

## Evidence

{chr(10).join('- evidence/' + s for s in shots) or '- none'}

Operator summary: {res.summary}
"""
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"task": task, "model": model, "finished": res.finished, "stop_reason": res.stop_reason, "outcomes": res.outcomes,
                   "checks": [c.__dict__ for c in res.checks], "escalations": human.escalations, "steps": len(res.steps),
                   "seconds": res.seconds, "audit_chain_intact": audit_ok}, f, indent=2)
    return md
