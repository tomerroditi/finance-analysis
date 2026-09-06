"""Harness for probing the zekestories retirement calculator."""
import re, time, json, html
from html.parser import HTMLParser
import requests

BASE = "https://zekestories.com"
CALC = BASE + "/calculators/retire_calc/"


class FormParser(HTMLParser):
    """Collect name->value pairs from the #myprevented form, in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.fields = []          # list of (name, value)
        self.meta = []            # list of dicts describing each control
        self._select = None
        self._sel_first = None
        self._sel_selected = None
        self._sel_opts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "myprevented":
            self.in_form = True
            return
        if not self.in_form:
            return
        if tag == "input":
            name = a.get("name")
            if not name:
                return
            typ = a.get("type", "text")
            if typ == "checkbox":
                if "checked" in a:
                    self.fields.append((name, a.get("value", "on")))
            else:
                self.fields.append((name, a.get("value", "")))
            self.meta.append({"tag": "input", "name": name, "type": typ,
                              "value": a.get("value", ""), "min": a.get("min"),
                              "max": a.get("max"), "required": "required" in a})
        elif tag == "select":
            self._select = a.get("name")
            self._sel_first = None
            self._sel_selected = None
            self._sel_opts = []
        elif tag == "option" and self._select:
            v = a.get("value", "")
            self._sel_opts.append(v)
            if self._sel_first is None:
                self._sel_first = v
            if "selected" in a:
                self._sel_selected = v

    def handle_endtag(self, tag):
        if tag == "form" and self.in_form:
            self.in_form = False
        elif tag == "select" and self._select:
            val = self._sel_selected if self._sel_selected is not None else (self._sel_first or "")
            self.fields.append((self._select, val))
            self.meta.append({"tag": "select", "name": self._select, "type": "select",
                              "value": val, "options": self._sel_opts})
            self._select = None


class Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (research)"
        self.token = None
        self.defaults = None
        self.meta = None

    def load(self):
        r = self.s.get(CALC, timeout=60)
        r.raise_for_status()
        self.html = r.text
        p = FormParser()
        p.feed(r.text)
        self.defaults = p.fields
        self.meta = p.meta
        self.token = dict(p.fields).get("csrfmiddlewaretoken")
        return self

    def _headers(self):
        return {"Referer": CALC, "X-CSRFToken": self.token,
                "X-Requested-With": "XMLHttpRequest"}

    def body(self, overrides=None, drop=()):
        """Full form body as a list of (k, v), with overrides applied."""
        overrides = overrides or {}
        out = []
        seen = set()
        for k, v in self.defaults:
            if k in drop:
                continue
            if k in overrides:
                if k in seen:
                    continue
                seen.add(k)
                val = overrides[k]
                if val is None:
                    continue
                out.append((k, str(val)))
            else:
                out.append((k, v))
        for k, v in overrides.items():
            if k not in seen and v is not None:
                out.append((k, str(v)))
        return out

    def table_action(self, action, asset_type, idx, body):
        url = f"{BASE}/calculators/retire_table_action/{action}/{asset_type}/{idx}"
        r = self.s.post(url, data=body, headers=self._headers(), timeout=60)
        return r

    def calc(self, overrides=None, poll_max=300, verbose=True):
        """Submit a scenario and return the finished job result.

        The initial (pre-job) response is kept under ``_initial`` because it
        carries ``id_of_pickle`` and the ``smart_advice`` token that the
        follow-up optimiser call needs.
        """
        body = self.body(overrides)
        r = self.s.post(BASE + "/calculators/get_calc_ajax/retireCalc",
                        data=body, headers=self._headers(), timeout=120)
        r.raise_for_status()
        js = r.json()
        self.last_initial = js
        if not js.get("threaded"):
            return js
        job = js["job_id"]
        t0 = time.time()
        while time.time() - t0 < poll_max:
            time.sleep(2)
            rr = self.s.get(BASE + "/calculators/get_calc_results/" + job,
                            headers={"Referer": CALC}, timeout=60)
            st = rr.json()
            if verbose:
                print("   status:", st.get("status"), st.get("position", ""), f"{time.time()-t0:.0f}s")
            if st.get("status") in ("finished", "failed"):
                st["_job"] = job
                st["_initial"] = js
                return st
        raise TimeoutError("job did not finish")

    def advice(self, overrides, token, pickle_id, poll_max=300):
        """Second-stage call: ask the optimiser for a personalised improvement.

        The page replays the same form with ``smart_advice`` set to the token
        the first response returned, alongside the pickle id of the state the
        server saved.
        """
        ov = dict(overrides or {})
        ov["smart_advice"] = token
        if pickle_id is not None:
            ov["pickle_id"] = pickle_id
        return self.calc(ov, poll_max=poll_max, verbose=False)


def text(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", h)).strip()

