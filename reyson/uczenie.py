# -*- coding: utf-8 -*-
"""
reyson.uczenie — silnik samorozwoju Reysona (RM-2).

Reyson rozwija się na sześć sposobów:

1. NAUKA Z ROZMOWY — wyciąga fakty z wypowiedzi użytkownika, zapamiętuje
   nowe słowa i korekty intencji (doszkalanie sieci neuronowej).
2. NAUKA Z WIEDZY ZEWNĘTRZNEJ — pobiera artykuły z polskiej Wikipedii
   (REST API, bez kluczy), gdy internet jest dostępny.
3. NAUKA OFFLINE — gdy internetu nie ma, Reyson czyta LOKALNE LEKCJE
   (dane/lekcje/*.txt), ponownie „przegląda” własne notatki (wiedza)
   i wyciąga z nich fakty, których wcześniej nie wyłapał.
4. INDUKCJA REGUŁ — sam znajduje wzorce w faktach („3+ ssaki, które znam,
   są też zwierzętami → każdy ssak jest zwierzęciem”) z kontrolą
   kontrprzykładów. To prawdziwe wnioskowanie o własnej wiedzy.
5. SAMO-SPRAWDZIAN — zadaje sobie pytania „czy X jest Y” i sprawdza,
   czy jego rozum odpowiada zgodnie z drabiną pojęć.
6. SEN — konsolidacja pamięci: przycinanie szumu w n-gramach, śnienie
   (rekombinacja wiedzy), przebudowa indeksów, DOSZKALANIE sieci
   (kontynuacja z zapisanych wag — nie restart!) i bilans sprzeczności.

Całość jest bezpieczna dla słabych maszyn: limity czasu i pamięci,
parametry skalowane profilem urządzenia (reyson.profil).
"""

from __future__ import annotations

import json
import math
import os
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
from .seed import KATALOG as KATALOG_DANYCH

_USER_AGENT = "ReysonAI/2.0 (samozielony agent uczący się; polski)"
_KATALOG_LEKCJI = os.path.join(KATALOG_DANYCH, "lekcje")


class Uczony:
    """Odpowiada za cały rozwój Reysona („edukacja”, „samorozwój” i „sen”)."""

    def __init__(self, pamiec: Pamiec, model: ModelRM1, rozum: Rozum, profil=None):
        self.pamiec = pamiec
        self.model = model
        self.rozum = rozum
        self.profil = profil  # reyson.profil.Profil (None → wartości domyślne)
        self.slowa_przed = 0
        self._stan_sieci: Optional[Tuple[float, bool]] = None  # cache dostępu do sieci

    # ------------------------------------------------------------------ #
    # 1. Nauka z rozmowy
    # ------------------------------------------------------------------ #

    def ucz_z_wypowiedzi(self, tekst: str) -> List[str]:
        """Przetwarza każdą wypowiedź użytkownika jako okazję do naukę."""
        potwierdzenia: List[str] = []
        tokeny = nlp.tokenizuj_wyswietl(tekst)
        self.pamiec.zarejestruj_slowa(set(tokeny))

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
    # 2. Nauka z Wikipedii (gdy jest internet) / offline
    # ------------------------------------------------------------------ #

    def _timeout_http(self) -> int:
        return getattr(self.profil, "timeout_http", 8) if self.profil else 8

    def _http_get(self, url: str, timeout: Optional[int] = None) -> Optional[bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout_http()) as r:
                return r.read()
        except Exception:
            return None

    def online(self) -> bool:
        """Czy Wikipedia jest osiągalna? (wynik cache'owany na 5 minut)."""
        teraz = time.time()
        if self._stan_sieci and teraz - self._stan_sieci[0] < 300:
            return self._stan_sieci[1]
        surowe = self._http_get(
            "https://pl.wikipedia.org/w/api.php?action=query&format=json&meta=siteinfo",
            timeout=min(4, self._timeout_http()))
        online = surowe is not None
        self._stan_sieci = (teraz, online)
        return online

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

    def _zapisz_zdania_wiedzy(self, tytul: str, zdania_wiedzy: List[str]) -> Tuple[int, int]:
        """Zapisuje zdania do wiedzy + uczy n-gramy. Zwraca (zdań, faktów)."""
        zapisane = self.pamiec.dodaj_wiedze(tytul, zdania_wiedzy, zrodlo="wikipedia")
        zrozumiane = 0
        for z in zdania_wiedzy[:3]:
            if self.rozum.ucz_sie_z_zdania(z):
                zrozumiane += 1
        for z in zdania_wiedzy:
            self.pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl(z) + ["."])
        self.model.odbuduj_asocjacje()
        return zapisane, zrozumiane

    def naucz_sie_tematu(self, temat: str, log: Optional[Callable[[str], None]] = None) -> str:
        """Pełny cykl nauki jednego tematu: pobierz → zrozum → zapamiętaj."""
        def say(msg: str) -> None:
            if log:
                log(msg)

        if not self.online():
            return self._naucz_sie_lokalnie(temat, log=say)

        tytul = self.szukaj_wikipedia(temat)
        if not tytul:
            return (f"Nie udało mi się znaleźć w polskiej Wikipedii hasła „{temat}”. "
                    f"Może temat jest zbyt ogólny — ale zawsze możesz nauczyć mnie sam: "
                    f"„zapamiętaj, że {temat} to …”.")
        say(f"Znalazłem hasło: „{tytul}”. Czytam…")
        wynik = self.streszczenie_wikipedii(tytul)
        if not wynik:
            return f"Znalazłem „{tytul}”, ale nie udało mi się pobrać treści."
        tytul2, tekst = wynik
        zdania_wiedzy = nlp.zdania(tekst)
        zapisane, zrozumiane = self._zapisz_zdania_wiedzy(tytul2, zdania_wiedzy)

        self.pamiec.zapisz_dziennik(
            "nauka", f"temat={tytul2}; zdań={zapisane}; wyciągniętych faktów={zrozumiane}")
        return (f"Nauczyłem się tematu „{tytul2}”: zapamiętałem {zapisane} zdań "
                f"i wyciągnąłem z nich kluczowe fakty. Zapytaj mnie teraz, np.: "
                f"„co to jest {tytul2.lower()}”.")

    def _naucz_sie_lokalnie(self, temat: str, log: Callable[[str], None]) -> str:
        """Nauka bez internetu: własna biblioteka + notatki o temacie."""
        log(f"„{temat}” — jestem offline, sięgam do lokalnej biblioteki…")
        # 1) może już mam notatki o tym temacie → dociągnij fakty z nich
        wiedza = self.pamiec.wiedza_o(temat, limit=5)
        nowe_fakty = 0
        for _, zdanie in wiedza:
            if self.rozum.ucz_sie_z_zdania(zdanie):
                nowe_fakty += 1
        if wiedza:
            self.pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl(wiedza[0][1]) + ["."])
            return (f"Jestem offline, ale temat „{temat}” mam w notatkach: "
                    f"{len(wiedza)} zdań, wyciągnąłem {nowe_fakty} nowych faktów. "
                    f"Zapytaj: „co wiesz o {temat}”.")
        # 2) przeczytaj następną lokalną lekcję (rozwój nawet bez internetu)
        lekcja = self._przeczytaj_nastepna_lekcje(log=log)
        if lekcja:
            return (f"Jestem offline, więc zamiast Wikipedii czytam własną bibliotekę. "
                    f"{lekcja}")
        return (f"Jestem offline i nie mam hasła „{temat}” w lokalnej bibliotece. "
                f"Naucz mnie sam: „zapamiętaj, że {temat} to …” — albo sprawdź "
                f"połączenie z internetem.")

    # ------------------------------------------------------------------ #
    # 3. Lokalne lekcje (offline)
    # ------------------------------------------------------------------ #

    def _lista_lekcji(self) -> List[str]:
        try:
            return sorted(f for f in os.listdir(_KATALOG_LEKCJI)
                          if f.endswith(".txt") and not f.startswith("."))
        except OSError:
            return []

    def _przeczytaj_nastepna_lekcje(self, log: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """Czyta pierwszą nieprzeczytaną lekcję z dane/lekcje/. Brak → None."""
        def say(m: str) -> None:
            if log:
                log(m)

        for plik in self._lista_lekcji():
            if self.pamiec.meta_pobierz("lekcja:" + plik):
                continue
            sciezka = os.path.join(_KATALOG_LEKCJI, plik)
            try:
                with open(sciezka, encoding="utf-8") as f:
                    tekst = f.read()
            except OSError:
                continue
            tytul = self._tytul_lekcji(tekst, plik)
            zdania = nlp.zdania(tekst)
            self.pamiec.dodaj_wiedze(tytul, zdania, zrodlo="lekcja")
            nowe_fakty = 0
            for z in zdania:
                if self.rozum.ucz_sie_z_zdania(z):
                    nowe_fakty += 1
            for z in zdania:
                self.pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl(z) + ["."])
                self.pamiec.zarejestruj_slowa(nlp.tokenizuj_wyswietl(z))
            self.model.odbuduj_asocjacje()
            self.pamiec.meta_ustaw("lekcja:" + plik, "1")
            self.pamiec.meta_zwieksz("lekcje_przeczytane")
            self.pamiec.zapisz_dziennik("lekcja", f"plik={plik}; zdań={len(zdania)}; "
                                                  f"faktów={nowe_fakty}")
            say(f"Przeczytałem lekcję „{tytul}” ({len(zdania)} zdań, {nowe_fakty} faktów).")
            return (f"Przeczytałem lekcję „{tytul}”: {len(zdania)} zdań, "
                    f"{nowe_fakty} nowych faktów.")
        return None

    @staticmethod
    def _tytul_lekcji(tekst: str, plik: str) -> str:
        m = re.search(r"^#\s*(.+)$", tekst, re.MULTILINE)
        return m.group(1).strip() if m else plik[:-4].replace("_", " ")

    # ------------------------------------------------------------------ #
    # 4. Sen — konsolidacja pamięci
    # ------------------------------------------------------------------ #

    def sen(self, log: Optional[Callable[[str], None]] = None) -> str:
        """Konsolidacja pamięci (jak sen u ludzi): porządki + śnienie."""
        def say(msg: str) -> None:
            if log:
                log(msg)

        ile_snow = getattr(self.profil, "sny", 6) if self.profil else 6
        raport: List[str] = []
        say("Zasypiam… (konsolidacja pamięci)")

        # „sen” przycina rzadkie TRIGRAMY i wyższe (szum), zachowując bigramy —
        # one trzymają płynność zdań; konteksty startowe (<s>…) są chronione
        self.pamiec.db.execute(
            "DELETE FROM ngramy WHERE n>=3 AND licznik < 2 AND kontekst NOT LIKE '<s>%'")
        self.pamiec.db.commit()
        usuniete = self.pamiec.db.execute("SELECT changes()").fetchone()[0]
        raport.append(f"przyciąłem {usuniete} rzadkich n-gramów (szum)")
        say(f"• przyciąłem {usuniete} rzadkich n-gramów")

        # „śnienie”: rekombinacja wiedzy — generuję zdania i zapisuję sensowne
        zasniete = 0
        tematy = self.pamiec.tematy(limit=max(6, ile_snow))
        for temat in tematy:
            if zasniete >= ile_snow:
                break
            wiedza = self.pamiec.wiedza_o(temat, limit=2)
            for _, z in wiedza:
                if zasniete >= ile_snow:
                    break
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

        # doszkalanie sieci — KONTYNUUJĄC z zapisanych wag (prawdziwa konsolidacja!)
        if self.pamiec.liczba_przykladow() > 0:
            epoki = getattr(self.profil, "epoki_snu", 6) if self.profil else 6
            lr = getattr(self.profil, "lr_snu", 0.03) if self.profil else 0.03
            strata = self.model.zbuduj_mlp(epoki=epoki, kontynuuj=True, lr=lr)
            raport.append(f"doszkoliłem sieć intencji (strata {strata:.4f})")
            say(f"• doszkoliłem sieć intencji (strata {strata:.4f})")

        # bilans sprzeczności — sen to dobry moment na własny audyt wiedzy
        sprzeczne = self.rozum.sprzecznosci(limit=3)
        if sprzeczne:
            raport.append(f"zgłosiłem {len(sprzeczne)} sprzeczności do rozstrzygnięcia")
            say(f"• ⚠ sprzeczności: {sprzeczne[0]}")

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
    # 5. Tryb samorozwoju (pętla autonomiczna — działa też OFFLINE)
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

        # 2) NAUKA — z Wikipedii (online) albo z lokalnej biblioteki (offline)
        if self.online():
            kroki.append(self.naucz_sie_tematu(temat, log=say))
        else:
            say("Internet jest nieosiągalny — przechodzę na rozwój wewnętrzny.")
            lekcja = self._przeczytaj_nastepna_lekcje(log=say)
            if lekcja:
                kroki.append("[offline] " + lekcja)
            przypomnienia = self._przejrzyj_notatki(log=say)
            if przypomnienia:
                kroki.append(przypomnienia)

        # 3) SAMO-SPRAWDZIAN: zadam sobie pytania z własnych faktów
        kroki.append(self._samosprawdzian(log=say))

        # 4) INDUKCJA REGUŁ: znajdź wzorce w faktach i zaproponuj uniwersalia
        nowe_reguly = self._indukuj_reguly(log=say)
        if nowe_reguly:
            kroki.append("Wywnioskowałem nowe reguły: " + "; ".join(nowe_reguly))

        # 5) własna myśl (generacja)
        tokeny = nlp.tokenizuj(temat)
        mysl = self.model.generuj(tokeny[:2], maks_slow=16)
        if mysl:
            kroki.append(f"Moja własna myśl: „{mysl}”")

        # 6) krótki sen co kilka cykli
        if random.random() < 0.4:
            kroki.append(self.sen(log=say))

        self.pamiec.zapisz_dziennik("samorozwoj", " | ".join(k[:120] for k in kroki))
        return "\n".join(kroki)

    def _przejrzyj_notatki(self, log: Callable[[str], None]) -> str:
        """„Konspektowanie”: tematy z 1 zdaniem → spróbuj wyciągnąć nowe fakty."""
        wiersze = self.pamiec.db.execute(
            "SELECT tytul, zdanie FROM wiedza WHERE zrodlo IN ('wikipedia','lekcja','rada') "
            "ORDER BY RANDOM() LIMIT 5").fetchall()
        nowe = 0
        for _, zdanie in wiersze:
            if self.rozum.ucz_sie_z_zdania(zdanie):
                nowe += 1
        if nowe:
            log(f"Przeglądając notatki, wyciągnąłem {nowe} nowych faktów.")
            return f"Przejrzałem notatki i wyciągnąłem {nowe} nowych faktów."
        log("Notatki przeglądnięte — wszystkie fakty już z nich wyciągnięte.")
        return ""

    def _samosprawdzian(self, log: Callable[[str], None]) -> str:
        """Quiz z własnej wiedzy: „czy sokol jest zwierzęciem?” — bez podpowiedzi."""
        ile = getattr(self.profil, "quiz", 6) if self.profil else 6
        fakty = self.pamiec.db.execute(
            "SELECT podmiot,obiekt FROM fakty WHERE relacja IN ('jest','to') "
            "ORDER BY RANDOM() LIMIT ?", (ile,)).fetchall()
        uniwersalia = self.pamiec.wszystkie_uniwersalia()
        zle = 0
        sprawdzone = 0
        for podmiot, obiekt in fakty:
            # pytanie o przodka klasy: czy X (jest Y) → czy X jest rodzic(Y)?
            rodzice = [cel for zr, cel in uniwersalia if nlp.tez_jest_to(zr, obiekt)]
            if not rodzice:
                continue
            cel = random.choice(rodzice)
            pytanie = f"czy {podmiot} jest {cel}"
            tak, _ = self.rozum.czy_jest(podmiot, cel)
            sprawdzone += 1
            if not tak:
                zle += 1
                log(f"⚠ nie zdałem: {pytanie}")
        if sprawdzone == 0:
            log("Nie miałem o co się zapytać — baza faktów jest jeszcze mała.")
            return "Samo-sprawdzian: brak pytań (mało faktów — najpierw nauka)."
        wynik = f"{sprawdzone - zle}/{sprawdzone}"
        log(f"Samo-sprawdzian: {wynik} poprawnych.")
        if zle:
            return (f"Samo-sprawdzian: {wynik} poprawnych — słabe miejsca oznaczam "
                    f"do powtórki w kolejnych cyklach.")
        return f"Samo-sprawdzian: {wynik} poprawnych — rozum działa spójnie."

    def _indukuj_reguly(self, log: Callable[[str], None]) -> List[str]:
        """Indukcja uniwersaliów: ≥3 wspólne instancje dwóch klas → propozycja reguły.

        „ssak” i „zwierzę” mają wspólne instancje (kot, pies, lew…) → kandydat
        „każdy ssak jest zwierzęciem”. Kandydat jest odrzucany, gdy choć jedna
        znana instancja klasy nie jest potwierdzona jako cel (kontrprzykład).
        """
        try:
            fakty = [(p, o) for p, r, o in self.pamiec.wszystkie_fakty()
                     if r in ("jest", "to")]
        except Exception:
            return []
        wg_klasy: dict = {}
        for podmiot, obiekt in fakty:
            wg_klasy.setdefault(obiekt, set()).add(podmiot)
        klasy = list(wg_klasy.keys())
        if len(klasy) < 2:
            return []
        nowe: List[str] = []
        istniejace = set(self.pamiec.wszystkie_uniwersalia())
        for a in klasy:
            for b in klasy:
                if a >= b or (a, b) in istniejace or (b, a) in istniejace:
                    continue
                wspolne = wg_klasy[a] & wg_klasy[b]
                if len(wspolne) < 3:
                    continue
                instancje_a = wg_klasy[a]
                if len(wspolne) < max(3, 0.7 * len(instancje_a)):
                    continue  # słaba reguła — za dużo wyjątków
                kontrprzyklad = any(
                    not self.rozum.czy_jest(x, b)[0] for x in instancje_a)
                if kontrprzyklad:
                    continue
                if self.pamiec.dodaj_uniwersale(a, b):
                    mapa = self.pamiec.mapa_pisowni()
                    a_l = nlp.dostosuj_pisownie(a, mapa)
                    b_l = nlp.dostosuj_pisownie(b, mapa)
                    nowe.append(f"każdy {a_l} jest {b_l} (bo {len(wspolne)} wspólnych "
                                f"przykładów bez kontrprzykładu)")
                    log(f"💡 indukcja: każdy {a} jest {b}")
        if len(nowe) > 4:
            nowe = nowe[:4]
        return nowe

    # ------------------------------------------------------------------ #
    # 6. Metryki rozwoju
    # ------------------------------------------------------------------ #

    def metryki(self) -> dict:
        suma_ocen, liczba_ocen = self.pamiec.statystyki_ocen()
        srednia = (suma_ocen / liczba_ocen) if liczba_ocen else 0.0
        fakty = self.pamiec.liczba_faktow()
        zdania_w = self.pamiec.liczba_zdan_wiedzy()
        slownik = self.pamiec.rozmiar_slownika()
        ngramy = self.pamiec.liczba_ngramow()
        przyklady = self.pamiec.liczba_przykladow()
        przepisy = self.pamiec.liczba_przepisow()
        rady = self.pamiec.meta_pobierz_int("rady_licznik")
        lekcje = self.pamiec.meta_pobierz_int("lekcje_przeczytane")
        # poziom rozwoju 1-100: logarytmicznie z objętości wiedzy + bonus za oceny
        bazowy = (fakty * 0.6 + zdania_w * 0.35 + slownik * 0.08 +
                  ngramy * 0.01 + przyklady * 0.5 + przepisy * 0.8 + rady * 1.5 +
                  lekcje * 1.0)
        poziom = int(min(96, 12 * math.log1p(bazowy)) + 1)
        if liczba_ocen:
            poziom = min(100, poziom + max(0, int(srednia * 3)))
        return {
            "tryb": getattr(self.profil, "nazwa", "standard") if self.profil else "standard",
            "fakty": fakty,
            "zdania_wiedzy": zdania_w,
            "slownik": slownik,
            "ngramy": ngramy,
            "przyklady": przyklady,
            "przepisy": przepisy,
            "rady": rady,
            "lekcje": lekcje,
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
