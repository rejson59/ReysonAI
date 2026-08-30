# 🧠 ReysonAI 2.0 — lekki, samorozwijający się AI mówiący po polsku

Reyson to **zupełnie nowy, autorski system AI** (model **RM-2**), napisany w czystym
Pythonie — **bez żadnych zewnętrznych zależności**. Uruchomisz go na maszynie z
**4 GB RAM** (realnie zużywa < 100 MB), a on od pierwszej sekundy **mówi po polsku**,
**rozumie** pytania, **wnioskuje**, liczy, **programuje**, **zwołuje radę agentów**,
które rozmawiają ze sobą i się uczą, oraz **rozwija się sam** — także **bez internetu**.
RM-2 **automatycznie dopasowuje się do możliwości urządzenia** (tryby mini /
standard / turbo).

```
Cześć! Jestem Reyson. Świat jest dziś ciekawy — o czym porozmawiamy?
Ty:  czy sokół jest zwierzęciem?
Reyson: Tak — sokol jest zwierzeciem (wnioskowałem: sokol → ptak → zwierze).
Ty:  napisz funkcję silnia
Reyson: Silnia (rekurencyjnie i iteracyjnie) — tak to wygląda w Pythonie: …
Ty:  oblicz w pythonie [x*2 for x in range(5)]
Reyson: Wyliczyłem w Pythonie: [x*2 for x in range(5)] = [0, 2, 4, 6, 8]
Ty:  rada: czy maszyny myślą?
Reyson: 🏛️ Rada agentów RM-2 — 🎓 Uczony:… 🧐 Krytyk:… ✨ Demiurg:… 🔧 Inżynier:…
```

---

## Co nowego w RM-2

| Cecha | Co się zmieniło |
|---|---|
| 🔧 **Naprawiony samorozwój** | działa też **OFFLINE**: czyta lokalne lekcje, przegląda notatki, robi sobie **samo-sprawdzian** i **indukuje nowe reguły** z własnych faktów („3+ wspólne instancje ⇒ każdy ssak jest zwierzęciem”, z kontrolą kontrprzykładów) |
| 😴 **Naprawiony sen** | sen **prawdziwie doszkala** sieć (kontynuacja z zapisanych wag zamiast losowego restartu), wykrywa sprzeczności w wiedzy, liczba „snów” zależna od sprzętu |
| 💻 **Programowanie** | ~20 przepisów kodu (silnia, Fibonacci, sortowanie, NWD, sito, klasy…), **bezpieczny ewaluator Pythona** (własny interpreter AST — bez eval, bez importów), wyjaśnianie kodu linia po linii, uczenie się własnych programów od użytkownika, 6 lekcji offline w `dane/lekcje/` |
| 🏛️ **Sieć agentów** | rada wyspecjalizowanych agentów (🎓 Uczony, 🧐 Krytyk, ✨ Demiurg, 🔧 Inżynier, 📊 Analityk) dyskutuje w rundach, weryfikuje hipotezy, obala je, **uczy się ze swoich wypowiedzi** (hipotezy nigdy nie stają się faktami), wzmacnia potwierdzone fakty |
| ⚙️ **Auto-adaptacja** | moduł `reyson/profil.py` mierzy CPU, RAM i szybkość wątku → dobiera rozmiar sieci, epoki, rząd n-gramów (3–4), liczbę agentów (3–5), limity i timeouty. Wymuszenie: `REYSON_TRYB=mini|standard|turbo` |
| 🐛 **Lepszy rozum** | pytania o instancje („co jest ssakiem?”), porównywanie wielowyrazowych form odmienionych („jezykiem programowania” = „jezyk programowania”), wykrywanie sprzeczności |

## Dlaczego to działa na 4 GB RAM

RM-2 nie jest kolejnym gigantycznym LLM-em. To **hybryda lekkich warstw**,
które razem dają rozumność:

| Warstwa | Co robi | Rozmiar |
|---|---|---|
| **RM-2·NN** — sieć neuronowa (czysty Python) | rozpoznaje intencję wypowiedzi (21 klas), uczy się w trakcie życia (SGD + augmentacja + L2, doszkalanie przez sen) | ~26–52 tys. parametrów (< 1 MB) |
| **Pamięć asocjacyjna** TF-IDF | „przypomina sobie” zdania podobne do pytania | indeks budowany w ~1 s |
| **Rozum symboliczny** | fakty (trójki) + reguły + BFS po drabinie pojęć + indukcja reguł + detekcja sprzeczności | SQLite |
| **Model generatywny** n-gramowy (2–4-gramy z backoffem) | tworzy własne zdania i „śni” (rekombinuje wiedzę) | kilka tys. rekordów |
| **Programista** | przepisy kodu + bezpieczny ewaluator AST + wyjaśniacz | ~20 przepisów |
| **Rada agentów** | 3–5 agentów dyskutujących na wspólnej pamięci | 0 MB dodatkowej |

Wszystko siedzi w **jednym pliku SQLite** (`dane/umysl.db`) + pliku wag sieci
(`dane/rm1_wagi.json`). Żadnych GPU, żadnych chmur, żadnych kluczy API.
Wikipedia (jeśli jest internet) pobierana jest publicznym REST API; bez internetu
Reyson czyta **własną bibliotekę lekcji**.

## Instalacja i szybki start — jedna komenda

Reyson nie wymaga `pip install`, żadnych pakietów ani kont w chmurze.
Wystarczy **Python 3.8+** (sprawdzisz: `python3 --version`).

```bash
git clone https://github.com/rejson59/ReysonAI.git && cd ReysonAI && python3 reyson.py
```

Pierwsze uruchomienie samo zbuduje umysł (~10 s) i od razu otworzy rozmowę
po polsku. Czat w przeglądarce? Dopisz `--web`:

```bash
python3 reyson.py --web 8080     # → http://localhost:8080
```

## Czym Reyson może Cię zaskoczyć

* **Wnioskowanie** — „czy ptak jest zwierzęciem?”, „czy python jest językiem
  programowania?” — sprawdzi całą drabinę pojęć i pokaże tor rozumowania.
* **Instancje** — „co jest ssakiem?”, „jakie znasz zwierzęta?” — wymieni przykłady.
* **Programowanie** — „napisz funkcję silnia”, „napisz fizzbuzz”,
  „oblicz w pythonie [x**2 for x in range(10)]”,
  „co robi ten kod: print('cześć')”, „co to jest zmienna”.
* **Rada agentów** — „rada: czy sztuczna inteligencja myśli?” — sieć agentów
  sama dyskutuje, krytykuje się, generuje hipotezy i uczy się z rozmowy.
* **Nauka z rozmowy** — „zapamiętaj, że …”, „każdy X jest Y”, „lubię …”, „nazywam się …”.
* **Nauka z Wikipedii** (online) i **z lokalnych lekcji** (offline) —
  „naucz się fotosyntezy”, „naucz się pythona”.
* **Arytmetyka** — „ile to 12 * (3+4)?”, „15% z 200”, „pierwiastek z 144”.
* **Samorozwój** — tryb autonomiczny: wybiera temat, się uczy (Wikipedia albo
  lekcje), zadaje sobie pytania (samo-sprawdzian), **indukuje reguły**, ocenia się
  i zasypia. Działa także całkowicie offline.
* **Sen** — przycinanie szumu w n-gramach, „śnienie”, przebudowa indeksów,
  **doszkalanie sieci z zapisanych wag** i audyt sprzeczności.
* **Oceny** — „super” / „nie tak” — Reyson zapamiętuje oceny i doszkala się.
* **Adaptacja** — „statystyki” pokazuje wykryty tryb urządzenia; samorozwój,
  sen i rada skalują się do możliwości sprzętu.

## Komendy

W rozmowie (CLI i www): `pomoc` · `co umiesz` · `kim jesteś` · `statystyki` ·
`samorozwój` · `sen` · `rada: TEMAT` · `napisz …` · `oblicz w pythonie …` ·
`dziennik` (www) · `do widzenia`.

Wiersz poleceń:

```bash
python3 reyson.py                      # rozmowa
python3 reyson.py --web [PORT]         # interfejs www (domyślnie 8000)
python3 reyson.py --naucz-sie TEMAT    # nauka tematu (Wikipedia / lekcje offline)
python3 reyson.py --samorozwoj [N]     # N cykli autonomicznego rozwoju (też offline)
python3 reyson.py --rada TEMAT         # rada agentów dyskutuje o temacie
python3 reyson.py --sen                # konsolidacja pamięci
python3 reyson.py --statystyki         # stan umysłu (fakty, słownik, tryb, poziom)
python3 reyson.py --dziennik [N]       # dziennik rozwoju
python3 reyson.py --buduj              # przebudowa umysłu od zera
python3 reyson.py --test               # testy wewnętrzne (48 testów)

REYSON_TRYB=mini  python3 reyson.py    # wymuszenie trybu (mini/standard/turbo)
REYSON_DANE=inny_katalog python3 reyson.py  # umysł w innym katalogu
```

## Jak go rozwijać (Ty i Reyson)

1. **Rozmawiaj** — każde zdanie to nauka: słownik rośnie, fakty się dopisują.
2. **Kaz mu czytać** — `naucz się Kopernik` (online) albo wrzuć własne lekcje
   do `dane/lekcje/*.txt` (każda nowa lekcja zostanie przeczytana w samorozwoju).
3. **Ucz reguł** — „każdy ssak karmi młody mlekiem” → Reyson zacznie wnioskować.
4. **Ucz go kodu** — „zapamiętaj program kwadrat: def kwadrat(x): return x*x”.
5. **Oceniaj** — „super” / „nie tak” wpływają na poziom rozwoju i wagi sieci.
6. **Kaz mu się rozwijać** — `samorozwoj`, `sen` albo `rada: temat`.
7. **Edytuj korpus startowy** — pliki w `dane/`:
   * `seed_fakty.tsv` — podmiot ⇥ relacja ⇥ obiekt,
   * `seed_uniwersalia.tsv` — reguły dziedziczenia,
   * `seed_wiedza.tsv` — tytuł ⇥ zdanie (pamięć asocjacyjna),
   * `seed_intencje.tsv` — przykłady treningowe sieci,
   * `seed_korpus.txt` — korpus językowy (wyobraźnia),
   * `lekcje/*.txt` — lekcje offline (programowanie i nie tylko).
   Po zmianach: `python3 reyson.py --buduj`.

## Architektura (mapa kodu)

```
reyson.py            — CLI (rozmowa, web, samorozwój, sen, rada, testy)
reyson/mozg.py       — mózg: pętla „zrozum → pomyśl → odpowiedz → naucz się”
reyson/model.py      — RM-2·NN: sieć intencji + TF-IDF + generator n-gramów
reyson/rozum.py      — wnioskowanie (fakty, reguły, sylogizmy, indukcja), arytmetyka
reyson/uczenie.py    — samorozwój (online+offline), sen, lekcje, samo-sprawdzian
reyson/programista.py — umiejętność programowania (przepisy, ewaluator AST)
reyson/agenci.py     — sieć agentów: rada dyskutująca i ucząca się
reyson/profil.py     — auto-dopasowanie do urządzenia (mini/standard/turbo)
reyson/pamiec.py     — pamięć długotrwała (SQLite)
reyson/nlp.py        — polszczyzna: normalizacja, odmiana, stemmer, tokenizacja
reyson/osoba.py      — osobowość i głos (warianty wypowiedzi)
reyson/web.py        — interfejs www (czysta biblioteka standardowa)
reyson/seed.py       — ładowanie korpusu startowego + lekcji
dane/seed_*          — wiedza startowa (edytuj!)
dane/lekcje/         — lekcje offline (m.in. nauka programowania)
testy/               — testy (python3 reyson.py --test)
```

## Uczciwe ograniczenia

Reyson jest mały z założenia: zna to, co mu dano, i to, co sam przeczyta.
Nie halucynuje w stylu dużych LLM-ów — gdy nie wie, mówi wprost i prosi o naukę
(dotyczy to też agentów: hipotezy Demiurga nigdy nie trafiają do faktów, dopóki
Krytyk ich nie potwierdzi). Evaluator kodu wykonuje wyłącznie czyste wyrażenia
(bez importów, plików, dundersów) — z bezpieczeństwa nie ma kompromisów.
Formy z odmianą dopasowuje heurystycznie (radzi sobie z przypadkami, ale nie ze
wszystkimi wyjątkami), a pamięć faktów przechowuje formy uproszczone (bez
diakrytyków) — przy wyświetlaniu przywraca polskie znaki ze słownika.

## Licencja

Projekt edukacyjny — rób z nim, co chcesz. Powodzenia na drodze samorozwoju! 🌱
