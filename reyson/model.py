# -*- coding: utf-8 -*-
"""
reyson.model — model RM-1: hybrydowy „mózg" Reysona.

RM-1 składa się z trzech współpracujących warstw:

1. Sieć neuronowa (MLP, czysty Python) — rozpoznaje INTENCJĘ wypowiedzi.
   Uczy się metodą spadku gradientu; wagi można doszkalać w trakcie życia.
2. Pamięć asocjacyjna TF-IDF — przypomina sobie pasujące zdania z wiedzy.
3. Model generatywny n-gramowy (bigram/trigram z backoffem) — tworzy
   własne zdania (np. opowieści) na bazie tego, czego się nauczył.

Całość waży mniej niż 1 MB i działa płynnie na maszynie z 4 GB RAM.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from . import nlp
from .pamiec import Pamiec

INTENCJE = (
    "powitanie", "pozegnanie", "jak_sie_masz", "tozsamosc", "mozliwosci",
    "podziekowanie", "pytanie_fakt", "uczenie", "uniwersalne", "arytmetyka",
    "czas_data", "opowiadanie", "opinia", "pytanie_o_mnie", "pomoc",
    "imie_uzytkownika", "sprzatanie", "ocena_dobra", "ocena_zla", "inne",
)

# hiperparametry RM-1·NN (dobrane eksperymentalnie; patrz testy/)
_SKALA_CECH = 8.0        # wzmocnienie wektora cech — stabilny start tanh
_L2 = 2e-4               # regularyzacja wag wyjściowych
_LR_HI, _LR_LO = 0.15, 0.05
_EPOKI = 25


# ---------------------------------------------------------------------------
# 1. Sieć neuronowa — MLP z hashowanym workiem słów
# ---------------------------------------------------------------------------

class MLP:
    """Mała sieć neuronowa (wejście → ukryta warstwa → softmax).

    Wymiary domyślne: 512 wejść (hashowane rdzenie słów), 48 neuronów
    ukrytych (tanh), wyjście = liczba intencji. ~26 tys. parametrów.
    """

    def __init__(self, wejscia: int = 512, ukryta: int = 32, wyjscia: int = len(INTENCJE)):
        self.wejscia, self.ukryta, self.wyjscia = wejscia, ukryta, wyjscia
        self.W1 = [[random.uniform(-0.08, 0.08) for _ in range(ukryta)] for _ in range(wejscia)]
        self.b1 = [0.0] * ukryta
        self.W2 = [[random.uniform(-0.08, 0.08) for _ in range(wyjscia)] for _ in range(ukryta)]
        self.b2 = [0.0] * wyjscia

    # -- matematyka ----------------------------------------------------------

    @staticmethod
    def _softmax(z: List[float]) -> List[float]:
        m = max(z)
        e = [math.exp(v - m) for v in z]
        s = sum(e) or 1.0
        return [v / s for v in e]

    def przewiduj(self, x: Sequence[float]) -> Tuple[List[float], List[float]]:
        """Zwraca (ukryta, prawdopodobieństwa)."""
        h = []
        for j in range(self.ukryta):
            s = self.b1[j]
            kol = self.W1
            # szybkie mnożenie kolumnowe (sparse input!)
            for i, xi in enumerate(x):
                if xi:
                    s += xi * kol[i][j]
            h.append(math.tanh(s))
        z = []
        for k in range(self.wyjscia):
            s = self.b2[k]
            for j in range(self.ukryta):
                s += h[j] * self.W2[j][k]
            z.append(s)
        return h, self._softmax(z)

    def ucz_probke(self, x: Sequence[float], cel: int, lr: float = 0.05) -> float:
        """Jeden krok SGD. Zwraca stratę (cross-entropy)."""
        h, p = self.przewiduj(x)
        delta2 = [p[k] - (1.0 if k == cel else 0.0) for k in range(self.wyjscia)]
        # warstwa wyjściowa
        for j in range(self.ukryta):
            g = h[j]
            if abs(g) < 1e-9:
                continue
            wiersz = self.W2[j]
            for k in range(self.wyjscia):
                wiersz[k] -= lr * delta2[k] * g
        for k in range(self.wyjscia):
            self.b2[k] -= lr * delta2[k]
        # warstwa ukryta
        delta1 = [0.0] * self.ukryta
        for j in range(self.ukryta):
            s = 0.0
            for k in range(self.wyjscia):
                s += self.W2[j][k] * delta2[k]
            delta1[j] = (1.0 - h[j] * h[j]) * s
        for i, xi in enumerate(x):
            if not xi:
                continue
            wiersz = self.W1[i]
            for j in range(self.ukryta):
                wiersz[j] -= lr * delta1[j] * xi
        for j in range(self.ukryta):
            self.b1[j] -= lr * delta1[j]
        return -math.log(max(p[cel], 1e-9))

    # -- zapis / odczyt --------------------------------------------------------

    def zapisz(self, sciezka: str) -> None:
        dane = {
            "wymiar": [self.wejscia, self.ukryta, self.wyjscia],
            "W1": self.W1, "b1": self.b1, "W2": self.W2, "b2": self.b2,
        }
        os.makedirs(os.path.dirname(sciezka) or ".", exist_ok=True)
        with open(sciezka, "w", encoding="utf-8") as f:
            json.dump(dane, f, ensure_ascii=False)

    @classmethod
    def wczytaj(cls, sciezka: str) -> "MLP":
        with open(sciezka, "r", encoding="utf-8") as f:
            dane = json.load(f)
        net = cls(*dane["wymiar"])
        net.W1, net.b1, net.W2, net.b2 = dane["W1"], dane["b1"], dane["W2"], dane["b2"]
        return net

    def doskalaj(self, x: Sequence[float], cel: int, epoki: int = 4, lr: float = 0.03) -> float:
        """Uczenie się w trakcie życia — strata po doszkoleniu."""
        strata = 0.0
        for _ in range(epoki):
            strata = self.ucz_probke(x, cel, lr)
        return strata


# ---------------------------------------------------------------------------
# 2. Pamięć asocjacyjna TF-IDF
# ---------------------------------------------------------------------------

class PamiecAsocjacyjna:
    """Przypomina sobie zdania podobne tematycznie do zapytania."""

    def __init__(self) -> None:
        self.zdania: List[str] = []
        self.rdzenie_zdan: List[Counter] = []
        self.idf: Dict[str, float] = {}

    def dodaj(self, zdanie: str) -> None:
        r = nlp.rdzenie(nlp.tokenizuj(zdanie))
        if not r:
            return
        self.zdania.append(zdanie)
        self.rdzenie_zdan.append(Counter(r))

    def odbuduj_idf(self) -> None:
        df: Counter = Counter()
        for c in self.rdzenie_zdan:
            for t in c:
                df[t] += 1
        N = max(len(self.zdania), 1)
        self.idf = {t: math.log((N + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    def szukaj(self, zapytanie: str, limit: int = 3) -> List[Tuple[str, float]]:
        q = Counter(nlp.rdzenie(nlp.tokenizuj(zapytanie)))
        if not q or not self.zdania:
            return []
        wyniki: List[Tuple[int, float]] = []
        for idx, c in enumerate(self.rdzenie_zdan):
            wspolne = set(q) & set(c)
            if not wspolne:
                continue
            wynik = sum(self.idf.get(t, 1.0) * min(q[t], c[t]) for t in wspolne)
            norm = math.sqrt(sum(self.idf.get(t, 1.0) * v * v for t, v in q.items())) or 1.0
            wyniki.append((idx, wynik / norm))
        wyniki.sort(key=lambda p: -p[1])
        return [(self.zdania[i], w) for i, w in wyniki[:limit] if w > 0.35]


# ---------------------------------------------------------------------------
# 3. Model RM-1 — spina wszystko
# ---------------------------------------------------------------------------

class ModelRM1:
    def __init__(self, pamiec: Pamiec, katalog_modelu: str = "dane"):
        self.pamiec = pamiec
        self.katalog = katalog_modelu
        self.sciezka_wag = os.path.join(katalog_modelu, "rm1_wagi.json")
        self.net: Optional[MLP] = None
        self.asocjacje = PamiecAsocjacyjna()
        self.intencja_idx = {n: i for i, n in enumerate(INTENCJE)}

    # -- intencje ---------------------------------------------------------------

    @staticmethod
    def _augmentuj(tokens: List[str], rng: random.Random) -> List[List[str]]:
        """Powiększa mały zbiór treningowy prostymi parafrazami."""
        prefiksy = ("hej", "słuchaj", "powiedz mi", "reyson", "proszę", "no", "to")
        sufiksy = ("proszę", "no", "mi", "bardzo", "właśnie", "hej")
        wyniki = [list(tokens)]
        for _ in range(3):
            t = [w for w in tokens if not (len(tokens) > 3 and rng.random() < 0.15)]
            if not t:
                t = list(tokens)
            if rng.random() < 0.5:
                t = [rng.choice(prefiksy)] + t
            else:
                t = t + [rng.choice(sufiksy)]
            wyniki.append(t)
        return wyniki

    def zbuduj_mlp(self, epoki: int = _EPOKI, log=None) -> float:
        """Trenuje sieć intencji na przykładach z pamięci (z augmentacją i L2)."""
        przyklady = self.pamiec.przyklady_intencji()
        if not przyklady:
            return 0.0
        rng = random.Random(7)  # powtarzalność budowy
        net = MLP()
        dane: List[Tuple[List[float], int]] = []
        for t, i in przyklady:
            if i not in self.intencja_idx:
                continue
            tokeny = nlp.tokenizuj(t)
            for wariant in self._augmentuj(tokeny, rng):
                x = nlp.hasz_wektor(wariant, net.wejscia)
                dane.append(([v * _SKALA_CECH for v in x], self.intencja_idx[i]))
        strata = 0.0
        for epoka in range(epoki):
            rng.shuffle(dane)
            strata = 0.0
            lr = _LR_HI if epoka < epoki * 0.7 else _LR_LO
            for x, cel in dane:
                strata += net.ucz_probke(x, cel, lr=lr)
                for j in range(net.ukryta):
                    wiersz = net.W2[j]
                    for k in range(net.wyjscia):
                        wiersz[k] *= (1.0 - _L2)
            if log and (epoka + 1) % 5 == 0:
                log(f"  epoka {epoka + 1}/{epoki}: strata={strata / len(dane):.4f}")
        self.net = net
        net.zapisz(self.sciezka_wag)
        return strata / max(len(dane), 1)

    def wczytaj_mlp(self) -> bool:
        if os.path.exists(self.sciezka_wag):
            try:
                self.net = MLP.wczytaj(self.sciezka_wag)
                return True
            except Exception:
                pass
        return False

    def rozpoznaj_intencje(self, tekst: str) -> Tuple[str, float]:
        """Intencja: najpierw kuratorowana lista fraz (pewniaki), potem sieć RM-1·NN."""
        klawisz = self.intencja_z_klawiszy(tekst)
        if klawisz != "inne":
            return klawisz, 0.95
        if self.net is None and not self.wczytaj_mlp():
            return "inne", 0.5
        x = nlp.hasz_wektor(nlp.tokenizuj(tekst), self.net.wejscia)
        x = [v * _SKALA_CECH for v in x]
        _, p = self.net.przewiduj(x)
        best = max(range(len(p)), key=lambda k: p[k])
        # sieci pomaga detekcja liczb/działań — krzywa bywa niepewna
        if INTENCJE[best] != "arytmetyka" and self.wyglada_jak_matma(tekst):
            return "arytmetyka", 0.99
        return INTENCJE[best], p[best]

    @staticmethod
    def wyglada_jak_matma(tekst: str) -> bool:
        t = nlp.normalizuj(tekst)
        if not any(ch.isdigit() for ch in t):
            return False
        return bool(any(sym in t for sym in "+-*/x^%=") or
                    any(s in t for s in ("plus", "minus", "razy", "podziel", "ile to",
                                         "oblicz", "ile jest", "procent", "pierwiastek")))

    KLUCZE: Dict[str, Sequence[str]] = {
        "powitanie": ("czesc", "hej", "witaj", "dzien dobry", "dobry wieczor",
                      "siema", "hello", "witam", "halo", "eloo", "dobranoc"),
        "pozegnanie": ("do widzenia", "papa", "narazie", "na razie", "zegnaj",
                       "koniec", "pa pa", "bywaj", "dobranoc mam isc"),
        "podziekowanie": ("dziekuje", "dzieki", "dzieki bardzo", "wielkie dzieki", "thx"),
        "tozsamosc": ("kim jestes", "kto ty jestes", "jak sie nazywasz", "coto za program",
                      "co to za program", "co ty jestes", "przedstaw sie"),
        "mozliwosci": ("co umiesz", "co potrafisz", "jakie masz mozliwosci", "co wiesz zrobic",
                       "do czego sluzysz", "pomocy", "co mozesz"),
        "jak_sie_masz": ("jak sie masz", "co u ciebie", "jak leci", "co robisz", "jak tam"),
        "czas_data": ("ktora godzina", "jaki dzien", "jaka data", "dzisiejsza data", "ktory dzis"),
        "opowiadanie": ("opowiedz", "opowiadaj", "wymysl historie", "bajke", "opowiedz cos"),
        "pomoc": ("pomoc", "help", "co mam robic", "instrukcja", "komendy"),
        "ocena_dobra": ("dobra odpowiedz", "swietnie", "super", "brawo", "madry jestes",
                        "dobrze", "ladnie", "ekstra"),
        "ocena_zla": ("zla odpowiedz", "blednie", "nie rozumiesz", "glupio", "nie tak",
                      "nieprawda", "bledna odpowiedz", "nie o to chodzi"),
    }

    def intencja_z_klawiszy(self, tekst: str) -> str:
        t = nlp.normalizuj(tekst)
        for intencja, frazy in self.KLUCZE.items():
            for fraza in frazy:
                if fraza in t:
                    return intencja
        return "inne"

    # -- uczenie w trakcie życia ---------------------------------------------------

    def doskalaj_intencje(self, tekst: str, intencja: str) -> bool:
        """Uczy się nowej korekty od użytkownika (samodoskonalenie)."""
        if self.net is None or intencja not in self.intencja_idx:
            return False
        x = nlp.hasz_wektor(nlp.tokenizuj(tekst), self.net.wejscia)
        x = [v * _SKALA_CECH for v in x]
        self.net.doskalaj(x, self.intencja_idx[intencja])
        self.net.zapisz(self.sciezka_wag)
        self.pamiec.dodaj_przyklad_intencji(tekst, intencja)
        return True

    # -- pamięć asocjacyjna ------------------------------------------------------------

    def odbuduj_asocjacje(self) -> int:
        """Ładuje wiedzę tekstową + fakty do pamięci asocjacyjnej."""
        self.asocjacje = PamiecAsocjacyjna()
        for tytul, zd in self.pamiec.db.execute("SELECT tytul,zdanie FROM wiedza"):
            self.asocjacje.dodaj(zd if not tytul else f"{tytul}: {zd}")
        for pod, rel, obj in self.pamiec.wszystkie_fakty():
            self.asocjacje.dodaj(f"{pod} {rel} {obj}")
        self.asocjacje.odbuduj_idf()
        return len(self.asocjacje.zdania)

    def przypomnij(self, zapytanie: str, limit: int = 2) -> List[Tuple[str, float]]:
        return self.asocjacje.szukaj(zapytanie, limit)

    # -- generowanie (n-gramy) ---------------------------------------------------------

    def generuj(self, seed: Sequence[str], maks_slow: int = 22) -> str:
        """Tworzy zdanie startując od nasionka (trigram z backoffem).

        Nasionko jest ważne tylko wtedy, gdy model zna jego konteksty —
        w przeciwnym razie zaczynamy od losowego znaku zdania z korpusu.
        """
        tokeny: List[str] = []
        for t in (s for s in seed if s):
            istnieje = self.pamiec.db.execute(
                "SELECT 1 FROM ngramy WHERE n=2 AND kontekst=? LIMIT 1", (t,)
            ).fetchone()
            if istnieje:
                tokeny = [t]
                break
        if not tokeny:
            # start „z pustego zdania”: rozkład pierwszych słów zdań z całej wiedzy
            row = self.pamiec.db.execute(
                "SELECT slowo, licznik FROM ngramy WHERE n=3 AND kontekst='<s> <s>' "
                "ORDER BY licznik DESC LIMIT 12"
            ).fetchall()
            if not row:
                return ""
            tokeny = [random.choices([r[0] for r in row],
                                     weights=[r[1] for r in row])[0]]
        for _ in range(maks_slow):
            kandydaci = self.pamiec.nastepne_slowa(tokeny, n=3 if len(tokeny) >= 2 else 2)
            if not kandydaci:
                # kontynuacja awaryjna: losowe częste słowo (bez interpunkcji/startów)
                awaryjne = self.pamiec.db.execute(
                    "SELECT slowo FROM ngramy WHERE n=2 "
                    "AND slowo NOT IN ('.', '!', '?', ',', '<s>') "
                    "GROUP BY slowo ORDER BY SUM(licznik) DESC LIMIT 60"
                ).fetchall()
                if not awaryjne:
                    break
                tokeny.append(random.choice(awaryjne)[0])
                continue
            slowa, wagi = zip(*kandydaci)
            nastepny = random.choices(slowa, weights=wagi)[0]
            if nastepny in ("<s>",):
                continue
            tokeny.append(nastepny)
            if nastepny in (".", "!", "?") or len(tokeny) >= maks_slow:
                break
        tekst = " ".join(tokeny)
        tekst = re.sub(r"\s+([.!?,])", r"\1", tekst)
        tekst = tekst[0].upper() + tekst[1:]
        if tekst[-1] not in ".!?":
            tekst += "."
        return tekst
