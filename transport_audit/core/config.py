"""Wczytanie i udostępnienie ``config.yaml`` + wspólne helpery normalizacji."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .models import FeeType, ServiceLevel, DeliveryStatus

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def normalize_text(value: str | None) -> str:
    """Znormalizuj tekst do porównań: lower + collapse spacji + trim.

    Nie usuwamy polskich znaków (klucze w config.yaml są z ogonkami),
    ale zwijamy białe znaki i ujednolicamy wielkość liter.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_diacritics(value: str | None) -> str:
    """Usuń znaki diakrytyczne (do dopasowania fuzzy nazwisk)."""
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass
class Config:
    """Zparsowany config z gotowymi mapami znormalizowanymi po kluczach."""

    service_items: dict[str, ServiceLevel]
    fee_type_map: dict[str, FeeType]
    fee_type_patterns: list[tuple[re.Pattern, FeeType]]
    status_map: dict[str, DeliveryStatus]
    zadbano_standard_map: dict[str, ServiceLevel]
    spt_order_type_map: dict[str, ServiceLevel]
    carrier_display: dict[str, str]
    carrier_aliases: dict[str, list[str]]
    thresholds: dict[str, float]
    raw: dict = field(default_factory=dict)

    # -- helpery mapujące (z normalizacją klucza) -------------------------- #

    def service_level_for_item(self, product_name: str) -> ServiceLevel | None:
        """Zwróć poziom usługi dla pozycji-usługi lub ``None`` (to produkt)."""
        return self.service_items.get(normalize_text(product_name))

    def fee_type_for(self, type_raw: str) -> FeeType:
        """Zmapuj surową nazwę komponentu na ``FeeType`` (exact -> pattern -> OTHER)."""
        key = normalize_text(type_raw)
        if key in self.fee_type_map:
            return self.fee_type_map[key]
        for pattern, code in self.fee_type_patterns:
            if pattern.search(key):
                return code
        return FeeType.OTHER

    def status_for(self, raw: str) -> DeliveryStatus:
        return self.status_map.get(normalize_text(raw), DeliveryStatus.UNKNOWN)

    def zadbano_service_level(self, standard: str) -> ServiceLevel:
        return self.zadbano_standard_map.get(normalize_text(standard), ServiceLevel.DOOR)

    def spt_service_level(self, order_type: str) -> ServiceLevel:
        key = normalize_text(order_type)
        if key in self.spt_order_type_map:
            return self.spt_order_type_map[key]
        # heurystyka awaryjna: cokolwiek z „wniesieniem" traktuj jako CARRY_IN
        if "wniesie" in key:
            return ServiceLevel.CARRY_IN
        if "zwykł" in key:
            return ServiceLevel.DOOR
        return ServiceLevel.UNKNOWN

    def carrier_label(self, carrier_code: str) -> str:
        return self.carrier_display.get(carrier_code, carrier_code)

    def threshold(self, name: str) -> float:
        return float(self.thresholds[name])


@lru_cache(maxsize=8)
def load_config(path: str | None = None) -> Config:
    """Wczytaj i zbuduj :class:`Config` (memoizowane po ścieżce)."""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    service_items = {
        normalize_text(k): ServiceLevel(v) for k, v in raw.get("service_items", {}).items()
    }
    fee_type_map = {
        normalize_text(k): FeeType(v) for k, v in raw.get("fee_type_map", {}).items()
    }
    fee_type_patterns = [
        (re.compile(entry["pattern"], re.IGNORECASE), FeeType(entry["type_code"]))
        for entry in raw.get("fee_type_patterns", [])
    ]
    status_map = {
        normalize_text(k): DeliveryStatus(v) for k, v in raw.get("status_map", {}).items()
    }
    zadbano_standard_map = {
        normalize_text(k): ServiceLevel(v)
        for k, v in raw.get("zadbano_standard_map", {}).items()
    }
    spt_order_type_map = {
        normalize_text(k): ServiceLevel(v)
        for k, v in raw.get("spt_order_type_map", {}).items()
    }

    return Config(
        service_items=service_items,
        fee_type_map=fee_type_map,
        fee_type_patterns=fee_type_patterns,
        status_map=status_map,
        zadbano_standard_map=zadbano_standard_map,
        spt_order_type_map=spt_order_type_map,
        carrier_display=raw.get("carrier_display", {}),
        carrier_aliases=raw.get("carrier_aliases", {}),
        thresholds=raw.get("thresholds", {}),
        raw=raw,
    )
