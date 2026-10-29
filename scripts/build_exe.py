"""Buduje TibiaHelper.exe (jeden plik) PyInstallerem. Uruchamiaj na Windowsie:

    pip install -r requirements-dev.txt
    python scripts/build_exe.py

Wynik: dist/TibiaHelper.exe. Ten plik wrzucasz jako załącznik do Release na GitHubie.
PyInstaller jest darmowy i działa lokalnie (bez GitHub Actions).
"""

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SEP = ";" if sys.platform == "win32" else ":"  # separator w --add-data zależy od systemu

# (źródło, katalog w .exe). paths.py, i18n.py i theme.py szukają plików właśnie tam.
DATA = [
    ("data/quests.json", "data"),
    ("data/spawns.json", "data"),
    ("data/reports.json", "data"),
    ("data/boss_spawns.json", "data"),
    ("data/raids.json", "data"),
    ("data/qol", "data/qol"),
    ("data/LICENSE-DATA.md", "data"),
    ("LICENSE", "."),
    ("app/tibiahelper/i18n", "tibiahelper/i18n"),
    ("app/tibiahelper/ui/assets", "tibiahelper/ui/assets"),
]


def main() -> None:
    args = [
        str(Path(__file__).with_name("launcher.py")),
        "--name=TibiaHelper",
        "--onefile",
        "--windowed",  # bez czarnego okna konsoli
        "--noconfirm",
        "--clean",
        f"--icon={APP / 'tibiahelper' / 'ui' / 'assets' / 'logo.ico'}",
        f"--paths={APP}",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
    ]
    for source, target in DATA:
        path = ROOT / source
        if not path.exists():
            print(f"Pomijam {source} (nie ma pliku)")
            continue
        args.append(f"--add-data={path}{SEP}{target}")
    PyInstaller.__main__.run(args)
    print(f"Gotowe: plik w {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
