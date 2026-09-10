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
- **If this carrier can reach `ParcelStatus.AT_PICKUP_POINT` from a real raw
  status/code**, it needs an `awaiting_pickup` sensor — see *Parcel contract*
  in `CONVENTIONS.md`. Say "pickup point", not "ServicePoint"/"parcel
  shop"/"locker", for the generic concept. `ha-dhl-nl`, `ha-dpd`, `ha-gls`,
  `ha-inpost` are reference implementations. `aramex` is **exempt**: the AU/NZ
  scan feed has no pickup-point delivery method — none of the observed scan
  codes maps to `AT_PICKUP_POINT`, and `pickup`/`pickup_point` are always
  `False`/`None` — so there is deliberately no `awaiting_pickup` sensor. Add
  one if a real parcel ever surfaces a pickup-point code.

## Carrier-specific notes

This integration is deliberately limited to the keyless Australian and New
Zealand datasets. Setup selects one country; labels keep that country and are
never retried against the other host. There is no global Aramex fallback.

The API contains recipient and delivery data. Normalisation retains only scan
code, cleaned status text and timestamp in `raw`; sender, receiver, weight,
dimensions and pickup-point fields are intentionally `None`. `planned_from`/
`planned_to` come from `result.DeliveryETADate` (`DD/MM/YYYY`, date-only) —
turned into an all-day window in the entry's country timezone, and cleared
once delivered. It is the carrier's booking-time estimate, not recomputed as
the parcel moves, so a delayed parcel can carry a date already in the past —
surface it as-is rather than guessing a correction. History is opt-in.
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
