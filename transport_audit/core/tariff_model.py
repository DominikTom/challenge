"""Nauka cennika referencyjnego z danych historycznych (§5.6, §6.5).

Buduje medianę komponentu `TRANSPORT` per klaster
``carrier × service_level × volume_bucket × postcode2`` z dostępnych danych
(bieżący okres + wszystko, co da się odczytać ze starych wpisów). Służy do
flagowania przepłaceń (linia > mediana × 1,20 przy >= N obserwacjach) oraz jest
zapisywany do `reference_tariff.json` (negocjacje, kolejne okresy).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, load_config
from .models import Delivery, ErpOrder, FeeType, MatchResult, ServiceLevel
from .util import postcode2, volume_bucket


def cluster_key(
    carrier: str, service_level: str, vol_bucket: str, pc2: str | None
) -> str:
    return f"{carrier}|{service_level}|{vol_bucket}|{pc2 or 'NA'}"


@dataclass
class ClusterStat:
    key: str
    carrier: str
    service_level: str
    volume_bucket: str
    postcode2: str | None
    values: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def median(self) -> float:
        return round(statistics.median(self.values), 2) if self.values else 0.0

    def to_dict(self) -> dict:
        vals = sorted(self.values)
        return {
            "carrier": self.carrier,
            "service_level": self.service_level,
            "volume_bucket": self.volume_bucket,
            "postcode2": self.postcode2,
            "count": self.count,
            "median": self.median,
            "min": round(min(vals), 2) if vals else None,
            "max": round(max(vals), 2) if vals else None,
            "p25": round(_quantile(vals, 0.25), 2) if vals else None,
            "p75": round(_quantile(vals, 0.75), 2) if vals else None,
        }


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] * (1 - frac) + sorted_vals[lo + 1] * frac
    return sorted_vals[lo]


class TariffModel:
    """Nauczony cennik referencyjny (mediana TRANSPORT per klaster)."""

    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or load_config()
        self.clusters: dict[str, ClusterStat] = {}
        self.min_obs = int(self.cfg.threshold("tariff_min_observations"))
        self.overpay_mult = self.cfg.threshold("tariff_overpay_multiplier")

    # -- budowa ------------------------------------------------------------ #

    def _key_for(self, delivery: Delivery, erp: ErpOrder | None) -> tuple[str, str, str, str | None]:
        service = delivery.service_level
        if service is ServiceLevel.UNKNOWN and erp is not None:
            service = erp.service_level
        pc = delivery.receiver_postcode or (erp.postcode if erp else None)
        vb = volume_bucket(delivery.volume_m3)
        return delivery.carrier.value, service.value, vb, postcode2(pc)

    def add(self, delivery: Delivery, erp: ErpOrder | None) -> None:
        transport = delivery.amount_of(FeeType.TRANSPORT)
        if transport <= 0:
            return
        carrier, service, vb, pc2 = self._key_for(delivery, erp)
        key = cluster_key(carrier, service, vb, pc2)
        stat = self.clusters.get(key)
        if stat is None:
            stat = ClusterStat(key=key, carrier=carrier, service_level=service,
                               volume_bucket=vb, postcode2=pc2)
            self.clusters[key] = stat
        stat.values.append(transport)

    @classmethod
    def learn(cls, matches: list[MatchResult], cfg: Config | None = None) -> "TariffModel":
        model = cls(cfg)
        for m in matches:
            model.add(m.delivery, m.erp_order)
        return model

    # -- odpytywanie ------------------------------------------------------- #

    def lookup(self, delivery: Delivery, erp: ErpOrder | None) -> ClusterStat | None:
        carrier, service, vb, pc2 = self._key_for(delivery, erp)
        return self.clusters.get(cluster_key(carrier, service, vb, pc2))

    def evaluate(self, delivery: Delivery, erp: ErpOrder | None) -> dict:
        """Zwróć ocenę linii względem klastra: median, count, ratio, verdict."""
        transport = delivery.amount_of(FeeType.TRANSPORT)
        stat = self.lookup(delivery, erp)
        if stat is None or stat.count < self.min_obs:
            return {
                "transport": transport,
                "median": stat.median if stat else None,
                "count": stat.count if stat else 0,
                "ratio": None,
                "verdict": "no_reference",
            }
        median = stat.median
        ratio = round(transport / median, 3) if median else None
        verdict = "above_tariff" if (median and transport > median * self.overpay_mult) else "ok"
        return {
            "transport": transport,
            "median": median,
            "count": stat.count,
            "ratio": ratio,
            "verdict": verdict,
        }

    # -- serializacja ------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {
            "min_observations": self.min_obs,
            "overpay_multiplier": self.overpay_mult,
            "clusters": {k: v.to_dict() for k, v in sorted(self.clusters.items())},
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, cfg: Config | None = None) -> "TariffModel":
        model = cls(cfg)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, c in data.get("clusters", {}).items():
            stat = ClusterStat(key=key, carrier=c["carrier"],
                               service_level=c["service_level"],
                               volume_bucket=c["volume_bucket"], postcode2=c["postcode2"])
            # odtwórz przybliżone wartości wokół mediany (do dalszych ocen)
            stat.values = [c["median"]] * max(1, c["count"])
            model.clusters[key] = stat
        return model
