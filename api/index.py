"""Wejście serverless dla Vercela (@vercel/python).

Vercel wykrywa obiekt WSGI `app` i serwuje go. `vercel.json` przepisuje
wszystkie ścieżki na tę funkcję, więc Flask obsługuje i UI ('/'), i API.
"""

import os
import sys

# dodaj katalog repo do ścieżki, żeby zaimportować pakiet transport_audit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transport_audit.web.app import app  # noqa: E402

# Vercel oczekuje `app` (WSGI) w module funkcji.
