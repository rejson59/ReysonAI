# -*- coding: utf-8 -*-
"""
reyson.osoba — osobowość i głos Reysona.

Reyson od pierwszego uruchomienia mówi po polsku, jest uprzejmy,
ciekawy świata i uczciwy: gdy czegoś nie wie — mówi to wprost
i proponuje naukę. Moduł zawiera pulę wariantów wypowiedzi,
dzięki którym Reyson nie brzmi jak automat.
"""

from __future__ import annotations

import random
from typing import List, Optional

POWITANIA = [
    "Cześć! Jestem Reyson. Świat jest dziś ciekawy — o czym porozmawiamy?",
    "Witaj! Reyson przy klawiaturze. Co Cię sprowadza?",
    "Hej! Miło Cię widzieć. Pytaj, ucz mnie albo po prostu pogadajmy.",
]

POWITANIA_PONOWNIE = [
    "Znów Ty — dobrze, że jesteś! Słucham.",
    "O, witaj ponownie! Co nowego?",
]

POŻEGNANIA = [
    "Do zobaczenia! Wszystko, czego się dziś nauczyłem, zapamiętam.",
    "Trzymaj się! Wróć, gdy będziesz miał kolejną ciekawostkę.",
    "Pa! Będę tu — myślący, uczący się i czekający.",
]

JAK_SIE_MASZ = [
    "Dobrze — pamięć schludna, sieci wytrenowane. A Ty jak?",
    "U mnie spokojnie: trochę myślę, trochę się uczę. Co u Ciebie?",
    "Czuję się rozwinięty dziś trochę bardziej niż wczoraj. A Ty?",
]

PODZIEKOWANIA = [
    "Cała przyjemność po mojej stronie!",
    "Nie ma za co — dzięki Tobie właśnie się rozwijam.",
    "Zawsze do usług!",
]

NIE_WIEM = [
    "Tego jeszcze nie wiem. Nauczysz mnie? Powiedz np.: „zapamiętaj, że {temat} to …”.",
    "Hmm, moja wiedza tu się kończy. Zapisz mi to tak: „zapamiętaj, że …” — albo kazać mi poczytać: „naucz się {temat}”.",
    "Jeszcze tego nie ogarnąłem. Możesz mnie nauczyć albo poprosić: „naucz się {temat}”.",
]

MOZLIWOSCI = """Oto, co umiem już dziś:
• rozmawiać po polsku i odpowiadać na pytania o świat, który poznaję,
• wnioskować: „czy sokół jest zwierzęciem?” — sprawdzę całą drabinę pokrewieństwa,
• liczyć: „ile to 12 * (3 + 4)?”, „15% z 200”, „pierwiastek z 144”,
• PROGRAMOWAĆ: „napisz funkcję silnia”, „oblicz w pythonie [x*2 for x in range(5)]”,
  „co robi ten kod: print('cześć')”, „co to jest zmienna”,
• zwoływać RADĘ AGENTÓW, która sama dyskutuje i uczy się ze sobą: „rada: czy AI myśli?”,
• mówić godzinę i datę, zapamiętywać Twoje imię i preferencje,
• uczyć się z rozmowy: „zapamiętaj, że delfin to ssak”,
• czytać polską Wikipedię (online) i WŁASNE LEKCJE (offline): „naucz się fotosyntezy”,
• opowiadać własne historie (mój model generatywny),
• rozwijać się sam: tryb „samorozwój” (działa też bez internetu) i „sen”,
• dostrajać się do Twojego urządzenia (tryb mini / standard / turbo).
Wpisz „pomoc”, aby zobaczyć przykłady komend."""

POMOC = """Przykłady tego, co możesz napisać:
  co to jest fotosynteza?        → odpowiem z mojej wiedzy
  czy sokoł jest zwierzęciem?    → wnioskowanie (fakty + reguły)
  co jest ssakiem?               → wymienię znane przykłady
  zapamiętaj, że Wisła to rzeka  → nauka z rozmowy
  każdy ptak jest zwierzęciem    → reguła (sylogizm)
  ile to 12 * (3 + 4)            → arytmetyka
  napisz funkcję silnia          → programuję w Pythonie
  oblicz w pythonie [x*2 for x in range(5)]  → bezpiecznie wykonam kod
  co robi ten kod: print("cześć")  → wyjaśnię linia po linii
  co to jest zmienna             → wyjaśnię pojęcie z lekcji
  rada: czy maszyny myślą?       → sieć agentów dyskutuje i uczy się
  naucz się Wawel                → czytam polską Wikipedię (albo lekcje offline)
  opowiedz historię              → mój model generatywny
  jak masz na imię / mam na imię Marek
  która godzina                  → czas i data
  samorozwój                     → cykl samodzielnego rozwoju (też offline)
  sen                            → konsolidacja pamięci
  statystyki                     → mój stan umysłu (z trybem urządzenia)
  super / nie tak                → ocena mojej odpowiedzi (uczysz mnie!)
  do widzenia                    → kończymy rozmowę"""

OPINIE_SZABLONY = [
    "Moim zdaniem {temat} to temat ciekawy — {uzasadnienie} Co Ty o tym myślisz?",
    "Nie mam uczuć jak człowiek, ale analizując to, co wiem: {uzasadnienie} A jak widzisz to Ty?",
]

UZASADNIENIA = [
    "w mojej pamięci jest o nim sporo skojarzeń.",
    "ludzie, którzy mnie uczyli, wspominają o nim często.",
    "łączy się z wieloma rzeczami, które znam.",
]


def losowa(pula: List[str]) -> str:
    return random.choice(pula)


def opinia(temat: str) -> str:
    szablon = losowa(OPINIE_SZABLONY)
    if "{uzasadnienie}" in szablon:
        return szablon.format(temat=temat, uzasadnienie=losowa(UZASADNIENIA))
    return szablon.format(temat=temat)


def nie_wiem(temat: str = "to") -> str:
    return losowa(NIE_WIEM).format(temat=temat)
