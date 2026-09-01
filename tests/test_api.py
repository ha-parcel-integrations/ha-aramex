"""Tests for the Aramex API client."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.aramex.api import (
    AramexApiClient,
    AramexApiError,
)

CODE = "MP0085494934"


def _session_returning(status: int, body: object = None) -> MagicMock:
    response = AsyncMock()
    response.status = status
    if isinstance(body, str):
        response.json = AsyncMock(side_effect=json.JSONDecodeError("x", body, 0))
    else:
        response.json = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


async def test_get_parcel_returns_parcel_on_success():
    session = _session_returning(
        200, {"generated_in": 1, "result": {"LabelNumber": CODE, "Scans": []}}
    )
    client = AramexApiClient(session)

    parcel = await client.async_get_parcel(CODE)

    assert parcel["tracking_code"] == CODE
    assert parcel["country"] == "AU"
    assert session.get.call_args.kwargs["params"] == {"LabelNo": CODE, "dataFormat": "json"}


async def test_get_parcel_returns_none_when_not_found():
    """An unknown or not-yet-scanned code is a normal state, not an error."""
    client = AramexApiClient(
        _session_returning(200, {"error": "Label does not have any scans."})
    )
    assert await client.async_get_parcel("EXAMPLE000000") is None


async def test_get_parcel_returns_none_on_missing_scans():
    """A 200 without a scan list is the normal semantic miss shape."""
    client = AramexApiClient(
        _session_returning(200, {"result": {"LabelNumber": CODE}})
    )
    assert await client.async_get_parcel(CODE) is None


async def test_get_parcel_raises_on_error_status():
    client = AramexApiClient(_session_returning(500, {}))
    with pytest.raises(AramexApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_unparseable_body():
    client = AramexApiClient(_session_returning(200, "not json"))
    with pytest.raises(AramexApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_non_object_body():
    client = AramexApiClient(_session_returning(200, ["not", "a", "dict"]))
    with pytest.raises(AramexApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_uses_selected_nz_host():
    session = _session_returning(200, {"result": {"LabelNumber": CODE, "Scans": []}})
    client = AramexApiClient(session)
    await client.async_get_parcel(CODE, "NZ")
    assert "aramex.co.nz" in session.get.call_args.args[0]


async def test_get_parcel_propagates_network_error():
    """ClientError is left alone — DataUpdateCoordinator already wraps it."""
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    client = AramexApiClient(session)
    with pytest.raises(aiohttp.ClientError):
        await client.async_get_parcel(CODE)
