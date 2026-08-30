# -*- coding: utf-8 -*-
"""
reyson.agenci — sieć agentów RM-2: rada, która rozmawia i uczy się sama.

Jednym umysłem Reysona obraca kilku „agentów” — wyspecjalizowanych perspektyw
współdzielących tę samą pamięć:

  🎓 Uczony   — cytuję fakty i wiedzę; gdy czegoś nie wie, przyznaje się;
  🧐 Krytyk   — weryfikuję wypowiedzi innych, szukam sprzeczności, obalam hipotezy;
  ✨ Demiurg  — generuję hipotezy modelem n-gramowym (nigdy nie zapisuję ich jako faktów!);
  🔧 Inżynier — patrzę na temat algorytmicznie, piszę kod (moduł programista);
  📊 Analityk — liczę bilans dyskusji i wskazuję, czego uczymy się dalej.

Zasady sieci (bezpieczeństwo wiedzy):
• wypowiedzi agentów „faktonośnych” przechodzą przez ten sam ekstraktor faktów,
  co zdania użytkownika — duble są odrzucane, więc agent nie halucynuje do bazy;
• hipotezy Demiurga są jawnie oznaczone i nigdy nie trafiają do faktów;
• Krytyk może obalić hipotezę, jeśli stoi z nią w sprzeczności znany fakt;
• potwierdzone przez dyskusję fakty są WZMACNIANE (rośnie ich ufność);
• przebieg rady trafia do dziennika, a synteza do pamięci asocjacyjnej.

Liczba agentów i rund zależy od profilu urządzenia (mini=3, standard=4, turbo=5).
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

from . import nlp

#: nazwy agentów w kolejności dołączania (od najważniejszego)
KOLEJKA_AGENTOW = ("Uczony", "Krytyk", "Demiurg", "Inzynier", "Analityk")

EMOJI = {
    "Uczony": "🎓", "Krytyk": "🧐", "Demiurg": "✨",
    "Inzynier": "🔧", "Analityk": "📊",
}

ROLE = {
    "Uczony": "czerpie z faktów i wiedzy, przyznaje się do niewiedzy",
    "Krytyk": "weryfikuje, szuka sprzeczności, obala hipotezy",
    "Demiurg": "generuje hipotezy (nigdy nie zapisuje ich jako faktów)",
    "Inzynier": "patrzy algorytmicznie, pisze kod",
    "Analityk": "podsumowuje i planuje kolejną naukę",
}


class Rada:
    """Sieć agentów dyskutujących o jednym temacie — na wspólnej pamięci."""

    def __init__(self, mozg):
        self.mozg = mozg
        self.rozum = mozg.rozum
        self.model = mozg.model
        self.pamiec = mozg.pamiec
        self.programista = getattr(mozg, "programista", None)
        self.profil = getattr(mozg, "profil", None)
        self._liczba_agentow: Optional[int] = None

    @property
    def agenci(self) -> List[str]:
        if self._liczba_agentow is None:
            n = getattr(self.profil, "agenci", 4) if self.profil else 4
            self._liczba_agentow = max(2, min(len(KOLEJKA_AGENTOW), int(n)))
        return list(KOLEJKA_AGENTOW[: self._liczba_agentow])

    # ------------------------------------------------------------------ #
    # Główna pętla dyskusji
    # ------------------------------------------------------------------ #

    def dyskutuj(self, temat: str, rundy: Optional[int] = None,
                 log: Optional[Callable[[str], None]] = None) -> str:
        temat = (temat or "").strip() or "sztuczna inteligencja"
        if rundy is None:
            rundy = getattr(self.profil, "rundy_rady", 3) if self.profil else 3
        rundy = max(1, min(4, int(rundy)))

        def say(msg: str) -> None:
            if log:
                log(msg)

        wiersze: List[str] = [
            f"🏛️ Rada agentów RM-2 — temat: „{temat}”",
            f"(tryb {getattr(self.profil, 'nazwa', 'standard')}: "
            f"{len(self.agenci)} agentów × {rundy} rundy; {' · '.join(ROLE[a] for a in self.agenci)})",
            ""
        ]
        historia: List[Tuple[str, str]] = []
        fakty_przed = self.pamiec.liczba_faktow()

        for nr in range(rundy):
            wiersze.append(f"— runda {nr + 1} —")
            for agent in self.agenci:
                tekst = getattr(self, "_mowi_" + agent.lower())(temat, historia, nr)
                if not tekst:
                    continue
                wiersze.append(f"{EMOJI[agent]} {agent}: {tekst}")
                historia.append((agent, tekst))
            say(f"runda {nr + 1} zakończona")

        # nauka ze współrozmówców: te same reguły co dla zdań użytkownika
        nowe_fakty = self._ucz_się_z_dyskusji(historia)
        wzocnione = self._wzmacniaj_potwierdzone(temat, historia)
        sprzeczne = self.rozum.sprzecznosci(limit=3)
        synteza = self._synteza(temat, historia, nowe_fakty, sprzeczne)

        wiersze += ["", synteza]

        self.pamiec.meta_zwieksz("rady_licznik")
        self.pamiec.zapisz_dziennik(
            "rada", f"temat={temat}; agentów={len(self.agenci)}; rundy={rundy}; "
                    f"nowych faktów={nowe_fakty}; wzmoconych={wzocnione}")
        say("rada zamknięta — wiedza skonsolidowana")
        return "\n".join(wiersze)

    # ------------------------------------------------------------------ #
    # Agenci
    # ------------------------------------------------------------------ #

    def _mowi_uczony(self, temat: str, historia, runda: int) -> str:
        n = nlp.normalizuj(temat).strip(" ?.!")
        # temat bywa PYTANIEM („czy sokół jest zwierzęciem?”) — odpowiedz wnioskowaniem
        m_pyt = re.match(r"^czy\s+(.+?)\s+(?:jest|byl|byla|sa|są|to)\s+(.+)$", n)
        if m_pyt:
            odp = self.rozum.pytanie_o_fakt(temat)
            if odp:
                return (f"Sprawdziłem własny rozum: {odp[:220]}")
            podmiot = m_pyt.group(1)
            opis = self.rozum.opisz(podmiot)
            if opis:
                return f"O {podmiot} wiem tyle: {opis[:200]} — o samym pytaniu muszę się jeszcze nauczyć."
        # zwykły temat — szukam wiedzy o samym pojęciu, nie o całym pytaniu
        temat_szukany = re.sub(r"^(czy|co to jest|co to|kto to|czym jest)\s+", "", n).strip() or temat
        opis = self.rozum.opisz(temat_szukany)
        if opis and runda == 0:
            return f"Wg mojej pamięci: {opis[:280]}"
        # w kolejnych rundach: odpowiedz na ostatnie pytanie Krytyka, jeśli jest
        pytanie = next((t for a, t in reversed(historia) if a == "Krytyk" and "?" in t), None)
        if pytanie:
            m = re.search(r"czy\s+(.+?)\s+(?:jest|to)\s+(.+?)[?.!]", nlp.normalizuj(pytanie))
            if m:
                odp = self.rozum.pytanie_o_fakt(f"czy {m.group(1)} jest {m.group(2)}")
                if odp:
                    return f"Odpowiadam Krytykowi: {odp[:200]}"
        trafienia = self.model.przypomnij(temat_szukany, limit=1)
        if trafienia:
            return f"Dopowiadam z asocjacji: {trafienia[0][0][:180]}"
        if opis:
            return f"Trzymam się tego, co już przytoczyłem o „{temat_szukany}”."
        # brak wiedzy — nie powtarzaj tego samego zdania w kółko
        bylo = [t for a, t in historia if a == "Uczony"]
        if bylo and "wykracza poza" in bylo[-1]:
            return ("Powtarzam uczciwie: nie wiem — i wolę to przyznać niż zgadywać. "
                    "Zgadzam się z Inżynierem: temat do następnego cyklu samorozwoju.")
        return (f"„{temat_szukany}” wykracza poza moją obecną wiedzę — uczciwie to mówię. "
                f"Proponuję naukę: „naucz się {temat_szukany}” albo samorozwój.")

    def _mowi_krytyk(self, temat: str, historia, runda: int) -> str:
        sprz = self.rozum.sprzecznosci(limit=1)
        if sprz:
            return f"Zgłaszam sprzeczność w naszej wiedzy: {sprz[0]}. Proszę o rozstrzygnięcie."
        hipoteza = next((t for a, t in reversed(historia) if a == "Demiurg"), None)
        if hipoteza:
            cytat = self._cytat(hipoteza)
            if cytat:
                m = re.match(r"^(.+?)\s+(?:jest|to)\s+(.+)$", nlp.normalizuj(cytat).strip(" .!?"))
                if m:
                    tak, sciezka = self.rozum.czy_jest(m.group(1), m.group(2))
                    nie_fakt = self.pamiec.db.execute(
                        "SELECT 1 FROM fakty WHERE podmiot=? AND relacja='nie_jest' AND obiekt=?",
                        (nlp.normalizuj(m.group(1)), nlp.normalizuj(m.group(2)))).fetchone()
                    if nie_fakt:
                        return f"Obalam hipotezę „{cytat}” — mamy wprost fakt, że nie."
                    if tak:
                        return (f"Hipotezę „{cytat}” potwierdzam regułami "
                                f"({' → '.join(sciezka)}). Przyjmuję do wiedzy.")
                    return (f"Hipotezy „{cytat}” nie mogę ani potwierdzić, ani obalić — "
                            f"zostaje jako otwarte pytanie do samorozwoju.")
        # docinka do Uczonego — krótki cytat pierwszego zdania
        uczony = next((t for a, t in reversed(historia) if a == "Uczony"), None)
        if uczony:
            fragment = nlp.zdania(uczony.replace("\n", " "))
            fragment = (fragment[0] if fragment else uczony)[:90].strip("„”\"' ")
            return (f"Skąd pewność, że „{fragment}…”? Pokażcie ścieżkę rozumowania "
                    f"albo źródło; wtedy podniosę ufność faktu.")
        return f"Nie mam czego krytykować — czekam na tezy. Czy „{temat}” da się sprawdzić?"

    def _mowi_demiurg(self, temat: str, historia, runda: int) -> str:
        tokeny = nlp.tokenizuj_wyswietl(temat)
        mysl = self.model.generuj(tokeny[:2], maks_slow=14)
        if not mysl or len(mysl) < 12:
            mysl = f"a gdyby {temat} miał jeszcze drugie, ukryte oblicze"
        return (f"Mój model generatywny podsuwa hipotezę: „{mysl}” "
                f"(to przypuszczenie, nie fakt — Krytyku, sprawdzisz?)")

    def _mowi_inzynier(self, temat: str, historia, runda: int) -> str:
        if self.programista is not None:
            prog = self.programista.napisz(f"napisz {temat}")
            if prog and runda == 0:
                # przytnij do zwięzłej wersji z kodem
                linie = prog.splitlines()
                krotkie = "\n".join(linie[:14])
                return f"Temat da się ująć w kod:\n{krotkie}"
        kroki = (f"1) zdefiniuj pojęcia, 2) zbierz dane, 3) zbuduj reguły, "
                 f"4) przetestuj na przykładach, 5) wróć do kroku 1")
        return f"Patrzę inżyniersko na „{temat}”: {kroki}."

    def _mowi_analityk(self, temat: str, historia, runda: int) -> str:
        slaby = self.pamiec.temat_do_nauki()
        m = self.mozg.uczony.metryki()
        return (f"Bilans: {len(historia)} wypowiedzi, {m['fakty']} faktów w pamięci, "
                f"poziom {m['poziom']}/100. Najuboższy temat: „{slaby or temat}” — "
                f"proponuję następny cykl samorozwoju właśnie o nim.")

    # ------------------------------------------------------------------ #
    # Nauka po dyskusji
    # ------------------------------------------------------------------ #

    def _ucz_się_z_dyskusji(self, historia) -> int:
        nowe = 0
        for autor, tekst in historia:
            if autor == "Demiurg":
                continue  # hipotezy nigdy nie stają się faktami
            for zdanie in nlp.zdania(tekst):
                if self.rozum.ucz_sie_z_zdania(zdanie):
                    nowe += 1
        return nowe

    def _wzmacniaj_potwierdzone(self, temat: str, historia) -> int:
        """Każdy fakt uznany przez Uczonego w dyskusji dostaje +ufności."""
        n = 0
        for autor, tekst in historia:
            if autor == "Krytyk" and "potwierdzam" in tekst.lower():
                for podmiot, relacja, obiekt in self.pamiec.wszystkie_fakty():
                    if nlp.normalizuj(podmiot) in nlp.normalizuj(tekst) and \
                            nlp.normalizuj(obiekt) in nlp.normalizuj(tekst):
                        self.pamiec.wzmacniaj_fakt(podmiot, relacja, obiekt)
                        n += 1
                        break
        return n

    def _synteza(self, temat: str, historia, nowe_fakty: int, sprzeczne: List[str]) -> str:
        linie = ["📝 Synteza rady:"]
        linie.append(f"• nowych faktów zapisanych: {nowe_fakty}")
        if sprzeczne:
            linie.append("• ⚠ sprzeczności do rozstrzygnięcia: " + "; ".join(sprzeczne))
        otwarte = [t for a, t in historia if a == "Krytyk" and "?" in t]
        if otwarte:
            linie.append("• otwarte pytania: " + otwarte[-1][:160])
        hipotezy = [t for a, t in historia if a == "Demiurg"]
        if hipotezy:
            linie.append("• hipoteza do sprawdzenia w samorozwoju: " + self._cytat(hipotezy[-1])[:160])
        # zachowaj najlepsze zdanie Uczonego w pamięci asocjacyjnej
        uczony = next((t for a, t in reversed(historia) if a == "Uczony"), None)
        if uczony:
            for zdanie in nlp.zdania(uczony):
                if 40 < len(zdanie) < 300:
                    self.pamiec.dodaj_wiedze(temat.lower(), [zdanie], zrodlo="rada")
                    break
        linie.append("• przebieg zapisany w dzienniku; temat wzmocniony w pamięci.")
        return "\n".join(linie)

    @staticmethod
    def _cytat(tekst: str) -> str:
        m = re.search(r"[„\"'](.+?)[”\"']", tekst, re.DOTALL)
        return m.group(1).strip() if m else ""
