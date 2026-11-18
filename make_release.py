"""
Przygotowanie nowej wersji programu do rozesłania (uruchamiasz na swoim komputerze, w folderze z projektem).

Użycie:
    python make_release.py 1.1.0 "Co nowego w tej wersji"
    python make_release.py 1.1.0 "Opis" --publish      # dodatkowo wrzuca na GitHub (wymaga programu `gh`)

Co robi:
 1. sprawdza, że w allegro.py nie ma wpisanych prawdziwych kluczy (bo trafiłyby do publicznego .exe),
 2. zmienia numer wersji w app_info.py,
 3. buduje plik .exe (PyInstaller),
 4. liczy sumę SHA-256 i zapisuje release/version.json,
 5. pokazuje, co wrzucić do Release na GitHubie.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def read_info(here=HERE):
    with open(os.path.join(here, "app_info.py"), encoding="utf-8") as f:
        text = f.read()
    def get(name):
        m = re.search(rf'^{name}\s*=\s*"([^"]*)"', text, re.M)
        if not m:
            raise SystemExit(f"W app_info.py brakuje {name}.")
        return m.group(1)
    return get("APP_VERSION"), get("UPDATE_MANIFEST_URL"), get("EXE_NAME")


def bump_version(version, here=HERE):
    path = os.path.join(here, "app_info.py")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new, n = re.subn(r'^(APP_VERSION\s*=\s*)"[^"]*"', rf'\g<1>"{version}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("Nie udało się zmienić APP_VERSION w app_info.py.")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)


def check_no_secrets(here=HERE):
    """Przerywa, jeśli w allegro.py jest wpisany prawdziwy CLIENT_SECRET (trafiłby do .exe)."""
    path = os.path.join(here, "allegro.py")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^CLIENT_SECRET\s*=\s*["\']([^"\']*)["\']', text, re.M)
    if m and m.group(1) and "WPISZ" not in m.group(1).upper():
        raise SystemExit(
            "STOP: w allegro.py jest wpisany CLIENT_SECRET. Trafiłby do pliku .exe, który publikujesz.\n"
            "Zostaw w allegro.py puste wartości (CLIENT_ID = \"\", CLIENT_SECRET = \"\"), a klucze\n"
            "trzymaj w pliku config.json obok programu na każdym komputerze.")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def exe_url(manifest_url, version, exe_name):
    """Adres, pod którym będzie leżał nowy .exe."""
    m = re.match(r"^(https://github\.com/[^/]+/[^/]+)/releases/latest/download/[^/]+$", manifest_url)
    if m:                                             # GitHub Releases
        return f"{m.group(1)}/releases/download/v{version}/{exe_name}"
    return manifest_url.rsplit("/", 1)[0] + "/" + exe_name   # własny serwer: obok version.json


def write_manifest(version, notes, exe_path, manifest_url, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(exe_path)
    manifest = {
        "version": version,
        "url": exe_url(manifest_url, version, name),
        "sha256": sha256_of(exe_path),
        "size": os.path.getsize(exe_path),
        "notes": notes,
    }
    with open(os.path.join(out_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def build(exe_name, here=HERE):
    name = os.path.splitext(exe_name)[0]
    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(here, d), ignore_errors=True)
    spec = os.path.join(here, name + ".spec")
    if os.path.exists(spec):
        os.remove(spec)
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--name", name]
    if os.path.exists(os.path.join(here, "icon.ico")):
        cmd += ["--icon", "icon.ico"]
    subprocess.run(cmd + ["allegro_gui.py"], cwd=here, check=True)
    return os.path.join(here, "dist", exe_name)


def main(version, notes, publish=False, skip_build=False, here=HERE):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Wersja ma mieć postać 1.2.3")
    old_version, manifest_url, exe_name = read_info(here)
    if "TWOJ_LOGIN" in manifest_url:
        raise SystemExit("Najpierw ustaw UPDATE_MANIFEST_URL w app_info.py (adres Twojego repozytorium na GitHubie).")
    check_no_secrets(here)
    print(f"Wersja {old_version} -> {version}")
    bump_version(version, here)
    exe = os.path.join(here, "dist", exe_name) if skip_build else build(exe_name, here)
    if not os.path.exists(exe):
        raise SystemExit(f"Nie znaleziono {exe}")
    out_dir = os.path.join(here, "release")
    shutil.rmtree(out_dir, ignore_errors=True)
    manifest = write_manifest(version, notes, exe, manifest_url, out_dir)
    shutil.copy(exe, os.path.join(out_dir, exe_name))
    print(f"\nGotowe. Pliki w folderze: {out_dir}")
    print(f"  {exe_name}  ({manifest['size'] / 1048576:.1f} MB)")
    print("  version.json")
    if publish and shutil.which("gh"):
        subprocess.run(["gh", "release", "create", f"v{version}",
                        os.path.join(out_dir, exe_name), os.path.join(out_dir, "version.json"),
                        "--title", f"v{version}", "--notes", notes or f"Wersja {version}"],
                       cwd=here, check=True)
        print("\nOpublikowano na GitHubie. Programy na innych komputerach zobaczą aktualizację przy następnym starcie.")
    else:
        print(f"\nTeraz na GitHubie: Releases -> Draft a new release -> tag v{version}")
        print(f"  wrzuć OBA pliki z folderu release ({exe_name} i version.json) i kliknij Publish release.")
        if publish:
            print("  (nie znaleziono programu `gh`, więc publikacja ręczna)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    main(args[0], args[1] if len(args) > 1 else "", publish="--publish" in sys.argv)
