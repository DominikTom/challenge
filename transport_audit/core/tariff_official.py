"""Oficjalne cenniki wynegocjowane z przewoźnikami (SPT PL, SPT DE, Zadbano).

Przepisane z materiałów od przewoźników. SPT PL to czysta formuła
(bez wniesienia = 71 + 11·próg, z wniesieniem = 130 + 20·próg, PLN).
SPT DE (EUR) i Zadbano (macierz objętość×waga, PLN) są literalne.

UWAGA: liczby przepisane ręcznie z materiałów — do weryfikacji w widoku
„Cenniki" (`/api/tariffs`). Poprawki wpisujemy tutaj (jedno źródło prawdy).

Lookup:
    expected_transport(carrier, market, volume_m3, weight_kg, service_level)
zwraca (cena_netto, waluta) dla oczekiwanej stawki transportu wg cennika,
albo None gdy brak cennika (np. D&M) lub wycena indywidualna.
"""

from __future__ import annotations

import re

from .models import ServiceLevel

# Rynek PL vs DE (dla SPT). UWAGA: polskie kody w ERP bywają bez myślnika
# (np. „48282”), więc po samym kodzie PL/DE jest niepewne — najlepszy sygnał to
# waluta/kraj zamówienia (currency). # TODO(dom): przekazać currency z fact_orders.
_PL_ZIP = re.compile(r"^\d{2}-\d{3}$")


def infer_market(postcode: str | None, currency: str | None = None,
                 country: str | None = None) -> str:
    """Zwróć 'PL' lub 'DE'. Priorytet: kraj -> waluta -> kod pocztowy -> PL."""
    if country:
        c = country.strip().upper()
        if c in ("DE", "DEU", "GERMANY", "NIEMCY"):
            return "DE"
        if c in ("PL", "POL", "POLAND", "POLSKA"):
            return "PL"
    if currency:
        cur = currency.strip().upper()
        if cur == "EUR":
            return "DE"
        if cur == "PLN":
            return "PL"
    if postcode and _PL_ZIP.match(postcode.strip()):
        return "PL"
    return "PL"  # domyślnie PL (bezpieczniej — cennik PLN)

# --------------------------------------------------------------------------- #
# SPT PL — formuła (PLN). Progi objętościowe: 0–0.99 co 0.1, potem co 0.2 do 7.99.
# --------------------------------------------------------------------------- #


def _spt_pl_brackets() -> list[dict]:
    rows = []
    for i in range(45):
        if i < 10:
            lo = round(0.1 * i, 2)
            hi = round(lo + 0.09, 2)
        else:
            lo = round(1.0 + 0.2 * (i - 10), 2)
            hi = round(lo + 0.19, 2)
        rows.append({"from": lo, "to": hi, "door": 71 + 11 * i, "carry": 130 + 20 * i})
    return rows


SPT_PL = {
    "carrier": "SPT",
    "market": "PL",
    "currency": "PLN",
    "mode": "volume_bracket",
    "brackets": _spt_pl_brackets(),
    "over_note": "> 7.99 m³ → wycena indywidualna",
    "services": {"montaz": 60.0, "sprzatanie": 40.0},
    "services_note": "Montaż tylko meble tapicerowane, po wyborze wniesienia. "
                     "Doliczane do pozycji „z wniesieniem”.",
}

# --------------------------------------------------------------------------- #
# SPT DE — EUR. (from, to, door=bez wniesienia, carry=z wniesieniem)
# --------------------------------------------------------------------------- #

SPT_DE = {
    "carrier": "SPT",
    "market": "DE",
    "currency": "EUR",
    "mode": "volume_bracket",
    "brackets": [
        {"from": 0.00, "to": 0.29, "door": 49.35, "carry": 73.50},
        {"from": 0.30, "to": 0.39, "door": 55.13, "carry": 89.25},
        {"from": 0.40, "to": 0.49, "door": 61.43, "carry": 94.50},
        {"from": 0.50, "to": 0.59, "door": 66.15, "carry": 99.75},
        {"from": 0.60, "to": 0.69, "door": 71.93, "carry": 110.25},
        {"from": 0.70, "to": 0.79, "door": 77.18, "carry": 115.50},
        {"from": 0.80, "to": 0.89, "door": 82.95, "carry": 126.00},
        {"from": 0.90, "to": 0.99, "door": 88.20, "carry": 136.50},
        {"from": 1.00, "to": 1.19, "door": 93.98, "carry": 141.75},
        {"from": 1.20, "to": 1.39, "door": 99.75, "carry": 152.25},
        {"from": 1.40, "to": 1.59, "door": 105.00, "carry": 157.50},
        {"from": 1.60, "to": 1.79, "door": 110.25, "carry": 168.00},
        {"from": 1.80, "to": 1.99, "door": 121.28, "carry": 183.75},
        {"from": 2.00, "to": 2.19, "door": 132.30, "carry": 199.50},
        {"from": 2.20, "to": 2.39, "door": 143.33, "carry": 220.50},
        {"from": 2.40, "to": 2.59, "door": 154.35, "carry": 236.25},
        {"from": 2.60, "to": 2.79, "door": 165.38, "carry": 252.00},
        {"from": 2.80, "to": 2.99, "door": 176.40, "carry": 267.75},
        {"from": 3.00, "to": 3.19, "door": 187.43, "carry": 283.50},
        {"from": 3.20, "to": 3.39, "door": 198.45, "carry": 304.50},
        {"from": 3.40, "to": 3.59, "door": 209.48, "carry": 320.25},
        {"from": 3.60, "to": 3.79, "door": 220.50, "carry": 336.00},
        {"from": 3.80, "to": 3.99, "door": 231.53, "carry": 351.75},
        {"from": 4.00, "to": 4.19, "door": 242.55, "carry": 367.50},
        {"from": 4.20, "to": 4.39, "door": 253.58, "carry": 388.50},
        {"from": 4.40, "to": 4.59, "door": 264.60, "carry": 404.25},
        {"from": 4.60, "to": 4.79, "door": 275.63, "carry": 420.00},
        {"from": 4.80, "to": 4.99, "door": 286.65, "carry": 435.75},
        {"from": 5.00, "to": 5.19, "door": 297.68, "carry": 451.50},
        {"from": 5.20, "to": 5.39, "door": 308.70, "carry": 472.50},
        {"from": 5.40, "to": 5.59, "door": 319.73, "carry": 488.25},
        {"from": 5.60, "to": 5.79, "door": 330.75, "carry": 504.00},
        {"from": 5.80, "to": 5.99, "door": 341.78, "carry": 519.75},
        {"from": 6.00, "to": 6.19, "door": 352.80, "carry": 535.50},
        {"from": 6.20, "to": 6.39, "door": 363.83, "carry": 556.50},
        {"from": 6.40, "to": 6.59, "door": 374.85, "carry": 572.25},
        {"from": 6.60, "to": 6.79, "door": 385.88, "carry": 588.00},
        {"from": 6.80, "to": 6.99, "door": 396.90, "carry": 603.75},
        {"from": 7.00, "to": 7.19, "door": 407.93, "carry": 619.50},
        {"from": 7.20, "to": 7.39, "door": 418.95, "carry": 640.50},
        {"from": 7.40, "to": 7.59, "door": 429.98, "carry": 656.25},
        {"from": 7.60, "to": 7.79, "door": 441.00, "carry": 672.00},
        {"from": 7.80, "to": 7.99, "door": 461.48, "carry": 687.75},
    ],
    "over_note": "> 7.99 m³ → wycena indywidualna",
    "services": {"montaz": 40.0, "sprzatanie": 20.0},
    "services_note": "Doliczane do pozycji „z wniesieniem”.",
}

# --------------------------------------------------------------------------- #
# Zadbano — macierz „wycena indywidualna” (PLN): objętość (wiersze) × waga (kolumny)
# --------------------------------------------------------------------------- #

ZADBANO_WEIGHTS = [15, 32, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210]

ZADBANO = {
    "carrier": "ZADBANO",
    "market": "PL",
    "currency": "PLN",
    "mode": "volume_weight_matrix",
    "weights": ZADBANO_WEIGHTS,
    "rows": [
        {"from": 0.0, "to": 0.1, "prices": [79.63, 80.97, 86.06, 88.10, 90.13, 92.16, 94.19, 96.23, 98.25, 100.29, 102.32, 104.35, 106.38, 108.42]},
        {"from": 0.1, "to": 0.2, "prices": [87.61, 88.95, 94.04, 96.08, 98.10, 100.14, 102.16, 104.20, 106.23, 108.27, 110.29, 112.33, 114.35, 116.39]},
        {"from": 0.2, "to": 0.3, "prices": [100.65, 101.99, 107.08, 109.11, 111.14, 113.18, 115.20, 117.24, 119.27, 121.30, 123.33, 125.37, 127.39, 129.43]},
        {"from": 0.3, "to": 0.4, "prices": [113.68, 115.03, 120.11, 122.15, 124.18, 126.22, 128.24, 130.28, 132.30, 134.34, 136.37, 138.41, 140.43, 142.47]},
        {"from": 0.4, "to": 0.5, "prices": [126.72, 128.06, 133.15, 135.19, 137.22, 139.25, 141.28, 143.32, 145.34, 147.38, 149.41, 151.44, 153.47, 155.51]},
        {"from": 0.5, "to": 0.6, "prices": [139.76, 141.10, 146.19, 148.23, 150.25, 152.29, 154.32, 156.35, 158.38, 160.42, 162.44, 164.48, 166.51, 168.54]},
        {"from": 0.6, "to": 0.7, "prices": [152.80, 154.14, 159.23, 161.27, 163.29, 165.33, 167.35, 169.39, 171.42, 173.46, 175.48, 177.52, 179.54, 181.58]},
        {"from": 0.7, "to": 0.8, "prices": [165.84, 167.18, 172.27, 174.30, 176.33, 178.37, 180.39, 182.43, 184.46, 186.49, 188.52, 190.56, 192.58, 194.62]},
        {"from": 0.8, "to": 0.9, "prices": [178.87, 180.22, 185.30, 187.34, 189.37, 191.41, 193.43, 195.47, 197.49, 199.53, 201.56, 203.59, 205.62, 207.66]},
        {"from": 0.9, "to": 1.0, "prices": [191.91, 193.25, 198.34, 200.38, 202.41, 204.44, 206.47, 208.51, 210.53, 212.57, 214.59, 216.63, 218.66, 220.70]},
        {"from": 1.0, "to": 1.1, "prices": [204.95, 206.29, 211.38, 213.42, 215.44, 217.48, 219.51, 221.54, 223.57, 225.61, 227.63, 229.67, 231.70, 233.73]},
        {"from": 1.1, "to": 1.2, "prices": [217.99, 219.33, 224.42, 226.46, 228.48, 230.52, 232.54, 234.58, 236.61, 238.65, 240.67, 242.71, 244.73, 246.77]},
        {"from": 1.2, "to": 1.3, "prices": [231.03, 232.37, 237.46, 239.49, 241.52, 243.56, 245.58, 247.62, 249.65, 251.68, 253.71, 255.75, 257.77, 259.81]},
        {"from": 1.3, "to": 1.4, "prices": [244.06, 245.41, 250.49, 252.53, 254.56, 256.59, 258.62, 260.66, 262.68, 264.72, 266.75, 268.78, 270.81, 272.85]},
        {"from": 1.4, "to": 1.5, "prices": [257.10, 258.44, 263.53, 265.57, 267.59, 269.63, 271.66, 273.70, 275.72, 277.76, 279.78, 281.82, 283.85, 285.89]},
        {"from": 1.5, "to": 1.6, "prices": [270.14, 271.48, 276.57, 278.61, 280.63, 282.67, 284.70, 286.73, 288.76, 290.80, 292.82, 294.86, 296.89, 298.92]},
        {"from": 1.6, "to": 1.7, "prices": [283.18, 284.52, 289.61, 291.65, 293.67, 295.71, 297.73, 299.77, 301.80, 303.84, 305.86, 307.90, 309.92, 311.96]},
        {"from": 1.7, "to": 1.8, "prices": [296.22, 297.56, 302.65, 304.68, 306.71, 308.75, 310.77, 312.81, 314.84, 316.87, 318.90, 320.94, 322.96, 325.00]},
        {"from": 1.8, "to": 1.9, "prices": [309.25, 310.59, 315.68, 317.72, 319.75, 321.78, 323.81, 325.85, 327.87, 329.91, 331.94, 333.97, 336.00, 338.04]},
        {"from": 1.9, "to": 2.0, "prices": [314.33, 315.64, 320.60, 322.59, 324.57, 326.56, 328.53, 330.52, 332.49, 334.48, 336.46, 338.44, 340.42, 342.41]},
        {"from": 2.0, "to": 2.1, "prices": [327.05, 328.36, 333.32, 335.31, 337.28, 339.27, 341.25, 343.23, 345.21, 347.20, 349.17, 351.16, 353.14, 355.12]},
        {"from": 2.1, "to": 2.2, "prices": [339.77, 341.07, 346.04, 348.02, 350.00, 351.99, 353.96, 355.95, 357.93, 359.91, 361.89, 363.88, 365.85, 367.84]},
        {"from": 2.2, "to": 2.3, "prices": [352.48, 353.79, 358.75, 360.74, 362.72, 364.70, 366.68, 368.67, 370.64, 372.63, 374.60, 376.59, 378.57, 380.56]},
        {"from": 2.3, "to": 2.4, "prices": [356.40, 357.67, 362.52, 364.46, 366.39, 368.33, 370.25, 372.19, 374.12, 376.06, 377.99, 379.93, 381.86, 383.80]},
        {"from": 2.4, "to": 2.5, "prices": [368.81, 370.08, 374.93, 376.87, 378.80, 380.73, 382.66, 384.60, 386.53, 388.47, 390.40, 392.34, 394.27, 396.20]},
        {"from": 2.5, "to": 2.6, "prices": [381.22, 382.49, 387.34, 389.28, 391.20, 393.14, 395.07, 397.01, 398.94, 400.88, 402.81, 404.75, 406.67, 408.61]},
        {"from": 2.6, "to": 2.7, "prices": [393.63, 394.90, 399.75, 401.69, 403.61, 405.55, 407.48, 409.42, 411.35, 413.29, 415.22, 417.16, 419.08, 421.02]},
        {"from": 2.7, "to": 2.8, "prices": [406.04, 407.31, 412.16, 414.10, 416.02, 417.96, 419.89, 421.83, 423.76, 425.70, 427.63, 429.57, 431.49, 433.43]},
        {"from": 2.8, "to": 2.9, "prices": [418.45, 419.72, 424.57, 426.51, 428.43, 430.37, 432.30, 434.24, 436.17, 438.11, 440.04, 441.98, 443.90, 445.84]},
        {"from": 2.9, "to": 3.0, "prices": [430.86, 432.13, 436.98, 438.92, 440.84, 442.78, 444.71, 446.65, 448.58, 450.52, 452.45, 454.39, 456.31, 458.25]},
    ],
    "carry_in": [0.00, 0.00, 35.58, 45.53, 58.33, 69.73, 81.09, 92.48, 103.85, 115.25, 128.05, 138.00, 150.82, 160.77],
    "rus": [14.23, 14.23, 18.48, 22.78, 29.88, 35.56, 41.28, 45.53, 52.65, 58.33, 64.02, 69.73, 75.40, 81.10],
    "over": {"per_0_1_m3": 9.19, "per_15_kg": 8.53, "carry_per_15_kg": 11.38, "rus_per_15_kg": 5.57},
    "over_note": "> 210 kg i/lub > 3 m³: +9,19/0,1 m³, +8,53/15 kg (transport).",
}

TARIFFS = {"SPT_PL": SPT_PL, "SPT_DE": SPT_DE, "ZADBANO": ZADBANO}


def all_tariffs() -> dict:
    """Zwróć wszystkie cenniki (do widoku „Cenniki” / API)."""
    return TARIFFS


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #

_CARRY_LEVELS = {ServiceLevel.CARRY_IN, ServiceLevel.CARRY_IN_ASSEMBLY}


def _bracket_price(tariff: dict, volume: float, service_level: ServiceLevel):
    for b in tariff["brackets"]:
        if b["from"] <= volume <= b["to"]:
            return b["carry"] if service_level in _CARRY_LEVELS else b["door"]
    return None  # poza tabelą → wycena indywidualna


def lookup_spt(market: str, volume_m3: float | None, service_level: ServiceLevel):
    if volume_m3 is None or volume_m3 <= 0:
        return None
    tariff = SPT_DE if str(market).upper() == "DE" else SPT_PL
    price = _bracket_price(tariff, volume_m3, service_level)
    return (round(price, 2), tariff["currency"]) if price is not None else None


def _weight_col(weight_kg: float | None) -> int:
    """Indeks kolumny wagowej: najmniejsza kolumna >= waga (domyślnie ostatnia)."""
    weights = ZADBANO_WEIGHTS
    if weight_kg is None or weight_kg <= 0:
        return 0
    for i, w in enumerate(weights):
        if weight_kg <= w:
            return i
    return len(weights) - 1


def lookup_zadbano(volume_m3: float | None, weight_kg: float | None,
                   service_level: ServiceLevel | None = None):
    """Bazowa stawka transportu z macierzy (do porównania z komponentem TRANSPORT).

    UWAGA: u Zadbano wniesienie jest OSOBNYM komponentem (Dopłata za standard),
    więc tu zwracamy tylko bazę — nie doliczamy `carry_in` (to osobny check).
    """
    if volume_m3 is None or volume_m3 <= 0:
        return None
    col = _weight_col(weight_kg)
    for row in ZADBANO["rows"]:
        if row["from"] < volume_m3 <= row["to"] or (volume_m3 == 0 and row["from"] == 0):
            return (round(row["prices"][col], 2), ZADBANO["currency"])
    return None  # ponad tabelą (>3 m³ / >210 kg) — wycena indywidualna


def zadbano_carry_in(weight_kg: float | None) -> float:
    """Dopłata za wniesienie z macierzy Zadbano (do osobnego porównania)."""
    return ZADBANO["carry_in"][_weight_col(weight_kg)]


def expected_transport(carrier: str, market: str, volume_m3: float | None,
                       weight_kg: float | None, service_level: ServiceLevel):
    """Oczekiwana stawka transportu wg oficjalnego cennika (cena, waluta) lub None."""
    carrier = (carrier or "").upper()
    if carrier == "SPT":
        return lookup_spt(market, volume_m3, service_level)
    if carrier == "ZADBANO":
        return lookup_zadbano(volume_m3, weight_kg, service_level)
    return None  # brak oficjalnego cennika (np. D&M) → fallback do mediany
