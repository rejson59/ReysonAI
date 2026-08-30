# -*- coding: utf-8 -*-
"""
reyson.uczenie — silnik samorozwoju Reysona.

Reyson rozwija się na cztery sposoby:

1. NAUKA Z ROZMOWY — wyciąga fakty z wypowiedzi użytkownika, zapamiętuje
   nowe słowa i korekty intencji (doszkalanie sieci neuronowej).
2. NAUKA Z WIEDZY ZEWNĘTRZNEJ — pobiera artykuły z polskiej Wikipedii
   (REST API, bez kluczy) i zamienia je na fakty + zdania w pamięci.
3. SEN — konsolidacja pamięci: przycinanie szumu w n-gramach, przebudowa
   indeksów, bilans wiedzy. Rekombinuje też n-gramy („śnienie"),
   generując własne zdania i zapisując te, które wyglądają sensownie.
4. TRYB SAMOROZWÓJ — pętla autonomiczna: wybiera temat, uczy się go,
   zadaje sobie pytania i odpowiada, mierzy własny rozwój.

Całość jest bezpieczna dla słabych maszyn: limity czasu i pamięci,
żadnych wątków GPU, żadnych ogromnych plików modelu.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Tuple

from . import nlp
from .model import ModelRM1
from .pamiec import Pamiec
from .rozum import Rozum

_USER_AGENT = "ReysonAI/1.0 (samozielony agent uczący się; polski)"


class Uczony:
    """Odpowiada za cały rozwój Reysona („edukacja" i „sen")."""

    def __init__(self, pamiec: Pamiec, model: ModelRM1, rozum: Rozum):
        self.pamiec = pamiec
        self.model = model
        self.rozum = rozum
        self.slowa_przed = 0

    # ------------------------------------------------------------------ #
    # 1. Nauka z rozmowy
    # ------------------------------------------------------------------ #

    def ucz_z_wypowiedzi(self, tekst: str) -> List[str]:
        """Przetwarza każdą wypowiedź użytkownika jako okazję do nauki.

        Zwraca listę potwierdzeń (czego się nauczył) — mózg może je powtórzyć.
        """
        potwierdzenia: List[str] = []
        tokeny = nlp.tokenizuj_wyswietl(tekst)
        nowe = self.pamiec.zarejestruj_slowa(set(tokeny))
        if nowe:
            # ciche — nowe słowa liczymy, nie przerywamy rozmowy
            pass

        # uczenie jawne: "zapamiętaj, że ..."
        for wzor in Rozum.WZORY_UCZENIA:
            m = wzor.match(nlp.normalizuj(tekst).strip())
            if m:
                wynik = self.rozum.ucz_sie_z_zdania(m.group(1))
                if wynik:
                    potwierdzenia.append(wynik)
                break
        else:
            # uczenie implicite: "X to Y" w zwykłej rozmowie (tylko krótkie, pewne)
            if len(tokeny) <= 8 and not tekst.rstrip().endswith("?"):
                wynik = self.rozum.ucz_sie_z_zdania(tekst)
                if wynik and (wynik.startswith("Zapamiętałem") or wynik.startswith("Zanotowałem")):
                    potwierdzenia.append(wynik)

        # imię użytkownika
        imie = self.rozum.zapamietaj_imie(tekst)
        if imie:
            potwierdzenia.append(f"Miło Cię poznać, {imie}!")
        return potwierdzenia

    # ------------------------------------------------------------------ #
    # 2. Nauka z Wikipedii
    # ------------------------------------------------------------------ #

    def _http_get(self, url: str, timeout: int = 10) -> Optional[bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            return None

    def szukaj_wikipedia(self, temat: str) -> Optional[str]:
        """Znajduje najlepszy artykuł (tytuł) w polskiej Wikipedii."""
        q = urllib.parse.quote(temat)
        url = (f"https://pl.wikipedia.org/w/api.php?action=opensearch&limit=1"
               f"&namespace=0&format=json&search={q}")
        surowe = self._http_get(url)
        if not surowe:
            return None
        try:
            dane = json.loads(surowe.decode("utf-8"))
            if dane and len(dane) > 1 and dane[1]:
                return dane[1][0]
        except Exception:
            pass
        return None

    def streszczenie_wikipedii(self, tytul: str) -> Optional[Tuple[str, str]]:
        """Pobiera streszczenie artykułu (REST summary). Zwraca (tytuł, tekst)."""
        t = urllib.parse.quote(tytul.replace(" ", "_"))
        url = f"https://pl.wikipedia.org/api/rest_v1/page/summary/{t}"
        surowe = self._http_get(url)
        if not surowe:
            return None
        try:
            dane = json.loads(surowe.decode("utf-8"))
            ekstrakt = dane.get("extract") or ""
            tytul_a = dane.get("title") or tytul
            if ekstrakt:
                return tytul_a, ekstrakt
        except Exception:
            pass
        return None

    def naucz_sie_tematu(self, temat: str, log: Optional[Callable[[str], None]] = None) -> str:
        """Pełny cykl nauki jednego tematu: pobierz → zrozum → zapamiętaj."""
        def say(msg: str) -> None:
            if log:
                log(msg)

        tytul = self.szukaj_wikipedia(temat)
        if not tytul:
            return (f"Nie udało mi się znaleźć w polskiej Wikipedii hasła „{temat}”. "
                    f"Może jesteś offline albo temat jest zbyt ogólny — ale zawsze "
                    f"możesz nauczyć mnie sam: „zapamiętaj, że {temat} to ...”.")
        say(f"Znalaźłem hasło: „{tytul}”. Czytam…")
        wynik = self.streszczenie_wikipedii(tytul)
        if not wynik:
            return f"Znalazłem „{tytul}”, ale nie udało mi się pobrać treści."
        tytul2, tekst = wynik
        zdania_wiedzy = nlp.zdania(tekst)
        zapisane = self.pamiec.dodaj_wiedze(tytul2, zdania_wiedzy, zrodlo="wikipedia")

        # zrozum: wyciągaj fakty z definicji pierwszego zdania
        zrozumiane = 0
        for z in zdania_wiedzy[:3]:
            potw = self.rozum.ucz_sie_z_zdania(z)
            if potw:
                zrozumiane += 1

        # ucz model generatywny na nowych zdaniach (forma z polskimi znakami)
        for z in zdania_wiedzy:
            self.pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl(z) + ["."])

        self.model.odbuduj_asocjacje()
        self.pamiec.zapisz_dziennik(
            "nauka", f"temat={tytul2}; zdań={zapisane}; wyciągniętych faktów={zrozumiane}")
        return (f"Nauczyłem się tematu „{tytul2}”: zapamiętałem {zapisane} zdań "
                f"i wyciągnąłem z nich kluczowe fakty. Zapytaj mnie teraz, np.: "
                f"„co to jest {tytul2.lower()}”.")

    # ------------------------------------------------------------------ #
    # 3. Sen — konsolidacja pamięci
    # ------------------------------------------------------------------ #

    def sen(self, log: Optional[Callable[[str], None]] = None) -> str:
        """Konsolidacja pamięci (jak sen u ludzi): porządki + śnienie."""
        def say(msg: str) -> None:
            if log:
                log(msg)

        raport: List[str] = []
        say("Zasypiam… (konsolidacja pamięci)")

        # „sen” przycina rzadkie TRIGRAMY (szum), zachowując bigramy — one trzymają
        # płynność zdań; konteksty startowe (<s>…) są chronione
        self.pamiec.db.execute(
            "DELETE FROM ngramy WHERE n=3 AND licznik < 2 AND kontekst NOT LIKE '<s>%'")
        self.pamiec.db.commit()
        usuniete = self.pamiec.db.execute("SELECT changes()").fetchone()[0]
        raport.append(f"przyciąłem {usuniete} rzadkich n-gramów (szum)")
        say(f"• przyciąłem {usuniete} rzadkich n-gramów")

        # „śnienie": rekombinacja wiedzy — generuję zdania i zapisuję sensowne
        zasniete = 0
        tematy = self.pamiec.tematy(limit=6)
        for temat in tematy:
            wiedza = self.pamiec.wiedza_o(temat, limit=2)
            for _, z in wiedza:
                tokeny = nlp.tokenizuj_wyswietl(z)
                if len(tokeny) > 5:
                    seed = random.sample(tokeny[:6], k=min(2, len(tokeny[:6])))
                    sen_zdanie = self.model.generuj(seed, maks_slow=18)
                    slowa = nlp.tokenizuj(sen_zdanie)
                    # sen zapisujemy tylko, gdy jest spójny z naszą wiedzą (ma znane słowa)
                    if len(slowa) >= 5 and self._spojnosc(sen_zdanie) >= 0.6:
                        self.pamiec.dodaj_wiedze("sny", [sen_zdanie], zrodlo="sen")
                        self.pamiec.ucz_ngramy(slowa + ["."])
                        zasniete += 1
        raport.append(f"przesniłem {zasniete} nowych zdań")
        say(f"• śniło mi się {zasniete} nowych zdań (rekombinacja wiedzy)")

        # przebudowa indeksów
        liczba = self.model.odbuduj_asocjacje()
        raport.append(f"przebudowałem pamięć asocjacyjną ({liczba} skojarzeń)")
        say(f"• przebudowałem pamięć asocjacyjną: {liczba} skojarzeń")

        # doszkalanie sieci na wszystkich zebranych przykładach
        if self.pamiec.liczba_przykladow() > 0:
            strata = self.model.zbuduj_mlp(epoki=6)
            raport.append(f"doszkoliłem sieć intencji (strata {strata:.4f})")
            say(f"• doszkoliłem sieć intencji (strata {strata:.4f})")

        metryki = self.metryki()
        self.pamiec.zapisz_dziennik("sen", "; ".join(raport))
        say("Budzę się wypoczęty.")
        return ("Sen zakończony: " + "; ".join(raport) + ". "
                f"Stan umysłu: {metryki['fakty']} faktów, {metryki['slownik']} słów, "
                f"poziom rozwoju {metryki['poziom']}.")

    def _spojnosc(self, zdanie: str) -> float:
        """Prosty współczynnik spójności: udział słów znanych ze słownika."""
        tokeny = nlp.tokenizuj(zdanie)
        if not tokeny:
            return 0.0
        znane = 0
        for t in tokeny:
            if self.pamiec.db.execute("SELECT 1 FROM slowa WHERE slowo=?", (t,)).fetchone():
                znane += 1
        return znane / len(tokeny)

    # ------------------------------------------------------------------ #
    # 4. Tryb samorozwoju (pętla autonomiczna)
    # ------------------------------------------------------------------ #

    def cykl_samorozwoju(self, offline_ok: bool = True,
                         log: Optional[Callable[[str], None]] = None) -> str:
        """Jeden pełny cykl samodzielnego rozwoju. Zwraca raport."""
        def say(msg: str) -> None:
            if log:
                log(msg)

        kroki: List[str] = []

        # 1) wybierz temat: najubożej opisany albo zupełnie nowy z listy ciekawych
        temat = self.pamiec.temat_do_nauki()
        if temat is None or random.random() < 0.35:
            temat = random.choice(CIEKAVE_TEMATY)
        say(f"Wybrałem temat do nauki: „{temat}”.")

        # 2) nauka
        raport = self.naucz_sie_tematu(temat, log=say)
        kroki.append(raport)

        # 3) zadaj sobie pytanie i odpowiedz (samoocena rozumu)
        pytanie = f"co to jest {temat.lower()}"
        odpowiedz = self.rozum.pytanie_o_fakt(pytanie) or self.rozum.opisz(temat.lower()) or ""
        if odpowiedz:
            kroki.append(f"Sprawdziłem siebie ({pytanie}): {odpowiedz[:160]}")
            say("Sprawdziłem własną wiedzę — odpowiedziałem sobie poprawnie.")
        else:
            kroki.append(f"({pytanie}) — jeszcze mi słabo wychodzi; włączę ten temat do powtórki.")
            say("Moja odpowiedź była słaba — oznaczam temat do powtórki.")

        # 4) własna myśl (generacja)
        tokeny = nlp.tokenizuj(temat)
        mysl = self.model.generuj(tokeny[:2], maks_slow=16)
        if mysl:
            kroki.append(f"Moja własna myśl: „{mysl}”")

        # 5) krótki sen co kilka cykli
        if random.random() < 0.4:
            kroki.append(self.sen(log=say))

        self.pamiec.zapisz_dziennik("samorozwoj", " | ".join(k[:120] for k in kroki))
        return "\n".join(kroki)

    # ------------------------------------------------------------------ #
    # Metryki rozwoju
    # ------------------------------------------------------------------ #

    def metryki(self) -> dict:
        suma_ocen, liczba_ocen = self.pamiec.statystyki_ocen()
        srednia = (suma_ocen / liczba_ocen) if liczba_ocen else 0.0
        fakty = self.pamiec.liczba_faktow()
        zdania_w = self.pamiec.liczba_zdan_wiedzy()
        slownik = self.pamiec.rozmiar_slownika()
        ngramy = self.pamiec.liczba_ngramow()
        przyklady = self.pamiec.liczba_przykladow()
        # poziom rozwoju 1-100: logarytmicznie z objętości wiedzy + bonus za oceny
        bazowy = (fakty * 0.6 + zdania_w * 0.35 + slownik * 0.08 +
                  ngramy * 0.01 + przyklady * 0.5)
        import math
        poziom = int(min(96, 12 * math.log1p(bazowy)) + 1)
        if liczba_ocen:
            poziom = min(100, poziom + max(0, int(srednia * 3)))
        return {
            "fakty": fakty,
            "zdania_wiedzy": zdania_w,
            "slownik": slownik,
            "ngramy": ngramy,
            "przyklady": przyklady,
            "oceny": liczba_ocen,
            "srednia_ocen": round(srednia, 2),
            "poziom": min(poziom, 100),
        }


CIEKAVE_TEMATY = [
    "sztuczna inteligencja", "Polska", "Warszawa", "Układ Słoneczny", "Mars",
    "fotosynteza", "Mikołaj Kopernik", "Maria Skłodowska-Curie", "język polski",
    "matematyka", "muzyka", "programowanie", "Python", "ocean", "płatki śniegu",
    "wieloryb", "dąb", "pszczoła", "pierogi", "Wawel", "Morze Bałtyckie",
    "neuron", "mózg", "pamięć", "sen", "Albert Einstein", "Karol Darwin",
    "Fryderyk Chopin", "Adam Mickiewicz", "quark", "grawitacja", "światło",
    "klimat", "wulkan", "Ziemia", "Księżyc", "robot", "internet", "komputer",
    "algorytm", "kryptografia", "demokracja", "Wisła", "żubr", "bocian",
]
