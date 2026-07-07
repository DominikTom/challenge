"""Glosariusz: co znaczy każda zakładka `audit_report.xlsx` i jak jest liczona.

Jedno źródło prawdy — używane i w raporcie XLSX (zakładka „Legenda"), i w UI
(sekcja „Metodyka" na dole strony), żeby opis był spójny z faktyczną logiką
(reguły §6, uzgodnienie §9, matcher §4).
"""

from __future__ import annotations

# Każdy wpis: tab, rule (§), priority, what (co pokazuje), how (jak liczone/próg)
GLOSSARY: list[dict] = [
    {
        "tab": "Cross_carrier", "rule": "§6.2", "priority": "FLAG",
        "what": "Ten sam rdzeń zamówienia obciążony przez WIĘCEJ niż jednego przewoźnika w tym samym okresie.",
        "how": "Grupujemy wszystkie linie kosztu po rdzeniu (numerze) i sprawdzamy liczbę różnych przewoźników. "
               "≥2 przewoźników → FLAG. Kwota = suma obciążeń; „do odzyskania” = mniejsze z obciążeń (min). "
               "Priorytet wysoki — sortowane malejąco po kwocie do odzyskania. Tego pole „Metoda dostawy” w ERP nie wychwyci.",
    },
    {
        "tab": "Duble", "rule": "§6.1", "priority": "FLAG / INFO",
        "what": "Ten sam rdzeń u JEDNEGO przewoźnika więcej niż raz (możliwe podwójne obciążenie lub podział przesyłki).",
        "how": "FLAG (potential double charge), gdy jedna linia jest FAILED/CANCELLED a druga DELIVERED, "
               "albo dwie identyczne kwoty; „do odzyskania” = suma obciążeń za nieudane (lub min. przy identycznych). "
               "INFO (split shipment), gdy obie linie DELIVERED (przesyłka podzielona).",
    },
    {
        "tab": "Przeplaty", "rule": "§6.5", "priority": "FLAG / INFO",
        "what": "Linie z kosztem transportu odbiegające w górę od normy („czy nie przepłacamy”).",
        "how": "Uczymy medianę składnika TRANSPORT w klastrze przewoźnik × poziom_usługi × koszyk_objętości × "
               "2-cyfry_kodu. FLAG, gdy koszt > mediana × 1,20 przy ≥5 obserwacjach (pokazujemy +X%). "
               "Przy <5 obserwacjach → INFO „brak referencji” (tylko dla linii powyżej mediany przewoźnika). "
               "[Docelowo: porównanie do oficjalnego cennika zamiast mediany.]",
    },
    {
        "tab": "Nieudane_obciazone", "rule": "§6.3", "priority": "FLAG",
        "what": "Dostawy nieudane lub anulowane, za które i tak naliczono koszt.",
        "how": "status ∈ {FAILED, CANCELLED} oraz koszt netto > 0 → FLAG zawsze (niezależnie od kwoty). "
               "Cała kwota do odzyskania. Statusy: Zadbano „niepowodzenie/anulowane”, SPT „Nieodebrane”.",
    },
    {
        "tab": "Service_mismatch", "rule": "§6.4", "priority": "FLAG / INFO",
        "what": "Rozjazd poziomu usługi: co przewoźnik policzył vs co sprzedano w ERP.",
        "how": "Porządek poziomów DOOR < CARRY_IN < CARRY_IN_ASSEMBLY. Przewoźnik WYŻEJ niż ERP → FLAG "
               "(policzone wniesienie/montaż nie sprzedane klientowi). ERP WYŻEJ niż przewoźnik → INFO "
               "(możliwa nieopłacona lub utracona usługa). Poziom ERP = z pozycji-usług zamówienia.",
    },
    {
        "tab": "Surcharge_outliers", "rule": "§6.6", "priority": "FLAG",
        "what": "Nietypowe proporcje dopłat do transportu (specyficzne dla Zadbano).",
        "how": "Dla każdego zlecenia liczymy udział FUEL/TRANSPORT, ROAD/TRANSPORT, STANDARD/TRANSPORT. "
               "Jeśli udział odbiega o >3 odchylenia standardowe od mediany okresu (przy ≥5 obserwacjach danego typu) → FLAG.",
    },
    {
        "tab": "Zmiany_ops", "rule": "§6.8", "priority": "INFO",
        "what": "Koszty operacyjne: zmiany daty, zmiany adresu, dodatkowe próby doręczenia.",
        "how": "Komponenty DATE_CHANGE / ADDR_CHANGE / EXTRA_ATTEMPT (kwota ≠ 0) → INFO per pozycja; "
               "sumowane per okres do przeglądu (koszty do renegocjacji/procesu).",
    },
    {
        "tab": "Weryfikacja_objetosci", "rule": "§6.7", "priority": "INFO / FLAG",
        "what": "Zlecenia, w których przewoźnik zmierzył/zweryfikował objętość.",
        "how": "Komponent VOLUME_RECHECK > 0 → INFO. Dodatkowo, jeśli objętość zlecenia przekracza o >20% proxy "
               "oczekiwanej objętości (mediana objętości przewoźnika — ERP nie ma jawnej objętości) → FLAG do weryfikacji.",
    },
    {
        "tab": "Osierocone", "rule": "§4", "priority": "—",
        "what": "Linie kosztu w zestawieniu przewoźnika BEZ dopasowania do zamówienia w ERP (orphan).",
        "how": "Matcher nie znalazł zamówienia po rdzeniu (4–6 cyfr) ani fuzzy (nazwisko + kod pocztowy, okno ±14 dni, "
               "rapidfuzz ≥90). Zwykle surowe ID / opisy / zwroty. Do ręcznego sprawdzenia.",
    },
    {
        "tab": "Nieobciazone", "rule": "§4", "priority": "—",
        "what": "Zamówienia z ERP w okresie z wysyłką/wniesieniem, których nie ma w żadnym zestawieniu (unbilled).",
        "how": "Zamówienia z okresu (po dacie zamówienia) z poziomem DOOR/CARRY_IN/ASSEMBLY, do których nie dopasowano "
               "żadnej linii kosztu. Możliwy brak obciążenia albo dostawa innym przewoźnikiem.",
    },
    {
        "tab": "Podsumowanie_per_przewoznik", "rule": "§7", "priority": "—",
        "what": "Zbiorczo per przewoźnik.",
        "how": "Σ kosztu netto z linii, netto z faktury, delta, czy uzgodnione (tolerancja 0,01), liczba przebiegów, liczba FLAG.",
    },
    {
        "tab": "Uzgodnienie_FV", "rule": "§9", "priority": "—",
        "what": "Uzgodnienie sumy zestawienia z kwotą netto faktury, per przebieg.",
        "how": "Σ total_cost_net linii vs netto FV, tolerancja 0,01. Dla D&M każda faktura parowana z rozliczeniem po "
               "numerze + sumie (nie po miesiącu). Sprawdzamy też stopkę zestawienia (PODSUMOWANIE / RAZEM) jako kontrolę.",
    },
    {
        "tab": "Walidacja_vs_reczne", "rule": "§7", "priority": "—",
        "what": "Gdzie automat NIE zgadza się z istniejącym ręcznym wpisem „Faktura transportowa”.",
        "how": "Odczytujemy przewoźnika z ręcznego wpisu i porównujemy z auto-przypisaniem. Pokazujemy tylko rozjazdy "
               "(MISMATCH) i nieczytelne wpisy. Pustych wpisów nie nadpisujemy — uzupełniamy je automatem.",
    },
    {
        "tab": "Marza", "rule": "§5.7", "priority": "—",
        "what": "Marża na dostawie: ile klient zapłacił vs ile kosztuje przewoźnik.",
        "how": "„Koszt dostawy” z ERP (przychód od klienta) − realny koszt przewoźnika. UWAGA: przy wniesieniu przychód "
               "siedzi w pozycjach-usługach zamówienia (poza „Koszt dostawy”), więc marża dla CARRY_IN* jest oznaczana "
               "jako zaniżona (carry_in_revenue_offbook).",
    },
    {
        "tab": "Backtest", "rule": "§9", "priority": "—",
        "what": "Kontrola jakości matchera na danych historycznych.",
        "how": "Na dopasowanych liniach z istniejącym ręcznym wpisem porównujemy auto-przewoźnika z ręcznym. "
               "Raportujemy zgodność (cel ≥98%) oraz precision/recall per przewoźnik.",
    },
    {
        "tab": "Backtest_niezgodnosci", "rule": "§9", "priority": "—",
        "what": "Konkretne rozjazdy z backtestu (auto ≠ ręczny).",
        "how": "Lista: numer, rdzeń, auto vs ręczny przewoźnik, surowy wpis. Zwykle to legalnie niejednoznaczne przypadki "
               "(np. zlecenie cross-carrier, gdzie człowiek wpisał jednego przewoźnika).",
    },
]

# Krótki opis pozostałych plików wyjściowych (nie-zakładek).
OUTPUT_FILES = [
    {"file": "enriched_orders.csv",
     "what": "Eksport ERP wzbogacony: uzupełniona „Faktura transportowa”, real_transport_cost_net, "
             "carrier, service_level_matched, status_carrier, cost_breakdown_json, match_method, audit_flags."},
    {"file": "reference_tariff.json",
     "what": "Nauczony cennik referencyjny (mediana TRANSPORT per klaster) — do negocjacji i kolejnych okresów."},
    {"file": "fact_delivery_costs (Supabase)",
     "what": "Fakt kosztu per (order_core, period, carrier): realny koszt, rozbicie, flagi. Klucz upsertu."},
]
