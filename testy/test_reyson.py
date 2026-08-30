# -*- coding: utf-8 -*-
"""Testy ReysonAI — uruchamianie: python reyson.py --test (albo unittest)."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

os.environ.setdefault("REYSON_TESTY", "1")

from reyson import nlp                      # noqa: E402
from reyson.model import MLP, ModelRM1      # noqa: E402
from reyson.pamiec import Pamiec            # noqa: E402
from reyson.profil import Profil, _klasyfikuj  # noqa: E402
from reyson.programista import (BladKodu, Programista,  # noqa: E402
                                policz_wyrazenie, wyjasnij_kod)
from reyson.rozum import Rozum             # noqa: E402


_MOZG = None


def wspolny_mozg():
    """Jeden pełny umysł na wszystkie testy pętli (budowa ~10 s, tylko raz)."""
    global _MOZG
    if _MOZG is None:
        from reyson.mozg import Mozg
        tmp = tempfile.mkdtemp(prefix="reyson_mozg_")
        _MOZG = Mozg(os.path.join(tmp, "dane"))
        _MOZG.zbuduj_siebie()
    return _MOZG


class TestNlp(unittest.TestCase):
    def test_normalizacja(self):
        self.assertEqual(nlp.normalizuj("ŻÓŁĆ"), "zolc")
        self.assertEqual(nlp.normalizuj("  Ala   ma kota "), "ala ma kota")

    def test_tokenizacja(self):
        self.assertEqual(nlp.tokenizuj("Ala ma kota, ale kot..."),
                         ["ala", "ma", "kota", "ale", "kot"])

    def test_tokenizacja_wyswietla_polskie(self):
        self.assertEqual(nlp.tokenizuj_wyswietl("Płyną łódką"), ["płyną", "łódką"])

    def test_zdania(self):
        self.assertEqual(len(nlp.zdania("Ala ma kota. Kot ma Alę! A ptak?")), 3)

    def test_stem(self):
        self.assertEqual(nlp.stem("kotku"), nlp.stem("kotku"))
        self.assertTrue(len(nlp.stem("czytałem")) >= 3)

    def test_kanon_i_tez_jest_to(self):
        self.assertTrue(nlp.tez_jest_to("polsce", "polska"))
        self.assertTrue(nlp.tez_jest_to("zwierzeciem", "zwierze"))
        self.assertTrue(nlp.tez_jest_to("Wisła", "wisla"))
        self.assertFalse(nlp.tez_jest_to("kot", "pies"))

    def test_dostosuj_pisownie(self):
        mapa = {"wisla": "Wisła", "plynie": "płynie"}
        self.assertEqual(nlp.dostosuj_pisownie("wisla plynie.", mapa), "Wisła płynie.")

    def test_hasz_wektor(self):
        v = nlp.hasz_wektor(nlp.tokenizuj("ala ma kota"), 128)
        self.assertAlmostEqual(sum(v), 1.0, places=5)
        self.assertEqual(len(v), 128)


class TestMLP(unittest.TestCase):
    def test_mala_siecz_uczy_sie(self):
        import random
        random.seed(3)
        net = MLP(wejscia=64, ukryta=16, wyjscia=3)
        dane = [
            (nlp.hasz_wektor(nlp.tokenizuj("kot pije mleko"), 64), 0),
            (nlp.hasz_wektor(nlp.tokenizuj("pies goni pile"), 64), 1),
            (nlp.hasz_wektor(nlp.tokenizuj("ptak lata w chmurach"), 64), 2),
        ]
        for _ in range(120):
            for x, c in dane:
                net.ucz_probke(x, c, 0.5)
        for x, c in dane:
            _, p = net.przewiduj(x)
            self.assertEqual(max(range(len(p)), key=lambda k: p[k]), c)


class TestRozum(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reyson_test_")
        self.pamiec = Pamiec(os.path.join(self.tmp, "t.db"))
        self.rozum = Rozum(self.pamiec)
        # mini-drabina
        self.pamiec.dodaj_fakt("sokol", "jest", "ptak")
        self.pamiec.dodaj_uniwersale("ptak", "zwierze")
        self.pamiec.dodaj_uniwersale("zwierze", "organizm")

    def tearDown(self):
        self.pamiec.zamknij()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lancuch_wnioskowania(self):
        tak, sciezka = self.rozum.czy_jest("sokol", "zwierze")
        self.assertTrue(tak)
        self.assertEqual(sciezka[0], "sokol")

    def test_czy_jest_odmiana(self):
        tak, _ = self.rozum.czy_jest("sokol", "zwierzeciem")
        self.assertTrue(tak)

    def test_arytmetyka(self):
        self.assertIsNotNone(self.rozum.arytmetyka("ile to 2 plus 2"))
        self.assertIn("4", self.rozum.arytmetyka("ile to 2 plus 2"))
        self.assertIn("144", self.rozum.arytmetyka("ile jest 12 razy 12"))
        self.assertIn("30", self.rozum.arytmetyka("ile to 15% z 200"))
        self.assertIn("12", self.rozum.arytmetyka("pierwiastek z 144"))

    def test_nauka_faktow(self):
        potw = self.rozum.ucz_sie_z_zdania("Wisła to rzeka")
        self.assertTrue(potw and potw.startswith("Zapamiętałem"))
        self.assertTrue(self.pamiec.fakty_o("wisla"))

    def test_nauka_uniwersalii(self):
        potw = self.rozum.ucz_sie_z_zdania("każdy ryba jest zwierzęciem")
        self.assertIn("regułę", potw.lower())

    def test_nauka_pytan_bez_znaku(self):
        # pytanie bez "?" nie może zostać faktem!
        potw = self.rozum.ucz_sie_z_zdania("co to jest fotosynteza")
        self.assertIsNone(potw)
        potw = self.rozum.ucz_sie_z_zdania("kto to byl kopernik")
        self.assertIsNone(potw)

    def test_lubie_i_mam(self):
        self.assertIn("lubisz", self.rozum.ucz_sie_z_zdania("lubię pierogi").lower())
        self.assertIn("masz", self.rozum.ucz_sie_z_zdania("mam psa").lower())

    def test_imie(self):
        imie = self.rozum.zapamietaj_imie("Nazywam się Marek")
        self.assertEqual(imie, "Marek")
        imie = self.rozum.zapamietaj_imie("nazywam sie Lukasz")
        self.assertEqual(imie, "Lukasz")
        self.assertIsNotNone(self.rozum.imie_uzytkownika())

    def test_czas(self):
        self.assertIn(".", self.rozum.czas_data())


class TestMozg(unittest.TestCase):
    """Pełna pętla odpowiedzi — wspólny umysł zbudowany raz (szybkość testów)."""

    @classmethod
    def setUpClass(cls):
        cls.mozg = wspolny_mozg()

    def odp(self, tekst):
        return self.mozg.odpowiedz(tekst)

    def test_powitanie(self):
        odp = self.odp("czesc")
        self.assertTrue(len(odp) > 5)  # wariant losowy, ale zawsze uprzejmy

    def test_tozsamosc(self):
        odp = self.odp("kim jesteś")
        self.assertIn("Reyson", odp)
        self.assertIn("RM-2", odp)

    def test_arytmetyka_przez_mozg(self):
        self.assertIn("15", self.odp("ile to 7 razy 2 plus 1"))

    def test_pytanie_o_wiedze(self):
        odp = self.odp("co to jest fotosynteza")
        self.assertIn("otosynteza", odp)

    def test_wnioskowanie_przez_mozg(self):
        odp = self.odp("czy sokol jest zwierzeciem")
        self.assertTrue(odp.lower().startswith("tak"))

    def test_uczenie_i_pamiec(self):
        self.assertIn("Zapamiętałem", self.odp("zapamiętaj, że Gdańsk to miasto portowe"))
        odp = self.odp("co wiesz o gdańsku")
        self.assertIn("dańsk", odp)

    def test_imie_przez_mozg(self):
        self.odp("nazywam się Testowy")
        self.assertIn("Testowy", self.odp("jak mam na imie"))

    def test_nigdy_nie_zawiesza_sie_puste(self):
        self.assertTrue(len(self.odp("")) > 0)

    def test_statystyki(self):
        m = self.mozg.uczony.metryki()
        self.assertGreater(m["fakty"], 200)
        self.assertGreater(m["slownik"], 300)
        self.assertTrue(1 <= m["poziom"] <= 100)
        self.assertIn(m["tryb"], ("mini", "standard", "turbo"))
        self.assertGreaterEqual(m["lekcje"], 6)

    def test_sen_dziala(self):
        raport = self.mozg.uczony.sen()
        self.assertIn("Sen zakończony", raport)

    def test_programowanie_przez_mozg(self):
        odp = self.odp("napisz funkcję silnia")
        self.assertIn("def silnia", odp)
        odp = self.odp("oblicz w pythonie [x*2 for x in range(5)]")
        self.assertIn("[0, 2, 4, 6, 8]", odp)

    def test_przyklady_typu_przez_mozg(self):
        odp = self.odp("co jest ssakiem")
        self.assertIn("lew", odp.lower())

    def test_rada_przez_rozmowe(self):
        odp = self.odp("rada: czy sokol jest zwierzęciem")
        self.assertIn("Uczony", odp)
        self.assertIn("Synteza", odp)


class TestProfil(unittest.TestCase):
    def test_knoby_trybow(self):
        mini, turbo = Profil("mini"), Profil("turbo")
        self.assertEqual(mini.agenci, 3)
        self.assertEqual(turbo.agenci, 5)
        self.assertEqual(mini.ngram_max, 3)
        self.assertEqual(turbo.ngram_max, 4)
        self.assertLess(mini.ukryta, turbo.ukryta)
        self.assertLess(mini.epoki_budowy, turbo.epoki_budowy)

    def test_klasyfikacja_urzadzen(self):
        self.assertEqual(_klasyfikuj(1, 1.0, 0.02), "mini")
        self.assertEqual(_klasyfikuj(2, 4.0, 0.20), "mini")   # wolny CPU
        self.assertEqual(_klasyfikuj(2, 4.0, 0.03), "standard")
        self.assertEqual(_klasyfikuj(8, 16.0, 0.03), "turbo")

    def test_adaptacja_mozgu(self):
        from reyson.mozg import Mozg
        with tempfile.TemporaryDirectory(prefix="reyson_adapt_") as tmp:
            m_mini = Mozg(os.path.join(tmp, "a"), profil=Profil("mini"))
            m_turbo = Mozg(os.path.join(tmp, "b"), profil=Profil("turbo"))
            self.assertEqual(m_mini.model._ukryta(), 24)
            self.assertEqual(m_turbo.model._ukryta(), 48)
            self.assertEqual(m_mini.pamiec.maks_n_gramu, 3)
            self.assertEqual(m_turbo.pamiec.maks_n_gramu, 4)
            self.assertEqual(len(m_mini.daj_rade().agenci), 3)
            self.assertEqual(len(m_turbo.daj_rade().agenci), 5)
            m_mini.zamknij()
            m_turbo.zamknij()


class TestProgramista(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reyson_prog_")
        self.pamiec = Pamiec(os.path.join(self.tmp, "t.db"))
        self.prog = Programista(self.pamiec)

    def tearDown(self):
        self.pamiec.zamknij()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_przepisy(self):
        for zapytanie, fraza in [("napisz funkcję silnia", "def silnia"),
                                 ("pokaz kod fibonacci", "fibonacci"),
                                 ("napisz fizzbuzz", "FizzBuzz"),
                                 ("napisz algorytm nwd", "def nwd")]:
            odp = self.prog.odpowiedz(zapytanie)
            self.assertIsNotNone(odp, zapytanie)
            self.assertIn(fraza, odp)

    def test_wyrazenia_pythona(self):
        self.assertEqual(policz_wyrazenie("2 + 3 * 4"), "14")
        self.assertEqual(policz_wyrazenie("[x*2 for x in range(5)]"), "[0, 2, 4, 6, 8]")
        self.assertEqual(policz_wyrazenie("sum([1, 2, 3])"), "6")
        self.assertEqual(policz_wyrazenie("len('Reyson')"), "6")
        self.assertEqual(policz_wyrazenie("{k: v for k, v in zip([1, 2], [3, 4])}"),
                         "{1: 3, 2: 4}")

    def test_blokady_bezpieczenstwa(self):
        for zle in ["__import__('os')", "().__class__", "open('/etc/passwd')",
                    "lambda x: x", "eval('1+1')", "exec('pass')"]:
            with self.assertRaises(BladKodu):
                policz_wyrazenie(zle)

    def test_wyjasnianie_kodu(self):
        opis = wyjasnij_kod("for i in range(3):\n    print(i)")
        self.assertIn("pętl", opis)
        self.assertIn("wypisuje", opis)
        opis2 = wyjasnij_kod("def silnia(n):\n    return 1")
        self.assertIn("funkcj", opis2)

    def test_nauczanie_wlasnych_programow(self):
        self.assertIn("Zapamiętałem", self.prog.odpowiedz(
            "zapamiętaj program kwadrat: def kwadrat(x): return x * x"))
        odp = self.prog.odpowiedz("napisz kwadrat")
        self.assertIn("kwadrat", odp)
        self.assertIn("x * x", odp)

    def test_odpowiedz_none_dla_niewlasnego(self):
        self.assertIsNone(self.prog.odpowiedz("jaka jest pogoda w Krakowie"))


class TestRada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mozg = wspolny_mozg()

    def test_rada_dyskutuje(self):
        rada = self.mozg.daj_rade()
        raport = rada.dyskutuj("czy sokol jest zwierzęciem", rundy=1)
        for agent in ("Uczony", "Krytyk", "Demiurg", "Inzynier"):
            self.assertIn(agent, raport)
        self.assertIn("Synteza", raport)
        # Uczony odpowiada wnioskowaniem na pytanie-test
        self.assertIn("zwierzeciem", raport.lower())

    def test_rada_uczy_sie_i_zapisuje(self):
        licznik_przed = self.mozg.pamiec.meta_pobierz_int("rady_licznik")
        self.mozg.daj_rade().dyskutuj("zmienna", rundy=1)
        self.assertGreater(self.mozg.pamiec.meta_pobierz_int("rady_licznik"), licznik_przed)
        wpisy = self.mozg.pamiec.wpisy_dziennika(limit=5)
        self.assertTrue(any(typ == "rada" for _, typ, _ in wpisy))


class TestSamorozwojOffline(unittest.TestCase):
    """Samorozwój MUSI działać bez internetu (to był główny błąd RM-1)."""

    @classmethod
    def setUpClass(cls):
        cls.mozg = wspolny_mozg()

    def test_cykl_offline(self):
        uczony = self.mozg.uczony
        uczony._stan_sieci = (time.time(), False)  # wymuś tryb offline
        raport = uczony.cykl_samorozwoju()
        self.assertNotIn("Nie udało mi się", raport)
        self.assertIn("Samo-sprawdzian", raport)
        uczony._stan_sieci = None

    def test_naucz_sie_offline(self):
        uczony = self.mozg.uczony
        uczony._stan_sieci = (time.time(), False)
        raport = uczony.naucz_sie_tematu("zmienna")
        self.assertNotIn("Nie udało mi się", raport)
        self.assertIn("offline", raport.lower())
        uczony._stan_sieci = None

    def test_indukcja_regul(self):
        # sztuczna wiedza: 3 „roboty” są JEDNOCZEŚNIE maszynami i urządzeniami
        from reyson.uczenie import Uczony
        tmp = tempfile.mkdtemp(prefix="reyson_induk_")
        p = Pamiec(os.path.join(tmp, "t.db"))
        r = Rozum(p)
        for nazwa in ("robot1", "robot2", "robot3"):
            p.dodaj_fakt(nazwa, "jest", "maszyna")
            p.dodaj_fakt(nazwa, "jest", "urzadzenie")
        model_atrapa = type("M", (), {"przypomnij": lambda *a, **k: []})()
        uczony = Uczony(p, model_atrapa, r)
        nowe = uczony._indukuj_reguly(log=lambda s: None)
        self.assertTrue(any("maszyna" in n and "urzadzenie" in n for n in nowe), nowe)
        p.zamknij()
        shutil.rmtree(tmp, ignore_errors=True)


class TestSenKontynuacja(unittest.TestCase):
    """Sen doszkala istniejącą sieć (kontynuacja), a nie startuje od zera."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reyson_sen_")
        self.pamiec = Pamiec(os.path.join(self.tmp, "t.db"))
        self.model = ModelRM1(self.pamiec, self.tmp)
        for t, i in [("czesc", "powitanie"), ("hej hej", "powitanie"),
                     ("do widzenia", "pozegnanie"), ("narazie", "pozegnanie")]:
            self.pamiec.dodaj_przyklad_intencji(t, i)

    def tearDown(self):
        self.pamiec.zamknij()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kontynuacja_nie_pogarsza(self):
        from reyson.model import INTENCJE
        s0 = self.model.zbuduj_mlp(epoki=40, kontynuuj=False)
        s1 = self.model.zbuduj_mlp(epoki=6, kontynuuj=True, lr=0.03)
        self.assertLessEqual(s1, s0 + 0.005)
        net = MLP.wczytaj(self.model.sciezka_wag)
        self.assertEqual(net.wyjscia, len(INTENCJE))


class TestModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reyson_model_")
        self.pamiec = Pamiec(os.path.join(self.tmp, "t.db"))
        self.model = ModelRM1(self.pamiec, self.tmp)
        for t, i in [("czesc", "powitanie"), ("hej hej", "powitanie"),
                     ("do widzenia", "pozegnanie"), ("narazie", "pozegnanie")]:
            self.pamiec.dodaj_przyklad_intencji(t, i)

    def tearDown(self):
        self.pamiec.zamknij()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_trening_i_rozpoznanie(self):
        self.model.zbuduj_mlp(epoki=40)
        intencja, _ = self.model.rozpoznaj_intencje("czesc czesc")
        self.assertEqual(intencja, "powitanie")
        intencja, _ = self.model.rozpoznaj_intencje("hej, hej")
        self.assertEqual(intencja, "powitanie")

    def test_generuj_cos_zwraca(self):
        self.pamiec.ucz_ngramy(nlp.tokenizuj_wyswietl("Kot śpi całe dni i myśli o swoim królestwie.") + ["."])
        zdanie = self.model.generuj(["kot"], maks_slow=15)
        self.assertTrue(len(zdanie) > 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
