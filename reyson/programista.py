# -*- coding: utf-8 -*-
"""
reyson.programista — umiejętność programowania Reysona (nowość RM-2).

Reyson potrafi teraz:
• PISAĆ kod — biblioteka „przepisów” (silnia, Fibonacci, sortowanie, FizzBuzz,
  palindrom, NWD, liczby pierwsze, tabliczka mnożenia, …) + przepisy nauczone
  od użytkownika („zapamiętaj program, który …”);
• LICZYĆ w Pythonie — własny, bezpieczny interpreter wyrażeń na drzewie AST
  (bez eval, bez importów, bez dundersów; limity głębokości, rozmiaru i kroków);
• WYJAŚNIAĆ kod — linia po linii, po polsku (heurystyki dla def/for/if/while…);
• UCZYĆ SIĘ programowania offline — lekcje w dane/lekcje/ (czyta je samorozwój).

Bezpieczeństwo: evaluator dopuszcza wyłącznie wyliczenia czysto arytmetyczno-
-funkcyjne (list, dict, str, comprehensions, bezpieczne metody). Każdy inny
węzeł AST jest odrzucany z czytelnym komunikatem.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import List, Optional

from . import nlp


# --------------------------------------------------------------------------- #
# 1. Bezpieczny evaluator wyrażeń Pythona (własny interpreter AST)
# --------------------------------------------------------------------------- #

class BladKodu(Exception):
    """Czytelny dla człowieka błąd wykonywania/parsowania wyrażenia."""


_BEZPIECZNE_FUNKCJE = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "sorted": sorted, "reversed": reversed, "list": list, "set": set, "dict": dict,
    "tuple": tuple, "str": str, "int": int, "float": float, "bool": bool,
    "range": range, "enumerate": enumerate, "zip": zip, "divmod": divmod,
    "pow": pow, "ord": ord, "chr": chr, "any": any, "all": all,
}
_BEZPIECZNE_METODY = frozenset({
    "upper", "lower", "title", "capitalize", "casefold", "strip", "lstrip",
    "rstrip", "split", "rsplit", "splitlines", "join", "replace", "startswith",
    "endswith", "count", "find", "index", "sort", "append", "extend", "insert",
    "remove", "pop", "clear", "copy", "reverse", "get", "keys", "values",
    "items", "update", "add", "discard", "union", "intersection", "difference",
    "isdigit", "isalpha", "isalnum", "isspace", "islower", "isupper",
})
_OPTY_BINARNE = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.LShift: operator.lshift,
    ast.RShift: operator.rshift, ast.BitOr: operator.or_, ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}
_OPTY_UNARNE = {
    ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_,
    ast.Invert: operator.invert,
}
_OPTY_POROWNANIA = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Is: operator.is_, ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}

_MAKS_GLEBIA = 60          # zagnieżdżenie wyrażenia
_MAKS_KROKI = 30_000       # liczba odwiedzonych węzłów (ochrona przed ciężką pracą)
_MAKS_ZNAKOW = 20_000      # długość napisów
_MAKS_ELEMENTOW = 100_000  # długość kontenerów
_MAKS_LICZBA = 10 ** 15


class _Licznik:
    def __init__(self) -> None:
        self.kroki = 0

    def tik(self) -> None:
        self.kroki += 1
        if self.kroki > _MAKS_KROKI:
            raise BladKodu("wyrażenie jest zbyt złożone (limit obliczeń)")


def _sprawdz_wartosc(w) -> None:
    if isinstance(w, (str, bytes)) and len(w) > _MAKS_ZNAKOW:
        raise BladKodu("wynik jest zbyt długi")
    if isinstance(w, (list, tuple, set, dict, range)) and len(w) > _MAKS_ELEMENTOW:
        raise BladKodu("wynik ma zbyt wiele elementów")
    if isinstance(w, int) and not isinstance(w, bool) and abs(w) > _MAKS_LICZBA:
        raise BladKodu("liczba wychodzi poza bezpieczny zakres")


def _wart(wezel, licznik: "_Licznik", srod: Optional[dict] = None, glebia: int = 0):
    """Rekurencyjnie wylicza wartość węzła AST w whiteliście bezpiecznych elementów.

    `srod` to środowisko zmiennych pętli dla wyrażeń listowych (comprehension).
    """
    licznik.tik()
    if glebia > _MAKS_GLEBIA:
        raise BladKodu("za dużo zagnieżdżeń")
    srod = srod or {}

    if isinstance(wezel, ast.Constant):
        w = wezel.value
        if isinstance(w, (int, float, bool, str, bytes, type(None))):
            if isinstance(w, (int, float)) and not isinstance(w, bool) \
                    and abs(w) > _MAKS_LICZBA ** 2:
                raise BladKodu("stała liczbowa poza bezpiecznym zakresem")
            return w
        raise BladKodu(f"nieobsługiwana stała: {type(w).__name__}")

    if isinstance(wezel, ast.Name):
        if wezel.id in srod:
            return srod[wezel.id]
        if wezel.id in _BEZPIECZNE_FUNKCJE:
            return _BEZPIECZNE_FUNKCJE[wezel.id]
        raise BladKodu(f"nie znam nazwy „{wezel.id}” "
                       f"(dozwolone funkcje: {', '.join(sorted(_BEZPIECZNE_FUNKCJE))})")

    if isinstance(wezel, (ast.List, ast.Tuple, ast.Set)):
        elementy = [_wart(e, licznik, srod, glebia + 1) for e in wezel.elts]
        w = elementy if isinstance(wezel, ast.List) else (
            set(elementy) if isinstance(wezel, ast.Set) else tuple(elementy))
        _sprawdz_wartosc(w)
        return w

    if isinstance(wezel, ast.Dict):
        w = {}
        for k, v in zip(wezel.keys, wezel.values):
            if k is not None:
                w[_wart(k, licznik, srod, glebia + 1)] = _wart(v, licznik, srod, glebia + 1)
        _sprawdz_wartosc(w)
        return w

    if isinstance(wezel, ast.BinOp):
        op = _OPTY_BINARNE.get(type(wezel.op))
        if op is None:
            raise BladKodu("nieznana operacja")
        a = _wart(wezel.left, licznik, srod, glebia + 1)
        b = _wart(wezel.right, licznik, srod, glebia + 1)
        if isinstance(wezel.op, ast.Pow) and (abs(a) > 1000 or abs(b) > 64):
            raise BladKodu("potęga jest zbyt duża, żebym liczył ją bezpiecznie")
        try:
            w = op(a, b)
        except ZeroDivisionError:
            raise BladKodu("wychodzi dzielenie przez zero")
        except TypeError:
            raise BladKodu("typy nie pasują do tej operacji")
        _sprawdz_wartosc(w)
        return w

    if isinstance(wezel, ast.UnaryOp):
        op = _OPTY_UNARNE.get(type(wezel.op))
        if op is None:
            raise BladKodu("nieznana operacja jednoargumentowa")
        w = op(_wart(wezel.operand, licznik, srod, glebia + 1))
        _sprawdz_wartosc(w)
        return w

    if isinstance(wezel, ast.BoolOp):
        wartosci = wezel.values
        if isinstance(wezel.op, ast.And):
            w = True
            for e in wartosci:
                w = _wart(e, licznik, srod, glebia + 1)
                if not w:
                    return w
            return w
        w = False
        for e in wartosci:
            w = _wart(e, licznik, srod, glebia + 1)
            if w:
                return w
        return w

    if isinstance(wezel, ast.Compare):
        lewa = _wart(wezel.left, licznik, srod, glebia + 1)
        for op_wezel, prawa_wezel in zip(wezel.ops, wezel.comparators):
            op = _OPTY_POROWNANIA.get(type(op_wezel))
            if op is None:
                raise BladKodu("nieznane porównanie")
            prawa = _wart(prawa_wezel, licznik, srod, glebia + 1)
            try:
                ok = op(lewa, prawa)
            except TypeError as e:
                raise BladKodu(f"nie da się porównać tych wartości ({e})")
            if not ok:
                return False
            lewa = prawa
        return True

    if isinstance(wezel, ast.IfExp):
        warunek = _wart(wezel.test, licznik, srod, glebia + 1)
        return _wart(wezel.body if warunek else wezel.orelse, licznik, srod, glebia + 1)

    if isinstance(wezel, ast.Call):
        fn = _wart(wezel.func, licznik, srod, glebia + 1)
        argumenty = [_wart(a, licznik, srod, glebia + 1) for a in wezel.args]
        nazwy = {k.arg: _wart(k.value, licznik, srod, glebia + 1) for k in wezel.keywords}
        try:
            w = fn(*argumenty, **nazwy)
        except ZeroDivisionError:
            raise BladKodu("wychodzi dzielenie przez zero")
        except (TypeError, ValueError, AttributeError, KeyError, IndexError) as e:
            raise BladKodu(f"to wywołanie nie wyszło: {e}")
        if isinstance(w, range):
            w = list(w)  # materializujemy od razu — bez leniwych generatorów
        _sprawdz_wartosc(w)
        return w

    if isinstance(wezel, ast.Attribute):
        if wezel.attr not in _BEZPIECZNE_METODY:
            raise BladKodu(f"metoda „.{wezel.attr}” nie znajduje się w moim bezpiecznym zestawie")
        return getattr(_wart(wezel.value, licznik, srod, glebia + 1), wezel.attr)

    if isinstance(wezel, ast.Subscript):
        pojemnik = _wart(wezel.value, licznik, srod, glebia + 1)
        wycinek = _wart(wezel.slice, licznik, srod, glebia + 1)
        try:
            return pojemnik[wycinek]
        except (IndexError, KeyError, TypeError, ValueError) as e:
            raise BladKodu(f"nie da się tego poindeksować: {e}")

    if isinstance(wezel, ast.Slice):
        dol = _wart(wezel.lower, licznik, srod, glebia + 1) if wezel.lower else None
        gora = _wart(wezel.upper, licznik, srod, glebia + 1) if wezel.upper else None
        krok = _wart(wezel.step, licznik, srod, glebia + 1) if wezel.step else None
        return slice(dol, gora, krok)

    if isinstance(wezel, ast.Index):  # Python 3.8
        return _wart(wezel.value, licznik, srod, glebia + 1)

    if isinstance(wezel, (ast.ListComp, ast.SetComp)):
        wynik = []
        for nowe_srod in _kombinacje(wezel.generators, srod, licznik, glebia + 1):
            wynik.append(_wart(wezel.elt, licznik, nowe_srod, glebia + 1))
        _sprawdz_wartosc(wynik)
        return wynik if isinstance(wezel, ast.ListComp) else set(wynik)

    if isinstance(wezel, ast.GeneratorExp):
        # sum(x for x in range(100)) — wyliczamy eagerly, ale z limitem kroków
        wynik = []
        for nowe_srod in _kombinacje(wezel.generators, srod, licznik, glebia + 1):
            wynik.append(_wart(wezel.elt, licznik, nowe_srod, glebia + 1))
        _sprawdz_wartosc(wynik)
        return iter(wynik)

    if isinstance(wezel, ast.DictComp):
        wynik = {}
        for nowe_srod in _kombinacje(wezel.generators, srod, licznik, glebia + 1):
            klucz = _wart(wezel.key, licznik, nowe_srod, glebia + 1)
            wynik[klucz] = _wart(wezel.value, licznik, nowe_srod, glebia + 1)
        _sprawdz_wartosc(wynik)
        return wynik

    raise BladKodu(f"nie obsługuję elementu języka: {type(wezel).__name__}")


def _kombinacje(generatory, srod_zewn: dict, licznik: "_Licznik", glebia: int):
    """Kolejne środowiska zmiennych pętli w comprehension (razem z warunkami ifs)."""
    if glebia > _MAKS_GLEBIA:
        raise BladKodu("za dużo zagnieżdżonych comprehension")

    def schodz(i: int, srod: dict):
        licznik.tik()
        if i == len(generatory):
            yield dict(srod)
            return
        gen = generatory[i]
        if not isinstance(gen, ast.comprehension):
            raise BladKodu("zły generator w wyrażeniu listowym")

        def przypisz(cel, wartosc, dokad: dict):
            # rozpakowanie krotek: „for k, v in …” oraz prosta zmienna: „for x in …»
            if isinstance(cel, ast.Name):
                dokad[cel.id] = wartosc
            elif isinstance(cel, (ast.Tuple, ast.List)):
                if not isinstance(wartosc, (list, tuple)) or len(wartosc) != len(cel.elts):
                    raise BladKodu("nie zgadza się liczba zmiennych w rozpakowaniu")
                for c2, w2 in zip(cel.elts, wartosc):
                    przypisz(c2, w2, dokad)
            else:
                raise BladKodu("rozwijam tylko proste zmienne pętli w comprehension")

        for element in _wart(gen.iter, licznik, srod, glebia + 1):
            przypisz(gen.target, element, srod)
            if all(_wart(war, licznik, srod, glebia + 1) for war in gen.ifs):
                yield from schodz(i + 1, srod)
        if isinstance(gen.target, ast.Name):
            srod.pop(gen.target.id, None)
        else:  # rozpakowana krotka — sprzątamy po nazwach
            for c2 in getattr(gen.target, "elts", []):
                if isinstance(c2, ast.Name):
                    srod.pop(c2.id, None)

    yield from schodz(0, dict(srod_zewn))


def policz_wyrazenie(wyrazenie: str) -> str:
    """Bezpiecznie wylicza czyste wyrażenie Pythona i zwraca wynik jako tekst."""
    wyrazenie = wyrazenie.strip().strip("`").strip()
    if not wyrazenie or len(wyrazenie) > 300:
        raise BladKodu("wyrażenie jest puste albo zbyt długie")
    if re.search(r"__|\bimport\b|\blambda\b|\bexec\b|\beval\b|\bglobals\b|\bopen\b",
                 wyrazenie):
        raise BladKodu("wyrażenie zawiera niedozwolone elementy")
    try:
        drzewo = ast.parse(wyrazenie, mode="eval")
    except SyntaxError as e:
        raise BladKodu(f"to nie jest poprawne wyrażenie Pythona ({e.msg})")
    wynik = _wart(drzewo.body, _Licznik())
    if isinstance(wynik, range):
        wynik = list(wynik)
    if isinstance(wynik, float) and wynik.is_integer() and abs(wynik) < 10 ** 12:
        wynik = int(wynik)
    if isinstance(wynik, bool):
        return "True" if wynik else "False"
    return repr(wynik) if isinstance(wynik, str) else str(wynik)


# --------------------------------------------------------------------------- #
# 2. Biblioteka przepisów kodu
# --------------------------------------------------------------------------- #

PRZEPISY_BAZOWE: List[dict] = [
    {"klucze": ("silnia", "factorial"), "tytul": "Silnia (rekurencyjnie i iteracyjnie)",
     "kod": ("def silnia(n):\n"
             "    if n <= 1:\n"
             "        return 1\n"
             "    return n * silnia(n - 1)\n"
             "\n"
             "def silnia_iter(n):\n"
             "    wynik = 1\n"
             "    for i in range(2, n + 1):\n"
             "        wynik *= i\n"
             "    return wynik\n"
             "\n"
             "print(silnia(5), silnia_iter(5))  # 120 120")},
    {"klucze": ("fibonacci", "fib", "ciag fibonacciego"), "tytul": "Ciąg Fibonacciego",
     "kod": ("def fibonacci(n):\n"
             "    a, b = 0, 1\n"
             "    for _ in range(n):\n"
             "        a, b = b, a + b\n"
             "    return a\n"
             "\n"
             "print([fibonacci(i) for i in range(10)])  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]")},
    {"klucze": ("fizzbuzz", "fizz buzz"), "tytul": "FizzBuzz",
     "kod": ("for i in range(1, 101):\n"
             "    if i % 15 == 0:\n"
             "        print('FizzBuzz')\n"
             "    elif i % 3 == 0:\n"
             "        print('Fizz')\n"
             "    elif i % 5 == 0:\n"
             "        print('Buzz')\n"
             "    else:\n"
             "        print(i)")},
    {"klucze": ("sortow", "posortuj", "babelkowe"), "tytul": "Sortowanie listy",
     "kod": ("liczby = [5, 2, 9, 1, 7]\n"
             "print(sorted(liczby))            # [1, 2, 5, 7, 9]\n"
             "\n"
             "def babelkowe(lista):            # klasyka „na piechotę”\n"
             "    for i in range(len(lista)):\n"
             "        for j in range(len(lista) - 1 - i):\n"
             "            if lista[j] > lista[j + 1]:\n"
             "                lista[j], lista[j + 1] = lista[j + 1], lista[j]\n"
             "    return lista\n"
             "\n"
             "print(babelkowe(liczby[:]))")},
    {"klucze": ("palindrom", "czytane wspak", "wspak"), "tytul": "Palindrom",
     "kod": ("def palindrom(tekst):\n"
             "    tekst = tekst.lower().replace(' ', '')\n"
             "    return tekst == tekst[::-1]\n"
             "\n"
             "print(palindrom('kajak'))   # True\n"
             "print(palindrom('Ada'))     # True")},
    {"klucze": ("nwd", "euklides", "najwiekszy wspolny dzielnik"),
     "tytul": "NWD algorytmem Euklidesa",
     "kod": ("def nwd(a, b):\n"
             "    while b:\n"
             "        a, b = b, a % b\n"
             "    return a\n"
             "\n"
             "print(nwd(48, 36))  # 12")},
    {"klucze": ("liczby pierwsze", "pierwsza", "sito"), "tytul": "Liczby pierwsze (sito Eratostenesa)",
     "kod": ("def sito(n):\n"
             "    pierwsze = [True] * (n + 1)\n"
             "    pierwsze[0:2] = [False, False]\n"
             "    for i in range(2, int(n ** 0.5) + 1):\n"
             "        if pierwsze[i]:\n"
             "            for k in range(i * i, n + 1, i):\n"
             "                pierwsze[k] = False\n"
             "    return [i for i, p in enumerate(pierwsze) if p]\n"
             "\n"
             "print(sito(30))  # [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]")},
    {"klucze": ("suma listy", "zsumuj", "suma elementow"), "tytul": "Suma elementów listy",
     "kod": ("liczby = [3, 7, 2, 8, 5]\n"
             "print(sum(liczby))               # 25\n"
             "\n"
             "suma = 0                         # wersja „na piechotę”\n"
             "for x in liczby:\n"
             "    suma += x\n"
             "print(suma)")},
    {"klucze": ("sredni", "srednia"), "tytul": "Średnia arytmetyczna",
     "kod": ("def srednia(lista):\n"
             "    return sum(lista) / len(lista) if lista else 0\n"
             "\n"
             "print(srednia([2, 4, 6, 8]))  # 5.0")},
    {"klucze": ("odwroc string", "odwracanie napisu", "odwroc napis", "string wspak"),
     "tytul": "Odwracanie napisu",
     "kod": ("napis = 'Reyson'\n"
             "print(napis[::-1])        # nosyeR\n"
             "print(''.join(reversed(napis)))")},
    {"klucze": ("licznik slow", "policz slowa", "zliczanie slow"), "tytul": "Licznik słów w tekście",
     "kod": ("from collections import Counter\n"
             "\n"
             "tekst = 'kot pies kot kot pies'\n"
             "licznik = Counter(tekst.split())\n"
             "print(licznik)             # Counter({'kot': 3, 'pies': 2})\n"
             "print(licznik.most_common(1))")},
    {"klucze": ("tabliczka mnozenia", "mnozenie", "tabliczka"), "tytul": "Tabliczka mnożenia",
     "kod": ("for i in range(1, 11):\n"
             "    for j in range(1, 11):\n"
             "        print(f'{i * j:4}', end='')\n"
             "    print()")},
    {"klucze": ("temperatura", "celsjusz", "fahrenheit", "konwersja temperatury"),
     "tytul": "Konwersja temperatur",
     "kod": ("def na_fahrenheit(c):\n"
             "    return c * 9 / 5 + 32\n"
             "\n"
             "def na_celsjusze(f):\n"
             "    return (f - 32) * 5 / 9\n"
             "\n"
             "print(na_fahrenheit(100))  # 212.0\n"
             "print(na_celsjusze(212))   # 100.0")},
    {"klucze": ("bmi", "indeks masy ciala"), "tytul": "Kalkulator BMI",
     "kod": ("def bmi(waga_kg, wzrost_m):\n"
             "    return round(waga_kg / wzrost_m ** 2, 1)\n"
             "\n"
             "print(bmi(70, 1.75))  # 22.9")},
    {"klucze": ("duplikaty", "powtarzajace sie", "unikalne"), "tytul": "Duplikaty w liście",
     "kod": ("lista = [1, 2, 2, 3, 4, 4, 5]\n"
             "print(list(set(lista)))            # unikalne: [1, 2, 3, 4, 5]\n"
             "print([x for i, x in enumerate(lista) if x in lista[:i]])  # duplikaty: [2, 4]")},
    {"klucze": ("wyszukiwanie binarne", "binary search", "szukaj w posortowanej"),
     "tytul": "Wyszukiwanie binarne",
     "kod": ("def szukaj_binarnie(lista, cel):\n"
             "    lo, hi = 0, len(lista) - 1\n"
             "    while lo <= hi:\n"
             "        mid = (lo + hi) // 2\n"
             "        if lista[mid] == cel:\n"
             "            return mid\n"
             "        if lista[mid] < cel:\n"
             "            lo = mid + 1\n"
             "        else:\n"
             "            hi = mid - 1\n"
             "    return -1\n"
             "\n"
             "print(szukaj_binarnie([1, 3, 5, 7, 9, 11], 7))  # 3")},
    {"klucze": ("zgadywanka", "losowa liczba", "gra w zgadywanie", "losuj"),
     "tytul": "Zgadywanka (losowa liczba)",
     "kod": ("import random\n"
             "\n"
             "sekret = random.randint(1, 100)\n"
             "proby = 0\n"
             "while True:\n"
             "    strzal = int(input('Twój strzał (1-100): '))\n"
             "    proby += 1\n"
             "    if strzal < sekret:\n"
             "        print('za mało...')\n"
             "    elif strzal > sekret:\n"
             "        print('za dużo...')\n"
             "    else:\n"
             "        print(f'trafiony w {proby} próbach!')\n"
             "        break")},
    {"klucze": ("plik", "zapis do pliku", "czytanie pliku"), "tytul": "Praca z plikiem",
     "kod": ("with open('notatki.txt', 'w', encoding='utf-8') as f:\n"
             "    f.write('Reyson uczy się programować.\\n')\n"
             "\n"
             "with open('notatki.txt', encoding='utf-8') as f:\n"
             "    print(f.read())")},
    {"klucze": ("klasa", "obiekt", "programowanie obiektowe", "oop"),
     "tytul": "Klasa (programowanie obiektowe)",
     "kod": ("class Zwierze:\n"
             "    def __init__(self, nazwa, dzwiek):\n"
             "        self.nazwa = nazwa\n"
             "        self.dzwiek = dzwiek\n"
             "\n"
             "    def powiedz(self):\n"
             "        return f'{self.nazwa} mówi: {self.dzwiek}!'\n"
             "\n"
             "kot = Zwierze('Kot', 'miau')\n"
             "print(kot.powiedz())  # Kot mówi: miau!")},
    {"klucze": ("slownik", "dict", "pary klucz wartosc"), "tytul": "Słownik (dict)",
     "kod": ("wiek = {'Ala': 30, 'Bartek': 25}\n"
             "wiek['Celina'] = 28\n"
             "\n"
             "for imie, lata in wiek.items():\n"
             "    print(f'{imie} ma {lata} lat')\n"
             "\n"
             "print(max(wiek, key=wiek.get))  # najstarsza osoba")},
    {"klucze": ("petla", "petle", "for while", "iteracja"), "tytul": "Pętle for i while",
     "kod": ("for i in range(5):          # pętla po liczbach 0..4\n"
             "    print(i)\n"
             "\n"
             "n = 5\n"
             "while n > 0:                # pętla z warunkiem\n"
             "    print(n)\n"
             "    n -= 1")},
]


def _dopasuj_przepis(tekst: str) -> Optional[dict]:
    """Wybiera przepis o największej liczbie trafionych słów kluczowych."""
    t = nlp.normalizuj(tekst)
    najlepszy, najlepszy_wynik = None, 0
    for przepis in PRZEPISY_BAZOWE:
        wynik = sum(1 for k in przepis["klucze"] if nlp.normalizuj(k) in t)
        if wynik > najlepszy_wynik:
            najlepszy, najlepszy_wynik = przepis, wynik
    return najlepszy if najlepszy_wynik > 0 else None


def _dopasuj_wlasny_przepis(pamiec, tekst: str):
    t = nlp.normalizuj(tekst)
    najlepszy, najlepszy_wynik = None, 0
    for temat, _jezyk, kod in pamiec.przepisy(limit=200):
        wynik = sum(1 for slowo in temat.split() if len(slowo) > 3 and slowo in t)
        if wynik > najlepszy_wynik:
            najlepszy, najlepszy_wynik = (temat, kod), wynik
    return najlepszy if najlepszy_wynik > 0 else None


# --------------------------------------------------------------------------- #
# 3. Wyjaśnianie kodu po polsku
# --------------------------------------------------------------------------- #

def wyjasnij_kod(kod: str) -> str:
    """Linia po linii opisuje, co robi prosty program (heurystyki)."""
    linie = [l.rstrip() for l in kod.strip().splitlines() if l.strip()]
    if not linie:
        return "Nie widzę tu żadnego kodu."
    opisy: List[str] = []
    for i, linia in enumerate(linie, 1):
        k = linia.strip()
        wciecie = len(linia) - len(linia.lstrip())
        poziom = " (wewnątrz bloku)" if wciecie >= 4 else ""
        if k.startswith("#"):
            op = "komentarz — interpreter go pomija"
        elif k.startswith(("import ", "from ")):
            op = "importuje bibliotekę"
        elif k.startswith("def "):
            nazwa = k[4:].split("(")[0]
            op = f"definiuje funkcję „{nazwa}”{poziom}"
        elif k.startswith("class "):
            nazwa = k[6:].split("(")[0].strip(": ")
            op = f"definiuje klasę „{nazwa}” (szablon obiektów){poziom}"
        elif k.startswith("for "):
            op = f"pętla — kod wykona się dla kolejnych elementów{poziom}"
        elif k.startswith("while "):
            op = f"pętla — powtarza, dopóki warunek jest prawdziwy{poziom}"
        elif k.startswith("if "):
            op = f"warunek{poziom}"
        elif k.startswith("elif "):
            op = f"warunek alternatywny{poziom}"
        elif k.startswith("else"):
            op = f"gałąź „w przeciwnym razie”{poziom}"
        elif k.startswith("try"):
            op = "początek bezpiecznego bloku (łapanie błędów)"
        elif k.startswith(("except", "finally")):
            op = "obróbka błędu / sprzątanie po try"
        elif k.startswith("return"):
            op = f"zwraca wynik funkcji{poziom}"
        elif k.startswith(("print(", "print (")):
            op = "wypisuje na ekran"
        elif k.startswith("with "):
            op = "otwiera zasób (np. plik) i automatycznie go zamknie"
        elif re.match(r"^[A-Za-z_]\w*(\s*,\s*[A-Za-z_]\w*)*\s*=[^=]", k):
            op = f"przypisuje wartość do zmiennej{poziom}"
        else:
            op = f"wykonuje: {k[:60]}{'…' if len(k) > 60 else ''}"
        opisy.append(f"  {i:2}. {op}")
    petle = sum(1 for l in linie if l.strip().startswith(("for ", "while ")))
    warunki = sum(1 for l in linie if l.strip().startswith(("if ", "elif ", "else")))
    funkcje = sum(1 for l in linie if l.strip().startswith("def "))
    czesci = []
    if funkcje:
        czesci.append(f"{funkcje} {'funkcję' if funkcje == 1 else 'funkcje'}")
    if petle:
        czesci.append(f"{petle} {'pętlę' if petle == 1 else 'pętle'}")
    if warunki:
        czesci.append(f"{warunki} {'warunek' if warunki == 1 else 'warunki'}")
    ogolnie = ("Program zawiera " + ", ".join(czesci) + ".") if czesci else \
        "To prosty ciąg instrukcji bez pętli i warunków."
    return "Ten kod, krok po kroku:\n" + "\n".join(opisy) + f"\nPodsumowanie: {ogolnie}"


# --------------------------------------------------------------------------- #
# 4. Brama główna — używana przez mózg
# --------------------------------------------------------------------------- #

_WZORY_PYTHONA = re.compile(
    r"(?:oblicz|policz|wykonaj|ile to|ile jest)\s+w\s+pythonie\s*[:,]?\s*(.+)$"
    r"|python(?:ie)?\s*[:：]\s*(.+)$"
    r"|^wykonaj\s+wyrazenie\s*[:,]?\s*(.+)$",
    re.IGNORECASE,
)


class Programista:
    """Moduł programistyczny Reysona — pisanie, liczenie i wyjaśnianie kodu."""

    nazwa = "Inżynier"

    def __init__(self, pamiec, rozum=None):
        self.pamiec = pamiec
        self.rozum = rozum  # wstrzykiwany przez mózg (dla pytań o pojęcia)

    # -- pisanie kodu ----------------------------------------------------------

    def napisz(self, tekst: str) -> Optional[str]:
        t = tekst.strip()
        wlasny = _dopasuj_wlasny_przepis(self.pamiec, t)
        if wlasny:
            temat, kod = wlasny
            return f"Proszę bardzo — program „{temat}” (nauczyłeś mnie go wcześniej):\n\n{kod}"
        przepis = _dopasuj_przepis(t)
        if przepis:
            return f"{przepis['tytul']} — tak to wygląda w Pythonie:\n\n{przepis['kod']}"
        return None

    # -- uczenie się własnych programów ------------------------------------------

    def zapisz_program(self, tekst: str) -> Optional[str]:
        """„zapamiętaj program, który <opis>: <kod>” — zapisuje nowy przepis."""
        t = nlp.normalizuj(tekst)
        m = re.match(r"^(?:zapamietaj|pamietaj|zapisz)\s+(?:program|kod|skrypt)[,:]?\s*"
                     r"(?:ktory|ktore|ze)?\s*(.{2,80}?)\s*[:\n]\s*(.+)$", t, re.DOTALL)
        if not m:
            return None
        temat, kod = m.group(1).strip(" ,"), m.group(2).strip()
        kod = re.sub(r"^```[a-zA-Z]*\n?", "", kod).strip("` \n")
        if len(kod) < 8:
            return None
        if self.pamiec.dodaj_przepis(temat, kod):
            return (f"Zapamiętałem nowy program „{temat}”. Napisz kiedyś "
                    f"„napisz {temat}”, a go przytoczę.")
        return "Ten program już znam."

    # -- odpowiedź główna ----------------------------------------------------------

    def odpowiedz(self, tekst: str) -> Optional[str]:
        """Pełna obsługa umiejętności programowania; None = „to nie moje”."""
        t = tekst.strip()
        n = nlp.normalizuj(t)

        # 1) zapis własnego programu
        zapis = self.zapisz_program(t)
        if zapis:
            return zapis

        # 2) wyliczenie wyrażenia Pythona
        m = _WZORY_PYTHONA.search(t)
        if m:
            wyrazenie = next(g for g in m.groups() if g)
            try:
                wynik = policz_wyrazenie(wyrazenie)
                return f"Wyliczyłem w Pythonie: {wyrazenie.strip()} = {wynik}"
            except BladKodu as blad:
                return (f"Sprawdziłem wyrażenie „{wyrazenie.strip()}”, ale {blad}. "
                        f"Bezpiecznie policzę np.: „oblicz w pythonie [x*2 for x in range(5)]”.")

        # 3) wyjaśnianie kodu
        if re.search(r"co robi (?:ten )?kod|wyjasnij (?:ten )?kod|opisz (?:ten )?kod", n):
            kod = _wytnij_kod(t)
            if kod:
                return wyjasnij_kod(kod)
            return "Wklej kod po dwukropku albo w bloku ``` … ```, a opiszę go linia po linii."

        # 4) pisanie kodu
        prog = self.napisz(t)
        if prog:
            return prog

        # 5) pytanie o pojęcie programistyczne (z moich lekcji/wiedzy)
        if self.rozum is not None and re.search(
                r"\b(zmienn|funkcj|petl|list|slown|koment|klas|algorytm|python|kod|"
                r"debug|test|blad|wyjat|typ|programow|interpreter)\w*", n):
            m2 = re.search(r"(?:co to(?: jest)?|czym jest|wyjasnij(?: mi)?)\s+(.{2,40})", n)
            temat = m2.group(1).strip() if m2 else _temat_z_slow(n)
            if temat:
                opis = self.rozum.opisz(temat)
                if opis:
                    return opis
        return None


def _wytnij_kod(tekst: str) -> str:
    m = re.search(r"```[a-zA-Z]*\n?(.*?)```", tekst, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:kod|program)[:\s]*\n((?:[ \t]+\S.*\n?)+)", tekst)
    if m:
        return m.group(1).strip()
    # kod podany po dwukropku w jednej linii
    m = re.search(r":(.+)$", tekst, re.DOTALL)
    if m and ("=" in m.group(1) or "(" in m.group(1)):
        return m.group(1).strip()
    return ""


_SLOWA_KODU = ("zmienna", "funkcja", "petla", "lista", "slownik", "komentarz",
               "klasa", "algorytm", "python", "debug", "test", "blad", "wyjatek",
               "typ", "kod", "programowanie", "interpreter")


def _temat_z_slow(n: str) -> str:
    tokeny = [w for w in nlp.tokenizuj(n) if w in _SLOWA_KODU]
    return tokeny[0] if tokeny else ""
