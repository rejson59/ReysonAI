# -*- coding: utf-8 -*-
"""
reyson.pamiec — długotrwała pamięć Reysona (SQLite).

Przechowuje: fakty (trójki podmiot–relacja–obiekt), słownik, statystyki
n-gramowe (model generatywny), przykłady intencji, dialogi, oceny i dziennik
rozwoju. Całość w jednym pliku bazy — lekko i przenośnie.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Iterable, List, Optional, Sequence, Tuple

from . import nlp

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    klucz TEXT PRIMARY KEY,
    wartosc TEXT
);
CREATE TABLE IF NOT EXISTS slowa (
    slowo TEXT PRIMARY KEY,
    licznik INTEGER DEFAULT 1,
    pierwsze INTEGER
);
CREATE TABLE IF NOT EXISTS fakty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podmiot TEXT NOT NULL,
    relacja TEXT NOT NULL,
    obiekt TEXT NOT NULL,
    zrodlo TEXT DEFAULT 'rozmowa',
    ufnosc REAL DEFAULT 0.8,
    ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fakty_podmiot ON fakty(podmiot);
CREATE INDEX IF NOT EXISTS idx_fakty_obiekt ON fakty(obiekt);
CREATE TABLE IF NOT EXISTS uniwersalia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zrodlo_klasy TEXT NOT NULL,     -- "każdy ptak"
    cel_klasy TEXT NOT NULL,        -- "jest zwierzęciem"
    zrodlo TEXT DEFAULT 'rozmowa',
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS wiedza (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tytul TEXT,
    zdanie TEXT NOT NULL,
    zrodlo TEXT,
    ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_wiedza_tytul ON wiedza(tytul);
CREATE TABLE IF NOT EXISTS ngramy (
    n INTEGER NOT NULL,
    kontekst TEXT NOT NULL,
    slowo TEXT NOT NULL,
    licznik INTEGER DEFAULT 1,
    PRIMARY KEY (n, kontekst, slowo)
);
CREATE TABLE IF NOT EXISTS intencje (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tekst TEXT NOT NULL,
    intencja TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_intencje_unikalne ON intencje(tekst, intencja);
CREATE TABLE IF NOT EXISTS przepisy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    temat TEXT NOT NULL,
    jezyk TEXT DEFAULT 'python',
    kod TEXT NOT NULL,
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS dialogi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sesja TEXT,
    rola TEXT NOT NULL,
    tresc TEXT NOT NULL,
    intencja TEXT,
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS oceny (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ocena INTEGER NOT NULL,
    kontekst TEXT,
    ts INTEGER
);
CREATE TABLE IF NOT EXISTS dziennik (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER,
    typ TEXT NOT NULL,
    tresc TEXT NOT NULL
);
"""


class Pamiec:
    """Fasada na bazę SQLite — cała pamięć długotrwała Reysona."""

    def __init__(self, sciezka: str = "dane/umysl.db"):
        self._mapa_pisowni: Optional[dict] = None
        self.sciezka = sciezka
        #: maksymalny rząd n-gramów (ustawia profil; 3 = lekko, 4 = tryb turbo)
        self.maks_n_gramu = 3
        katalog = os.path.dirname(sciezka)
        if katalog:
            os.makedirs(katalog, exist_ok=True)
        # check_same_thread=False: serwer www obsługuje żądania w wątkach,
        # dostęp serializuje blokada w reyson/web.py (jeden mózg = jedna myśl)
        self.db = sqlite3.connect(sciezka, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- narzędzia ---------------------------------------------------------

    @staticmethod
    def teraz() -> int:
        return int(time.time())

    def meta_pobierz(self, klucz: str) -> Optional[str]:
        w = self.db.execute("SELECT wartosc FROM meta WHERE klucz=?", (klucz,)).fetchone()
        return w[0] if w else None

    def meta_ustaw(self, klucz: str, wartosc: str) -> None:
        self.db.execute(
            "INSERT INTO meta(klucz,wartosc) VALUES(?,?) "
            "ON CONFLICT(klucz) DO UPDATE SET wartosc=excluded.wartosc",
            (klucz, str(wartosc)),
        )
        self.db.commit()

    def meta_pobierz_int(self, klucz: str, domyslne: int = 0) -> int:
        w = self.meta_pobierz(klucz)
        try:
            return int(w) if w is not None else domyslne
        except (TypeError, ValueError):
            return domyslne

    def meta_zwieksz(self, klucz: str, o_ile: int = 1) -> int:
        nowa = self.meta_pobierz_int(klucz) + o_ile
        self.meta_ustaw(klucz, str(nowa))
        return nowa

    def zapisz_dziennik(self, typ: str, tresc: str) -> None:
        self.db.execute(
            "INSERT INTO dziennik(ts,typ,tresc) VALUES(?,?,?)",
            (self.teraz(), typ, tresc),
        )
        self.db.commit()

    def wpisy_dziennika(self, limit: int = 50) -> List[Tuple[int, str, str]]:
        return self.db.execute(
            "SELECT ts,typ,tresc FROM dziennik ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # -- słownik -----------------------------------------------------------

    def mapa_pisowni(self) -> dict:
        """Mapa: forma znormalizowana → najlepsza forma wyświetlania (ze słownika).

        Wybiera najczęstszą odnalezioną formę (podstawowa zwykle wygrywa),
        przy remisie preferując tę z polskimi znakami — „Wisła”, nie „Wisłą”.
        """
        if getattr(self, "_mapa_pisowni", None) is None:
            najlepsze: dict = {}
            for slowo, licznik in self.db.execute("SELECT slowo, licznik FROM slowa"):
                k = nlp.normalizuj(slowo)
                wynik = (licznik, 1 if slowo != k else 0)
                if k not in najlepsze or wynik > najlepsze[k][0]:
                    najlepsze[k] = (wynik, slowo)
            self._mapa_pisowni = {k: v[1] for k, v in najlepsze.items()}
        return self._mapa_pisowni

    def zarejestruj_slowa(self, tokens: Iterable[str]) -> int:
        """Dodaje nowe słowa do słownika; zwraca ile było nowych."""
        nowe = 0
        for t in set(tokens):
            cur = self.db.execute(
                "INSERT INTO slowa(slowo,licznik,pierwsze) VALUES(?,1,?) "
                "ON CONFLICT(slowo) DO UPDATE SET licznik=licznik+1",
                (t, self.teraz()),
            )
            if self._mapa_pisowni is not None:
                # dopisz nową formę, jeśli jest częstsza albo jedyna (uproszczenie:
                # dokładne przeliczanie nastąpi przy kolejnej odbudowie mapy)
                klucz = nlp.normalizuj(t)
                if klucz not in self._mapa_pisowni or t != klucz:
                    self._mapa_pisowni[klucz] = t
            nowe += 1 if cur.lastrowid else 0
        self.db.commit()
        return nowe

    def rozmiar_slownika(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM slowa").fetchone()[0]

    # -- fakty (trójki) ------------------------------------------------------

    def dodaj_fakt(self, podmiot: str, relacja: str, obiekt: str,
                   zrodlo: str = "rozmowa", ufnosc: float = 0.8) -> bool:
        # klucze pamięci są znormalizowane (małe litery, bez diakrytyków),
        # dzięki czemu zapytania zawsze trafiają niezależnie od formy
        podmiot, relacja, obiekt = nlp.normalizuj(podmiot), nlp.normalizuj(relacja), nlp.normalizuj(obiekt)
        if not podmiot or not obiekt:
            return False
        ist = self.db.execute(
            "SELECT 1 FROM fakty WHERE podmiot=? AND relacja=? AND obiekt=?",
            (podmiot, relacja, obiekt),
        ).fetchone()
        if ist:
            return False
        self.db.execute(
            "INSERT INTO fakty(podmiot,relacja,obiekt,zrodlo,ufnosc,ts) VALUES(?,?,?,?,?,?)",
            (podmiot, relacja, obiekt, zrodlo, ufnosc, self.teraz()),
        )
        self.db.commit()
        return True

    def dopasuj_temat(self, podmiot: str) -> Optional[str]:
        """Zwraca kanoniczną nazwę tematu z pamięci (lub None).

        Kolejność prób: dokładne dopasowanie → ten sam rdzeń (odmiana) →
        nazwa zawiera temat (np. „kopernik” ⊂ „mikolaj kopernik”).
        """
        p = nlp.normalizuj(podmiot).strip()
        if not p:
            return None
        if self.db.execute("SELECT 1 FROM fakty WHERE podmiot=?", (p,)).fetchone():
            return p
        # poziom 2: ten sam rdzeń (odmiana przez przypadki)
        k = nlp.kanon(p)
        kandydaci = [r[0] for r in self.db.execute(
            "SELECT DISTINCT podmiot FROM fakty WHERE podmiot LIKE ?", (k[: max(3, len(k) - 2)] + "%",)
        ).fetchall()]
        pasujacy = [c for c in kandydaci if nlp.tez_jest_to(p, c)]
        # poziom 3: „kopernik” ⊂ „mikolaj kopernik”
        if not pasujacy and len(p) >= 4:
            pasujacy = [r[0] for r in self.db.execute(
                "SELECT DISTINCT podmiot FROM fakty WHERE podmiot LIKE ?", (f"%{p}%",)
            ).fetchall() if len(r[0]) > len(p)][:5]
        if not pasujacy:
            return None
        pasujacy.sort(key=lambda c: 0 if c == p else -min(len(c), len(p)))
        return pasujacy[0]

    def fakty_o(self, podmiot: str) -> List[Tuple[str, str]]:
        """Fakty o temacie — z tolerancją na polską odmianę i warianty nazw."""
        p = self.dopasuj_temat(podmiot)
        if p is None:
            return []
        return self.db.execute(
            "SELECT relacja,obiekt FROM fakty WHERE podmiot=? ORDER BY ufnosc DESC, id DESC",
            (p,),
        ).fetchall()

    def fakty_z_obiektem(self, obiekt: str) -> List[Tuple[str, str]]:
        obiekt = nlp.normalizuj(obiekt)
        return self.db.execute(
            "SELECT podmiot,relacja FROM fakty WHERE obiekt=? ORDER BY id DESC LIMIT 50",
            (obiekt,),
        ).fetchall()

    def wszystkie_fakty(self) -> List[Tuple[str, str, str]]:
        return self.db.execute(
            "SELECT podmiot,relacja,obiekt FROM fakty ORDER BY id"
        ).fetchall()

    def liczba_faktow(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM fakty").fetchone()[0]

    # -- uniwersalia ("każdy X jest Y") --------------------------------------

    def dodaj_uniwersale(self, zrodlo_klasy: str, cel_klasy: str) -> bool:
        zrodlo_klasy, cel_klasy = nlp.normalizuj(zrodlo_klasy), nlp.normalizuj(cel_klasy)
        if not zrodlo_klasy or not cel_klasy or zrodlo_klasy == cel_klasy:
            return False
        ist = self.db.execute(
            "SELECT 1 FROM uniwersalia WHERE zrodlo_klasy=? AND cel_klasy=?",
            (zrodlo_klasy, cel_klasy),
        ).fetchone()
        if ist:
            return False
        self.db.execute(
            "INSERT INTO uniwersalia(zrodlo_klasy,cel_klasy,ts) VALUES(?,?,?)",
            (zrodlo_klasy, cel_klasy, self.teraz()),
        )
        self.db.commit()
        return True

    def wszystkie_uniwersalia(self) -> List[Tuple[str, str]]:
        return self.db.execute(
            "SELECT zrodlo_klasy,cel_klasy FROM uniwersalia"
        ).fetchall()

    def wzmacniaj_fakt(self, podmiot: str, relacja: str, obiekt: str) -> None:
        """Potwierdzenie faktu (np. przez radę agentów) podnosi jego ufność."""
        self.db.execute(
            "UPDATE fakty SET ufnosc=MIN(0.99, ufnosc+0.03) "
            "WHERE podmiot=? AND relacja=? AND obiekt=?",
            (nlp.normalizuj(podmiot), nlp.normalizuj(relacja), nlp.normalizuj(obiekt)),
        )
        self.db.commit()

    # -- wiedza tekstowa ------------------------------------------------------

    def dodaj_wiedze(self, tytul: str, zdania_wiedzy: Iterable[str], zrodlo: str) -> int:
        n = 0
        for z in zdania_wiedzy:
            z = z.strip()
            if 10 < len(z) < 600:
                self.db.execute(
                    "INSERT INTO wiedza(tytul,zdanie,zrodlo,ts) VALUES(?,?,?,?)",
                    (tytul.strip().lower(), z, zrodlo, self.teraz()),
                )
                n += 1
        self.db.commit()
        return n

    def wiedza_o(self, tytul: str, limit: int = 8) -> List[Tuple[str, str]]:
        """Zdania wiedzy o temacie — z tolerancją odmiany i skrótów nazw."""
        t = nlp.normalizuj(tytul).strip()
        if not t:
            return []
        wiersze = self.db.execute(
            "SELECT tytul,zdanie FROM wiedza WHERE tytul=? ORDER BY id LIMIT ?",
            (t, limit),
        ).fetchall()
        if wiersze:
            return wiersze
        k = nlp.kanon(t)
        wiersze = self.db.execute(
            "SELECT tytul,zdanie FROM wiedza WHERE tytul LIKE ? ORDER BY id LIMIT ?",
            (k[: max(3, len(k) - 2)] + "%", limit),
        ).fetchall()
        if wiersze:
            return wiersze
        if len(t) >= 4:
            wiersze = self.db.execute(
                "SELECT tytul,zdanie FROM wiedza WHERE tytul LIKE ? ORDER BY id LIMIT ?",
                (f"%{t}%", limit),
            ).fetchall()
        return wiersze

    def szukaj_w_wiedzy(self, rdzenie: Sequence[str], limit: int = 5) -> List[Tuple[str, str, float]]:
        """Prosty scoring: liczba trafionych rdzeni w zdaniu."""
        if not rdzenie:
            return []
        wyniki: List[Tuple[str, str, float]] = []
        rows = self.db.execute("SELECT tytul,zdanie FROM wiedza ORDER BY id DESC LIMIT 20000").fetchall()
        for tytul, zd in rows:
            zn = set(zd.lower().split())
            traf = sum(1 for r in rdzenie if r in zd.lower() or any(r in w for w in zn))
            if traf:
                wyniki.append((tytul, zd, traf / len(rdzenie) + 0.01 * len(zd)))
        wyniki.sort(key=lambda x: -x[2])
        return wyniki[:limit]

    def temat_do_nauki(self) -> Optional[str]:
        """Wybiera temat, o którym wiadomo najmniej (do samorozwoju)."""
        row = self.db.execute(
            "SELECT tytul, COUNT(*) c FROM wiedza GROUP BY tytul ORDER BY c ASC, RANDOM() LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def tematy(self, limit: int = 40) -> List[str]:
        return [r[0] for r in self.db.execute(
            "SELECT DISTINCT tytul FROM wiedza ORDER BY RANDOM() LIMIT ?", (limit,)
        ).fetchall()]

    def liczba_zdan_wiedzy(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM wiedza").fetchone()[0]

    # -- n-gramy (model generatywny) ------------------------------------------

    def ucz_ngramy(self, tokens: Sequence[str], maks_n: Optional[int] = None) -> int:
        """Liczy n-gramy (2..maks_n) z sekwencji tokenów. Zwraca liczbę zapisów.

        Konteksty są dopełniane znacznikami „<s>”, dzięki czemu każdy rząd
        modelu zna rozpoczęcia zdań („<s> <s>”, „<s> <s> <s>”, …), a generator
        umie zaczynać nowe zdania i płynnie się cofać (backoff 4→3→2).
        """
        maks_n = maks_n or self.maks_n_gramu
        zapisy = 0
        for n in range(2, maks_n + 1):
            pad = ["<s>"] * (n - 1) + [t for t in tokens if t != "<s>"]
            if len(pad) < n:
                continue
            for i in range(len(pad) - n + 1):
                kontekst = " ".join(pad[i:i + n - 1])
                cel = pad[i + n - 1]
                self.db.execute(
                    "INSERT INTO ngramy(n,kontekst,slowo,licznik) VALUES(?,?,?,1) "
                    "ON CONFLICT(n,kontekst,slowo) DO UPDATE SET licznik=licznik+1",
                    (n, kontekst, cel),
                )
                zapisy += 1
        self.db.commit()
        return zapisy

    def nastepne_slowa(self, kontekst: Sequence[str], n: int = 3, limit: int = 8) -> List[Tuple[str, int]]:
        """Kandydaci na następne słowo dla kontekstu (backoff aż do bigramu)."""
        while n >= 2:
            okno = list(kontekst[-(n - 1):]) if n > 1 else []
            pad = ["<s>"] * (n - 1 - len(okno)) + okno
            k = " ".join(pad)
            rows = self.db.execute(
                "SELECT slowo,licznik FROM ngramy WHERE n=? AND kontekst=? ORDER BY licznik DESC LIMIT ?",
                (n, k, limit),
            ).fetchall()
            if rows:
                return rows
            n -= 1
        return []

    def liczba_ngramow(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM ngramy").fetchone()[0]

    def przytnij_ngramy(self, min_licznik: int = 2) -> int:
        """„Sen": usuwa n-gramy pojedyncze (szum) — kompresja pamięci."""
        cur = self.db.execute("DELETE FROM ngramy WHERE licznik < ?", (min_licznik,))
        self.db.commit()
        return cur.rowcount

    # -- intencje (przykłady treningowe) ---------------------------------------

    def dodaj_przyklad_intencji(self, tekst: str, intencja: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO intencje(tekst,intencja) VALUES(?,?)",
            (tekst.strip().lower(), intencja))
        self.db.commit()

    def przyklady_intencji(self) -> List[Tuple[str, str]]:
        return self.db.execute("SELECT tekst,intencja FROM intencje").fetchall()

    def liczba_przykladow(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM intencje").fetchone()[0]

    # -- dialogi i oceny ---------------------------------------------------------

    # -- przepisy kodu (umiejętność programowania) ------------------------------

    def dodaj_przepis(self, temat: str, kod: str, jezyk: str = "python") -> bool:
        temat_n = nlp.normalizuj(temat).strip()
        kod = kod.strip()
        if not temat_n or not kod:
            return False
        ist = self.db.execute(
            "SELECT 1 FROM przepisy WHERE temat=? AND kod=?", (temat_n, kod)
        ).fetchone()
        if ist:
            return False
        self.db.execute(
            "INSERT INTO przepisy(temat,jezyk,kod,ts) VALUES(?,?,?,?)",
            (temat_n, jezyk, kod, self.teraz()),
        )
        self.db.commit()
        return True

    def przepisy(self, limit: int = 50) -> List[Tuple[str, str, str]]:
        return self.db.execute(
            "SELECT temat,jezyk,kod FROM przepisy ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def liczba_przepisow(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM przepisy").fetchone()[0]

    # -- dialogi i oceny ----------------------------------------------------------

    def zapisz_dialog(self, sesja: str, rola: str, tresc: str, intencja: str = "") -> None:
        self.db.execute(
            "INSERT INTO dialogi(sesja,rola,tresc,intencja,ts) VALUES(?,?,?,?,?)",
            (sesja, rola, tresc, intencja, self.teraz()),
        )
        self.db.commit()

    def dodaj_ocene(self, ocena: int, kontekst: str = "") -> None:
        self.db.execute("INSERT INTO oceny(ocena,kontekst,ts) VALUES(?,?,?)",
                        (ocena, kontekst[:300], self.teraz()))
        self.db.commit()

    def statystyki_ocen(self) -> Tuple[int, int]:
        r = self.db.execute("SELECT COALESCE(SUM(ocena),0), COUNT(*) FROM oceny").fetchone()
        return int(r[0]), int(r[1])

    def zamknij(self) -> None:
        self.db.commit()
        self.db.close()
