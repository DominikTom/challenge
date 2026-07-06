"""Kompatybilność wsteczna — logika przeniesiona do ``supabase_io``.

Zostawiamy cienkie re-eksporty, żeby istniejące importy (CLI, testy) działały.
"""

from __future__ import annotations

from pathlib import Path

from .supabase_io import (  # noqa: F401
    SupabaseClient,
    SupabaseError,
    build_fact_rows,
    build_recon_rows,
    load_erp_from_supabase,
    write_results,
)


def load_to_supabase(result, out_dir: str | Path) -> dict:
    """Zapisz wyniki do Supabase (fallback: JSONL). Patrz ``supabase_io.write_results``."""
    return write_results(result, out_dir=out_dir)
