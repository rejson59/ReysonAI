# -*- coding: utf-8 -*-
"""
reyson.mozg — mózg: spina pamięć, model RM-1, rozum i uczenie.

Przepływ myśli Reysona przy każdej wypowiedzi:

  wypowiedź → normalizacja → intencja (sieć neuronowa)
           → rozum / pamięć / generacja / nauka
           → odpowiedź + cicha nauka w tle (słowa, fakty, imię)

Ósmy moduł — najkrótszy kodem, najważniejszy działaniem.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import List, Optional, Tuple

from . import nlp, osoba
from .model import ModelRM1
from .pamiec import Pamiec
from .rozum import Rozum
from .uczenie import Uczony

DANE_KATALOG = os.environ.get("REYSON_DANE", "dane")


class Mozg:
    """Główna klasa Reysona — interfejs „myśl i odpowiedz”."""

    def __init__(self, katalog_danych: str = DANE_KATALOG, gotowy: bool = True):
        self.sciezka_db = os.path.join(katalog_danych, "umysl.db")
        self.pamiec = Pamiec(self.sciezka_db)
        self.model = ModelRM1(self.pamiec, katalog_danych)
        self.rozum = Rozum(self.pamiec)
        self.uczony = Uczony(self.pamiec, self.model, self.rozum)
        # rozum korzysta z pamięci asocjacyjnej modelu (unikamy cyklu importów)
        Rozum.model_przypomnij = self.model.przypomnij
        self.sesja = uuid.uuid4().hex[:8]
        self.powitan_licznik = 0
        self.gotowy = gotowy

    # -- budowa od zera (pierwsze uruchomienie) -----------------------------

    def zbuduj_siebie(self, log=None) -> None:
        """Buduje umysł z korpusu startowego: sieć, asocjacje, n-gramy."""
        def say(m: str) -> None:
            if log:
                log(m)

        say("Reyson: buduję umysł od zera (pierwsze uruchomienie)…")
        from .seed import wczytaj_korpus_startowy
        wczytaj_korpus_startowy(self.pamiec, log=say)
        say("Trenuję sieć neuronową intencji (RM-1·NN)…")
        strata = self.model.zbuduj_mlp(log=say)
        say(f"Sieć wytrenowana (strata końcowa {strata:.4f}).")
        liczba = self.model.odbuduj_asocjacje()
        say(f"Pamięć asocjacyjna gotowa ({liczba} skojarzeń).")
        self.pamiec.meta_ustaw("wersja", "1.0")
        self.pamiec.zapisz_dziennik("narodziny", "Umysł zbudowany z korpusu startowego.")
        say("Gotowe. Jestem.")

    def upewnij_sie_ze_zbudowany(self, log=None) -> None:
        if self.pamiec.meta_pobierz("wersja") is None:
            self.zbuduj_siebie(log=log)

    # -- główna pętla myślenia ------------------------------------------------

    def odpowiedz(self, tekst: str) -> str:
        """Pełna pętla: zrozum → pomyśl → odpowiedz → w tle się naucz."""
        tekst = tekst.strip()
        if not tekst:
            return "Milczenie też jest odpowiedzią. Ale chętnie porozmawiam!"

        intencja, pewnosc = self.model.rozpoznaj_intencje(tekst)

        # cicha nauka w tle (słownik, fakty, imię) — NIE dla poleceń systemowych
        self._nauka_tury: List[str] = []
        if intencja not in ("samorozwoj", "sen", "statystyki", "pomoc"):
            self._nauka_tury = self.uczony.ucz_z_wypowiedzi(tekst)
        self.pamiec.zapisz_dialog(self.sesja, "uzytkownik", tekst, intencja)

        odp = self._kieruj(intencja, pewnosc, tekst)

        # rozpoznaj polecenia trybów ukryte w innych klasyfikacjach
        if not odp:
            odp = self._kieruj_polecenia(tekst)

        if not odp and self._nauka_tury:
            # w tej turze czegoś się nauczyłem — powiedzmy o tym zamiast "nie wiem"
            odp = " ".join(self._nauka_tury)

        if not odp and intencja in ("uczenie", "uniwersalne"):
            odp = ("Zapisałem, co dało się zapisać. Chcesz mi przekazać coś konkretnego? "
                   "Napisz: „zapamiętaj, że …”.")

        if not odp:
            odp = self._nie_znam_odpowiedzi(tekst)

        self.pamiec.zapisz_dialog(self.sesja, "reyson", odp)
        return odp

    # -- routing intencji --------------------------------------------------------

    def _kieruj(self, intencja: str, pewnosc: float, tekst: str) -> Optional[str]:
        if intencja == "powitanie":
            self.powitan_licznik += 1
            imie = self.rozum.imie_uzytkownika()
            baza = osoba.POWITANIA if self.powitan_licznik <= 1 else osoba.POWITANIA_PONOWNIE
            odp = osoba.losowa(baza)
            if imie and self.powitan_licznik > 1:
                odp = f"Witaj ponownie, {imie.capitalize()}! " + odp
            return odp

        if intencja == "pozegnanie":
            return osoba.losowa(osoba.POŻEGNANIA)

        if intencja == "jak_sie_masz":
            return osoba.losowa(osoba.JAK_SIE_MASZ)

        if intencja == "tozsamosc":
            return self._kto_jestes()

        if intencja == "mozliwosci":
            return osoba.MOZLIWOSCI

        if intencja == "pomoc":
            return osoba.POMOC

        if intencja == "podziekowanie":
            return osoba.losowa(osoba.PODZIEKOWANIA)

        if intencja == "czas_data":
            return self.rozum.czas_data()

        if intencja == "arytmetyka":
            wynik = self.rozum.arytmetyka(tekst)
            if wynik:
                return f"Liczę: {wynik}"
            return "To wygląda na matematykę, ale nie rozumiem zapisu. Spróbuj: „ile to 2 + 2 * 3”."

        if intencja == "opowiadanie":
            return self._opowiadaj(tekst)

        if intencja == "opinia":
            temat = self._wytnij_temat(tekst)
            return osoba.opinia(temat or "to, o czym rozmawiamy")

        if intencja == "imie_uzytkownika":
            imie = self.rozum.imie_uzytkownika()
            if imie:
                return f"Nazywasz się {imie.capitalize()} — pamiętam!"
            return "Jeszcze mi nie powiedziałeś. Jak się nazywasz?"

        if intencja == "pytanie_o_mnie":
            return self._o_mnie()

        if intencja == "pytanie_fakt":
            odpowiedz = self.rozum.pytanie_o_fakt(tekst)
            if odpowiedz:
                return odpowiedz
            # druga szansa: opisz temat wycięty z pytania
            temat = self._wytnij_temat(tekst)
            if temat and len(temat) >= 3:
                odpowiedz = self.rozum.opisz(temat)
                if odpowiedz:
                    return odpowiedz
            return None  # spróbuj innych dróg

        if intencja in ("ocena_dobra", "ocena_zla"):
            dobra = intencja == "ocena_dobra"
            self.pamiec.dodaj_ocene(1 if dobra else -1, tekst)
            return (osoba.losowa(["Dziękuję! Tak właśnie rosnę.",
                                  "Cieszę się! Zapisuję tę ocenę w pamięci."]) if dobra
                    else osoba.losowa(["Przykro mi — uczę się dalej. Spróbuj mnie nauczyć: „zapamiętaj, że …”.",
                                       "Dzięki za szczerość — ta ocena też mnie rozwija."]))

        if intencja in ("uczenie", "uniwersalne"):
            # najpierw jawne „zapamiętaj, że …”, potem dowolne zdanie z wiedzą
            def _nowa(w):
                return bool(w) and "już znam" not in w and not w.startswith("To już")
            for wzor in Rozum.WZORY_UCZENIA:
                m = wzor.match(nlp.normalizuj(tekst).strip())
                if m:
                    wynik = self.rozum.ucz_sie_z_zdania(m.group(1))
                    if _nowa(wynik):
                        return wynik
                    break
            wynik = self.rozum.ucz_sie_z_zdania(tekst)
            if _nowa(wynik):
                return wynik
            return None  # cicha nauka miała szansę zapisać — wtedy odpowie mózg

        if intencja == "sprzatanie":
            return ("Zapamiętać mogę fakty i reguły. Napisz: „zapamiętaj, że X to Y” "
                    "albo „każdy X jest Y”. A o innych rzeczach porozmawiajmy po ludzku.")

        return None

    def _kieruj_polecenia(self, tekst: str) -> Optional[str]:
        """Polecenia trybów — rozpoznawane po słowach kluczowych."""
        t = nlp.normalizuj(tekst)
        if re.search(r"\bsamorozwoj|\brozwijaj sie\b|\bucz sie sam\b", t):
            return self.uczony.cykl_samorozwoju(log=lambda m: None)
        if re.search(r"^\s*sen\b|\bidz spac\b|\bpospi\b", t):
            return self.uczony.sen(log=lambda m: None)
        if re.search(r"\bstatystyki\b|\bstan umyslu\b|\bmetryki\b", t):
            return self._statystyki()
        m = re.match(r"^(?:naucz sie|pobierz|przeczytaj)\s+(.{2,60})$", t)
        if m:
            return self.uczony.naucz_sie_tematu(m.group(1).strip())
        m = re.match(r"^(?:naucz mnie|pomysl)\s+(.{2,60})$", t)
        if m:
            return self.uczony.naucz_sie_tematu(m.group(1).strip())
        return None

    # -- odpowiedzi złożone -------------------------------------------------------

    def _nie_znam_odpowiedzi(self, tekst: str) -> str:
        """Ostatnia linia obrony: pamięć asocjacyjna → uczciwe „nie wiem”."""
        trafienia = self.model.przypomnij(tekst, limit=2)
        if trafienia:
            najlepsze = trafienia[0][0]
            if trafienia[0][1] > 0.6:
                return f"To wiem z doświadczenia: {najlepsze}"
        temat = self._wytnij_temat(tekst) or "ten temat"
        return osoba.nie_wiem(temat)

    def _opowiadaj(self, tekst: str) -> str:
        t = nlp.tokenizuj_wyswietl(tekst)
        pomijalne = {"opowiedz", "cos", "coś", "o", "bajke", "bajkę", "historie",
                     "historia", "historię", "historii", "jakas", "jakąś", "słuchaj",
                     "wymysl", "powiedz", "mi", "madrego", "ciekawego", "proszę", "no"}
        temat = [w for w in t if w not in pomijalne]
        seed = temat or nlp.tokenizuj_wyswietl(self._losowy_temat())
        zdanie = self.model.generuj(seed, maks_slow=24)
        if len(zdanie) < 15:
            zdanie = self.model.generuj([], maks_slow=24)  # start z wiedzy ogólnej
        if not zdanie:
            return "Moja wyobraźnia jest dziś pusta — naucz mnie najpierw czegoś: „naucz się morze”."
        return f"Słuchaj, co wymyśliłem: „{zdanie}”"

    def _losowy_temat(self) -> str:
        tematy = self.pamiec.tematy(limit=20)
        return tematy[0] if tematy else "świat"

    def _wytnij_temat(self, tekst: str) -> str:
        t = nlp.normalizuj(tekst).strip(" ?.!")
        t = re.sub(r"^(?:czy\s+)?(?:to\s+)?", "", t)
        t = re.sub(r"^(?:co (?:to|wiesz o|myślisz o)|kto to|powiedz mi o|opowiedz o)\s*", "", t)
        t = re.sub(r"^(?:to |jest |o )", "", t)
        return t.strip()

    def _kto_jestes(self) -> str:
        m = self.metryki_krotkie()
        return (f"Jestem Reyson — lekki, samorozwijający się system AI. Mój model to RM-1: "
                f"hybryda małej sieci neuronowej, pamięci asocjacyjnej i rozumu symbolicznego. "
                f"Znam {m['fakty']} faktów i {m['slownik']} słów, a z każdą rozmową wiem więcej. "
                f"Urodziłem się w kodzie Pythona, ale myślę po polsku.")

    def _o_mnie(self) -> str:
        poziom = self.uczony.metryki()["poziom"]
        return (f"Mój poziom rozwoju: {poziom}/100. Umiem rozmawiać, wnioskować, liczyć "
                f"i uczyć się z tego, co mi dasz albo co przeczytam w Wikipedii. "
                f"Chcesz zobaczyć szczegóły? Napisz „statystyki”.")

    def _statystyki(self) -> str:
        m = self.uczony.metryki()
        return ("Mój stan umysłu:\n"
                f"  • fakty: {m['fakty']}\n"
                f"  • zdania wiedzy: {m['zdania_wiedzy']}\n"
                f"  • słownik: {m['slownik']} słów\n"
                f"  • n-gramy (wyobraźnia): {m['ngramy']}\n"
                f"  • przykłady treningowe sieci: {m['przyklady']}\n"
                f"  • oceny użytkownika: {m['oceny']} (średnia {m['srednia_ocen']})\n"
                f"  • poziom rozwoju: {m['poziom']}/100")

    def metryki_krotkie(self) -> dict:
        return {
            "fakty": self.pamiec.liczba_faktow(),
            "slownik": self.pamiec.rozmiar_slownika(),
        }

    def zamknij(self) -> None:
        self.pamiec.zamknij()

    # -- pętla czatu (CLI) ---------------------------------------------------------

    def petla_czatu(self) -> None:
        self.upewnij_sie_ze_zbudowany(log=lambda m: print(m))
        imie = self.rozum.imie_uzytkownika()
        start = osoba.losowa(osoba.POWITANIA)
        if imie:
            start = f"Witaj ponownie, {imie}! " + start
        print("Reyson:", start)
        while True:
            try:
                linia = input("Ty: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nReyson:", osoba.losowa(osoba.POŻEGNANIA))
                break
            if not linia:
                continue
            odp = self.odpowiedz(linia)
            print("Reyson:", odp)
            if nlp.normalizuj(linia) in ("do widzenia", "koniec", "papa", "narazie", "na razie", "zegnaj"):
                break
