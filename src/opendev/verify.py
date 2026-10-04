from dataclasses import dataclass


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def line(self):
        return f"{'PASS' if self.passed else 'FAIL'}  {self.name}  [{self.detail}]"
