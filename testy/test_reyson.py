# -*- coding: utf-8 -*-
"""Testy ReysonAI — uruchamianie: python reyson.py --test (albo unittest)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("REYSON_TESTY", "1")

from reyson import nlp                      # noqa: E402
from reyson.model import MLP, ModelRM1      # noqa: E402
from reyson.pamiec import Pamiec            # noqa: E402
from reyson.rozum import Rozum             # noqa: E402


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
        from reyson.mozg import Mozg
        cls.tmp = tempfile.mkdtemp(prefix="reyson_mozg_")
        cls.mozg = Mozg(os.path.join(cls.tmp, "dane"))
        cls.mozg.zbuduj_siebie()  # buduje z pełnego korpusu (~8 s)

    @classmethod
    def tearDownClass(cls):
        cls.mozg.zamknij()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def odp(self, tekst):
        return self.mozg.odpowiedz(tekst)

    def test_powitanie(self):
        self.assertIn("Reyson", self.odp("czesc"))

    def test_tozsamosc(self):
        odp = self.odp("kim jesteś")
        self.assertIn("Reyson", odp)

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
        self.assertGreater(m["fakty"], 100)
        self.assertGreater(m["slownik"], 300)
        self.assertTrue(1 <= m["poziom"] <= 100)

    def test_sen_dziala(self):
        raport = self.mozg.uczony.sen()
        self.assertIn("Sen zakończony", raport)


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
