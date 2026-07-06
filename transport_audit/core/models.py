"""Znormalizowany, dwupoziomowy model danych audytu kosztów transportu.

Wszystkie trzy adaptery przewoźników (SPT / Zadbano / D&M Trans) zwracają
identyczną listę obiektów :class:`Delivery`, dzięki czemu matcher, reguły
audytu oraz raporty działają niezależnie od formatu źródłowego.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from enum import Enum

# --------------------------------------------------------------------------- #
# Enumy dziedzinowe
# --------------------------------------------------------------------------- #


class Carrier(str, Enum):
    """Kanoniczne kody przewoźników."""

    SPT = "SPT"
    ZADBANO = "ZADBANO"
    DM_TRANS = "DM_TRANS"


class ServiceLevel(str, Enum):
    """Poziom usługi dostawy.

    DOOR                – dostawa pod drzwi (baza),
    CARRY_IN            – wniesienie,
    CARRY_IN_ASSEMBLY   – wniesienie + montaż + sprzątanie.
    """

    DOOR = "DOOR"
    CARRY_IN = "CARRY_IN"
    CARRY_IN_ASSEMBLY = "CARRY_IN_ASSEMBLY"
    UNKNOWN = "UNKNOWN"

    @property
    def rank(self) -> int:
        """Ranga do wyboru „najwyższego" poziomu usługi w zamówieniu."""
        return _SERVICE_RANK[self]


_SERVICE_RANK = {
    ServiceLevel.UNKNOWN: -1,
    ServiceLevel.DOOR: 0,
    ServiceLevel.CARRY_IN: 1,
    ServiceLevel.CARRY_IN_ASSEMBLY: 2,
}


class DeliveryStatus(str, Enum):
    """Znormalizowany status realizacji zlecenia u przewoźnika."""

    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    IN_PROGRESS = "IN_PROGRESS"
    UNKNOWN = "UNKNOWN"


class FeeType(str, Enum):
    """Znormalizowany typ komponentu opłaty (`Typ usługi` u Zadbano itd.)."""

    TRANSPORT = "TRANSPORT"
    FUEL = "FUEL"
    ROAD = "ROAD"
    SEASONAL = "SEASONAL"
    STANDARD = "STANDARD"
    PICKUP = "PICKUP"
    VOLUME_RECHECK = "VOLUME_RECHECK"
    EXTRA_ATTEMPT = "EXTRA_ATTEMPT"
    DATE_CHANGE = "DATE_CHANGE"
    ADDR_CHANGE = "ADDR_CHANGE"
    HEAVY = "HEAVY"
    OVERSIZE = "OVERSIZE"
    DISCOUNT = "DISCOUNT"
    SERVICE = "SERVICE"          # wniesienie/montaż jako osobna kolumna (D&M)
    CARRY_IN = "CARRY_IN"        # jw. – gdy przewoźnik nazywa wprost wniesienie
    OTHER = "OTHER"


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    FLAG = "FLAG"


# --------------------------------------------------------------------------- #
# Ekstrakcja rdzenia numeru zamówienia (§4 specyfikacji)
# --------------------------------------------------------------------------- #

#: rdzeń = pierwsza grupa 4–6 cyfr z części PRZED znakiem '_'.
_CORE_RE = re.compile(r"\d{4,6}")


def extract_core(order_ref_raw: str | None) -> str | None:
    """Wyprowadź rdzeń numeryczny użyty do złączenia z ERP.

    Przykłady (potwierdzone w specyfikacji §4):
        MYBED43503                -> 43503
        Shoper46281-1_8801122     -> 46281   (obcinamy _<id>)
        Shoper43183-1             -> 43183
        47559                     -> 47559
        ZAM/01847                 -> 01847
    Zwraca ``None``, gdy w części przed '_' nie ma grupy 4–6 cyfr
    (np. czysto tekstowy opis).
    """
    if not order_ref_raw:
        return None
    before_underscore = str(order_ref_raw).split("_", 1)[0]
    match = _CORE_RE.search(before_underscore)
    return match.group(0) if match else None


# --------------------------------------------------------------------------- #
# Modele danych
# --------------------------------------------------------------------------- #


@dataclass
class FeeComponent:
    """Pojedynczy komponent opłaty w obrębie jednego zlecenia."""

    type_code: FeeType
    type_raw: str
    amount_net: float

    def to_dict(self) -> dict:
        return {
            "type_code": self.type_code.value,
            "type_raw": self.type_raw,
            "amount_net": round(self.amount_net, 2),
        }


@dataclass
class Delivery:
    """Jedno zlecenie w zestawieniu przewoźnika (znormalizowane)."""

    carrier: Carrier
    invoice_no: str
    period: str                       # 'YYYY-MM'
    order_ref_raw: str
    order_core: str | None
    status: DeliveryStatus = DeliveryStatus.UNKNOWN
    service_level: ServiceLevel = ServiceLevel.UNKNOWN
    waybill: str | None = None
    qty: float | None = None
    weight_kg: float | None = None
    volume_m3: float | None = None
    total_cost_net: float = 0.0
    fees: list[FeeComponent] = field(default_factory=list)

    # Dane pomocnicze do fallbacku fuzzy (§4.2) i raportów – nie wchodzą do modelu
    # kanonicznego z §3, ale są potrzebne operacyjnie.
    receiver_name: str | None = None
    receiver_postcode: str | None = None
    receiver_city: str | None = None
    delivery_date: str | None = None
    settlement_no: str | None = None  # nr rozliczenia (D&M paruje FV↔rozliczenie)
    source_row: int | None = None     # Lp./LP w źródle – do dedupu i evidence

    def fee_sum(self) -> float:
        """Suma komponentów – powinna równać się ``total_cost_net``."""
        return round(sum(f.amount_net for f in self.fees), 2)

    def fees_by_type(self, type_code: FeeType) -> list[FeeComponent]:
        return [f for f in self.fees if f.type_code is type_code]

    def amount_of(self, type_code: FeeType) -> float:
        """Zsumowana kwota komponentów danego typu (0.0 jeśli brak)."""
        return round(sum(f.amount_net for f in self.fees_by_type(type_code)), 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["carrier"] = self.carrier.value
        d["status"] = self.status.value
        d["service_level"] = self.service_level.value
        d["fees"] = [f.to_dict() for f in self.fees]
        return d


@dataclass
class ErpOrder:
    """Jedno zamówienie z ERP (po forward-fill i pogrupowaniu po `Numer`)."""

    number: str                       # 'Shoper46281-1'
    core: str | None
    order_date: str | None
    products: list[str]               # pozycje-produkty (bez usług)
    service_level: ServiceLevel
    sizes_cm: list[str]
    postcode: str | None
    city: str | None
    delivery_fee_charged: float       # 'Koszt dostawy' – przychód od klienta
    order_total: float                # 'Suma'
    status: str | None
    tags: list[str]
    existing_transport_invoice: str | None  # istniejący ręczny wpis (walidacja)
    prefix: str | None = None         # 'Shoper' | 'Shopify' | 'ZAM' | ...
    delivery_method: str | None = None  # 'Metoda dostawy' – tylko poglądowo
    receiver_name: str | None = None
    street: str | None = None
    row_index: int | None = None      # numer wiersza-nagłówka w CSV (evidence)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["service_level"] = self.service_level.value
        return d


@dataclass
class Invoice:
    """Faktura zbiorcza przewoźnika (§2.5) – referencja do uzgodnienia sumy."""

    carrier: Carrier
    invoice_no: str
    seller: str | None
    nip: str | None
    issue_date: str | None
    period: str | None
    net: float | None
    vat: float | None
    gross: float | None
    payment_due: str | None
    settlement_no: str | None = None  # nr rozliczenia (D&M) – parowanie z zestawieniem
    source_path: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["carrier"] = self.carrier.value
        return d


@dataclass
class AuditFlag:
    """Pojedyncze ustalenie audytowe (§6)."""

    order_core: str | None
    carrier: str                      # kod przewoźnika lub 'CROSS' dla dubli cross-carrier
    rule: str                         # kod reguły, np. 'CROSS_CARRIER'
    severity: Severity
    message: str                      # opis PL, np. 'charged by multiple carriers'
    amount: float | None = None
    expected: float | None = None
    delta: float | None = None
    recoverable: float | None = None  # kwota możliwa do odzyskania (duble)
    evidence: str | None = None
    order_number: str | None = None   # numer ERP, jeśli dopasowano

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class MatchResult:
    """Wynik złączenia jednej linii kosztu (`Delivery`) z ERP (§4)."""

    delivery: Delivery
    erp_order: ErpOrder | None
    match_method: str                 # 'core' | 'fuzzy' | 'orphan'
    score: float | None = None        # podobieństwo fuzzy (jeśli dotyczy)

    @property
    def is_matched(self) -> bool:
        return self.erp_order is not None
