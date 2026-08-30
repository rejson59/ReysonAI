#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReysonAI — lekki, samorozwijający się system AI mówiący po polsku.

Użycie:
    python reyson.py                     # rozmowa (tryb interaktywny)
    python reyson.py --buduj             # (re)budowa umysłu z korpusu startowego
    python reyson.py --naucz-sie TEMAT   # nauka tematu (Wikipedia online / lekcje offline)
    python reyson.py --samorozwoj [N]    # N cykli samodzielnego rozwoju (domyślnie 1)
    python reyson.py --rada TEMAT        # rada agentów dyskutuje o temacie
    python reyson.py --sen               # konsolidacja pamięci („sen”)
    python reyson.py --statystyki        # stan umysłu (z trybem urządzenia)
    python reyson.py --dziennik [N]      # ostatnie wpisy z dziennika rozwoju
    python reyson.py --web [PORT]        # interfejs www (domyślnie port 8000)
    python reyson.py --test              # testy wewnętrzne

Wymagania: Python 3.8+, tylko biblioteka standardowa. RAM: < 100 MB.
Tryb pracy dopasowuje się automatycznie do urządzenia (REYSON_TRYB=mini|standard|turbo).
"""

from __future__ import annotations

import argparse
import sys
import time

from reyson import __nazwa__, __wersja__, __model__
from reyson.mozg import Mozg


def _nowy_mozg() -> Mozg:
    m = Mozg()
    m.upewnij_sie_ze_zbudowany(log=lambda s: print(s, flush=True))
    return m


def cmd_chat(m: Mozg, args) -> None:
    print(f"{__nazwa__} v{__wersja__} (model {__model__}) — pisz po polsku; "
          f"„pomoc” pokaże komendy, „do widzenia” kończy.")
    m.petla_czatu()


def cmd_naucz(m: Mozg, args) -> None:
    print(m.uczony.naucz_sie_tematu(args.temat, log=lambda s: print(s)))


def cmd_samorozwoj(m: Mozg, args) -> None:
    n = args.samorozwoj or 1
    for i in range(n):
        print(f"--- cykl samorozwoju {i + 1}/{n} ---")
        print(m.uczony.cykl_samorozwoju(log=lambda s: print(f"  · {s}")))
        if i < n - 1:
            time.sleep(1.0)  # grzeczność wobec API Wikipedii
    mtr = m.uczony.metryki()
    print(f"Poziom rozwoju po cyklach: {mtr['poziom']}/100 "
          f"(fakty: {mtr['fakty']}, słownik: {mtr['slownik']})")


def cmd_rada(m: Mozg, args) -> None:
    print(m.daj_rade().dyskutuj(args.rada, log=lambda s: print(f"  · {s}")))


def cmd_sen(m: Mozg, args) -> None:
    print(m.uczony.sen(log=lambda s: print(f"  · {s}")))


def cmd_statystyki(m: Mozg, args) -> None:
    mtr = m.uczony.metryki()
    print("Stan umysłu Reysona:")
    for k, v in mtr.items():
        print(f"  {k:16} {v}")


def cmd_dziennik(m: Mozg, args) -> None:
    for ts, typ, tresc in m.pamiec.wpisy_dziennika(limit=args.dziennik or 20):
        import datetime
        dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        print(f"[{dt}] {typ}: {tresc}")


def cmd_buduj(m: Mozg, args) -> None:
    import os
    import reyson.mozg as mz
    print("Usuwanie starego umysłu i budowa od zera…")
    m.pamiec.zamknij()
    if os.path.exists(m.sciezka_db):
        os.remove(m.sciezka_db)
    m2 = mz.Mozg()
    m2.zbuduj_siebie(log=lambda s: print(s))
    m2.zamknij()
    print("Umysł zbudowany. Uruchom ponownie, aby rozmawiać.")


def cmd_web(m: Mozg, args) -> None:
    from reyson.web import uruchom_serwer
    uruchom_serwer(m, port=args.web or 8000)


def main() -> int:
    ap = argparse.ArgumentParser(prog="reyson", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wersja", action="version", version=f"{__nazwa__} {__wersja__}")
    ap.add_argument("--buduj", action="store_true", help="budowa umysłu od zera")
    ap.add_argument("--naucz-sie", metavar="TEMAT", dest="temat", help="nauka tematu z Wikipedii")
    ap.add_argument("--samorozwoj", nargs="?", type=int, const=1, metavar="N",
                    help="N cykli autonomicznego rozwoju")
    ap.add_argument("--rada", metavar="TEMAT",
                    help="rada agentów dyskutuje o temacie")
    ap.add_argument("--sen", action="store_true", help="konsolidacja pamięci")
    ap.add_argument("--statystyki", action="store_true", help="stan umysłu")
    ap.add_argument("--dziennik", nargs="?", type=int, const=20, metavar="N",
                    help="ostatnie wpisy dziennika rozwoju")
    ap.add_argument("--web", nargs="?", type=int, const=8000, metavar="PORT",
                    help="interfejs www")
    ap.add_argument("--test", action="store_true", help="testy wewnętrzne")
    args = ap.parse_args()

    if args.test:
        import unittest
        loader = unittest.TestLoader()
        suite = loader.discover("testy")
        wynik = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if wynik.wasSuccessful() else 1

    if args.buduj:
        import os
        import reyson.mozg as mz
        sciezka = os.path.join(mz.DANE_KATALOG, "umysl.db")
        for sufiks in ("", "-wal", "-shm"):
            if os.path.exists(sciezka + sufiks):
                os.remove(sciezka + sufiks)
        m = mz.Mozg()
        m.zbuduj_siebie(log=lambda s: print(s))
        m.zamknij()
        return 0

    m = _nowy_mozg()
    try:
        if args.temat:
            cmd_naucz(m, args)
        elif args.rada:
            cmd_rada(m, args)
        elif args.samorozwoj is not None:
            cmd_samorozwoj(m, args)
        elif args.sen:
            cmd_sen(m, args)
        elif args.statystyki:
            cmd_statystyki(m, args)
        elif args.dziennik is not None:
            cmd_dziennik(m, args)
        elif args.web:
            cmd_web(m, args)
        else:
            cmd_chat(m, args)
    finally:
        m.zamknij()
    return 0


if __name__ == "__main__":
    sys.exit(main())
