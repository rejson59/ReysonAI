# -*- coding: utf-8 -*-
"""
reyson.profil — automatyczna adaptacja Reysona do możliwości urządzenia.

RM-2 nie ma jednego sztywnego rozmiaru: przy starcie mierzy urządzenie
(liczba rdzeni CPU, pamięć RAM, szybkość pojedynczego wątku) i dobiera
„pokrętła” pracy — rozmiar sieci neuronowej, liczbę epok treningu,
rząd n-gramów, liczbę agentów w radzie, limity wyszukiwania itd.

Trzy tryby:
  • mini     — słabe maszyny (1–2 GB RAM / 1 rdzeń / wolny CPU): mniej niż 100 MB,
               mniejsza sieć, krótszy trening, 3 agentów;
  • standard — komputer klasy 4 GB RAM / 2 rdzenie (domyślny, jak RM-1);
  • turbo    — 8+ GB RAM / 4+ rdzenie / szybki CPU: większa sieć, 4-gramy,
               5 agentów, więcej „snów” i przykładów.

Ręczne wymuszenie: zmienna środowiskowa REYSON_TRYB=mini|standard|turbo.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time
from typing import Optional

TRYBY = ("mini", "standard", "turbo")

# pokrętła zależne od trybu — wszystkie liczby dobrane „na lekko”
KNOPKI = {
    "mini": dict(
        ukryta=24,            # neurony ukryte RM-2·NN (~13 tys. parametrów)
        epoki_budowy=16,      # epoki treningu przy budowie umysłu
        epoki_snu=4,          # epoki doszkalania w czasie snu
        lr_snu=0.03,
        augmentacja=2,        # parafrazy przykładu treningowego
        ngram_max=3,          # rząd modelu generatywnego
        limit_przypomnien=2,  # trafień pamięci asocjacyjnej
        agenci=3,             # liczba agentów w radzie
        rundy_rady=2,         # rundy dyskusji agentów
        sny=3,                # nowych zdań na sen
        quiz=4,               # pytań w samo-sprawdzianie
        timeout_http=4,       # sekundy na zapytanie do Wikipedii
    ),
    "standard": dict(
        ukryta=32,
        epoki_budowy=25,
        epoki_snu=6,
        lr_snu=0.03,
        augmentacja=3,
        ngram_max=3,
        limit_przypomnien=3,
        agenci=4,
        rundy_rady=3,
        sny=6,
        quiz=6,
        timeout_http=8,
    ),
    "turbo": dict(
        ukryta=48,
        epoki_budowy=32,
        epoki_snu=8,
        lr_snu=0.025,
        augmentacja=4,
        ngram_max=4,
        limit_przypomnien=5,
        agenci=5,
        rundy_rady=3,
        sny=10,
        quiz=10,
        timeout_http=10,
    ),
}

OPISY = {
    "mini": "urządzenie słabe — tryb oszczędny (mikrosieć, 3 agentów)",
    "standard": "komputer typowy — pełnia możliwości przy < 100 MB RAM",
    "turbo": "mocna maszyna — większa sieć, 4-gramy, 5 agentów",
}


class Profil:
    """Aktywny profil sprzętowy — źródło pokręteł dla całego umysłu."""

    def __init__(self, nazwa: str, cpu: int = 0, ram_gb: float = 0.0,
                 bench_s: float = 0.0, wymuszony: bool = False):
        nazwa = nazwa if nazwa in TRYBY else "standard"
        self.nazwa = nazwa
        self.opis = OPISY[nazwa]
        self.cpu = cpu
        self.ram_gb = ram_gb
        self.bench_s = bench_s
        self.wymuszony = wymuszony
        for klucz, wartosc in KNOPKI[nazwa].items():
            setattr(self, klucz, wartosc)

    def __repr__(self) -> str:  # pragma: no cover
        return (f"Profil({self.nazwa}, cpu={self.cpu}, ram={self.ram_gb:g} GB, "
                f"bench={self.bench_s:.3f}s)")

    def jako_slownik(self) -> dict:
        d = dict(KNOPKI[self.nazwa])
        d.update({"nazwa": self.nazwa, "cpu": self.cpu,
                  "ram_gb": round(self.ram_gb, 2), "bench_s": round(self.bench_s, 4),
                  "wymuszony": self.wymuszony})
        return d


# ------------------------------------------------------------------ #
# Pomiar urządzenia
# ------------------------------------------------------------------ #

def _ram_gb() -> Optional[float]:
    """Całkowita pamięć RAM w GB (None, gdy nie da się odczytać)."""
    try:  # 1) psutil, jeśli ktoś go ma (nie jest wymagany)
        import psutil  # type: ignore
        return psutil.virtual_memory().total / 2 ** 30
    except Exception:
        pass
    try:  # 2) Linux (również Android/Termux)
        with open("/proc/meminfo", encoding="ascii") as f:
            for linia in f:
                if linia.startswith("MemTotal:"):
                    return int(linia.split()[1]) / 2 ** 20  # kB → GB
    except Exception:
        pass
    try:  # 3) macOS
        wyj = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, timeout=3)
        return int(wyj.stdout.strip()) / 2 ** 30
    except Exception:
        pass
    try:  # 4) Windows
        import ctypes
        if platform.system() == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stan = MEMORYSTATUSEX()
            stan.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stan))  # type: ignore
            return stan.ullTotalPhys / 2 ** 30
    except Exception:
        pass
    return None


def _benchmark() -> float:
    """Szybkość pojedynczego wątku (~0,02 s na desktopie, ~0,1 s na słabym CPU)."""
    t0 = time.perf_counter()
    x = 0.0
    for i in range(200_000):
        x += i * 0.5
    return time.perf_counter() - t0


def _klasyfikuj(cpu: int, ram: Optional[float], bench: float) -> str:
    if ram is not None and (ram <= 2.2 or cpu <= 1):
        return "mini"
    if cpu <= 2 and bench > 0.075:
        return "mini"          # mało rdzeni i wolny pojedynczy wątek
    if (ram or 4.0) >= 7.5 and cpu >= 4 and bench <= 0.045:
        return "turbo"
    return "standard"


def wykryj_profil(wymus: Optional[str] = None) -> Profil:
    """Mierzy urządzenie i zwraca aktywny profil (z opcjonalnym wymuszeniem)."""
    wymus = (wymus or os.environ.get("REYSON_TRYB") or "").strip().lower()
    cpu = os.cpu_count() or 2
    ram = _ram_gb()
    bench = _benchmark()
    if wymus in TRYBY:
        return Profil(wymus, cpu=cpu, ram_gb=ram or 0.0, bench_s=bench, wymuszony=True)
    nazwa = _klasyfikuj(cpu, ram, bench)
    return Profil(nazwa, cpu=cpu, ram_gb=ram or 0.0, bench_s=bench)


#: Profil aktywny w tym procesie (importowane raz, używane jako domyślne).
PROFIL_AKTYWNY: Profil = wykryj_profil()
