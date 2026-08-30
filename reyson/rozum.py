# -*- coding: utf-8 -*-
"""
reyson.rozum — warstwa rozumowania (symboliczna).

Reyson nie tylko „przypomina sobie" — potrafi WNIOSKOWAĆ:
• łańcuchy dziedziczenia: „Sokół jest ptakiem, każdy ptak jest zwierzęciem"
  ⇒ odpowie, że sokół jest zwierzęciem,
• sylogizmy uczone od użytkownika („każdy X to Y"),
• arytmetyka (w tym zapis słowny i procenty),
• data i godzina.

To ta warstwa daje „rozumność" mimo mikroskopijnych rozmiarów modelu.
"""

from __future__ import annotations

import datetime
import re
from typing import Dict, List, Optional, Tuple

from . import nlp
from .pamiec import Pamiec

# słowna polska arytmetyka
_LICZBY_SLOWNIE: Dict[str, int] = {
    "zero": 0, "jeden": 1, "jedna": 1, "dwa": 2, "dwie": 2, "trzy": 3,
    "cztery": 4, "piec": 5, "szesc": 6, "siedem": 7, "osiem": 8, "dziewiec": 9,
    "dziesiec": 10, "jedenascie": 11, "dwanascie": 12, "trzynascie": 13,
    "czternascie": 14, "pietnascie": 15, "szesnascie": 16, "siedemnascie": 17,
    "osiemnascie": 18, "dziewietnascie": 19, "dwadziescia": 20, "trzydziesci": 30,
    "czterdziesci": 40, "piecdziesiat": 50, "szescdziesiat": 60,
    "siedemdziesiat": 70, "osiemdziesiat": 80, "dziewiecdziesiat": 90,
    "sto": 100, "dwieście": 200, "tysiac": 1000,
}

_DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
_MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
             "sierpnia", "września", "października", "listopada", "grudnia"]


class Rozum:
    """Silnik wnioskowania na faktach i regułach."""

    def __init__(self, pamiec: Pamiec):
        self.pamiec = pamiec

    # -- wnioskowanie: czy X jest Y? -----------------------------------------

    def czy_jest(self, x: str, y: str, maks_glebokosc: int = 6) -> Tuple[bool, List[str]]:
        """Sprawdza „czy x jest y" — fakty + uniwersalia, BFS z torą ścieżką."""
        x, y = nlp.normalizuj(x), nlp.normalizuj(y)
        if not x or not y:
            return False, []
        odwiedzone = {x}
        kolejka: List[Tuple[str, List[str]]] = [(x, [x])]
        while kolejka:
            biezacy, sciezka = kolejka.pop(0)
            if nlp.tez_jest_to(biezacy, y):
                return True, sciezka
            if len(sciezka) > maks_glebokosc:
                continue
            # fakty bezpośrednie
            for relacja, obiekt in self.pamiec.fakty_o(biezacy):
                if relacja in ("jest", "to", "nazywa_sie", "rodzaj", "gatunek", "typ"):
                    if obiekt not in odwiedzone:
                        odwiedzone.add(obiekt)
                        kolejka.append((obiekt, sciezka + [obiekt]))
            # uniwersalia: „każdy bieżący jest Z"
            for zrodlo, cel in self.pamiec.wszystkie_uniwersalia():
                if nlp.tez_jest_to(zrodlo, biezacy):
                    if cel not in odwiedzone:
                        odwiedzone.add(cel)
                        kolejka.append((cel, sciezka + [cel]))
        return False, []

    def wyjasnij_lancuch(self, sciezka: List[str]) -> str:
        if len(sciezka) < 2:
            return ""
        return " (wnioskowałem: " + " → ".join(sciezka) + ")"

    # -- arytmetyka -------------------------------------------------------------

    def arytmetyka(self, tekst: str) -> Optional[str]:
        """Parsuje i liczy wyrażenia matematyczne (także słowne i procenty)."""
        t = nlp.normalizuj(tekst)
        t = t.replace(",", ".")
        # procent: "15% z 200", "15 procent z 200"
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|procent)\s*(?:z|ze|od)\s*(\d+(?:\.\d+)?)", t)
        if m:
            p, z = float(m.group(1)), float(m.group(2))
            return f"{z:g} × {p:g}% = {round(z * p / 100, 4):g}"
        # pierwiastek
        m = re.search(r"pierwiastek\s*(?:kwadratowy)?\s*z\s*(?:liczby\s*)?(\d+(?:\.\d+)?)", t)
        if m:
            z = float(m.group(1))
            if z < 0:
                return "Pierwiastek z liczby ujemnej nie istnieje w liczbach rzeczywistych."
            return f"√{z:g} = {round(math_sqrt(z), 4):g}"
        # zamiana słów na cyfry
        wyrazy = t.split()
        przemapowane = []
        for w in wyrazy:
            w2 = w.strip("?.!:")
            if w2 in _LICZBY_SLOWNIE:
                przemapowane.append(str(_LICZBY_SLOWNIE[w2]))
            else:
                przemapowane.append(w)
        t2 = " ".join(przemapowane)
        t2 = t2.replace("plus", "+").replace("minus", "-").replace("dodać", "+").replace("dodac", "+")
        t2 = t2.replace("razy", "*").replace("przez", "/").replace("podzielić", "/").replace("podzielic", "/")
        t2 = re.sub(r"podziel(?:one)?\s+przez", "/", t2)
        t2 = t2.replace("×", "*").replace("÷", "/").replace("^", "**").replace("=", "==")
        m = re.search(r"(-?\d+(?:\.\d+)?)((?:\s*(?:\*\*|\*|\+|-|/|x)\s*-?\d+(?:\.\d+)?)+)", t2)
        if not m:
            return None
        wyrazenie = (m.group(1) + m.group(2)).replace(" x ", " * ")
        wyrazenie = re.sub(r"\bx\b", "*", wyrazenie)
        try:
            if not re.fullmatch(r"[-+*/(). 0-9]+", wyrazenie):
                return None
            wynik = eval(wyrazenie, {"__builtins__": {}}, {})  # ograniczone do arytmetyki
        except Exception:
            return None
        if isinstance(wynik, float) and wynik.is_integer():
            wynik = int(wynik)
        opis = wyrazenie.replace("**", "^").replace(" ", "").replace("==", "=")
        return f"{opis} = {wynik}"

    # -- czas i data ------------------------------------------------------------

    def czas_data(self) -> str:
        teraz = datetime.datetime.now()
        dzien = _DNI[teraz.weekday()]
        return (f"Jest {teraz.hour:02d}:{teraz.minute:02d}, "
                f"{dzien}, {teraz.day} {_MIESIACE[teraz.month - 1]} {teraz.year}.")

    # -- pytania o wiedzę ----------------------------------------------------------

    def pytanie_o_fakt(self, tekst: str) -> Optional[str]:
        """Odpowiada na „co to jest X", „kto to X", „czy X jest Y", „co wiesz o X"."""
        t = nlp.normalizuj(tekst).strip(" ?.!")

        # "czy X jest Y?" — wnioskowanie
        m = re.match(r"^czy\s+(.+?)\s+(?:jest|byl|byla|było|byly|sa|są)\s+(.+)$", t)
        if m:
            x, y = m.group(1), m.group(2)
            tak, sciezka = self.czy_jest(x, y)
            if tak:
                dodatek = self.wyjasnij_lancuch(sciezka) if len(sciezka) > 2 else ""
                return f"Tak — {x} jest {y}{dodatek}."
            if len(x.split()) <= 4:
                return (f'W tym, co wiem o „{x}”, nie znalazłem informacji, że jest {y}. '
                        f'Możesz mnie nauczyć: „zapamiętaj, że {x} jest {y}”.')
            return None

        # "co to jest X" / "kto to jest X" / "kto to X" / "co to X"
        m = re.match(r"^(?:co|kto|kim|czym)\s+(?:to\s+(?:jest|są|sa)?|to\s+jest\s*|jest\s*)?(.*?)(?:\?)?$", t)
        if m and any(k in t for k in ("co to", "kto to", "kim jest", "czym jest", "co jest",
                                      "kto jest", "kto byl", "kto była", "co bylo")):
            cel = m.group(1).strip()
            cel = re.sub(r"^(?:to\s+)?(?:jest|sa|są|byl|byla|było|byly)\s+", "", cel)
            if cel:
                return self.opisz(cel)

        # "co wiesz o X" / "opowiedz o X"
        m = re.match(r"^(?:co\s+(?:wiesz|wiesz\s+sie)\s+o|opowiedz\s+mi\s+o|opowiedz\s+o|powiedz\s+mi\s+coś\s+o|powiedz\s+cos\s+o)\s+(.+)$", t)
        if m:
            return self.opisz(m.group(1).strip())

        return None

    ALIASY_UZYTKOWNIKA = {"mnie", "mnie samego", "ja", "moje", "mnie samym", "o mnie"}

    def opisz(self, temat: str) -> Optional[str]:
        """Kompletuje wszystko, co Reyson wie o temacie."""
        temat = temat.strip().strip("?.!").lower()
        if not temat:
            return None
        if nlp.normalizuj(temat) in self.ALIASY_UZYTKOWNIKA:
            return self.opisz_uzytkownika()
        mapa = self.pamiec.mapa_pisowni()
        nazwa = self.pamiec.dopasuj_temat(temat) or nlp.normalizuj(temat)
        nazwa_ladna = (mapa.get(nazwa) or nazwa).capitalize()
        czesci: List[str] = []

        # 1) fakty (bez duplikatów „to X”/„jest X”)
        fakty = self.pamiec.fakty_o(temat)
        if fakty:
            def _sort(rel):
                return 0 if rel[0] == "to" else (1 if rel[0] == "jest" else 2)
            obiektowe_to = {o for r, o in fakty if r == "to"}
            relacje = []
            for relacja, obiekt in sorted(fakty, key=_sort):
                if relacja == "jest" and obiekt in obiektowe_to:
                    continue  # „jest X” dubluje „to X”
                if len(relacje) >= 6:
                    break
                obiekt_l = nlp.dostosuj_pisownie(obiekt, mapa)
                relacje.append(f"{relacja.replace('_', ' ')} {obiekt_l}" if relacja != "to"
                               else f"to {obiekt_l}")
            czesci.append(f"{nazwa_ladna}: " + "; ".join(relacje) + ".")

        # 2) fakty odwrotne (X należy do Y)
        odwrotne = self.pamiec.fakty_z_obiektem(temat)
        if odwrotne and len(czesci) < 2:
            przyklady = [nlp.dostosuj_pisownie(f"{pod} ({rel})", mapa) for pod, rel in odwrotne[:4]]
            czesci.append("Wiem też o: " + ", ".join(przyklady) + ".")

        # 3) wiedza tekstowa
        wiedza = self.pamiec.wiedza_o(temat, limit=3)
        if wiedza:
            zdania = " ".join(z for _, z in wiedza)
            czesci.append(zdania)

        # 4) pamięć asocjacyjna
        if not czesci:
            trafienia = self.model_przypomnij(temat)
            if trafienia:
                czesci.append("Przypominam sobie: " + " ".join(t for t, _ in trafienia))

        if not czesci:
            return None
        return " ".join(czesci)

    _FORMY_UZYTKOWNIKA = {
        "ma": "masz", "lubi": "lubisz", "nie_lubi": "nie lubisz",
        "pracuje_w": "pracujesz w", "pracuje_jako": "pracujesz jako",
        "mieszka_w": "mieszkasz w", "zyje_w": "żyjesz w", "studiuje": "studiujesz",
        "zajęcia": "Twoje zajęcia:",
    }

    def opisz_uzytkownika(self) -> Optional[str]:
        fakty = self.pamiec.fakty_o("użytkownik")
        if not fakty:
            return None
        czesci = []
        imie = self.imie_uzytkownika()
        if imie:
            czesci.append(f"Masz na imię {imie.capitalize()}.")
        mapa = self.pamiec.mapa_pisowni()
        inne = []
        for relacja, obiekt in fakty:
            if relacja == "ma_imie":
                continue
            forma = self._FORMY_UZYTKOWNIKA.get(relacja, relacja.replace("_", " "))
            inne.append(f"{forma} {nlp.dostosuj_pisownie(obiekt, mapa)}")
        if inne:
            czesci.append("Zapamiętałem o Tobie: " + "; ".join(inne) + ".")
        return " ".join(czesci) if czesci else None

    # wstrzykiwane przez mózg (unikam cyklu importów)
    model_przypomnij = None  # type: ignore

    # -- uczenie z języka naturalnego ---------------------------------------------

    WZORY_UCZENIA = [
        re.compile(r"^(?:zapamietaj|zapamiętaj|pamiętaj|pamietaj)\s*(?:[,;:]\s*)?(?:ż[ęe]|ze)?\s+(.+)$"),
        re.compile(r"^(?:naucz\s+się|naucz\s+sie)\s*(?:[,;:]\s*)?(?:ż[ęe]|ze)?\s+(.+)$"),
        re.compile(r"^(?:wiedz)\s*(?:[,;:]\s*)?(?:ż[ęe]|ze)?\s+(.+)$"),
    ]

    def ucz_sie_z_zdania(self, zdanie: str) -> Optional[str]:
        """Wyciąga wiedzę ze zdania typu „X to Y", „X jest Y", „lubię X", „każdy X jest Y".

        Zwraca potwierdzenie, albo None, gdy nie da się wyciągnąć faktu.
        """
        z = nlp.normalizuj(zdanie).strip().strip(".!?")
        z = re.sub(r"^(?:ze|że)\s+", "", z)
        # zdejmij resztki prefiksów poleceń ("zapamiętaj, że ...", "naucz się ...")
        z = re.sub(r"^(?:zapamietaj|zapamiętaj|pamietaj|pamiętaj|naucz\s+sie|naucz\s+się|wiedz|zapisz)"
                   r"\s*(?:[,;:]\s*)?(?:ż[ęe]|ze)?\s+", "", z)
        slowa_z = z.split()
        if not slowa_z or len(slowa_z) > 12:
            return None

        # ochrona: pytania i zaimek-podmioty nie są faktami
        # (pytanie bywa zapisane bez znaku zapytania!)
        pytajace = {"kto", "co", "jak", "czy", "gdzie", "kiedy", "ile", "czym",
                    "kim", "ktory", "ktora", "ktore", "po co", "dlaczego", "skad",
                    "czyli", "coz", "coto"}
        if slowa_z[0] in pytajace or (len(slowa_z) > 1 and slowa_z[1] in pytajace):
            return None

        # uniwersalia: "każdy ptak jest zwierzęciem" / "każdy X to Y"
        m = re.match(r"^(?:kazd[aey]|wszystkie|wszystko co jest)\s+(.+?)\s+(?:jest|to|sa|są)\s+(.+)$", z)
        if m:
            a, b = m.group(1), m.group(2)
            mapa = self.pamiec.mapa_pisowni()
            a_l, b_l = nlp.dostosuj_pisownie(a, mapa), nlp.dostosuj_pisownie(b, mapa)
            if self.pamiec.dodaj_uniwersale(a, b):
                return (f"Zapamiętałem regułę: każdy {a_l} jest {b_l}. "
                        f"Teraz będę to wnioskował.")
            return f'Regułę „każdy {a_l} jest {b_l}” już znam.'

        # negacje zapisujemy osobno (nie jako prawdę)
        m = re.match(r"^(.{2,40}?)\s+(?:jest\s+)?nie\s+(.{2,60})$", z)
        if m:
            a, b = m.group(1), m.group(2)
            if len(a.split()) <= 4 and len(b.split()) <= 4 and a not in pytajace:
                if self.pamiec.dodaj_fakt(a, "nie_jest", b, zrodlo="rozmowa", ufnosc=0.6):
                    return f"Zanotowałem: {a} nie jest {b}."
            return None

        # preferencje i posiadanie: "lubię X", "mam X", "kocham X"
        m = re.match(r"^(?:ja\s+)?(?:lubie|lubię|kocham|uwielbiam)\s+(.{2,50})$", z)
        if m:
            b = m.group(1)
            if self.pamiec.dodaj_fakt("użytkownik", "lubi", b):
                return f"Zanotowałem: lubisz {b}!"
            return "To już wiem — lubisz to."
        m = re.match(r"^(?:ja\s+)?(?:mam|posiadam)\s+(.{2,50})$", z)
        if m:
            b = m.group(1)
            if self.pamiec.dodaj_fakt("użytkownik", "ma", b):
                return f"Zanotowałem: masz {b}."
            return "To już wiem."
        m = re.match(r"^nie\s+(?:lubie|lubię)\s+(.{2,50})$", z)
        if m:
            b = m.group(1)
            if self.pamiec.dodaj_fakt("użytkownik", "nie_lubi", b):
                return f"Zanotowałem: nie lubisz {b}."

        # proste fakty: "X to Y" / "X jest Y"
        m = re.match(r"^(.{2,40}?)\s+(?:to\s+jest\s+|to\s+|jest\s+)(.{2,60})$", z)
        if m:
            a, b = m.group(1), m.group(2)
            if (a in ("to", "co", "tu", "tam") or len(a.split()) > 6 or a in pytajace
                    or "," in a or "," in b):
                return None
            if b.startswith(("bardzo", "naprawde", "naprawdę")):
                return None
            if self.pamiec.dodaj_fakt(a, "to", b):
                self.pamiec.dodaj_fakt(a, "jest", b, zrodlo="rozmowa", ufnosc=0.85)
                mapa = self.pamiec.mapa_pisowni()
                return f"Zapamiętałem: {nlp.dostosuj_pisownie(a, mapa)} to {nlp.dostosuj_pisownie(b, mapa)}."
            return None  # znane — nie odzywaj się w każdej wypowiedzi

        # pierwszoosobowe bez podmiotu: "pracuję w banku", "mieszkam w X", "studiuje X"
        m = re.match(r"^(pracuje|pracuję|zyje|żyje|studiuje|mieszkam|poszukuje|szukam|pisze|piszę)"
                     r"(?:\s+(w|we|na|jako|do))?\s+(.{2,60})$", z)
        if m:
            czas, przyimek, b = m.group(1), m.group(2) or "", m.group(3)
            if czas.startswith("pracuje"):
                relacja = "pracuje_jako" if przyimek == "jako" else ("pracuje_w" if przyimek in ("w", "we", "na", "do") else "zajęcia")
            elif czas.startswith(("mieszkam",)):
                relacja = "mieszka_w" if przyimek in ("w", "we", "na") else "zajęcia"
            elif czas.startswith(("zyje", "żyje")):
                relacja = "zyje_w" if przyimek in ("w", "we", "na") else "zajęcia"
            else:
                relacja = "zajęcia"
            obiekt = b if relacja != "zajęcia" else f"{czas} {przyimek} {b}".replace("  ", " ")
            if self.pamiec.dodaj_fakt("użytkownik", relacja, obiekt):
                forma = self._FORMY_UZYTKOWNIKA.get(relacja, relacja)
                return f"Zanotowałem o Tobie: {forma} {nlp.dostosuj_pisownie(obiekt, self.pamiec.mapa_pisowni())}."
            return None

        # inne relacje: "X ma Y", "X lubi Y", "X mieszka w Y", "X pracuje w/jako Y"
        m = re.match(r"^(.{2,40}?)\s+(ma|lubi|pracuje|mieszka|studiuje)"
                     r"(?:\s+(?:w|we|na|jako))?\s+(.{2,60})$", z)
        if m:
            a, rel, b = m.group(1), m.group(2), m.group(3)
            if a in pytajace or a in ("ja", "ty"):
                return None
            if self.pamiec.dodaj_fakt(a, rel, b):
                mapa = self.pamiec.mapa_pisowni()
                return (f"Zapamiętałem: {nlp.dostosuj_pisownie(a, mapa)} {rel} "
                        f"{nlp.dostosuj_pisownie(b, mapa)}.")
            return None

        return None

    # -- imię użytkownika ------------------------------------------------------------

    def zapamietaj_imie(self, tekst: str) -> Optional[str]:
        # działamy na ORYGINALNYM tekście, żeby zachować polskie znaki w imieniu
        m = re.search(r"(?:[Nn]azywa[mw]\s+si[ęe]|[Mm]am\s+na\s+imi[ęe]|[Jj]estem)\s+([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+)", tekst)
        if m:
            imie = m.group(1).capitalize()
            if imie in ("Dobry", "Zly", "Zły", "Zmeczony", "Zmęczony", "Glodny", "Głodny"):
                return None  # "jestem zmęczony" ≠ imię
            self.pamiec.dodaj_fakt("użytkownik", "ma_imie", imie, zrodlo="rozmowa", ufnosc=0.95)
            return imie
        return None

    def imie_uzytkownika(self) -> Optional[str]:
        fakty = self.pamiec.fakty_o("użytkownik")
        for relacja, obiekt in fakty:
            if relacja == "ma_imie":
                return obiekt
        return None


def math_sqrt(x: float) -> float:
    return x ** 0.5
