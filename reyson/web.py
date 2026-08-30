# -*- coding: utf-8 -*-
"""
reyson.web — interfejs www Reysona (czysta biblioteka standardowa).

Strona jest jednym plikiem HTML osadzonym w kodzie — bez frameworków,
bez node_modules, bez budowania. API (JSON): /api/wyslij, /api/stan,
/api/ucz-sie, /api/sen, /api/samorozwoj, /api/dziennik.

Uruchomienie:  python reyson.py --web 8080   (domyślnie port 8000)
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .mozg import Mozg

_STAN_ZABLOKOWANY = threading.Lock()


_STRONA = """<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReysonAI — samorozwijający się AI po polsku</title>
<style>
  :root {
    --tlo: #0e1116; --panel: #161b24; --obwod: #263043; --tekst: #e6ebf2;
    --przycichly: #8b96a8; --akcent: #4f8cff; --akcent2: #37c98b; --zle: #ff6b6b;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         background: var(--tlo); color: var(--tekst); height: 100vh;
         display: flex; flex-direction: column; }
  header { display: flex; align-items: baseline; gap: 12px; padding: 14px 20px;
           border-bottom: 1px solid var(--obwod); background: var(--panel); }
  header h1 { font-size: 20px; margin: 0; }
  header .model { color: var(--przycichly); font-size: 13px; }
  #stan { margin-left: auto; font-size: 13px; color: var(--przycichly); }
  #stan b { color: var(--akcent2); }
  main { flex: 1; overflow-y: auto; padding: 18px 20px; display: flex;
         flex-direction: column; gap: 10px; max-width: 900px; width: 100%;
         margin: 0 auto; }
  .wiad { max-width: 78%; padding: 10px 14px; border-radius: 14px;
          line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
  .uzytkownik { align-self: flex-end; background: var(--akcent); color: #fff;
                border-bottom-right-radius: 4px; }
  .reyson { align-self: flex-start; background: var(--panel);
            border: 1px solid var(--obwod); border-bottom-left-radius: 4px; }
  .reyson.system { border-color: var(--akcent2); }
  .pisze { color: var(--przycichly); font-style: italic; align-self: flex-start; }
  footer { border-top: 1px solid var(--obwod); background: var(--panel); padding: 12px 20px; }
  .pasek { max-width: 900px; margin: 0 auto; display: flex; gap: 8px; flex-wrap: wrap; }
  #wejscie { flex: 1; min-width: 220px; padding: 11px 14px; border-radius: 10px;
             border: 1px solid var(--obwod); background: var(--tlo); color: var(--tekst);
             font-size: 15px; outline: none; }
  #wejscie:focus { border-color: var(--akcent); }
  button { padding: 10px 14px; border-radius: 10px; border: 1px solid var(--obwod);
           background: var(--tlo); color: var(--tekst); cursor: pointer; font-size: 14px; }
  button:hover { border-color: var(--akcent); }
  button.glowne { background: var(--akcent); border-color: var(--akcent); color: #fff; }
  .podpowiedzi { max-width: 900px; margin: 8px auto 0; display: flex; gap: 6px;
                 flex-wrap: wrap; }
  .podpowiedzi button { font-size: 12px; padding: 6px 10px; color: var(--przycichly);
                        border-radius: 999px; }
</style>
</head>
<body>
<header>
  <h1>🧠 ReysonAI</h1>
  <span class="model">model RM-1 · czysty Python · działa na 4 GB RAM</span>
  <span id="stan">ładowanie…</span>
</header>
<main id="log"></main>
<footer>
  <div class="pasek">
    <input id="wejscie" placeholder="Napisz po polsku… (np. co to jest Wisła?)"
           autocomplete="off" autofocus>
    <button class="glowne" onclick="wyslij()">Wyślij</button>
    <button onclick="polecenie('/api/samorozwoj')" title="Autonomiczny cykl nauki">samorozwoj</button>
    <button onclick="polecenie('/api/sen')" title="Konsolidacja pamięci">sen</button>
    <button onclick="polecenie('/api/dziennik')" title="Dziennik rozwoju">dziennik</button>
  </div>
  <div class="podpowiedzi">
    <button onclick="wstaw('co to jest fotosynteza?')">co to jest fotosynteza?</button>
    <button onclick="wstaw('czy sokół jest zwierzęciem?')">czy sokół jest zwierzęciem?</button>
    <button onclick="wstaw('ile to 12 * (3 + 4)?')">ile to 12 * (3 + 4)?</button>
    <button onclick="wstaw('zapamiętaj, że lubię pierogi')">zapamiętaj, że lubię pierogi</button>
    <button onclick="wstaw('naucz się Wawel')">naucz się Wawel</button>
    <button onclick="wstaw('opowiedz historię')">opowiedz historię</button>
  </div>
</footer>
<script>
const log = document.getElementById('log');
const wejscie = document.getElementById('wejscie');

function dodaj(klasa, tekst) {
  const d = document.createElement('div');
  d.className = 'wiad ' + klasa;
  d.textContent = tekst;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}

async function odswiezStan() {
  try {
    const r = await fetch('/api/stan');
    const s = await r.json();
    document.getElementById('stan').innerHTML =
      `poziom <b>${s.poziom}/100</b> · fakty <b>${s.fakty}</b> · słownik <b>${s.slownik}</b> · n-gramy <b>${s.ngramy}</b>`;
  } catch (e) {}
}

async function api(sciezka, dane) {
  const r = await fetch(sciezka, dane ? {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(dane)
  } : undefined);
  return (await r.json()).odp || '(brak odpowiedzi)';
}

let zajety = false;
async function wykonaj(sciezka, dane, etykieta) {
  if (zajety) return;
  zajety = true;
  const czekaj = dodaj('pisze', etykieta);
  try {
    const odp = await api(sciezka, dane);
    czekaj.remove();
    dodaj('reyson system', odp);
    odswiezStan();
  } catch (e) {
    czekaj.remove();
    dodaj('reyson', 'Coś się zawiesiło w Warszawie… spróbuj ponownie.');
  }
  zajety = false;
  wejscie.focus();
}

function wyslij() {
  const t = wejscie.value.trim();
  if (!t) return;
  wejscie.value = '';
  dodaj('uzytkownik', t);
  wykonaj('/api/wyslij', {tekst: t}, 'Reyson myśli…');
}

function polecenie(sciezka) {
  const etykiety = {
    '/api/samorozwoj': 'Reyson sam się rozwija (pobiera wiedzę, wnioskuje)…',
    '/api/sen': 'Reyson zasypia — konsoliduje pamięć…',
    '/api/dziennik': 'Czytam dziennik rozwoju…'
  };
  wykonaj(sciezka, null, etykiety[sciezka] || 'Pracuję…');
}

function wstaw(t) { wejscie.value = t; wejscie.focus(); }

wejscie.addEventListener('keydown', e => { if (e.key === 'Enter') wyslij(); });

dodaj('reyson system',
  'Cześć! Jestem Reyson — mówię po polsku, wnioskuję, liczę i uczę się od Ciebie. ' +
  'Zapytaj o coś, naucz mnie czegoś albo naciśnij „samorozwoj”, a poczytam sobie sam.');
odswiezStan();
</script>
</body>
</html>
"""


def _zrob_handler(mozg: Mozg):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ReysonAI/1.0"

        def _wyslij_html(self) -> None:
            bajty = _STRONA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(bajty)))
            self.end_headers()
            self.wfile.write(bajty)

        def _wyslij_json(self, dane: dict) -> None:
            bajty = json.dumps(dane, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(bajty)))
            self.end_headers()
            self.wfile.write(bajty)

        def _odp_bezpiecznie(self, akcja) -> None:
            try:
                with _STAN_ZABLOKOWANY:  # jeden mózg — jedna myśl na raz
                    wynik = akcja()
                self._wyslij_json({"odp": wynik})
            except Exception as blad:  # pragma: no cover
                self._wyslij_json({"odp": f"Błąd wewnętrzny: {blad}"})

        def do_GET(self) -> None:
            sciezka = urllib.parse.urlparse(self.path).path
            if sciezka in ("/", "/index.html"):
                self._wyslij_html()
            elif sciezka == "/api/stan":
                self._wyslij_json(mozg.uczony.metryki())
            elif sciezka == "/api/dziennik":
                import datetime
                wpisy = mozg.pamiec.wpisy_dziennika(limit=15)
                tekst = "\n".join(
                    f"• [{datetime.datetime.fromtimestamp(t).strftime('%m-%d %H:%M')}] {typ}: {tresc}"
                    for t, typ, tresc in wpisy) \
                    or "Dziennik jest jeszcze pusty — dopiero się rodzę."
                self._wyslij_json({"odp": "Dziennik rozwoju (najnowsze wpisy):\n" + tekst})
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            sciezka = urllib.parse.urlparse(self.path).path
            dlugosc = int(self.headers.get("Content-Length") or 0)
            dane = {}
            if dlugosc:
                try:
                    dane = json.loads(self.rfile.read(dlugosc).decode("utf-8"))
                except Exception:
                    dane = {}
            if sciezka == "/api/wyslij":
                tekst = str(dane.get("tekst", ""))[:500]
                self._odp_bezpiecznie(lambda: mozg.odpowiedz(tekst))
            elif sciezka == "/api/ucz-sie":
                temat = str(dane.get("temat", ""))[:60]
                self._odp_bezpiecznie(lambda: mozg.uczony.naucz_sie_tematu(temat))
            elif sciezka == "/api/sen":
                self._odp_bezpiecznie(lambda: mozg.uczony.sen())
            elif sciezka == "/api/samorozwoj":
                self._odp_bezpiecznie(lambda: mozg.uczony.cykl_samorozwoju())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):  # cichy log
            pass

    return Handler


def uruchom_serwer(mozg: Mozg, port: int = 8000, host: str = "0.0.0.0") -> None:
    serwer = ThreadingHTTPServer((host, port), _zrob_handler(mozg))
    print(f"ReysonAI: interfejs www na http://{host}:{port} (Ctrl+C kończy)")
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print("\nDo zobaczenia!")
    finally:
        serwer.server_close()
        mozg.zamknij()
