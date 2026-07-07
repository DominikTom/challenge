"""Reguły audytu (§6) — wykrywanie dubli, obciążeń za nieudane, niespójności
poziomu usługi, przepłaceń, outlierów dopłat, objętości i kosztów operacyjnych.

Każda flaga: {order_core, carrier, rule, severity, amount, expected, delta,
evidence}. Reguły są niezależne od przewoźnika (działają na znormalizowanym
modelu Delivery), z wyjątkiem reguły 6 (dopłaty), specyficznej dla Zadbano.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config, load_config
from .matcher import MatchOutcome
from .models import (
    AuditFlag,
    DeliveryStatus,
    FeeType,
    MatchResult,
    ServiceLevel,
    Severity,
)
from .tariff_model import TariffModel

# kody reguł
R_DOUBLE = "DOUBLE_INTRA"
R_CROSS = "CROSS_CARRIER"
R_FAILED = "FAILED_CHARGED"
R_SERVICE = "SERVICE_MISMATCH"
R_TARIFF = "ABOVE_TARIFF"
R_SURCHARGE = "SURCHARGE_OUTLIER"
R_VOLUME = "VOLUME_RECHECK"
R_OPS = "OPS_CHANGE"

_TERMINAL_FAIL = {DeliveryStatus.FAILED, DeliveryStatus.CANCELLED}


@dataclass
class AuditResult:
    flags: list[AuditFlag] = field(default_factory=list)
    surcharge_category_sums: dict[str, float] = field(default_factory=dict)
    ops_sums: dict[str, float] = field(default_factory=dict)
    no_reference_count: int = 0

    def by_rule(self, rule: str) -> list[AuditFlag]:
        return [f for f in self.flags if f.rule == rule]

    def flags_of_severity(self, sev: Severity) -> list[AuditFlag]:
        return [f for f in self.flags if f.severity is sev]


class AnomalyDetector:
    def __init__(self, tariff: TariffModel | None = None, cfg: Config | None = None) -> None:
        self.cfg = cfg or load_config()
        self.tariff = tariff
        self.split_tol = self.cfg.threshold("split_volume_tolerance")
        self.vol_tol = self.cfg.threshold("volume_upcharge_tolerance")
        self.sigma = self.cfg.threshold("surcharge_sigma")

    def run(self, outcome: MatchOutcome, zadbano_summary: dict | None = None) -> AuditResult:
        result = AuditResult()
        matches = outcome.matches  # wszystkie linie (dopasowane + orphany)

        self._rule_double_intra(matches, result)
        self._rule_cross_carrier(matches, result)
        self._rule_failed_charged(matches, result)
        self._rule_service_mismatch(matches, result)
        self._rule_above_tariff(matches, result)
        self._rule_surcharge_outlier(matches, result)
        self._rule_volume_recheck(matches, result)
        self._rule_ops_changes(matches, result)

        if zadbano_summary and zadbano_summary.get("categories"):
            result.surcharge_category_sums = dict(zadbano_summary["categories"])
        return result

    # -- Reguła 1: duble / split w obrębie jednego przewoźnika ------------- #

    def _rule_double_intra(self, matches: list[MatchResult], result: AuditResult) -> None:
        groups: dict[tuple, list[MatchResult]] = defaultdict(list)
        for m in matches:
            if m.delivery.order_core:
                groups[(m.delivery.carrier.value, m.delivery.order_core)].append(m)

        for (carrier, core), items in groups.items():
            if len(items) < 2:
                continue
            amounts = [round(i.delivery.total_cost_net, 2) for i in items]
            statuses = [i.delivery.status for i in items]
            erp = next((i.erp_order for i in items if i.erp_order), None)
            has_fail = any(s in _TERMINAL_FAIL for s in statuses)
            has_delivered = any(s is DeliveryStatus.DELIVERED for s in statuses)
            identical = len(set(amounts)) < len(amounts)
            total = round(sum(amounts), 2)
            evidence = "; ".join(
                f"{i.delivery.status.value} {i.delivery.total_cost_net:.2f} "
                f"(Lp {i.delivery.source_row})" for i in items)

            if (has_fail and has_delivered) or identical:
                # kwota do odzyskania: obciążenia za nieudane (albo nadmiarowy duplikat)
                recoverable = round(
                    sum(a for a, s in zip(amounts, statuses) if s in _TERMINAL_FAIL), 2)
                if recoverable == 0 and identical:
                    recoverable = min(amounts)
                result.flags.append(AuditFlag(
                    order_core=core, carrier=carrier, rule=R_DOUBLE,
                    severity=Severity.FLAG,
                    message="potential double charge (możliwe podwójne obciążenie)",
                    amount=total, recoverable=recoverable, evidence=evidence,
                    order_number=erp.number if erp else None))
            else:
                # obie DELIVERED: sprawdź spójność objętości (split shipment)
                sum_vol = sum((i.delivery.volume_m3 or 0.0) for i in items)
                result.flags.append(AuditFlag(
                    order_core=core, carrier=carrier, rule=R_DOUBLE,
                    severity=Severity.INFO,
                    message="split shipment (przesyłka podzielona)",
                    amount=total, evidence=f"{evidence}; Σvol={sum_vol:.2f}",
                    order_number=erp.number if erp else None))

    # -- Reguła 2: duble CROSS-CARRIER (priorytet WYSOKI) ----------------- #

    def _rule_cross_carrier(self, matches: list[MatchResult], result: AuditResult) -> None:
        by_core: dict[str, list[MatchResult]] = defaultdict(list)
        for m in matches:
            if m.delivery.order_core:
                by_core[m.delivery.order_core].append(m)

        for core, items in by_core.items():
            per_carrier: dict[str, float] = defaultdict(float)
            for i in items:
                per_carrier[i.delivery.carrier.value] += i.delivery.total_cost_net
            if len(per_carrier) < 2:
                continue
            total = round(sum(per_carrier.values()), 2)
            recoverable = round(min(per_carrier.values()), 2)  # min z dwóch (§6.2)
            erp = next((i.erp_order for i in items if i.erp_order), None)
            evidence = ", ".join(f"{c}={v:.2f}" for c, v in sorted(per_carrier.items()))
            result.flags.append(AuditFlag(
                order_core=core, carrier="CROSS", rule=R_CROSS, severity=Severity.FLAG,
                message="charged by multiple carriers (obciążony przez >1 przewoźnika)",
                amount=total, recoverable=recoverable, evidence=evidence,
                order_number=erp.number if erp else None))

    # -- Reguła 3: nieudane / anulowane obciążone ------------------------- #

    def _rule_failed_charged(self, matches: list[MatchResult], result: AuditResult) -> None:
        for m in matches:
            d = m.delivery
            if d.status in _TERMINAL_FAIL and d.total_cost_net > 0:
                result.flags.append(AuditFlag(
                    order_core=d.order_core, carrier=d.carrier.value, rule=R_FAILED,
                    severity=Severity.FLAG,
                    message=f"charged for failed delivery (status={d.status.value})",
                    amount=round(d.total_cost_net, 2), recoverable=round(d.total_cost_net, 2),
                    evidence=f"ref={d.order_ref_raw}; waybill={d.waybill}",
                    order_number=m.erp_order.number if m.erp_order else None))

    # -- Reguła 4: niespójność poziomu usługi ----------------------------- #

    def _rule_service_mismatch(self, matches: list[MatchResult], result: AuditResult) -> None:
        for m in matches:
            if not m.is_matched:
                continue
            dl = m.delivery.service_level
            el = m.erp_order.service_level
            if dl is ServiceLevel.UNKNOWN or el is ServiceLevel.UNKNOWN:
                continue
            if dl.rank > el.rank:
                result.flags.append(AuditFlag(
                    order_core=m.delivery.order_core, carrier=m.delivery.carrier.value,
                    rule=R_SERVICE, severity=Severity.FLAG,
                    message=f"charged carry-in not sold (przewoźnik={dl.value}, ERP={el.value})",
                    evidence=f"ref={m.delivery.order_ref_raw}",
                    order_number=m.erp_order.number))
            elif dl.rank < el.rank:
                result.flags.append(AuditFlag(
                    order_core=m.delivery.order_core, carrier=m.delivery.carrier.value,
                    rule=R_SERVICE, severity=Severity.INFO,
                    message=f"ERP wyższy poziom niż przewoźnik (ERP={el.value}, przewoźnik={dl.value}) "
                            f"— możliwa nieopłacona usługa",
                    evidence=f"ref={m.delivery.order_ref_raw}",
                    order_number=m.erp_order.number))

    # -- Reguła 5: przepłacenie (cennik) ---------------------------------- #

    def _rule_above_tariff(self, matches: list[MatchResult], result: AuditResult) -> None:
        """Przepłata: najpierw względem OFICJALNEGO cennika (dokładny),
        w razie braku danych/cennika — fallback do nauczonej mediany."""
        from .tariff_official import expected_transport, infer_market

        official_mult = float(self.cfg.thresholds.get("official_overpay_multiplier", 1.05))

        carrier_transport: dict[str, list[float]] = defaultdict(list)
        for m in matches:
            t = m.delivery.amount_of(FeeType.TRANSPORT)
            if t > 0:
                carrier_transport[m.delivery.carrier.value].append(t)
        carrier_median = {
            c: statistics.median(v) for c, v in carrier_transport.items() if v}

        for m in matches:
            d = m.delivery
            transport = d.amount_of(FeeType.TRANSPORT)
            if transport <= 0:
                continue
            if d.status in _TERMINAL_FAIL:
                continue  # nieudane/anulowane audytujemy w Nieudane_obciazone, nie jako przepłatę

            # 1) OFICJALNY CENNIK (jeśli mamy objętość/wagę i zgodną walutę)
            pc = (m.erp_order.postcode if m.erp_order else None) or d.receiver_postcode
            market = infer_market(pc)
            exp = expected_transport(d.carrier.value, market, d.volume_m3,
                                     d.weight_kg, d.service_level)
            if exp is not None:
                price, cur = exp
                charge_cur = "PLN"  # TODO(dom): SPT DE fakturowane w EUR -> kurs/waluta z zestawienia
                if cur == charge_cur and price > 0:
                    if transport > price * official_mult:
                        pct = round((transport / price - 1) * 100, 1)
                        result.flags.append(AuditFlag(
                            order_core=d.order_core, carrier=d.carrier.value, rule=R_TARIFF,
                            severity=Severity.FLAG,
                            message=f"above official tariff (+{pct}%)",
                            amount=transport, expected=price,
                            delta=round(transport - price, 2),
                            evidence=f"cennik {d.carrier.value}/{market}: oczekiwane {price} {cur} "
                                     f"(obj={d.volume_m3}, waga={d.weight_kg})",
                            order_number=m.erp_order.number if m.erp_order else None))
                    continue  # cennik był porównywalny -> nie dubluj medianą

            # 2) FALLBACK: nauczona mediana (brak cennika lub brak danych do lookupu)
            if self.tariff is None:
                continue
            ev = self.tariff.evaluate(d, m.erp_order)
            if ev["verdict"] == "above_tariff":
                median = ev["median"]
                delta_pct = round((transport / median - 1) * 100, 1) if median else None
                result.flags.append(AuditFlag(
                    order_core=d.order_core, carrier=d.carrier.value,
                    rule=R_TARIFF, severity=Severity.FLAG,
                    message=f"above tariff — mediana (+{delta_pct}%)",
                    amount=transport, expected=median,
                    delta=round(transport - median, 2) if median else None,
                    evidence=f"klaster n={ev['count']}, mediana={median}",
                    order_number=m.erp_order.number if m.erp_order else None))
            elif ev["verdict"] == "no_reference":
                result.no_reference_count += 1
                med = carrier_median.get(d.carrier.value)
                if med and transport > med:
                    result.flags.append(AuditFlag(
                        order_core=d.order_core, carrier=d.carrier.value,
                        rule=R_TARIFF, severity=Severity.INFO,
                        message="no reference (za mało obserwacji w klastrze)",
                        amount=transport, expected=ev["median"],
                        evidence=f"klaster n={ev['count']} (< {self.tariff.min_obs})",
                        order_number=m.erp_order.number if m.erp_order else None))

    # -- Reguła 6: surcharge sanity (Zadbano) ----------------------------- #

    def _rule_surcharge_outlier(self, matches: list[MatchResult], result: AuditResult) -> None:
        ratio_types = {"FUEL": FeeType.FUEL, "ROAD": FeeType.ROAD, "STANDARD": FeeType.STANDARD}
        # zbierz ratio per typ dla Zadbano
        samples: dict[str, list[tuple[MatchResult, float]]] = {k: [] for k in ratio_types}
        for m in matches:
            if m.delivery.carrier.value != "ZADBANO":
                continue
            transport = m.delivery.amount_of(FeeType.TRANSPORT)
            if transport <= 0:
                continue
            for name, ft in ratio_types.items():
                amt = m.delivery.amount_of(ft)
                if amt > 0:
                    samples[name].append((m, amt / transport))

        for name, pairs in samples.items():
            if len(pairs) < 5:
                continue
            ratios = [r for _, r in pairs]
            med = statistics.median(ratios)
            std = statistics.pstdev(ratios)
            if std <= 0:
                continue
            for m, ratio in pairs:
                if abs(ratio - med) > self.sigma * std:
                    result.flags.append(AuditFlag(
                        order_core=m.delivery.order_core, carrier="ZADBANO",
                        rule=R_SURCHARGE, severity=Severity.FLAG,
                        message=f"surcharge outlier {name}/TRANSPORT={ratio:.2%}",
                        amount=round(ratio, 4), expected=round(med, 4),
                        delta=round(ratio - med, 4),
                        evidence=f"mediana={med:.2%}, std={std:.2%}, n={len(pairs)}",
                        order_number=m.erp_order.number if m.erp_order else None))

    # -- Reguła 7: weryfikacja objętości ---------------------------------- #

    def _rule_volume_recheck(self, matches: list[MatchResult], result: AuditResult) -> None:
        # mediana objętości per przewoźnik jako proxy „oczekiwanej" objętości
        # (ERP nie ma jawnej objętości — TODO(dom): policzyć z wymiarów produktów)
        carrier_vol: dict[str, list[float]] = defaultdict(list)
        for m in matches:
            if m.delivery.volume_m3:
                carrier_vol[m.delivery.carrier.value].append(m.delivery.volume_m3)
        carrier_median_vol = {
            c: statistics.median(v) for c, v in carrier_vol.items() if v}

        for m in matches:
            vr = m.delivery.amount_of(FeeType.VOLUME_RECHECK)
            if vr <= 0:
                continue
            expected_vol = carrier_median_vol.get(m.delivery.carrier.value)
            vol = m.delivery.volume_m3
            sev = Severity.INFO
            msg = "volume re-measured by carrier (weryfikacja objętości)"
            delta = None
            if expected_vol and vol and expected_vol > 0:
                delta = round(vol / expected_vol - 1, 3)
                if abs(delta) > self.vol_tol:
                    sev = Severity.FLAG
                    msg = f"volume upcharge to verify (objętość {vol} vs proxy {expected_vol:.2f})"
            result.flags.append(AuditFlag(
                order_core=m.delivery.order_core, carrier=m.delivery.carrier.value,
                rule=R_VOLUME, severity=sev, message=msg,
                amount=round(vr, 2), expected=round(expected_vol, 2) if expected_vol else None,
                delta=delta, evidence=f"volume_m3={vol}",
                order_number=m.erp_order.number if m.erp_order else None))

    # -- Reguła 8: zmiany daty/adresu, dodatkowa próba -------------------- #

    def _rule_ops_changes(self, matches: list[MatchResult], result: AuditResult) -> None:
        ops_types = {
            FeeType.DATE_CHANGE: "DATE_CHANGE",
            FeeType.ADDR_CHANGE: "ADDR_CHANGE",
            FeeType.EXTRA_ATTEMPT: "EXTRA_ATTEMPT",
        }
        sums: dict[str, float] = defaultdict(float)
        for m in matches:
            for fee in m.delivery.fees:
                if fee.type_code in ops_types and fee.amount_net != 0:
                    label = ops_types[fee.type_code]
                    sums[label] += fee.amount_net
                    result.flags.append(AuditFlag(
                        order_core=m.delivery.order_core, carrier=m.delivery.carrier.value,
                        rule=R_OPS, severity=Severity.INFO,
                        message=f"{label} ({fee.type_raw})",
                        amount=round(fee.amount_net, 2),
                        evidence=f"ref={m.delivery.order_ref_raw}",
                        order_number=m.erp_order.number if m.erp_order else None))
        result.ops_sums = {k: round(v, 2) for k, v in sums.items()}
