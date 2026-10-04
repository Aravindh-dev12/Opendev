import os
import re
import time

from playwright.sync_api import sync_playwright

from .base import ToolResult

TAG_JS = """
() => {
  const sel = 'a[href],button,input:not([type=hidden]),select,textarea';
  const out = [];
  let n = 0;
  document.querySelectorAll(sel).forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    n += 1;
    el.setAttribute('data-op-id', String(n));
    let label = (el.innerText || el.value || '').trim();
    if (el.id) {
      const l = document.querySelector('label[for="' + el.id + '"]');
      if (l && el.tagName !== 'BUTTON') label = l.innerText.trim();
    }
    label = label || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
    const item = {id: n, tag: el.tagName.toLowerCase(), type: el.type || '', label: label.slice(0, 80), name: el.name || '', href: el.getAttribute('href') || ''};
    if (el.tagName === 'SELECT') item.options = Array.from(el.options).map(o => o.text.trim()).slice(0, 30);
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') item.value = (el.value || '').slice(0, 60);
    out.push(item);
  });
  return out;
}
"""


class Browser:
    def __init__(self, policy, evidence_dir, base_url, headless=True, record_video=False):
        self.policy = policy
        self.evidence_dir = evidence_dir
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.record_video = record_video
        self.pw = None
        self.browser = None
        self.page = None
        self.elements = {}
        self.shots = 0
        self.blocked_nav = []
        os.makedirs(evidence_dir, exist_ok=True)

    def start(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=self.headless, slow_mo=350 if self.record_video else 0)
        kw = {"record_video_dir": os.path.join(self.evidence_dir, "video"), "record_video_size": {"width": 1100, "height": 800}} if self.record_video else {}
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 800}, **kw)
        ctx.route("**/*", self._route)
        self.page = ctx.new_page()

    def close(self):
        if self.browser:
            self.browser.close()
        if self.pw:
            self.pw.stop()

    def _route(self, route):
        req = route.request
        if req.resource_type == "document":
            d = self.policy.check_url(req.url)
            if not d.allowed:
                self.blocked_nav.append((req.url, d.reason))
                route.abort()
                return
        route.continue_()

    def _text(self):
        return self.page.inner_text("body")

    def observe(self, limit_text=2200, limit_el=45):
        text = re.sub(r"\n{2,}", "\n", self._text()).strip()
        els = self.page.evaluate(TAG_JS)
        self.elements = {e["id"]: e for e in els}
        lines = []
        for e in els[:limit_el]:
            extra = ""
            if e.get("options"):
                extra = " options=" + "|".join(e["options"])
            if e["tag"] in ("input", "textarea"):
                extra = f" value={e.get('value', '')!r}"
            kind = e["tag"] if e["tag"] != "input" else f"input:{e['type']}"
            href = f" -> {e['href']}" if e["tag"] == "a" else ""
            lines.append(f"[{e['id']}] {kind} {e['label']!r}{href}{extra}")
        title = self.page.title()
        return f"URL: {self.page.url}\nTITLE: {title}\nPAGE TEXT:\n{text[:limit_text]}\nELEMENTS:\n" + "\n".join(lines)

    def shot(self, tag):
        self.shots += 1
        name = f"{self.shots:03d}_{re.sub(r'[^a-z0-9]+', '_', tag.lower())[:40]}.png"
        path = os.path.join(self.evidence_dir, name)
        self.page.screenshot(path=path, full_page=True)
        return path

    def goto(self, url):
        if url.startswith("/"):
            url = self.base_url + url
        d = self.policy.check_url(url)
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            return ToolResult(False, f"navigation failed: {str(e)[:200]}")
        return ToolResult(True, self.observe())

    def read(self):
        return ToolResult(True, self.observe())

    def _el(self, idx):
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            return None, f"element id must be a number from the last observation, got {idx!r}"
        if idx not in self.elements:
            return None, f"no element [{idx}] on the current page. Call read_page to refresh the element list."
        return self.page.locator(f'[data-op-id="{idx}"]'), None

    def click(self, element):
        loc, err = self._el(element)
        if err:
            return ToolResult(False, err)
        info = self.elements[int(element)]
        label = info["label"]
        d = self.policy.check_click(label, self._text())
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        before = self.page.url
        self.blocked_nav.clear()
        try:
            with self.page.expect_navigation(timeout=4000):
                loc.click(timeout=4000)
        except Exception:
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception:
                pass
        if self.blocked_nav:
            url, why = self.blocked_nav[-1]
            return ToolResult(False, f"BLOCKED by policy: navigation to {url} refused. {why}", blocked=True)
        ev = []
        if info["tag"] == "button" or self.page.url != before:
            ev.append(self.shot(f"click {label}"))
        return ToolResult(True, f"clicked [{element}] {label!r}\n" + self.observe(), evidence=ev)

    def fill(self, element, text):
        loc, err = self._el(element)
        if err:
            return ToolResult(False, err)
        info = self.elements[int(element)]
        if info["tag"] not in ("input", "textarea"):
            return ToolResult(False, f"[{element}] is a {info['tag']}, use select_option for dropdowns")
        d = self.policy.check_fill(info["name"] + " " + info["label"])
        if not d.allowed:
            return ToolResult(False, f"BLOCKED by policy: {d.reason}", blocked=True)
        loc.fill(str(text), timeout=4000)
        return ToolResult(True, f"filled [{element}] {info['label']!r} with {str(text)!r}")

    def select_option(self, element, option):
        loc, err = self._el(element)
        if err:
            return ToolResult(False, err)
        info = self.elements[int(element)]
        if info["tag"] != "select":
            return ToolResult(False, f"[{element}] is not a dropdown")
        opts = info.get("options", [])
        match = next((o for o in opts if o.lower() == str(option).lower()), None) or next((o for o in opts if str(option).lower() in o.lower()), None)
        if not match:
            return ToolResult(False, f"option {option!r} not found. Options: {opts}")
        loc.select_option(label=match, timeout=4000)
        return ToolResult(True, f"selected {match!r} in [{element}]")
