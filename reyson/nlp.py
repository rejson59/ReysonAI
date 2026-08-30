# -*- coding: utf-8 -*-
"""
reyson.nlp — przetwarzanie języka polskiego.

Zawiera: normalizację tekstu, tokenizację, lekki stemmer polski,
listę stop-słów, odległość Levenshteina i pomocnicze dopasowywanie.
Wszystko w czystym Pythonie (bez zewnętrznych zależności).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Normalizacja
# ---------------------------------------------------------------------------

_MAPA_ZNAKOW = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s",
    "ź": "z", "ż": "z", "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N",
    "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z",
})


def bez_polskich_znakow(tekst: str) -> str:
    """Zamienia polskie znaki diakrytyczne na literę bazową."""
    return tekst.translate(_MAPA_ZNAKOW)


def normalizuj(tekst: str) -> str:
    """Tekst → małe litery, bez diakrytyków, bez zbędnych spacji."""
    tekst = tekst.lower().strip()
    tekst = bez_polskich_znakow(tekst)
    tekst = re.sub(r"\s+", " ", tekst)
    return tekst


# uwzględnia polskie litery — ważne dla tokenizacji „wyświetlanej” (z diakrytykami)
_TOKEN_RE = re.compile(r"[a-ząćęłńóśźż0-9]+(?:[-'][a-ząćęłńóśźż0-9]+)*", re.UNICODE)


def tokenizuj(tekst: str) -> List[str]:
    """Dzieli znormalizowany tekst na tokeny (słowa/liczby)."""
    return _TOKEN_RE.findall(normalizuj(tekst))


def tokenizuj_wyswietl(tekst: str) -> List[str]:
    """Tokeny do modelu generatywnego: małe litery, ALE z polskimi znakami —
    dzięki temu Reyson generuje zdania z poprawną polską pisownią."""
    tekst = tekst.lower().replace("ą", "ą")  # (czytelność — znaki zostają)
    return _TOKEN_RE.findall(tekst)


def zdania(tekst: str) -> List[str]:
    """Dzieli tekst na zdania po znakach interpunkcyjnych."""
    tekst = re.sub(r"\s+", " ", tekst.strip())
    if not tekst:
        return []
    czesci = re.split(r"(?<=[.!?…])\s+", tekst)
    wynik = []
    for czesc in czesci:
        czesc = czesc.strip()
        if czesc and not re.fullmatch(r"[.!?…]+", czesc):
            wynik.append(czesc)
    return wynik


# ---------------------------------------------------------------------------
# Stop-słowa (polskie, rozszerzona lista funkcjonalna)
# ---------------------------------------------------------------------------

STOP_SLOWA = frozenset("""
a aby ale albo az bardzo bez bo by byc byl byla bylo byly chce choo czasami
co czy czyli dla do gdy gdzie go i ich ile im inne iz ja jak jakie jako je
jednak jego jej jest jestem jeszcze jesli juz kazdy kiedy kto ktora ktore
ktorego ktorej ktory ktos ktorym lecz lub ma maja mam mało mi mnie moze mozna
mu my na nad nam nas nasz nawet nic nie no o od oraz oto owszem po pod przez
przy raz sie skad sobie sebe sa such szybki ze ta tak taka takie tam te tego
tej ten teraz tez to tobie tu tuż twoje ty tych tylko tym u w we wie wszyscy
z za ze zeby to znaczy właśnie zawsze coś coś coś
""".split())


# ---------------------------------------------------------------------------
# Lekki stemmer polski — obcina typowe końcówki fleksyjne
# ---------------------------------------------------------------------------

_KONCOWKI: Sequence[Tuple[str, int]] = sorted(
    [
        # rzeczowniki
        "ami", "ami", "ach", "ach", "ami", "owi", "owie", "ami", "om", "om",
        "ami", "y", "a", "e", "ę", "o", "ą", "u", "i", "ów", "om", "ami",
        # przymiotniki
        "ego", "ej", "emu", "ym", "ym", "ych", "ymi",
        # czasowniki (część)
        "iem", "esz", "emy", "ecie", "ą", "ał", "ała", "ało", "ali", "ę",
        "en", "ony", "any", "ony",
        # inne
        "cie", "esz", "źć", "ść", "ć",
    ],
    key=lambda k: -len(k),
)


def stem(slowo: str) -> str:
    """Heurystyczny stemmer polski (bez słowników — szybki i lekki)."""
    if len(slowo) <= 4:
        return slowo
    for konc in _KONCOWKI:
        konc2 = bez_polskich_znakow(konc)
        if slowo.endswith(konc2) and len(slowo) - len(konc2) >= 3:
            return slowo[: len(slowo) - len(konc2)]
    return slowo


def rdzenie(tokens: Sequence[str], bez_stop: bool = True) -> List[str]:
    """Tokeny → rdzenie (stemy), opcjonalnie bez stop-słów."""
    wynik = []
    for t in tokens:
        if bez_stop and t in STOP_SLOWA:
            continue
        wynik.append(stem(t))
    return wynik or list(tokens)


# ---------------------------------------------------------------------------
# Levenshtein + dopasowanie rozmyte
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str, maks: int = 3) -> int:
    """Odległość Levenshteina z wczesnym porzuceniem (> maks)."""
    if abs(len(a) - len(b)) > maks:
        return maks + 1
    poprz = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        aktual = [i]
        najm = i
        for j, cb in enumerate(b, 1):
            koszt = 0 if ca == cb else 1
            w = min(poprz[j] + 1, aktual[j - 1] + 1, poprz[j - 1] + koszt)
            aktual.append(w)
            if w < najm:
                najm = w
        if najm > maks:
            return maks + 1
        poprz = aktual
    return poprz[-1]


def podobne(a: str, b: str, prog: float = 0.82) -> bool:
    """Czy dwa słowa są podobne (ze względu na literówki)?"""
    a, b = normalizuj(a), normalizuj(b)
    if a == b:
        return True
    if not a or not b:
        return False
    dl = max(len(a), len(b))
    return levenshtein(a, b, maks=2) / dl <= (1.0 - prog)


_KONCOWKI_ODMIANY = ("ami", "ach", "ów", "iem", "omi", "ecie", "ach", "cie",
                     "ce", "ie", "ę", "ą", "y", "a", "e", "u", "i", "o")


def kanon(slowo: str) -> str:
    """Zgrubna forma podstawowa rzeczownika — obcina końcówki odmiany.

    „polsce” → „polsc”, „zwierzeciem” → „zwierzec”; łączone z dopasowaniem
    prefiksowym pozwala trafić w formę słownikową niezależnie od przypadka.
    """
    s = normalizuj(slowo)
    for konc in _KONCOWKI_ODMIANY:
        if s.endswith(konc) and len(s) - len(konc) >= 4:
            return s[: len(s) - len(konc)]
    return s


def tez_jest_to(a: str, b: str) -> bool:
    """Czy dwa zapisy oznaczają ten sam temat (z tolerancją na odmianę)?"""
    a, b = normalizuj(a), normalizuj(b)
    if a == b:
        return True
    ka, kb = kanon(a), kanon(b)
    if ka == kb:
        return True
    # „pols” vs „polsk” (polsce/polska): wspólny prefiks z małym zapasem
    wspolny = 0
    for ca, cb in zip(ka, kb):
        if ca != cb:
            break
        wspolny += 1
    return wspolny >= max(4, min(len(ka), len(kb)) - 2)


def znajdz_najblizsze(fraza: str, kandydaci: Sequence[str]) -> Tuple[str | None, float]:
    """Zwraca najbliższe dopasowanie z kandydatów (lub None)."""
    fraza = normalizuj(fraza)
    najlepszy, najlepszy_wynik = None, 0.0
    for k in kandydaci:
        kn = normalizuj(k)
        if fraza == kn:
            return k, 1.0
        if fraza in kn or kn in fraza:
            wynik = min(len(fraza), len(kn)) / max(len(fraza), len(kn))
        else:
            wynik = 1.0 - levenshtein(fraza, kn, maks=3) / max(len(fraza), len(kn), 1)
        if wynik > najlepszy_wynik:
            najlepszy, najlepszy_wynik = k, wynik
    return (najlepszy, najlepszy_wynik) if najlepszy_wynik >= 0.6 else (None, najlepszy_wynik)


# ---------------------------------------------------------------------------
# Wektoryzacja: worek rdzeni z hashowaniem (dla sieci neuronowej)
# ---------------------------------------------------------------------------

def hasz_wektor(tokens: Sequence[str], wymiar: int) -> List[float]:
    """Cechy tekstu → gęsty wektor o stałym wymiarze (haszowanie cech).

    Cechy: wyraz + jego rdzeń, z prefiksem przestrzeni („w:") — dzięki temu
    odmienione formy („pisarz”/„pisarza”) trafiają w to samo okolice wektora.
    """
    wek = [0.0] * wymiar
    for t in tokens:
        for cecha in ("w:" + t, "w:" + stem(t)):
            h = 0
            for ch in cecha:
                h = (h * 31 + ord(ch)) & 0xFFFFFF
            wek[h % wymiar] += 1.0
    norm = sum(wek) or 1.0
    return [x / norm for x in wek]


def dostosuj_pisownie(tekst: str, mapa: dict) -> str:
    """Przywraca polskie znaki, mapując znormalizowane słowa na formy ze słownika."""
    wyrazy = tekst.split(" ")
    wynik = []
    for w in wyrazy:
        rdzen = w
        interpunkcja = ""
        while rdzen and rdzen[-1] in ",.;:!?)":
            interpunkcja = rdzen[-1] + interpunkcja
            rdzen = rdzen[:-1]
        ladne = mapa.get(rdzen) or mapa.get(normalizuj(rdzen))
        wynik.append((ladne or rdzen) + interpunkcja)
    return " ".join(wynik)
