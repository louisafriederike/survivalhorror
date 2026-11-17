#!/usr/bin/env python3
"""
Captive portal server for one game chapter.
Python standard library only, no installs needed.

What it does:
  - answers the "is there internet?" checks from iOS, Android, Windows
    and Firefox with a redirect, so phones pop up the portal page
  - shows a short entry screen: network name, lease time, an enter button
  - serves your own interface from the ./site folder (index.html, css,
    js, images, video... subfolders are fine)
  - gives every visitor a "lease" (minutes on this network); when it
    runs out, the site is locked for that device
  - offers two small JSON endpoints your interface can use:
      GET  /lease        -> {"remaining": seconds, "ssid": ..., "chapter": ...}
      GET  /guestbook    -> list of entries
      POST /guestbook    -> add an entry (form fields or JSON: name, text)

Run for testing on your laptop:   PORT=8080 python3 server.py
                       (Windows:  $env:PORT=8080 ; python server.py)
Run on the Pi (needs port 80):    sudo python3 server.py
"""

import html
import json
import mimetypes
import os
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
SITE = (BASE / "site").resolve()
DATA = BASE / "data"
GUESTBOOK = DATA / "guestbook.json"
LEASES = DATA / "leases.json"
CHAPTER = json.loads((BASE / "chapter.json").read_text(encoding="utf-8"))

PORT = int(os.environ.get("PORT", "80"))
HOME = f"http://{CHAPTER['server_ip']}/" if PORT == 80 else "/"

# URLs that phones and laptops request to check for internet access.
# Answering with a redirect makes them open the portal page.
CAPTIVE_CHECKS = {
    "/generate_204", "/gen_204",          # Android / Chrome
    "/hotspot-detect.html",               # Apple
    "/library/test/success.html",         # Apple (older)
    "/connecttest.txt", "/ncsi.txt",      # Windows
    "/redirect",                          # Windows
    "/canonical.html", "/success.txt",    # Firefox
}

# Types some systems don't know out of the box
for ext, typ in {".woff2": "font/woff2", ".woff": "font/woff", ".webp": "image/webp",
                 ".m4a": "audio/mp4", ".m4v": "video/mp4", ".mp4": "video/mp4",
                 ".webm": "video/webm", ".svg": "image/svg+xml", ".js": "text/javascript",
                 ".json": "application/json", ".css": "text/css"}.items():
    mimetypes.add_type(typ, ext)

DATA.mkdir(exist_ok=True)
SITE.mkdir(exist_ok=True)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


KAPSALONS = {str(c).strip().upper() for c in CHAPTER.get("kapsalons", [])}
KAPSALON_SECONDS = int(CHAPTER.get("kapsalon_minutes", 5) * 60)
KAPSALON_REVIVES = bool(CHAPTER.get("kapsalon_revives", True))
MAX_FAILS, COOLDOWN = 5, 60          # 5 wrong codes -> wait 60 seconds


def lease_record(leases, client_ip, now):
    """Each device: when it arrived, bonus seconds earned, codes used."""
    rec = leases.get(client_ip)
    if not isinstance(rec, dict):                 # first visit
        rec = {"start": now, "bonus": 0, "used": [], "fails": 0, "fail_at": 0}
        leases[client_ip] = rec
    return rec


def seconds_left(rec, now):
    total = CHAPTER["lease_minutes"] * 60 + rec["bonus"]
    return max(0, int(total - (now - rec["start"])))


def lease_remaining(client_ip):
    """Seconds left for this device. The first visit starts the lease."""
    leases = load(LEASES, {})
    now = time.time()
    is_new = not isinstance(leases.get(client_ip), dict)
    rec = lease_record(leases, client_ip, now)
    if is_new:
        save(LEASES, leases)
    return seconds_left(rec, now)


def redeem_kapsalon(client_ip, code):
    """Try a kapsalon code. Returns (ok, message, seconds_remaining)."""
    code = "".join(str(code).split()).upper()
    leases = load(LEASES, {})
    now = time.time()
    rec = lease_record(leases, client_ip, now)
    left = seconds_left(rec, now)

    def done(ok, msg):
        save(LEASES, leases)
        return ok, msg, seconds_left(rec, now)

    if rec["fails"] >= MAX_FAILS:
        wait = int(COOLDOWN - (now - rec["fail_at"]))
        if wait > 0:
            return done(False, f"too many attempts. retry in {wait} s")
        rec["fails"] = 0
    if not code:
        return done(False, "no code entered")
    if code not in KAPSALONS:
        rec["fails"] += 1
        rec["fail_at"] = now
        return done(False, "unknown code")
    if code in rec["used"]:
        return done(False, "code already used on this network")
    if left == 0 and not KAPSALON_REVIVES:
        return done(False, "lease expired. codes can't renew it")

    rec["used"].append(code)
    rec["fails"] = 0
    if left == 0:
        # Expired: restart the clock from now with the bonus time
        rec["bonus"] = (now - rec["start"]) - CHAPTER["lease_minutes"] * 60
    rec["bonus"] += KAPSALON_SECONDS
    return done(True, f"lease renewed +{fmt(KAPSALON_SECONDS)}")


def fmt(seconds):
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# Entry screen. Styled to sit next to the chapter interface; change freely.
ENTRY = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{ssid}</title>
<style>
  :root {{ --bg:#3a2cf5; --box:#111111; --line:#b8ad3c; --fg:#d6e6d3; --muted:#8f9b8c; }}
  body {{ margin:0; min-height:100vh; background:var(--bg); color:var(--fg);
         font:16px/1.6 ui-monospace, "Courier New", Menlo, monospace; }}
  main {{ max-width:32rem; margin:0 auto; padding:24px 16px; }}
  .box {{ background:var(--box); border:2px solid var(--line); border-radius:8px;
         padding:12px 14px; margin-bottom:14px; white-space:pre-wrap; }}
  .muted {{ color:var(--muted); }}
  form.code {{ display:flex; gap:8px; margin-top:8px; }}
  form.code input {{ flex:1; min-width:0; font:inherit; padding:8px; border-radius:4px;
                    border:0; background:#c8cdb8; color:#111; text-transform:uppercase; }}
  form.code button {{ font:inherit; padding:8px 12px; border-radius:4px; cursor:pointer;
                     border:2px solid var(--line); background:var(--box); color:var(--fg); }}
  .msg {{ margin-top:8px; }}
  a.enter {{ display:block; text-align:center; text-decoration:none; color:var(--box);
            background:var(--fg); border:2px solid var(--line); border-radius:8px;
            padding:14px; font-weight:bold; }}
</style></head>
<body><main>
<div class="box">connected to {ssid}
lease: <span id="lease">{lease}</span></div>
{body}
</main>
<script>
  var left = {remaining}, el = document.getElementById('lease');
  if (left > 0) setInterval(function () {{
    left = Math.max(0, left - 1);
    var m = Math.floor(left / 60), s = left % 60;
    el.textContent = left ? m + ':' + (s < 10 ? '0' : '') + s + ' remaining' : 'expired';
  }}, 1000);
</script>
</body></html>"""


def code_box(msg=""):
    if not KAPSALONS:
        return ""
    note = f'<div class="msg">{html.escape(msg)}</div>' if msg else ""
    return f"""<div class="box">found a kapsalon? enter its code:<form class="code" method="post" action="/kapsalon">
<input name="code" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="32">
<button type="submit">renew</button></form>{note}</div>"""


def entry_page(remaining, msg=""):
    ssid = html.escape(CHAPTER["ssid"])
    if remaining == 0:
        body = ('<div class="box">lease expired.\n'
                'this network has closed for your device.</div>')
        if KAPSALON_REVIVES:
            body += code_box(msg)
        return ENTRY.format(ssid=ssid, lease="expired", remaining=0, body=body)
    body = f"""{code_box(msg)}<div class="box">{html.escape(CHAPTER.get('intro', ''))}</div>
<div class="box muted">your phone may say this network has no internet.
choose "stay connected" / "use without internet".

for the best view, open {html.escape(CHAPTER['server_ip'])} in your normal browser.</div>
<a class="enter" href="/site/">{html.escape(CHAPTER.get('enter_label', 'enter'))}</a>"""
    return ENTRY.format(ssid=ssid, lease=fmt(remaining) + " remaining",
                        remaining=remaining, body=body)


class Portal(BaseHTTPRequestHandler):
    server_version = "roodkapje"

    def log_message(self, fmt_, *args):
        print(f"{self.client_address[0]} {fmt_ % args}")

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, value, code=200):
        self.send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"),
                  ctype="application/json; charset=utf-8")

    def redirect(self, to=HOME):
        self.send(302, b"", headers={"Location": to})

    def send_file(self, target):
        """Stream a file in chunks, with Range support.
        iPhones only play video if the server can send parts of a file
        (HTTP 206); streaming keeps memory use low on the Pi."""
        size = target.stat().st_size
        start, end = 0, size - 1
        code = 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes=") and size > 0:
            first = rng[6:].split(",")[0].strip()
            a, _, b = first.partition("-")
            try:
                if a == "":                      # "bytes=-500": last 500 bytes
                    start = max(0, size - int(b))
                else:
                    start = int(a)
                    if b:
                        end = min(int(b), size - 1)
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206

        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        length = max(0, end - start + 1)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(target, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(64 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the phone skipped ahead or closed the video; that's normal

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        host = (self.headers.get("Host") or "").split(":")[0]

        # Any request for another website (DNS points everything here)
        # or any OS connectivity check gets sent to the entry screen.
        if path in CAPTIVE_CHECKS or (PORT == 80 and host not in (CHAPTER["server_ip"], "")):
            return self.redirect()

        ip = self.client_address[0]
        remaining = lease_remaining(ip)

        if path == "/":
            msg = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("msg", [""])[0]
            return self.send(200, entry_page(remaining, msg[:80]).encode("utf-8"))

        if path == "/lease":
            return self.send_json({"remaining": remaining, "ssid": CHAPTER["ssid"],
                                   "chapter": CHAPTER.get("chapter"),
                                   "title": CHAPTER.get("title")})

        if path == "/guestbook":
            return self.send_json(load(GUESTBOOK, []))

        if path == "/site":
            return self.redirect("/site/")

        if path.startswith("/site/"):
            if remaining == 0:
                return self.redirect("/")       # back to the "lease expired" screen
            rel = urllib.parse.unquote(path[len("/site/"):])
            target = (SITE / rel).resolve()
            if target != SITE and not target.is_relative_to(SITE):
                return self.send(404, b"not found")
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                return self.send(404, b"not found")
            return self.send_file(target)

        return self.redirect()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/guestbook", "/kapsalon"):
            return self.redirect()
        length = min(int(self.headers.get("Content-Length") or 0), 4096)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        is_json = "json" in (self.headers.get("Content-Type") or "")
        if is_json:
            try:
                form = json.loads(raw)
                if not isinstance(form, dict):
                    form = {}
            except json.JSONDecodeError:
                form = {}
            field = lambda k: str(form.get(k, ""))
        else:
            form = urllib.parse.parse_qs(raw)
            field = lambda k: (form.get(k) or [""])[0]

        if path == "/kapsalon":
            ok, msg, left = redeem_kapsalon(self.client_address[0], field("code")[:32])
            if is_json:
                return self.send_json({"ok": ok, "message": msg, "remaining": left})
            return self.redirect("/?msg=" + urllib.parse.quote(msg))

        text, name = field("text").strip()[:500], field("name").strip()[:40]
        ok = bool(text) and lease_remaining(self.client_address[0]) > 0
        if ok:
            entries = load(GUESTBOOK, [])
            entries.append({"name": name, "text": text,
                            "time": time.strftime("%d %b %Y, %H:%M")})
            save(GUESTBOOK, entries)
        if is_json:
            return self.send_json({"ok": ok})
        self.redirect(self.headers.get("Referer") or "/site/")


if __name__ == "__main__":
    print(f"Chapter {CHAPTER['chapter']} ({CHAPTER['title']}) on port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Portal).serve_forever()
