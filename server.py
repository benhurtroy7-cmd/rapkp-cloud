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
import base64, io, json, os, sqlite3, threading, time, traceback
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

def get_chart(selector=None):
    with _lock, db() as c:
        if selector:
            r = c.execute("SELECT * FROM charts WHERE name=? OR id=?",
                          (selector, str(selector))).fetchone()
            if r:
                return row_to_chart(r)
        r = c.execute("SELECT * FROM charts ORDER BY id LIMIT 1").fetchone()
        return row_to_chart(r) if r else DEFAULT_CHART

def log(msg):
    line = "[%s] %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

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
                                       engine="MIT openephem DE421/Skyfield"))
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
        with _lock, db() as c:
            corrs = [dict(r) for r in c.execute(
                "SELECT * FROM corrections WHERE applied=1 ORDER BY id DESC LIMIT 200")]
        ayan = (q.get("ayan") or ["kp_new"])[0]
        calc = (q.get("calc") or ["swiss"])[0]
        pos = (q.get("pos") or ["apparent"])[0]
        t0 = time.time()
        res = E.answer(query, ch, corrections=corrs, ayan=ayan, calc=calc, pos=pos)
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
                return self._json(dict(ok=True, logged=True))

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
                user_q = (body.get("query") or "Read this PDF attachment and give astrology prediction based on the attached document").strip()
                combined_q = (user_q + "\n\nPDF attachment context:\n" + preview[:1800]).strip()
                chart_sel = body.get("chart") or ""
                if body.get("dob"):
                    ch = dict(name=body.get("name") or "PDF Person", dob=body.get("dob"),
                              tob=body.get("tob") or "12:00", lat=float(body.get("lat") or 13.05705),
                              lon=float(body.get("lon") or 80.20982), tz=float(body.get("tz") or 5.5),
                              place=body.get("place") or "")
                else:
                    ch = get_chart(chart_sel)
                with _lock, db() as c:
                    corrs = [dict(r) for r in c.execute(
                        "SELECT * FROM corrections WHERE applied=1 ORDER BY id DESC LIMIT 200")]
                res = E.answer(combined_q, ch, corrections=corrs,
                               ayan=body.get("ayan") or "kp_new",
                               calc=body.get("calc") or "swiss",
                               pos=body.get("pos") or "apparent")
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

            if p == "/api/correction":
                self._need_token(q)
                if not body.get("correct_date") and not body.get("note"):
                    return self._json(dict(error="correct_date or note required"), 400)
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
