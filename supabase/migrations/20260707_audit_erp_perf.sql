-- Wydajność RPC audit_erp (import ERP z Supabase).
--
-- Problem: pierwotny audit_erp filtrował rdzeń zamówienia wyrażeniem
--   substring(split_part(order_id,'_',1) from '[0-9]{4,6}') = any(p_cores)
-- czyli funkcją NA KOLUMNIE -> brak użycia indeksu -> seq scan 43k+ wierszy z
-- regexem per wiersz. Do tego OR z oknem dat całkiem blokował indeksy. Na małym
-- computeе Supabase zapytanie przekraczało statement_timeout (kod 57014).
--
-- Fix:
--  1) indeks funkcyjny na tym samym wyrażeniu „rdzenia" -> dopasowanie po indeksie,
--  2) OR -> UNION dwóch gałęzi (rdzeń: idx_orders_core, okno dat: idx_orders_date),
--     kolumny wybierane wprost w gałęziach (bez ponownego join-a fact_orders),
--     a items dołączane jednym leftem + jsonb_agg.
-- Efekt: ~0,26 s dla 3000 rdzeni + okno miesiąca (było: timeout).

create index if not exists idx_orders_core
  on public.fact_orders (substring(split_part(order_id, '_', 1) from '[0-9]{4,6}'));

create or replace function public.audit_erp(p_cores text[], p_start date, p_end date)
returns table(order_id text, order_date timestamptz, delivery_zip text, delivery_city text,
  status text, shipping_cost_pln numeric, total_gross_pln numeric, invoice_transport text,
  customer_name text, operational_tags text[], delivery_method text, items jsonb)
language sql stable as $function$
  with base as (
    select o.order_id, o.order_date, o.delivery_zip, o.delivery_city, o.status,
      o.shipping_cost_pln, o.total_gross_pln, o.invoice_transport, o.customer_name,
      o.operational_tags, o.delivery_method
    from public.fact_orders o
    where p_cores is not null and array_length(p_cores, 1) is not null
      and substring(split_part(o.order_id, '_', 1) from '[0-9]{4,6}') = any(p_cores)
    union
    select o.order_id, o.order_date, o.delivery_zip, o.delivery_city, o.status,
      o.shipping_cost_pln, o.total_gross_pln, o.invoice_transport, o.customer_name,
      o.operational_tags, o.delivery_method
    from public.fact_orders o
    where p_start is not null and p_end is not null
      and o.order_date >= p_start::timestamptz and o.order_date < p_end::timestamptz
  )
  select b.order_id, b.order_date, b.delivery_zip, b.delivery_city, b.status,
    b.shipping_cost_pln, b.total_gross_pln, b.invoice_transport, b.customer_name,
    b.operational_tags, b.delivery_method,
    coalesce(jsonb_agg(jsonb_build_object(
      'product_name', i.product_name, 'item_type', i.item_type,
      'bed_size', i.bed_size, 'quantity', i.quantity
    ) order by i.line_number) filter (where i.id is not null), '[]'::jsonb) as items
  from base b
  left join public.fact_order_items i on i.order_id = b.order_id
  group by b.order_id, b.order_date, b.delivery_zip, b.delivery_city, b.status,
    b.shipping_cost_pln, b.total_gross_pln, b.invoice_transport, b.customer_name,
    b.operational_tags, b.delivery_method;
$function$;
