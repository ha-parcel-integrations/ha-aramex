# Working in this repository

Home Assistant custom integration for **Aramex** parcel tracking.
Distributed via HACS; not part of HA core. One carrier in the
[ha-parcel-integrations](https://github.com/ha-parcel-integrations) suite,
**generated from ha-carrier-template** — everything outside *Carrier-specific
notes* is suite-wide; when in doubt check the template or a sibling repo.
No DTO layer.

## Shared conventions — fetch when relevant

Suite-wide rules live in
[`.github/CONVENTIONS.md`](https://github.com/ha-parcel-integrations/.github/blob/main/CONVENTIONS.md)
and are **not** repeated here. Don't fetch it every session — fetch it **before**
you act in one of these areas:

| Before you … | Fetch `CONVENTIONS.md` § |
|---|---|
| touch entities, sensors, config/options flow, coordinator, diagnostics, translations | *Home Assistant developer docs* (its table points on to the canonical HA page — don't rely on memory) |
| add/rename a parcel field, a `ParcelStatus`, or a bus event; change the sort/first-refresh; touch unmapped-status logging | *Parcel contract* — exact key set, units, sort, events + suppression; `test_parcels.py::test_normalize_publishes_exactly_the_canonical_keys` guards the key set |
| change which optional field this carrier populates vs. always returns `None` | Update `const.py`'s `CAPABILITIES` in the same commit — it feeds the comparison table on the docs site, so a field that starts (or stops) coming back non-null and isn't reflected there is a wrong claim on the website, not just a stale comment. If this carrier has more than one backend (a country-specific transport, not just a config option) with genuinely different field support, `CAPABILITIES` should be a `CAPABILITIES_BY_VARIANT` dict instead — one frozenset per backend, so a field only some backends populate doesn't get silently intersected away or overclaimed for the rest |
| ship anything while below 1.0.0 (unconfirmed data) | *Pre-1.0 releases* — one-shot WARNINGs for every guessed shape/code |
| consider "fixing" a lint/pattern the skill flags (poll interval, inline client, sync requests) | *Deliberate skill divergences* — likely intentional, don't re-flag |
| commit, bump, tag, release, or write release notes; add a feature without a test | *Workflow / Commits / Versioning / Testing* |

**Structure, options flow, dynamic polling and module layout are suite-wide**
and identical in every carrier — the authoritative spec is
[`ha-carrier-template/scaffold/CLAUDE.md`](https://github.com/ha-parcel-integrations/ha-carrier-template/blob/main/scaffold/CLAUDE.md).
This repo follows it exactly.

**Suite-wide tripwires, kept inline on purpose:**
- **First refresh in `__init__.py`, before `async_forward_entry_setups`** — from
  a forwarded platform HA can't catch `ConfigEntryNotReady` and half-sets-up the
  entry. Runtime-only; tests don't catch a regression.
- **Setup stale-entity sweep is scoped to `domain == "sensor"` and skips
  `non_parcel_unique_ids`** — else it deletes the refresh button / the
  summary+diagnostic sensors. Add a new non-parcel sensor's unique_id to the set.
- **Per-parcel sensors are removed by the summary sensor** via
  `entity_registry.async_remove` (self-removal races and leaves ghosts).
- **The pickup-point summaries are a pair.** A carrier that can deliver to a
  pickup point or locker exposes both `en_route_to_pickup_point` and
  `awaiting_pickup`, even before a real parcel has shown the status or flag
  (they read 0 until then; record it in `PENDING_*`). A carrier without pickup
  points exposes neither and keeps `pickup` constantly False.
  See *Parcel contract* in `CONVENTIONS.md`. Say "pickup point", not
  "ServicePoint"/"parcel shop"/"locker", for the generic concept; the
  example carrier demonstrates both canonical sensors.
  Aramex ships both `awaiting_pickup` and `en_route_to_pickup_point`. `pickup`
  comes from `is_pickup` (status or any scan mapping to `AT_PICKUP_POINT`),
  and `pickup_point` stays `None` until a real pickup-point name is seen.
  Pending evidence: no observed scan code maps to `AT_PICKUP_POINT` yet, so
  both sensors read 0; map the code and fill `pickup_point` when one shows up
  (`PENDING_CAPABILITIES`).

## Carrier-specific notes

This integration is deliberately limited to the keyless Australian and New
Zealand datasets. Setup selects one country; labels keep that country and are
never retried against the other host. There is no global Aramex fallback.

The API contains recipient and delivery data. `raw` is the full carrier record; diagnostics redact the personal fields (`TO_REDACT`). Sender, receiver, weight,
dimensions and `pickup_point` are intentionally `None`. `planned_from`/
`planned_to` come from `result.DeliveryETADate` (`DD/MM/YYYY`, date-only) —
turned into an all-day window (00:00:00 to 23:59:59) in the carrier's zone
(Pacific/Auckland for NZ; Home Assistant's own zone for AU, which spans several), and cleared once delivered, returning or at a pickup point. It is the carrier's booking-time estimate, not
recomputed as the parcel moves, so a delayed parcel can carry a date already in the past —
surface it as-is rather than guessing a correction. History is opt-in.
The observed AU `CNS` scan reports that the parcel left a facility for the
next destination, so it maps to `in_transit`.
Unknown scan codes produce a one-shot warning. `url` is a confirmed
`?l=<label>` deep link (`TRACKING_URL_BASES` in `const.py`), not just the
bare tracking page. API mechanics live in the private
`carrier-research/aramex/api/` notes.

## Running tests

```
python -m pytest tests/ --cov=custom_components.aramex
```

Coverage must stay **above 95%** (silver `test-coverage` rule). Run before
committing. A code change updates the README + this file + `docs/` in the same
commit; the API reference lives in your own private research notes, never in
this repo.
