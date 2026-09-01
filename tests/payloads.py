"""Redacted Aramex AU/NZ-shaped payload fixtures."""
ACTIVE_CODE = "MP0085494934"
DELIVERED_CODE = "MP0085494935"


def event(status_code: str, timestamp: str, description: str) -> dict:
    return {"Status": status_code, "RealDateTime": timestamp, "StatusDescription": description}


def _sample(code: str, scans: list[dict]) -> dict:
    return {"tracking_code": code, "country": "AU", "result": {"LabelNumber": code, "Scans": scans}}


def delivered_sample(code: str = DELIVERED_CODE) -> dict:
    return _sample(code, [
        event("PP8", "2026-04-27T23:03:58Z", "Shipment announced"),
        event("PPP", "2026-04-28T15:52:17Z", "At sorting facility"),
        event("ONB", "2026-04-29T08:46:00Z", "Out for delivery"),
        event("R36", "2026-04-29T13:12:42Z", "Delivered"),
    ])


def active_sample(code: str = ACTIVE_CODE) -> dict:
    return _sample(code, [
        event("PP8", "2026-04-27T23:03:58Z", "Shipment announced"),
        event("PPP", "2026-04-28T15:52:17Z", "At sorting facility"),
        event("ONB", "2026-04-29T08:46:00Z", "Out for delivery"),
    ])


def pickup_sample(code: str = ACTIVE_CODE) -> dict:
    return active_sample(code)
