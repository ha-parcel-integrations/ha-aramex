"""Aramex AU/NZ public tracking API client.

The client keeps the
*contract* the coordinator relies on:

* ``async_get_parcel`` returns the raw per-parcel dict on success,
* returns ``None`` when the carrier says the tracking code is unknown or not
  yet scanned (a normal, expected state — never an error),
* raises :class:`AramexApiError` for anything else, with
  ``status_code`` set on a non-2xx response and ``retry_after`` set when the
  carrier's own ``Retry-After`` header on a 429 could be parsed as seconds —
  the coordinator's backoff (Section 3 of the dynamic-polling plan) reads
  both,
* lets ``aiohttp.ClientError`` propagate untouched — ``DataUpdateCoordinator``
  already wraps those into ``UpdateFailed``.
"""
from __future__ import annotations

from typing import Any

import aiohttp

from .const import TRACKING_API_URLS


class AramexApiError(Exception):
    """Raised when an Aramex API call returns an unexpected response."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the status code and the ``Retry-After`` header, if any."""
        super().__init__(f"Aramex API request failed: {detail}")
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class AramexApiClient:
    """Client for the public Aramex tracking endpoint.

    No authentication: the endpoint is keyed on the tracking code alone. It
    answers HTTP 200 with a JSON envelope of ``{"generated_in": ..., "result":
    {...}}``; a tracking code with no scans yet, or one the carrier does not
    recognise, still answers HTTP 200 with a semantic "no scans" body.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with an aiohttp session."""
        self._session = session

    async def async_get_parcel(self, tracking_code: str, country: str = "AU") -> dict[str, Any] | None:
        """Fetch one parcel's tracking details.

        Returns the parcel dict for a known parcel, or ``None`` when the
        endpoint reports the code as unknown — which is also what a
        not-yet-scanned parcel gets. Any other failure envelope or non-2xx
        status raises :class:`AramexApiError`; network errors propagate
        as ``aiohttp.ClientError``.
        """
        async with self._session.get(
            TRACKING_API_URLS[country],
            params={"LabelNo": tracking_code, "dataFormat": "json"},
        ) as response:
            if response.status == 429:
                retry_after_header = response.headers.get("Retry-After")
                try:
                    retry_after = float(retry_after_header) if retry_after_header else None
                except ValueError:
                    retry_after = None  # an HTTP-date, not seconds; let the caller's own backoff handle it
                raise AramexApiError(
                    "HTTP 429", status_code=429, retry_after=retry_after
                )
            if response.status != 200:
                raise AramexApiError(
                    f"HTTP {response.status}", status_code=response.status
                )
            try:
                # content_type=None: consumer endpoints routinely serve JSON as
                # text/plain, and aiohttp would otherwise refuse to parse it.
                payload = await response.json(content_type=None)
            except ValueError as err:
                raise AramexApiError(f"unparseable body ({err})") from err

        if not isinstance(payload, dict):
            raise AramexApiError("unexpected body (not a JSON object)")

        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("Scans"), list):
            return None
        return {"result": result, "country": country, "tracking_code": tracking_code}
