"""Wspólny interfejs adaptera przewoźnika.

Każdy adapter (SPT / Zadbano / D&M) czyta swój format zestawienia i zwraca
identyczną listę :class:`Delivery`. Dzięki temu matcher, audyt i raport są
niezależne od przewoźnika — nowy przewoźnik = tylko nowy adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.config import Config, load_config
from ..core.models import Carrier, Delivery


class CarrierAdapter(ABC):
    """Bazowy adapter: ``parse(spec_path) -> list[Delivery]``."""

    carrier: Carrier

    def __init__(
        self,
        invoice_no: str,
        period: str,
        cfg: Config | None = None,
        settlement_no: str | None = None,
    ) -> None:
        self.invoice_no = invoice_no
        self.period = period
        self.cfg = cfg or load_config()
        self.settlement_no = settlement_no

    @abstractmethod
    def parse(self, spec_path: str | Path) -> list[Delivery]:
        """Zparsuj zestawienie przewoźnika do listy :class:`Delivery`."""
        raise NotImplementedError

    def _base_delivery_kwargs(self) -> dict:
        return {
            "carrier": self.carrier,
            "invoice_no": self.invoice_no,
            "period": self.period,
        }
