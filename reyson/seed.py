# -*- coding: utf-8 -*-
"""
reyson.seed — korpus startowy: wiedza „z niemowlęctwa" Reysona.

Reyson rodzi się z małym, ale dobrze dobranym polskim korpusem:
• fakty o świecie (trójki podmiot–relacja–obiekt),
• reguły dziedziczenia („każdy ptak jest zwierzęciem"),
• przykłady intencji (trening sieci neuronowej),
• zdania wiedzy (pamięć asocjacyjna),
• korpus językowy (model generatywny n-gramowy).

Pliki leżą w dane/ i mają prosty format TSV — każdy może Reysona
„douczać" edytując tekst. Przy pierwszym uruchomieniu korpus jest
wczytywany i trenowany automatycznie (to trwa kilka sekund).
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from .pamiec import Pamiec
from . import nlp

KATALOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dane")


def _sciezka(nazwa: str) -> str:
    return os.path.join(KATALOG, nazwa)


def _czytaj_tsv(nazwa: str, min_kol: int) -> List[List[str]]:
    sciezka = _sciezka(nazwa)
    wiersze: List[List[str]] = []
    if not os.path.exists(sciezka):
        return wiersze
    with open(sciezka, encoding="utf-8") as f:
        for linia in f:
            linia = linia.strip()
            if not linia or linia.startswith("#"):
                continue
            czesci = [c.strip() for c in linia.split("\t")]
            if len(czesci) >= min_kol:
                wiersze.append(czesci)
    return wiersze


def wczytaj_korpus_startowy(pamiec: Pamiec, log: Optional[Callable[[str], None]] = None,
                            rozum=None) -> None:
    def say(m: str) -> None:
        if log:
            log("  " + m)

    # 1) fakty
    fakty = _czytaj_tsv("seed_fakty.tsv", 3)
    n_faktow = 0
    for wiersz in fakty:
        podmiot, relacja, obiekt = wiersz[0], wiersz[1], " ".join(wiersz[2:])
        # słowa faktów zasysamy do słownika (mapa polskiej pisowni przy wyświetlaniu)
        pamiec.zarejestruj_slowa(nlp.tokenizuj_wyswietl(podmiot + " " + obiekt))
        if pamiec.dodaj_fakt(podmiot, relacja, obiekt, zrodlo="korpus", ufnosc=0.95):
            n_faktow += 1
    say(f"fakty: {n_faktow}")

    # 2) uniwersalia (reguły)
    uni = _czytaj_tsv("seed_uniwersalia.tsv", 2)
    for a, b in uni:
        pamiec.dodaj_uniwersale(a, b)
    say(f"reguły (uniwersalia): {len(uni)}")

    # 3) wiedza tekstowa
    wiedza = _czytaj_tsv("seed_wiedza.tsv", 2)
    bufor: dict = {}
    for tytul, z in wiedza:
        bufor.setdefault(tytul, []).append(z)
    for tytul, zdania_w in bufor.items():
        for z in zdania_w:
            pamiec.zarejestruj_slowa(nlp.tokenizuj_wyswietl(z))
        pamiec.dodaj_wiedze(tytul, zdania_w, zrodlo="korpus")
    say(f"tematy wiedzy: {len(bufor)} (zdań: {len(wiedza)})")

    # 4) przykłady intencji
    intencje = _czytaj_tsv("seed_intencje.tsv", 2)
    for tekst, intencja in intencje:
        pamiec.dodaj_przyklad_intencji(tekst, intencja)
    say(f"przykłady intencji: {len(intencje)}")

    # 5) korpus językowy → n-gramy + słownik
    korpus_path = _sciezka("seed_korpus.txt")
    n_gramow = 0
    if os.path.exists(korpus_path):
        with open(korpus_path, encoding="utf-8") as f:
            tekst = f.read()
        zdania_k = nlp.zdania(tekst)
        for z in zdania_k:
            tokeny = nlp.tokenizuj_wyswietl(z)
            if len(tokeny) >= 3:
                pamiec.zarejestruj_slowa(tokeny)
                n_gramow += pamiec.ucz_ngramy(tokeny + ["."])
    say(f"n-gramy z korpusu: {n_gramow}")

    # 6) lokalne lekcje (m.in. programowanie) — wiedza dostępna od urodzenia
    katalog_lekcji = os.path.join(KATALOG, "lekcje")
    n_lekcji = 0
    if os.path.isdir(katalog_lekcji):
        if rozum is None:
            from .rozum import Rozum as _Rozum
            rozum = _Rozum(pamiec)
        import re as _re
        for plik in sorted(os.listdir(katalog_lekcji)):
            if not plik.endswith(".txt") or plik.startswith("."):
                continue
            try:
                with open(os.path.join(katalog_lekcji, plik), encoding="utf-8") as f:
                    tekst_l = f.read()
            except OSError:
                continue
            m = _re.search(r"^#\s*(.+)$", tekst_l, _re.MULTILINE)
            tytul = m.group(1).strip() if m else plik[:-4].replace("_", " ")
            zdania_l = [z for z in nlp.zdania(tekst_l) if not z.startswith("#")]
            for z in zdania_l:
                pamiec.zarejestruj_slowa(nlp.tokenizuj_wyswietl(z))
                pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl(z) + ["."])
                rozum.ucz_sie_z_zdania(z)  # definicje „X to Y” → fakty od urodzenia
            pamiec.dodaj_wiedze(tytul.lower(), zdania_l, zrodlo="lekcja")
            pamiec.meta_ustaw("lekcja:" + plik, "1")
            n_lekcji += 1
        if n_lekcji:
            pamiec.meta_ustaw("lekcje_przeczytane", str(n_lekcji))
    say(f"lokalne lekcje: {n_lekcji}")
