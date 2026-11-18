"""
Samoaktualizacja programu (Windows, wersja .exe zbudowana PyInstallerem).

Jak to działa:
 1. Program pobiera mały plik version.json z adresu UPDATE_MANIFEST_URL (patrz app_info.py).
 2. Jeśli jest w nim nowsza wersja niż uruchomiona, pyta użytkownika i pobiera nowy .exe.
 3. Sprawdza sumę kontrolną SHA-256 (musi zgadzać się z tą z version.json).
 4. Zamyka się, a mały skrypt .bat podmienia plik .exe i uruchamia program ponownie.

Format version.json:
 {"version": "1.1.0", "url": "https://.../AllegroPaczki.exe", "sha256": "<64 znaki>",
  "size": 15700000, "notes": "Co nowego"}
"""
import hashlib
import os
import re
import subprocess
import sys

import requests

TEMP_NAME = "update_download.exe"

# Skrypt, który po zamknięciu programu podmienia plik .exe i uruchamia go ponownie.
# ping zamiast timeout, bo timeout nie działa bez okna konsoli.
BAT_TEMPLATE = """@echo off
chcp 65001 >nul
set PYINSTALLER_RESET_ENVIRONMENT=1
set "OLD={old}"
set "NEW={new}"
set /a n=0
:wait
set /a n+=1
if %n% gtr 40 goto fail
ping -n 2 127.0.0.1 >nul
move /y "%NEW%" "%OLD%" >nul 2>&1
if errorlevel 1 goto wait
start "" "%OLD%"
goto done
:fail
start "" "%OLD%"
:done
(goto) 2>nul & del "%~f0"
"""


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Folder, w którym leży program (.exe) albo skrypt."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def parse_version(v):
    nums = [int(x) for x in re.findall(r"\d+", str(v))][:4]
    if not nums:
        raise ValueError(f"niepoprawny numer wersji: {v!r}")
    return tuple(nums + [0] * (3 - len(nums)))


def check(manifest_url, current, require_https=True, timeout=10):
    """Zwraca manifest (dict), jeśli na serwerze jest nowsza wersja niż `current`, inaczej None."""
    if require_https and not str(manifest_url).lower().startswith("https://"):
        raise ValueError("adres aktualizacji musi zaczynać się od https://")
    r = requests.get(manifest_url, timeout=timeout, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    m = r.json()
    for key in ("version", "url", "sha256"):
        if not m.get(key):
            raise ValueError(f"w version.json brakuje pola '{key}'")
    if require_https and not str(m["url"]).lower().startswith("https://"):
        raise ValueError("adres pobierania musi zaczynać się od https://")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(m["sha256"])):
        raise ValueError("pole sha256 w version.json ma zły format")
    return m if parse_version(m["version"]) > parse_version(current) else None


def download(manifest, progress=None, dest_dir=None, timeout=30):
    """Pobiera nowy .exe obok programu i sprawdza sumę SHA-256. Zwraca ścieżkę do pliku."""
    dest = os.path.join(dest_dir or app_dir(), TEMP_NAME)
    h = hashlib.sha256()
    done = 0
    try:
        with requests.get(manifest["url"], stream=True, timeout=timeout) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or manifest.get("size") or 0)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if h.hexdigest().lower() != str(manifest["sha256"]).lower():
            raise RuntimeError("Suma kontrolna pobranego pliku się nie zgadza (plik uszkodzony lub podmieniony). "
                               "Aktualizacja przerwana.")
        if manifest.get("size") and int(manifest["size"]) != done:
            raise RuntimeError("Pobrany plik ma inny rozmiar niż zapowiedziano. Aktualizacja przerwana.")
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    return dest


def build_bat(old_exe, new_exe):
    esc = lambda p: str(p).replace("%", "%%")
    return BAT_TEMPLATE.format(old=esc(old_exe), new=esc(new_exe))


def apply_and_restart(new_path):
    """Uruchamia skrypt podmieniający plik. Zaraz po tym program MUSI się zamknąć."""
    if os.name != "nt" or not is_frozen():
        raise RuntimeError("Automatyczna aktualizacja działa tylko w wersji .exe na Windows.")
    bat = os.path.join(os.path.dirname(new_path), "update_apply.bat")
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(build_bat(sys.executable, new_path))
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # nowy egzemplarz rozpakuje się od nowa
    subprocess.Popen(
        ["cmd.exe", "/c", bat], env=env, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=0x08000000 | 0x00000200,   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    )
