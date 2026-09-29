#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAPKP v26 MASTER — CLOUD API  (server.py)
Token-gated KP astrology engine for the native Android app.

  GET  /api/ask?query=...&token=...&chart=<name|id>   -> KP timing answer
  GET  /api/charts?token=...                          -> list saved charts
  POST /api/charts  (JSON)                            -> save / update a chart
  POST /api/bug-report?token=...   (JSON)             -> log a bug from the app
  GET  /api/bugs?token=...                            -> read bug log
  POST /api/correction?token=...   (JSON)             -> tell it the right answer
  GET  /api/corrections?token=...                     -> list corrections
  GET  /health                                        -> liveness
"""
import base64, io, json, os, sqlite3, threading, time, traceback, re, urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from pypdf import PdfReader

import engine as E
from pdf_report import make_chart_pdf

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DB = os.path.join(DATA, "rapkp.db")
LOG = os.path.join(DATA, "mit_server.log")
PORT = int(os.environ.get("PORT", "8000"))
TOKEN = os.environ.get("RAPKP_TOKEN", "KVYezIWxlkS6bwKDAi4i1pT3l7PLNvO2")
# v30 optional AI gate. No key required: safe rule-based fallback is always active.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "").strip().rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b").strip()
DEFAULT_CHART = dict(name="Venkat Kalyan", dob="1971-01-23", tob="09:53",
                     lat=13.05705, lon=80.20982, tz=5.5,
                     place="Chennai, India", relation="self")
os.makedirs(DATA, exist_ok=True)
_lock = threading.Lock()

# ------------------------------------------------------------------ storage
def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init():
    with _lock, db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS charts(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, dob TEXT, tob TEXT,
            lat REAL, lon REAL, tz REAL, place TEXT, relation TEXT, ts TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bugs(
            id INTEGER PRIMARY KEY, ts TEXT, query TEXT, error TEXT,
            context TEXT, engine TEXT, status TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS corrections(
            id INTEGER PRIMARY KEY, ts TEXT, query TEXT, domain TEXT, chart TEXT,
            correct_date TEXT, correct_time TEXT, note TEXT, applied INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS queries(
            id INTEGER PRIMARY KEY, ts TEXT, query TEXT, domain TEXT, chart TEXT,
            answer_date TEXT, probability REAL, ms INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pdf_readings(
            id INTEGER PRIMARY KEY, ts TEXT, filename TEXT, chart TEXT, query TEXT,
            pages INTEGER, chars INTEGER, domain TEXT, answer_date TEXT, probability REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS rules(
            id INTEGER PRIMARY KEY, ts TEXT, title TEXT, rule TEXT, rule_type TEXT,
            active INTEGER DEFAULT 1, source TEXT, applied_count INTEGER DEFAULT 0)""")
        # v29.4 safety: old empty-query note-only corrections were bug notes, not valid learning.
        c.execute("UPDATE corrections SET applied=0 WHERE (query IS NULL OR trim(query)='') AND (correct_date IS NULL OR trim(correct_date)='')")
        c.execute("SELECT COUNT(*) n FROM charts")
        if c.execute("SELECT COUNT(*) n FROM charts").fetchone()["n"] == 0:
            _save_chart(DEFAULT_CHART, c)

def _save_chart(ch, c):
    c.execute("""INSERT INTO charts(name,dob,tob,lat,lon,tz,place,relation,ts)
                 VALUES(:name,:dob,:tob,:lat,:lon,:tz,:place,:relation,:ts)
                 ON CONFLICT(name) DO UPDATE SET dob=:dob,tob=:tob,lat=:lat,lon=:lon,
                 tz=:tz,place=:place,relation=:relation,ts=:ts""",
              dict(name=ch["name"], dob=ch["dob"], tob=ch.get("tob", "12:00"),
                   lat=float(ch["lat"]), lon=float(ch["lon"]), tz=float(ch.get("tz", 5.5)),
                   place=ch.get("place", ""), relation=ch.get("relation", "self"),
                   ts=datetime.now(timezone.utc).isoformat()))

def row_to_chart(r):
    return dict(id=r["id"], name=r["name"], dob=r["dob"], tob=r["tob"], lat=r["lat"],
                lon=r["lon"], tz=r["tz"], place=r["place"], relation=r["relation"])

PERSON_STOPWORDS = set(['i', 'me', 'my', 'mine', 'myself', 'you', 'your', 'yours', 'he', 'she', 'they', 'we', 'us', 'when', 'will', 'can', 'should', 'is', 'are', 'am', 'do', 'does', 'did', 'would', 'could', 'may', 'timing', 'date', 'event', 'predict', 'prediction', 'marriage', 'remarriage', 'third', 'second', 'first', 'wife', 'husband', 'spouse', 'wedding', 'health', 'career', 'job', 'property', 'flat', 'house', 'plot', 'land', 'visa', 'travel', 'foreign', 'abroad', 'overseas', 'international', 'local', 'domestic', 'short', 'trip', 'journey', 'train', 'bus', 'flight', 'road', 'within', 'india', 'nearby', 'tour', 'money', 'finance', 'court', 'case', 'legal', 'general', 'read', 'pdf', 'chart', 'for', 'give', 'and', 'the', 'of', 'to', 'in', 'on', 'with', 'from', 'dob', 'birth', 'time', 'issue', 'matter', 'question'])

def _tokens(x):
    return re.findall(r"[a-z][a-z0-9]{1,}", str(x or '').lower())

def detect_person_chart_mismatch(query, chart):
    """Block unsafe cross-person predictions: e.g. query says Mydhili but active chart is Venkat."""
    q = str(query or '')
    qt = _tokens(q)
    if not qt:
        return None
    chart_name = str((chart or {}).get('name') or '')
    ct = set(_tokens(chart_name))
    # Known/saved chart names have highest confidence.
    known = []
    try:
        with _lock, db() as c:
            known = [str(r['name'] or '') for r in c.execute('SELECT name FROM charts ORDER BY id')]
    except Exception:
        known = []
    qlow=' '.join(qt)
    for name in known:
        nt=_tokens(name)
        if nt and all(t in qt for t in nt[:2] if t) and not set(nt).issubset(ct):
            return dict(person=name, active_chart=chart_name, reason='query references saved chart/person but active chart is different')
    # Explicit common alternate spelling / current bug case.
    for special in ('mydhili','maithili','mythili','mydhilee'):
        if special in qt and special not in ct:
            return dict(person=special.title(), active_chart=chart_name, reason='query references another person name')
    # Generic: if the first meaningful word before a domain question is not in active chart, treat as person name.
    domain_present = any(w in qt for w in ('marriage','remarriage','wife','husband','health','career','job','property','flat','visa','travel','money','court','education','child'))
    if domain_present:
        for t in qt[:4]:
            if t not in PERSON_STOPWORDS and t not in ct and len(t) >= 4:
                return dict(person=t.title(), active_chart=chart_name, reason='query appears to name another person before event domain')
    return None

def get_chart(selector=None):
    with _lock, db() as c:
        if selector:
            r = c.execute("SELECT * FROM charts WHERE name=? OR id=?",
                          (selector, str(selector))).fetchone()
            if r:
                return row_to_chart(r)
        r = c.execute("SELECT * FROM charts ORDER BY id LIMIT 1").fetchone()
        return row_to_chart(r) if r else DEFAULT_CHART

def active_rules():
    with _lock, db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM rules WHERE active=1 ORDER BY id DESC LIMIT 300")]

def log(msg):
    line = "[%s] %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def add_text_prediction(res):
    """Add ChatGPT/Gemini-style narrative while keeping deterministic KP calculation."""
    try:
        q = res.get("query") or "your question"
        p = res.get("presentable") or {}
        b = res.get("best") or {}
        domain = res.get("domain_label") or res.get("domain") or "event"
        date = p.get("date") or b.get("date") or "not available"
        time_s = p.get("time") or b.get("time") or ""
        prob = p.get("probability") or b.get("combined") or ""
        conf = p.get("confidence") or "MEDIUM"
        dasha = p.get("dasha") or b.get("dasha") or ""
        asc = p.get("asc") or b.get("asc") or ""
        note = str(b.get("intelligence_note") or "Realistic KP sequence applied")
        if res.get("domain") == "local_travel":
            opening = "This is read as a local/domestic travel question, not a foreign/visa matter."
            caution = "If you meant abroad/visa travel, ask using words like abroad, foreign, visa or overseas."
        elif res.get("domain") == "travel":
            opening = "This is read as a foreign/abroad or long-distance travel question."
            caution = "If you meant only local travel, ask 'local travel' or 'domestic travel' explicitly."
        else:
            opening = "I checked the KP timing factors for this specific question."
            caution = "Treat this as an astrology timing indication, not a guaranteed event."
        text = (f"{opening}\n\n"
                f"For '{q}', the stronger timing window is {date}"
                f"{' at ' + time_s + ' IST' if time_s else ''}. "
                f"The calculated probability is about {prob}% with {conf} confidence. "
                f"The running dasha pattern shown is {dasha}, and the event ASC is {asc}.\n\n"
                f"Why: {note[:260]}.\n\n"
                f"Summary: watch the period around {date}; use this date as the main KP timing marker, then validate with real-world readiness and follow-up chart context. {caution}")
        res["text_prediction"] = text
        res.setdefault("presentable", {})["text_prediction"] = text
    except Exception:
        pass
    return res

# ------------------------------------------------------------------ v30 AI intent gate
DOMAIN_WORDS = {
    "marriage": ("marriage", "remarriage", "wife", "husband", "spouse", "wedding"),
    "property": ("flat", "302", "house", "property", "plot", "land", "handover", "possession", "registration"),
    "career": ("job", "career", "promotion", "work", "business", "client", "salary"),
    "health": ("health", "surgery", "medical", "hospital", "disease", "recovery"),
    "local_travel": ("local travel", "domestic", "within india", "short trip", "road trip", "train journey", "bus travel"),
    "travel": ("visa", "foreign", "abroad", "overseas", "international", "passport", "onsite"),
    "finance": ("money", "loan", "wealth", "income", "debt", "profit", "finance"),
    "education": ("exam", "education", "study", "admission", "result"),
    "litigation": ("court", "case", "legal", "police", "litigation"),
}

def _extract_json(txt):
    txt = (txt or "").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError("no json in model output")
    return json.loads(m.group(0))

def local_intent_gate(query, chart=None, filename="", context="ask"):
    q = " ".join(str(query or "").split()).strip()
    low = q.lower()
    fname = str(filename or "")
    neutral_pdf = low.startswith("read this pdf") or ("chart-specific prediction summary" in low)
    vague = (not q) or neutral_pdf or low in ("general", "prediction", "predict", "chart", "read chart", "read pdf")
    domain = "general"
    matched=[]
    for d, words in DOMAIN_WORDS.items():
        hits=[w for w in words if w in low]
        if hits:
            domain=d; matched=hits; break
    is_question = any(w in low for w in ("when", "will", "can", "is", "are", "should", "timing", "date", "happen", "get", "meet")) or bool(matched)
    if vague or not is_question:
        return dict(ok=True, provider="local-intent-gate", should_predict=False,
                    needs_clarification=True, domain="none", normalized_query=q,
                    reason="No specific predictive question found. Loading a chart/PDF alone must not create event timing.",
                    ask_user="Please type a specific question, e.g. 'Mydhili marriage timing', 'Mydhili health issue', 'Mydhili career', or 'Mydhili property matter'.")
    # Normalize flat 302 safely
    normalized = re.sub(r"\bflat\s*(?:no\.?|number)?\s*302\b", "flat", q, flags=re.I)
    return dict(ok=True, provider="local-intent-gate", should_predict=True,
                needs_clarification=False, domain=domain, matched_terms=matched,
                normalized_query=normalized, reason="Specific predictive question detected.")

def gemini_intent_gate(query, chart=None, filename="", context="ask"):
    if not GEMINI_API_KEY:
        return None
    prompt = f"""You are an astrology product intent gate, not the astrologer.
Decide if the user text is a specific predictive question. Loading a PDF/chart alone is NOT a prediction request.
Never invent an event. If vague, block and ask clarification.
Return JSON only with keys: should_predict boolean, needs_clarification boolean, domain string, normalized_query string, reason string, ask_user string.
Domains: marriage, property, career, health, travel, finance, education, litigation, child, meeting_partner, general.
User text: {query!r}
PDF/chart filename: {filename!r}
Context: {context!r}
"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (GEMINI_MODEL, GEMINI_API_KEY)
    payload = {"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"temperature":0.05, "maxOutputTokens":512}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=18) as r:
        j=json.loads(r.read().decode("utf-8","replace"))
    txt = j.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    out = _extract_json(txt)
    out["provider"] = "google-gemini"
    out["ok"] = True
    return out

def ollama_intent_gate(query, chart=None, filename="", context="ask"):
    if not OLLAMA_URL:
        return None
    prompt = "Return JSON only. Is this a specific astrology predictive question? Block vague PDF/chart load. Text=%r filename=%r" % (query, filename)
    payload={"model":OLLAMA_MODEL,"prompt":prompt,"stream":False,"options":{"temperature":0.05}}
    req=urllib.request.Request(OLLAMA_URL+"/api/generate", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        j=json.loads(r.read().decode("utf-8","replace"))
    out=_extract_json(j.get("response", ""))
    out["provider"]="ollama-open-source"
    out["ok"]=True
    return out

def ai_intent_gate(query, chart=None, filename="", context="ask"):
    # Try Gemini, then open-source/Ollama, then deterministic safe fallback.
    for fn in (gemini_intent_gate, ollama_intent_gate):
        try:
            out = fn(query, chart, filename, context)
            if out:
                # Safety override: model cannot allow neutral PDF summary as event timing.
                local = local_intent_gate(query, chart, filename, context)
                if not local.get("should_predict"):
                    local["provider"] = out.get("provider", "ai") + "+local-safety"
                    return local
                return out
        except Exception as ex:
            log("AI intent gate fallback: %s" % str(ex)[:160])
    return local_intent_gate(query, chart, filename, context)

# ------------------------------------------------------------------ handler
class H(BaseHTTPRequestHandler):
    server_version = "RAPKP/26"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Auth-Token,Authorization")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _bin(self, body, ctype, filename=None, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", "inline; filename=\"%s\"" % filename)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, *a):
        pass

    # -------------------------------------------------------------- GET
    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path.rstrip("/") or "/", parse_qs(u.query)
        try:
            if p in ("/", "/app", "/index.html"):
                return self._serve_app()
            if p == "/api/chart-pdf":
                self._need_token(q)
                sel = (q.get("chart") or [""])[0]
                if (q.get("dob") or [""])[0]:
                    ch = dict(name=(q.get("name") or ["Ad-hoc"])[0],
                              dob=(q.get("dob") or [""])[0],
                              tob=(q.get("tob") or ["12:00"])[0],
                              lat=float((q.get("lat") or [13.05705])[0]),
                              lon=float((q.get("lon") or [80.20982])[0]),
                              tz=float((q.get("tz") or [5.5])[0]),
                              place=(q.get("place") or [""])[0])
                else:
                    ch = get_chart(sel)
                res = E.chart_payload(ch, (q.get("ayan") or ["kp_new"])[0],
                                      (q.get("calc") or ["swiss"])[0],
                                      (q.get("pos") or ["apparent"])[0],
                                      (q.get("system") or ["placidus"])[0])
                pdf = make_chart_pdf(res)
                safe = (str(ch.get("name") or "chart").replace(" ", "_").replace("/", "_"))[:40]
                log("PDF CHART %s (%s %s)" % (ch.get("name"), ch.get("dob"), ch.get("tob")))
                return self._bin(pdf, "application/pdf", "RAPKP_v26_%s_chart.pdf" % safe)
            if p == "/api/chart":
                self._need_token(q)
                sel = (q.get("chart") or [""])[0]
                if (q.get("dob") or [""])[0]:
                    ch = dict(name=(q.get("name") or ["Ad-hoc"])[0],
                              dob=(q.get("dob") or [""])[0],
                              tob=(q.get("tob") or ["12:00"])[0],
                              lat=float((q.get("lat") or [13.05705])[0]),
                              lon=float((q.get("lon") or [80.20982])[0]),
                              tz=float((q.get("tz") or [5.5])[0]),
                              place=(q.get("place") or [""])[0])
                else:
                    ch = get_chart(sel)
                try:
                    res = E.chart_payload(ch, (q.get("ayan") or ["kp_new"])[0],
                                          (q.get("calc") or ["swiss"])[0],
                                          (q.get("pos") or ["apparent"])[0],
                                          (q.get("system") or ["placidus"])[0])
                except Exception as ex:
                    log("CHART error: %s" % traceback.format_exc(limit=2))
                    return self._json(dict(error=str(ex)), 500)
                log("CHART %s (%s %s) ayan=%s" % (ch.get("name"), ch.get("dob"),
                                                  ch.get("tob"),
                                                  (q.get("ayan") or ["kp_new"])[0]))
                return self._json(res)
            if p == "/api/modes":
                return self._json(dict(
                    ayanamsa=[dict(id=k, **v) for k, v in E.AYAN_INFO.items()],
                    calculator=[dict(id="swiss", label="Swiss (apparent — light-time + deflection + aberration)"),
                                dict(id="classic", label="Classic (astrometric — light-time only)")],
                    position=[dict(id="apparent", label="Apparent place"),
                              dict(id="geometric", label="Geometric / true position (no light-time, no aberration)")],
                    house_systems=["placidus", "whole", "equal"],
                    dasha=["Vimshottari (maha / antar / pratyantar)"]))
            if p == "/health":
                return self._json(dict(ok=True, service="RAPKP v26 Cloud",
                                       time=datetime.now(timezone.utc).isoformat(),
                                       engine="MIT openephem DE421/Skyfield", ai_gate=("gemini" if GEMINI_API_KEY else ("ollama" if OLLAMA_URL else "local"))))
            if p == "/api/intent-gate":
                self._need_token(q)
                query=(q.get("query") or [""])[0]
                filename=(q.get("filename") or [""])[0]
                return self._json(ai_intent_gate(query, filename=filename, context="get"))
            if p == "/api/ask":
                return self._ask(q)
            if p == "/api/charts":
                self._need_token(q)
                with _lock, db() as c:
                    rows = [row_to_chart(r) for r in
                            c.execute("SELECT * FROM charts ORDER BY id")]
                return self._json(dict(charts=rows, count=len(rows)))
            if p == "/api/bugs":
                self._need_token(q)
                with _lock, db() as c:
                    rows = [dict(r) for r in c.execute(
                        "SELECT * FROM bugs ORDER BY id DESC LIMIT 100")]
                return self._json(dict(bugs=rows, count=len(rows)))
            if p == "/api/corrections":
                self._need_token(q)
                with _lock, db() as c:
                    rows = [dict(r) for r in c.execute(
                        "SELECT * FROM corrections WHERE applied=1 ORDER BY id DESC LIMIT 200")]
                return self._json(dict(corrections=rows, count=len(rows)))
            if p == "/api/rules":
                self._need_token(q)
                rows = active_rules()
                return self._json(dict(rules=rows, count=len(rows), note="Rules are applied automatically on every prediction."))
            return self._json(dict(error="not found", path=p), 404)
        except PermissionError:
            return self._json(dict(error="forbidden — invalid token"), 403)
        except Exception as ex:
            log("GET %s error: %s" % (p, traceback.format_exc(limit=2)))
            return self._json(dict(error=str(ex)), 500)

    def _serve_app(self):
        for cand in (os.path.join(HERE, "..", "rapkp_apk", "assets", "index.html"),
                     os.path.join(HERE, "app", "index.html")):
            if os.path.exists(cand):
                data = open(cand, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self._cors()
                self.end_headers()
                self.wfile.write(data)
                return
        return self._json(dict(ok=True, msg="RAPKP v26 cloud is live — use the Android app."))

    def _need_token(self, q):
        tok = (q.get("token") or [""])[0] or self.headers.get("X-Auth-Token") or ""
        if tok != TOKEN:
            raise PermissionError("bad token")

    def _ask(self, q):
        self._need_token(q)
        query = (q.get("query") or [""])[0].strip()
        if not query:
            return self._json(dict(error="empty query"), 400)
        gate = ai_intent_gate(query, context="ask")
        if not gate.get("should_predict"):
            return self._json(dict(error="specific query required", intent_gate=gate,
                                   msg=gate.get("ask_user") or gate.get("reason")), 409)
        query = gate.get("normalized_query") or query
        # chart selection: saved chart by name/id, or ad-hoc birth data in the URL
        sel = (q.get("chart") or [""])[0]
        if (q.get("dob") or [""])[0]:
            ch = dict(name=(q.get("name") or ["Ad-hoc"])[0],
                      dob=(q.get("dob") or [""])[0],
                      tob=(q.get("tob") or ["12:00"])[0],
                      lat=float((q.get("lat") or [13.05705])[0]),
                      lon=float((q.get("lon") or [80.20982])[0]),
                      tz=float((q.get("tz") or [5.5])[0]))
        else:
            ch = get_chart(sel)
        mismatch = detect_person_chart_mismatch(query, ch)
        if mismatch:
            return self._json(dict(error="chart_mismatch", chart_mismatch=True,
                                   active_chart=ch.get("name"), referenced_person=mismatch.get("person"),
                                   reason=mismatch.get("reason"),
                                   msg="Query appears to refer to %s but active chart is %s. Select/save the correct chart first, then ask again." % (mismatch.get("person"), ch.get("name")),
                                   action="Select or save the referenced person's chart before prediction."), 409)
        with _lock, db() as c:
            corrs = [dict(r) for r in c.execute(
                "SELECT * FROM corrections WHERE applied=1 ORDER BY id DESC LIMIT 200")]
        ayan = (q.get("ayan") or ["kp_new"])[0]
        calc = (q.get("calc") or ["swiss"])[0]
        pos = (q.get("pos") or ["apparent"])[0]
        t0 = time.time()
        res = E.answer(query, ch, corrections=corrs, ayan=ayan, calc=calc, pos=pos)
        res["intent_gate"] = gate
        res = add_text_prediction(res)
        ms = int((time.time() - t0) * 1000)
        res["server_ms"] = ms
        res["token_ok"] = True
        try:
            with _lock, db() as c:
                c.execute("INSERT INTO queries(ts,query,domain,chart,answer_date,probability,ms)"
                          " VALUES(?,?,?,?,?,?,?)",
                          (datetime.now(timezone.utc).isoformat(), query, res["domain"],
                           ch.get("name"), res["presentable"]["date"],
                           res["presentable"]["probability"], ms))
        except Exception:
            pass
        log("ASK %r chart=%s -> %s %s (%.1f%%) %dms" %
            (query[:60], ch.get("name"), res["presentable"]["date"],
             res["domain"], res["presentable"]["probability"], ms))
        return self._json(res)

    # -------------------------------------------------------------- POST
    def do_POST(self):
        u = urlparse(self.path)
        p, q = u.path.rstrip("/") or "/", parse_qs(u.query)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}
        try:
            if p == "/api/intent-gate":
                self._need_token(q)
                return self._json(ai_intent_gate(body.get("query") or "", filename=body.get("filename") or "", context=body.get("context") or "post"))
            if p == "/api/charts":
                self._need_token(q)
                if not body.get("name") or not body.get("dob"):
                    return self._json(dict(error="name and dob required"), 400)
                with _lock, db() as c:
                    _save_chart(body, c)
                    r = c.execute("SELECT * FROM charts WHERE name=?",
                                  (body["name"],)).fetchone()
                log("CHART saved: %s (%s %s)" % (body["name"], body["dob"], body.get("tob")))
                return self._json(dict(ok=True, chart=row_to_chart(r)))

            if p == "/api/bug-report":
                self._need_token(q)
                with _lock, db() as c:
                    c.execute("INSERT INTO bugs(ts,query,error,context,engine,status) "
                              "VALUES(?,?,?,?,?,?)",
                              (datetime.now(timezone.utc).isoformat(),
                               body.get("query", ""), body.get("error", ""),
                               body.get("context", ""), body.get("engine", ""), "open"))
                log("BUG: %s | %s" % (str(body.get("query"))[:60],
                                      str(body.get("error"))[:120]))
                return self._json(dict(ok=True, logged=True, msg='Bug report logged. This does not auto-change predictions; use Correction with query/date or Rules to teach engine.'))

            if p == "/api/pdf-reading":
                self._need_token(q)
                filename = body.get("filename") or "attachment.pdf"
                b64 = body.get("data") or ""
                if "," in b64 and b64.strip().lower().startswith("data:"):
                    b64 = b64.split(",", 1)[1]
                if not b64:
                    return self._json(dict(error="PDF data missing"), 400)
                raw = base64.b64decode(b64)
                if len(raw) > 15 * 1024 * 1024:
                    return self._json(dict(error="PDF too large; limit 15 MB"), 413)
                reader = PdfReader(io.BytesIO(raw))
                pages_text = []
                max_pages = min(len(reader.pages), int(body.get("max_pages") or 30))
                for i in range(max_pages):
                    try:
                        pages_text.append(reader.pages[i].extract_text() or "")
                    except Exception:
                        pages_text.append("")
                text = "\n\n".join(pages_text).strip()
                preview = text[:6000]
                user_q = (body.get("query") or "").strip()
                if body.get("pdf_safety") and not body.get("explicit_query"):
                    return self._json(dict(error="specific query required before PDF prediction", mode="pdf_loaded_no_prediction", filename=filename,
                                           msg="PDF/chart loaded. Type a specific question before prediction."), 409)
                gate = ai_intent_gate(user_q, filename=filename, context="pdf")
                if (not user_q) or user_q.lower().startswith("read this pdf chart for") or not gate.get("should_predict"):
                    return self._json(dict(error="specific query required before PDF prediction", mode="pdf_loaded_no_prediction", filename=filename,
                                           intent_gate=gate,
                                           msg=gate.get("ask_user") or "PDF/chart loaded. Type a specific question before prediction."), 409)
                user_q = gate.get("normalized_query") or user_q
                combined_q = (user_q + "\n\nPDF attachment context:\n" + preview[:1800]).strip()
                chart_sel = body.get("chart") or ""
                if body.get("dob"):
                    ch = dict(name=body.get("name") or "PDF Person", dob=body.get("dob"),
                              tob=body.get("tob") or "12:00", lat=float(body.get("lat") or 13.05705),
                              lon=float(body.get("lon") or 80.20982), tz=float(body.get("tz") or 5.5),
                              place=body.get("place") or "")
                else:
                    ch = get_chart(chart_sel)
                mismatch = detect_person_chart_mismatch(user_q + " " + filename, ch)
                if mismatch:
                    return self._json(dict(error="chart_mismatch", chart_mismatch=True,
                                           active_chart=ch.get("name"), referenced_person=mismatch.get("person"),
                                           reason=mismatch.get("reason"), filename=filename,
                                           msg="PDF/query appears to refer to %s but active chart is %s. Save/select that person's chart first, then ask a specific question." % (mismatch.get("person"), ch.get("name")),
                                           action="Save/select the PDF person's chart before prediction."), 409)
                with _lock, db() as c:
                    corrs = [dict(r) for r in c.execute(
                        "SELECT * FROM corrections WHERE applied=1 ORDER BY id DESC LIMIT 200")]
                rules = active_rules()
                rule_corrs = [dict(query=r.get("title") or "", note=r.get("rule") or "", domain=r.get("rule_type") or "", source="cloud_rule", ts=r.get("ts")) for r in rules]
                res = E.answer(combined_q, ch, corrections=corrs + rule_corrs,
                               ayan=body.get("ayan") or "kp_new",
                               calc=body.get("calc") or "swiss",
                               pos=body.get("pos") or "apparent")
                res["cloud_rules_applied"] = [r.get("title") or r.get("rule")[:60] for r in rules[:12]]
                res["intent_gate"] = gate
                res = add_text_prediction(res)
                # Add a document-aware reading block. Keep the original presentable shape intact.
                key_lines = []
                for line in text.splitlines():
                    line = " ".join(line.split())
                    if len(line) > 35:
                        key_lines.append(line[:220])
                    if len(key_lines) >= 8:
                        break
                res["attachment"] = dict(ok=True, filename=filename, pages=len(reader.pages),
                                         pages_read=max_pages, chars=len(text),
                                         extracted_preview=preview[:1200], key_lines=key_lines,
                                         note="PDF text extracted and included in astrology reading query")
                try:
                    with _lock, db() as c:
                        c.execute("INSERT INTO pdf_readings(ts,filename,chart,query,pages,chars,domain,answer_date,probability) VALUES(?,?,?,?,?,?,?,?,?)",
                                  (datetime.now(timezone.utc).isoformat(), filename, ch.get("name"),
                                   user_q, len(reader.pages), len(text), res.get("domain"),
                                   res.get("presentable", {}).get("date"),
                                   res.get("presentable", {}).get("probability")))
                except Exception:
                    pass
                log("PDF READING %s chart=%s pages=%s chars=%s -> %s" %
                    (filename[:60], ch.get("name"), len(reader.pages), len(text), res.get("domain")))
                return self._json(res)

            if p == "/api/rules":
                self._need_token(q)
                rule = (body.get("rule") or body.get("note") or "").strip()
                title = (body.get("title") or body.get("query") or rule[:60] or "Rule").strip()
                rtype = (body.get("rule_type") or body.get("domain") or "auto").strip()
                if not rule:
                    return self._json(dict(error="rule required"), 400)
                with _lock, db() as c:
                    c.execute("INSERT INTO rules(ts,title,rule,rule_type,active,source) VALUES(?,?,?,?,1,?)",
                              (datetime.now(timezone.utc).isoformat(), title, rule, rtype, body.get("source") or "app"))
                    rid = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                log("RULE #%s saved: %s -> %s" % (rid, title[:50], rule[:120]))
                return self._json(dict(ok=True, id=rid, msg="Rule saved — cloud will apply automatically ✓"))

            if p == "/api/correction":
                self._need_token(q)
                if not body.get("correct_date") and not body.get("note"):
                    return self._json(dict(error="correct_date or note required"), 400)
                if not str(body.get("query") or "").strip() and not str(body.get("correct_date") or "").strip():
                    return self._json(dict(error="query required for note-only correction; bug reports do not auto-change predictions"), 400)
                with _lock, db() as c:
                    c.execute("""INSERT INTO corrections(ts,query,domain,chart,
                                 correct_date,correct_time,note,applied)
                                 VALUES(?,?,?,?,?,?,?,1)""",
                              (datetime.now(timezone.utc).isoformat(),
                               body.get("query", ""), body.get("domain", ""),
                               body.get("chart", ""), body.get("correct_date", ""),
                               body.get("correct_time", ""), body.get("note", "")))
                    cid = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                log("CORRECTION #%s: %s -> %s" % (cid, body.get("query", "")[:40],
                                                  body.get("correct_date", "")))
                return self._json(dict(ok=True, id=cid,
                                       msg="Correction saved — future answers will use it ✓"))
            return self._json(dict(error="not found", path=p), 404)
        except PermissionError:
            return self._json(dict(error="forbidden — invalid token"), 403)
        except Exception as ex:
            log("POST %s error: %s" % (p, traceback.format_exc(limit=2)))
            return self._json(dict(error=str(ex)), 500)

if __name__ == "__main__":
    init()
    with _lock, db() as c:
        n = c.execute("SELECT COUNT(*) n FROM charts").fetchone()["n"]
    log("RAPKP v26 cloud booting on 0.0.0.0:%d — charts=%d engine=DE421" % (PORT, n))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
