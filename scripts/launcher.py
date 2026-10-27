"""Punkt startowy .exe: PyInstaller potrzebuje zwykłego skryptu, a __main__.py używa importów względnych."""

import sys

from tibiahelper.__main__ import main

sys.exit(main())
