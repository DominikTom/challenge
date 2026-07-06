# Transport Audit — atrybucja i audyt kosztów transportu (MyBed / Delta Industries)

CLI w Pythonie, które dla danego okresu rozliczeniowego:

1. **Przypisuje realny koszt dostawy** do każdego zamówienia, łącząc zestawienia
   trzech przewoźników (SPT, Zadbano, D&M Trans) z eksportem ERP.
2. **Audytuje** koszty: duble (w tym cross-carrier), dostawy nieudane/anulowane
   obciążone mimo to, niespójność poziomu usługi, przepłaty względem nauczonego
   cennika, outliery dopłat, weryfikacje objętości, koszty operacyjne.
3. **Uzgadnia** sumę zestawienia z kwotą netto faktury zbiorczej (tolerancja 0,01).
4. **Wypełnia kolumnę `Faktura transportowa`** w eksporcie ERP (dziś ręcznie).
5. **Uczy cennik referencyjny** każdego przewoźnika z danych historycznych.

Kod, nazwy plików i identyfikatory są po angielsku; komentarze i raporty po polsku.

---

## Instalacja

```bash
pip install -r requirements.txt
# lub: pip install -e .
```

> **Uwaga o środowisku:** `pdfplumber` (przez `pdfminer` → `cryptography`) wymaga
> działającego backendu `cffi`. Jeśli import `pdfplumber` wywala
> `ModuleNotFoundError: _cffi_backend`, wykonaj:
> `pip install --upgrade --force-reinstall cffi cryptography`.

## Uruchomienie

```bash
python -m transport_audit run \
  --erp Eksport.csv \
  --carrier SPT:invoice=FS_38.pdf,spec=MYBED_LUTY_II.pdf \
  --carrier ZADBANO:invoice=307_02_2026_TR.pdf,spec=307_02_2026_TR_specyfikacja.xlsx \
  --carrier DM_TRANS:invoice=FS_24_02_2026.pdf,spec=MYBED_07_02_2026.pdf \
  --period 2026-02 \
  --out ./out [--load-supabase]
```

- `--carrier` można podać **wiele razy** (także wiele rozliczeń D&M w miesiącu —
  reconciler paruje każdą fakturę z jej rozliczeniem po numerze + sumie).
- `--load-supabase` upsertuje fakty do `fact_delivery_costs`
  (klucz `order_core + period + carrier`); bez poświadczeń zapisuje
  `fact_delivery_costs.jsonl` do ręcznego importu.

### Demo bez realnych danych

Repo nie zawiera danych produkcyjnych. Wygeneruj syntetyczne, ale wierne
formatom fikstury (odwzorowują wszystkie golden case'y z §9) i uruchom na nich:

```bash
python -m transport_audit make-fixtures
F=transport_audit/tests/fixtures
python -m transport_audit run --erp $F/Eksport.csv \
  --carrier SPT:invoice=$F/invoice_spt.pdf,spec=$F/spt_spec.pdf \
  --carrier ZADBANO:invoice=$F/invoice_zadbano.pdf,spec=$F/zadbano_spec_broken.xlsx \
  --carrier DM_TRANS:invoice=$F/invoice_dm.pdf,spec=$F/dm_settlement.pdf \
  --period 2026-02 --out ./out
```

## Aplikacja web (deploy na Vercel)

Oprócz CLI dołączona jest lekka warstwa web (Flask) deployowalna na Vercel jako
funkcja serverless — wgrywasz pliki w przeglądarce, dostajesz uzgodnienie,
flagi audytowe i pliki do pobrania.

```
api/index.py            # wejście serverless (WSGI `app`) dla @vercel/python
vercel.json             # rewrite wszystkich ścieżek na funkcję Flask
transport_audit/web/    # app.py (Flask), service.py (pipeline->JSON), ui.py (frontend)
transport_audit/web/sample/  # wbudowane dane demo (przycisk „Pokaż na danych demo")
```

Endpointy:
- `GET /` — interfejs (upload ERP + zestawień + faktur, wybór okresu),
- `POST /api/run` — uruchamia audyt na wgranych plikach → JSON + pliki (base64),
- `POST /api/sample` — audyt na wbudowanych danych demo (golden cases, bez uploadu),
- `GET /api/health` — health check.

**Deploy:** repo jest podpięte do Vercela — `git push` na gałąź produkcyjną
uruchamia build. Vercel instaluje `requirements.txt` (szczupły: bez
reportlab/pytest) i serwuje `api/index.py`. Lokalnie: `vercel dev` albo
`flask --app transport_audit.web.app run`.

**Ograniczenia serverless (ważne dla realnych danych):**
- **Limit ciała żądania ~4,5 MB** — duży `Eksport.csv` (~225 tys. wierszy) może
  się nie zmieścić w uploadzie; użyj wtedy CLI albo pojedynczego okresu.
- **Timeout 60 s** (Pro) i limit pamięci — dobre do jednego okresu / mniejszych
  plików. Ciężki, pełny audyt miesięczny lepiej puszczać przez CLI.
- Przycisk **„Pokaż na danych demo"** działa zawsze (dane wbudowane, bez uploadu).

## Wyjścia (`--out`)

| Plik | Zawartość |
|------|-----------|
| `enriched_orders.csv` | ERP wzbogacony: `Faktura transportowa` (uzupełniona tam, gdzie pusta), `real_transport_cost_net`, `carrier`, `service_level_matched`, `status_carrier`, `cost_breakdown_json`, `match_method`, `audit_flags`, walidacja vs ręczny wpis. |
| `audit_report.xlsx` | Zakładki: **Cross_carrier** (na górze, z kwotą do odzyskania), Duble, Przeplaty, Nieudane_obciazone, Service_mismatch, Surcharge_outliers, Zmiany_ops, Weryfikacja_objetosci, Osierocone, Nieobciazone, Podsumowanie_per_przewoznik, Uzgodnienie_FV, Walidacja_vs_reczne, Marza, Backtest. |
| `reference_tariff.json` | Nauczony cennik: mediana `TRANSPORT` per klaster `carrier × service_level × volume_bucket × postcode2`. |
| `backtest.json` | Zgodność auto-przypisania przewoźnika z historycznym wpisem ręcznym (precision/recall). |

## Architektura

```
transport_audit/
  adapters/          # parsery per przewoźnik -> wspólny model Delivery
    base.py            CarrierAdapter (interfejs parse(path)->list[Delivery])
    spt.py             PDF „flat" (Symfonia print)
    zadbano.py         XLSX „itemized" (wiele komponentów, surowy XML)
    dm_trans.py        PDF „flat + usługi" (+ dedup zdublowanych stron)
    invoice_pdf.py     faktury zbiorcze (kontrola sumy)
  core/
    models.py          Delivery / FeeComponent / ErpOrder / Invoice / AuditFlag
    config.py          config.yaml + normalizacja
    util.py            liczby PL, daty, rozmiary, kody pocztowe, kubatura
    xlsx_raw.py        surowy czytnik XLSX (odporny na zepsuty styles.xml)
    pdf_util.py        rekonstrukcja kolumn PDF po pozycjach X
    erp.py             wczytanie CSV, forward-fill, grupowanie, service_level
    matcher.py         złączenie po core + fallback fuzzy + orphan/unbilled
    reconciler.py      Σ vs netto FV (parowanie FV↔rozliczenie dla D&M)
    tariff_model.py    nauka cennika referencyjnego
    anomalies.py       reguły audytu §6
    margin.py          marża klient vs koszt przewoźnika
    backtest.py        walidacja matchera na historii
    pipeline.py        orkiestracja całości
    supabase_loader.py opcjonalny upsert do panelu CFO
  report.py            generowanie wyjść §7
  cli.py               interfejs typer
  config.yaml          mapowania (Typ usługi, pozycje-usługi), progi
  tests/               testy + fixtures/generate.py (golden cases)
```

Wszystkie trzy adaptery zwracają identyczny model `Delivery`, więc matcher,
audyt i raport działają bez zmian. **Nowy przewoźnik = tylko nowy adapter.**

## Reguły audytu (progi w `config.yaml`)

| Reguła | Warunek | Severity |
|--------|---------|----------|
| Cross-carrier | ten sam `core` u >1 przewoźnika | FLAG (kwota do odzyskania = min z dwóch) |
| Dubel / split (intra) | ten sam `core` u 1 przewoźnika | FLAG (failed+delivered / identyczne kwoty) lub INFO (split) |
| Nieudane obciążone | `status ∈ {FAILED, CANCELLED}` i koszt > 0 | FLAG |
| Service mismatch | poziom przewoźnika ≠ ERP | FLAG (przewoźnik > ERP) / INFO (odwrotnie) |
| Przepłata | `TRANSPORT` > mediana klastra × 1,20 przy ≥5 obs. | FLAG (`+X%`) / INFO no_reference |
| Surcharge outlier | `FUEL/ROAD/STANDARD ÷ TRANSPORT` > 3σ (Zadbano) | FLAG |
| Weryfikacja objętości | `VOLUME_RECHECK` > 0 | INFO / FLAG (>20% rozjazdu) |
| Zmiany ops | `DATE_CHANGE / ADDR_CHANGE / EXTRA_ATTEMPT` | INFO (sumowane per okres) |

## Walidacja (twarde asserty, §9)

- Reconciliation: Σ SPT = **29 225,96**, Σ Zadbano = **98 172,50**,
  Σ D&M (po dedup) = **5 445,00** (±0,01).
- Golden cases: dubel intra `Shoper46046-1` (259,60 + 583,00),
  dubel cross-carrier `47559` (Zadbano 568,52 + D&M 455,00),
  12 „niepowodzenie" Zadbano (Σ 5 251,37) + 3 „anulowane",
  złączenia `MYBED43503→Shoper43503-1`, `Shoper46281-1_8801122→Shoper46281-1`,
  `47559→Shoper47559-1`, dedup zdublowanej treści PDF D&M.
- Backtest matchera: zgodność przewoźnika ≥ 98% na dopasowanych.

```bash
python -m pytest transport_audit/tests -q
```

---

## 🔔 Rekomendacja procesowa — SPT: prosić o XLSX/CSV zamiast PDF

Parser zestawienia **SPT jest z natury kruchy** — to druk (Symfonia/print),
z którego kolumny odtwarzamy po pozycjach X słów. Każda zmiana układu wydruku
(inne szerokości kolumn, zawijanie adresu, dodatkowa kolumna) może wymagać
korekty parsera; przy zbyt ciasnych kolumnach sąsiednie wartości potrafią się
skleić w ekstrakcji tekstu.

**Zadbano dostarcza już XLSX** — ustrukturyzowany, jednoznaczny, bez ryzyka
błędów ekstrakcji. Rekomendujemy **poprosić SPT (i D&M) o zestawienie w
XLSX/CSV** zamiast PDF. Korzyści:

- eliminacja błędów rekonstrukcji kolumn (kwoty, statusy, poziom usługi),
- szybsze i stabilne uzgodnienie sumy z fakturą,
- brak potrzeby ręcznej weryfikacji „czy PDF się dobrze sparsował".

Do czasu migracji parser PDF działa, ale traktujmy `PODSUMOWANIE`/`RAZEM` jako
twardy check sumy i pilnujmy uzgodnienia z fakturą (zakładka `Uzgodnienie_FV`).

## Uwaga o danych i fiksturach

Repozytorium **nie zawiera realnych danych** MyBed. Zamiast nich dołączony jest
deterministyczny generator syntetycznych fikstur (`tests/fixtures/generate.py`),
wiernie odwzorowujący struktury z §2 i wszystkie golden case'y z §9 — dzięki
temu parsery, audyt i uzgodnienia są w pełni przetestowane end-to-end i narzędzie
zadziała po podłożeniu prawdziwych plików. Realne pliki wejściowe są w
`.gitignore`.
