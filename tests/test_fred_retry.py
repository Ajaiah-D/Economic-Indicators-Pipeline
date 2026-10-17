"""Retries on transient FRED errors, driven through the real fredapi client.

fredapi turns every HTTPError into ValueError(<message from the XML body>),
raised inside the `except HTTPError` block, so the HTTPError survives only as
the ValueError's __context__. These tests stub urllib's urlopen underneath a
real Fred client so the chaining is exactly what production sees.
"""

import io
import urllib.error

import fredapi.fred
import pytest
from fredapi import Fred

import fetch_fred
import fetch_fred_states
import fetch_fred_vintages
import fred_retry

OK_XML = (
    b'<observations>'
    b'<observation realtime_start="2026-01-15" realtime_end="9999-12-31" date="2025-01-01" value="1.5"/>'
    b'<observation realtime_start="2026-01-15" realtime_end="9999-12-31" date="2025-04-01" value="2.5"/>'
    b'</observations>'
)
REASONS = {400: "Bad Request", 429: "Too Many Requests", 502: "Bad Gateway", 503: "Service Unavailable"}


def http_error(code, message=None):
    body = f'<error code="{code}" message="{message}"/>' if message else f'<error code="{code}"/>'
    return urllib.error.HTTPError(
        "https://api.stlouisfed.org/fred/series/observations", code, REASONS[code], None, io.BytesIO(body.encode())
    )


class FakeResponse:
    def read(self):
        return OK_XML


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(fred_retry, "_sleep", calls.append)
    monkeypatch.setattr(fetch_fred_states, "REQUEST_SPACING_SECONDS", 0)
    return calls


@pytest.fixture
def fred_responses(monkeypatch):
    """Map series_id -> list of outcomes (an exception to raise, or None for success).

    The last outcome repeats once the list runs out. Returns per-series call counts.
    """
    script, counts = {}, {}

    def fake_urlopen(url):
        series_id = url.split("series_id=")[1].split("&")[0]
        counts[series_id] = counts.get(series_id, 0) + 1
        outcomes = script.get(series_id, [None])
        outcome = outcomes[min(counts[series_id], len(outcomes)) - 1]
        if isinstance(outcome, urllib.error.HTTPError):
            outcome.fp.seek(0)  # the same error object can be raised repeatedly
        if outcome is not None:
            raise outcome
        return FakeResponse()

    monkeypatch.setattr(fredapi.fred, "urlopen", fake_urlopen)
    return script, counts


def test_fredapi_chains_the_http_error_as_context(fred_responses):
    # guards the assumption the classifier is built on
    script, _ = fred_responses
    script["PAPCPI"] = [http_error(503)]
    with pytest.raises(ValueError) as info:
        Fred(api_key="test").get_series("PAPCPI")
    assert str(info.value) == "None"
    assert isinstance(info.value.__context__, urllib.error.HTTPError)
    assert info.value.__context__.code == 503


def test_states_one_transient_503_then_success_records_no_failure(monkeypatch, fred_responses, sleeps):
    script, counts = fred_responses
    script["PAPCPI"] = [http_error(503), None]
    monkeypatch.setattr(fetch_fred_states, "STATES", {"PA": "Pennsylvania", "CA": "California"})

    df, errors = fetch_fred_states.fetch_indicator(Fred(api_key="test"), "per_capita_income", "{code}PCPI")

    assert errors == []
    assert sorted(df["state"].unique()) == ["CA", "PA"]
    assert counts == {"PAPCPI": 2, "CAPCPI": 1}
    assert sleeps == [2]


def test_states_persistent_503_is_recorded_with_http_status_and_exits_1(monkeypatch, fred_responses, sleeps):
    script, counts = fred_responses
    script["PAPCPI"] = [http_error(503)]
    monkeypatch.setattr(fetch_fred_states, "STATES", {"PA": "Pennsylvania", "CA": "California"})
    monkeypatch.setattr(fetch_fred_states, "STATE_INDICATORS", {"per_capita_income": "{code}PCPI"})
    monkeypatch.setattr(fetch_fred_states, "_fred_client", lambda: Fred(api_key="test"))
    monkeypatch.setattr(fetch_fred_states, "upload_to_s3", lambda df, label, run_date: "k")

    successes, failures = fetch_fred_states.run_all()

    assert [s["states"] for s in successes] == [1]
    assert [f["series_id"] for f in failures] == ["PAPCPI"]
    assert "HTTP 503 Service Unavailable" in failures[0]["error"]
    assert "after 4 attempts" in failures[0]["error"]
    assert "None" not in failures[0]["error"]
    assert counts["PAPCPI"] == 4
    assert sleeps == [2, 4, 8]

    counts.clear()
    assert fetch_fred_states.main() == 1


def test_states_permanent_400_is_not_retried_and_is_recorded(monkeypatch, fred_responses, sleeps):
    script, counts = fred_responses
    script["PAPCPI"] = [http_error(400, "Bad Request.  The series does not exist.")]
    monkeypatch.setattr(fetch_fred_states, "STATES", {"PA": "Pennsylvania"})

    df, errors = fetch_fred_states.fetch_indicator(Fred(api_key="test"), "per_capita_income", "{code}PCPI")

    assert df.empty
    assert counts == {"PAPCPI": 1}
    assert sleeps == []
    assert [e["series_id"] for e in errors] == ["PAPCPI"]
    assert "HTTP 400" in errors[0]["error"]
    assert "series does not exist" in errors[0]["error"]


def test_429_and_network_errors_are_retried(fred_responses, sleeps):
    script, counts = fred_responses
    script["UNRATE"] = [http_error(429), urllib.error.URLError("timed out"), TimeoutError(), None]

    data = fred_retry.call_with_retry(Fred(api_key="test").get_series, "UNRATE")

    assert len(data) == 2
    assert counts == {"UNRATE": 4}
    assert sleeps == [2, 4, 8]


def test_5xx_with_a_non_xml_body_is_still_retried(fred_responses, sleeps):
    # a proxy's HTML 502 page makes fredapi's XML parse fail; the HTTPError is still the context
    script, counts = fred_responses
    gateway = urllib.error.HTTPError("https://api.stlouisfed.org", 502, "Bad Gateway", None,
                                     io.BytesIO(b"<html><body>502</body>"))
    script["UNRATE"] = [gateway, None]

    data = fred_retry.call_with_retry(Fred(api_key="test").get_series, "UNRATE")

    assert len(data) == 2
    assert counts == {"UNRATE": 2}
    assert sleeps == [2]


def test_national_one_transient_503_then_success(monkeypatch, fred_responses, sleeps):
    script, counts = fred_responses
    script["GDP"] = [http_error(503), None]
    monkeypatch.setattr(fetch_fred, "_fred_client", lambda: Fred(api_key="test"))

    df = fetch_fred.fetch_series("GDP", "gdp")

    assert list(df["value"]) == [1.5, 2.5]
    assert counts == {"GDP": 2}


def test_national_persistent_503_is_recorded_with_http_status_and_exits_1(monkeypatch, fred_responses, sleeps):
    script, _ = fred_responses
    script["GDP"] = [http_error(503)]
    monkeypatch.setattr(fetch_fred, "_fred_client", lambda: Fred(api_key="test"))
    monkeypatch.setattr(fetch_fred, "upload_to_s3", lambda df, series_id, label, run_date: "k")

    successes, failures = fetch_fred.run_all()

    assert len(successes) == len(fetch_fred.INDICATORS) - 1
    assert failures == [{"series_id": "GDP", "error": "HTTP 503 Service Unavailable (after 4 attempts)"}]
    assert fetch_fred.main() == 1


def test_vintages_one_transient_503_then_success(fred_responses, sleeps):
    script, counts = fred_responses
    script["PAYEMS"] = [http_error(503), None]

    df = fetch_fred_vintages.fetch_vintages(Fred(api_key="test"), "PAYEMS", "nonfarm_payrolls")

    assert list(df["release_date"]) == ["2026-01-15", "2026-01-15"]
    assert counts == {"PAYEMS": 2}


def test_vintages_persistent_503_exits_1(monkeypatch, fred_responses, sleeps):
    script, _ = fred_responses
    script["PAYEMS"] = [http_error(503)]
    monkeypatch.setattr(fetch_fred_vintages, "_fred_client", lambda: Fred(api_key="test"))
    monkeypatch.setattr(fetch_fred_vintages, "upload_to_s3", lambda df, label, run_date: "k")

    _, failures = fetch_fred_vintages.run_all()

    assert failures == [{"series_id": "PAYEMS", "error": "HTTP 503 Service Unavailable (after 4 attempts)"}]
    assert fetch_fred_vintages.main() == 1
