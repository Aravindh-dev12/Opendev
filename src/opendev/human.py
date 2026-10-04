import sys


class Human:
    def __init__(self, mode="batch", answers=None):
        self.mode = mode
        self.answers = answers or []
        self.escalations = []

    def ask(self, question, context=""):
        rec = {"question": question, "context": context, "answer": None}
        self.escalations.append(rec)
        if self.answers:
            rec["answer"] = self.answers.pop(0)
            return f"Human answered: {rec['answer']}"
        if self.mode == "interactive" and sys.stdin.isatty():
            print(f"\n[operator needs help]\n{question}\n")
            rec["answer"] = input("your answer (empty to defer): ").strip() or None
            if rec["answer"]:
                return f"Human answered: {rec['answer']}"
        return "No answer is available right now. The escalation has been recorded and routed. Do not wait, continue with the remaining work and mark this item escalated."
