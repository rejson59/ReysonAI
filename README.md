# 🧠 ReysonAI — lekki, samorozwijający się AI mówiący po polsku

Reyson to **zupełnie nowy, autorski system AI** (model **RM-1**), napisany w czystym
Pythonie — **bez żadnych zewnętrznych zależności**. Uruchomisz go na maszynie z
**4 GB RAM** (realnie zużywa < 100 MB), a on od pierwszej sekundy **mówi po polsku**,
**rozumie** pytania, **wnioskuje**, liczy, i **rozwija się sam**: uczy się z rozmów,
z polskiej Wikipedii i z własnych „snów”.

```
Cześć! Jestem Reyson. Świat jest dziś ciekawy — o czym porozmawiamy?
Ty:  czy sokół jest zwierzęciem?
Reyson: Tak — sokol jest zwierzeciem (wnioskowałem: sokol → ptak → zwierze).
Ty:  zapamiętaj, że moja ulubiona drużyna to Legia
Reyson: Zapamiętałem: moja ulubiona drużyna to legia.
Ty:  ile to 12 * (3 + 4)?
Reyson: Liczę: 12*(3+4) = 84
```

---

## Dlaczego to działa na 4 GB RAM

RM-1 nie jest kolejnym gigantycznym LLM-em. To **hybryda trzech lekkich warstw**,
które razem dają rozumność:

| Warstwa | Co robi | Rozmiar |
|---|---|---|
| **RM-1·NN** — sieć neuronowa (czysty Python) | rozpoznaje intencję wypowiedzi (20 klas), uczy się w trakcie życia (SGD + augmentacja + L2) | ~26 tys. parametrów (< 1 MB) |
| **Pamięć asocjacyjna** TF-IDF | „przypomina sobie” zdania podobne do pytania | indeks budowany w ~1 s |
| **Rozum symboliczny** | fakty (trójki) + reguły („każdy ptak jest zwierzęciem”) + BFS po drabinie pojęć = wnioskowanie | SQLite |
| **Model generatywny** n-gramowy (bigram/trigram z backoffem) | tworzy własne zdania i „śni” (rekombinuje wiedzę) | kilka tys. rekordów |

Wszystko siedzi w **jednym pliku SQLite** (`dane/umysl.db`) + pliku wag sieci
(`dane/rm1_wagi.json`). Żadnych GPU, żadnych chmur, żadnych kluczy API.
Wikipedia (jeśli jest internet) pobierana jest publicznym REST API.

## Instalacja i szybki start — jedna komenda

Reyson nie wymaga `pip install`, żadnych pakietów ani kont w chmurze.
Wystarczy **Python 3.8+** (sprawdzisz: `python3 --version`).

**Linux / macOS / Windows (z gitem) — klonuj i rozmawiaj:**

```bash
git clone https://github.com/rejson59/ReysonAI.git && cd ReysonAI && python3 reyson.py
```

**Bez gita — pobierz archiwum i odpal (Linux/macOS):**

```bash
curl -L https://github.com/rejson59/ReysonAI/archive/refs/heads/main.tar.gz | tar xz && cd ReysonAI-main && python3 reyson.py
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/rejson59/ReysonAI.git; cd ReysonAI; python reyson.py
```

Pierwsze uruchomienie samo zbuduje umysł (~8 s) i od razu otworzy rozmowę po polsku.
Wolisz czat w przeglądarce niż terminal? Dopisz `--web`:

```bash
python3 reyson.py --web 8080     # → http://localhost:8080
```

Po instalacji napisz do Reysona `pomoc` albo zajrzyj do sekcji
[„Czym Reyson może Cię zaskoczyć”](#czym-reyson-może-cię-zaskoczyć).

## Czym Reyson może Cię zaskoczyć

* **Wnioskowanie** — zapytaj „czy ptak jest zwierzęciem?”, „czy Chopin był muzykiem?” —
  sprawdzi całą drabinę pojęć (fakty + reguły) i pokaże tor rozumowania.
* **Nauka z rozmowy** — „zapamiętaj, że …”, „każdy X jest Y”, „lubię …”, „nazywam się …”.
  Reyson też sam wyciąga fakty ze zwykłych zdań (i nie łapie się na pytania bez „?”).
* **Nauka z Wikipedii** — „naucz się fotosyntezy” → pobiera streszczenie z pl.wikipedia,
  wydobywa fakty, uczy model generatywny.
* **Arytmetyka** — „ile to 12 * (3+4)?”, „15% z 200”, „pierwiastek z 144”, „dwa plus dwa”.
* **Pamięć o Tobie** — imię, preferencje, fakty z życia („co wiesz o mnie?”).
* **Opowiadanie** — „opowiedz coś o gwiazdach” → własne zdania z modelu n-gramowego.
* **Samorozwój** — tryb autonomiczny: wybiera temat, się uczy, zadaje sobie pytania,
  odpowiada, ocenia się i zasypia (konsolidacja pamięci).
* **Sen** — porządki w n-gramach (usuwanie szumu), „śnienie” (rekombinacja wiedzy
  w nowe zdania), przebudowa indeksów, doszkolenie sieci na zebranych przykładach.
* **Oceny** — napisz „super” albo „nie tak” — Reyson zapamiętuje oceny i doszkala się.

## Komendy

W rozmowie (CLI i www): `pomoc` · `co umiesz` · `kim jesteś` · `statystyki` ·
`samorozwój` · `sen` · `dziennik` (www) · `do widzenia`.

Wiersz poleceń:

```bash
python3 reyson.py                      # rozmowa
python3 reyson.py --web [PORT]         # interfejs www (domyślnie 8000)
python3 reyson.py --naucz-sie TEMAT    # nauka tematu z polskiej Wikipedii
python3 reyson.py --samorozwoj [N]     # N cykli autonomicznego rozwoju
python3 reyson.py --sen                # konsolidacja pamięci
python3 reyson.py --statystyki         # stan umysłu (fakty, słownik, poziom)
python3 reyson.py --dziennik [N]       # dziennik rozwoju
python3 reyson.py --buduj              # przebudowa umysłu od zera
python3 reyson.py --test               # testy wewnętrzne (30 testów)
```

## Jak go rozwijać (Ty i Reyson)

1. **Rozmawiaj** — każde zdanie to nauka: słownik rośnie, fakty się dopisują.
2. **Kaz mu czytać** — `naucz się Kopernik`, `naucz się czarna dziura`, …
3. **Ucz reguł** — „każdy ssak karmi młodymi mlekiem” → Reyson zacznie wnioskować.
4. **Oceniaj** — „super” / „nie tak” wpływają na poziom rozwoju i wagi sieci.
5. **Kaz mu się rozwijać samemu** — `samorozwoj` albo `sen`.
6. **Edytuj korpus startowy** — pliki w `dane/` to zwykłe TSV:
   * `seed_fakty.tsv` — podmiot ⇥ relacja ⇥ obiekt,
   * `seed_uniwersalia.tsv` — reguły dziedziczenia,
   * `seed_wiedza.tsv` — tytuł ⇥ zdanie (pamięć asocjacyjna),
   * `seed_intencje.tsv` — przykłady treningowe sieci,
   * `seed_korpus.txt` — korpus językowy (wyobraźnia).
   Po zmianach: `python3 reyson.py --buduj`.

## Architektura (mapa kodu)

```
reyson.py            — CLI (rozmowa, web, samorozwój, sen, testy)
reyson/mozg.py       — mózg: pętla „zrozum → pomyśl → odpowiedz → naucz się”
reyson/model.py      — RM-1: sieć neuronowa intencji + TF-IDF + generator n-gramów
reyson/rozum.py      — wnioskowanie (fakty, reguły, sylogizmy), arytmetyka, czas
reyson/uczenie.py    — samorozwój: nauka z rozmowy i Wikipedii, sen, metryki
reyson/pamiec.py     — pamięć długotrwała (SQLite)
reyson/nlp.py        — polszczyzna: normalizacja, odmiana, stemmer, tokenizacja
reyson/osoba.py      — osobowość i głos (warianty wypowiedzi)
reyson/web.py        — interfejs www (czysta biblioteka standardowa)
reyson/seed.py       — ładowanie korpusu startowego
dane/seed_*          — wiedza startowa (edytuj!)
testy/               — testy (python3 reyson.py --test)
```

## Uczciwe ograniczenia

Reyson jest mały z założenia: zna to, co mu dano, i to, co sam przeczyta.
Nie halucynuje w stylu dużych LLM-ów — gdy nie wie, mówi wprost i prosi o naukę.
Formy z odmianą dopasowuje heurystycznie (radzi sobie z przypadkami, ale nie ze
wszystkimi wyjątkami), a pamięć faktów przechowuje formy uproszczone (bez
diakrytyków) — przy wyświetlaniu przywraca polskie znaki ze słownika.

## Licencja

Projekt edukacyjny — rób z nim, co chcesz. Powodzenia na drodze samorozwoju! 🌱
