import argparse
import os
import sys

from rich.console import Console

from .llm import LLMError, LocalLLM
from .packs.ap_invoices import DEFAULT_TASK
from .runtime import ErpServer, find_root, run_task

console = Console()


def llm_from(args):
    return LocalLLM(base_url=args.base_url, model=args.model, temperature=args.temperature)


def cmd_doctor(args):
    llm = llm_from(args)
    try:
        names = llm.models()
    except LLMError as e:
        console.print(f"[red]model server not reachable[/red] at {args.base_url}: {e}")
        console.print("start it with: ollama serve   (then: ollama list)")
        return 1
    console.print(f"server ok at {args.base_url}; models: {', '.join(names) or '(none)'}")
    if args.model not in names:
        console.print(f"[yellow]model {args.model!r} not listed. Pass --model with one of the names above.[/yellow]")
        return 1
    try:
        out = llm.chat([{"role": "user", "content": 'Reply with the JSON {"tool": "ping"} and nothing else.'}])
        console.print(f"test reply: {out[:120]}")
    except LLMError as e:
        console.print(f"[red]chat failed[/red]: {e}")
        return 1
    return 0


def cmd_run(args):
    root = find_root()
    llm = llm_from(args)

    def show(s):
        tag = "[red]BLOCKED[/red]" if s.blocked else ("[green]ok[/green]" if s.ok else "[yellow]failed[/yellow]")
        console.print(f"[bold]{s.n:>2}[/bold] {s.tool} {tag}  [dim]{s.thought[:90]}[/dim]")

    try:
        res, run_dir = run_task(root, llm, args.task, headless=not args.headed, human_mode="interactive" if args.interactive else "batch",
                                on_step=show, erp_url=args.erp_url, record_video=args.record)
    except LLMError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    console.print(f"\nfinished={res.finished} steps={len(res.steps)} checks passed={sum(c.passed for c in res.checks)}/{len(res.checks)}")
    console.print(f"report: {os.path.join(run_dir, 'report.md')}")
    return 0 if res.finished and all(c.passed for c in res.checks) else 2


def cmd_erp(args):
    root = find_root()
    srv = ErpServer(root, port=args.port)
    srv.start()
    console.print(f"ERP running at {srv.url} (Ctrl+C to stop)")
    try:
        srv.proc.wait()
    except KeyboardInterrupt:
        srv.stop()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="opendev")
    p.add_argument("--base-url", default=os.environ.get("OPENDEV_BASE_URL", "http://localhost:11434/v1"))
    p.add_argument("--model", default=os.environ.get("OPENDEV_MODEL", "qwen3.5"))
    p.add_argument("--temperature", type=float, default=0.2)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    r = sub.add_parser("run")
    r.add_argument("task", nargs="?", default=DEFAULT_TASK)
    r.add_argument("--headed", action="store_true")
    r.add_argument("--interactive", action="store_true")
    r.add_argument("--record", action="store_true", help="record a video of the browser session")
    r.add_argument("--erp-url", default=None)
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("erp")
    e.add_argument("--port", type=int, default=5055)
    e.set_defaults(fn=cmd_erp)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
