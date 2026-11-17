"""Attention and farm follow Faustus onto a Spark over the owner's tailnet."""
import httpx
import pytest

from cassandra_hoard import faustus_attention as fa
from cassandra_hoard import faustus_farm as ff
from cassandra_hoard.hoard_link import where

NOW = 1_800_000_000.0
LOCAL = "http://127.0.0.1:7000"
SPARK = "https://spark3.example-tailnet.ts.net"
RUNS = [{"session_id": "s1", "kind": "approval", "label": "Fix the build", "since": NOW - 45 * 60}]
FARM = {"schema": 1, "generated_at": NOW, "counts": {"total": 0}, "items": []}


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """No Hub and no real Faustus: the placement is whatever each test says."""
    for name in ("CASSANDRA_FAUSTUS_URL", "CASSANDRA_FAUSTUS_TOKEN", "CASSANDRA_FAUSTUS_FARM_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(where, "fetch", lambda *a, **k: {})
    where.forget()
    yield
    where.forget()


def _place(monkeypatch, url):
    monkeypatch.setattr(where, "faustus_urls", lambda configured, *a, **k: list(configured) + ([url] if url else []))


def _transport(alive, *, seen):
    """A transport where only the hosts in ``alive`` answer; the rest refuse the connection."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host not in alive:
            raise httpx.ConnectError("refused")
        if request.url.path == "/api/attention":
            return httpx.Response(200, json={"runs": RUNS, "unread_count": 1})
        etag = 'W/"spark"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"ETag": etag})
        return httpx.Response(200, json=FARM, headers={"ETag": etag})
    return httpx.MockTransport(handler)


# -- which addresses may hear the token -------------------------------------------------------------

@pytest.mark.parametrize("url,ok", [
    ("http://127.0.0.1:7000", True),
    ("http://localhost:7000", True),
    ("http://[::1]:7000", True),
    ("https://spark3.example-tailnet.ts.net", True),
    ("https://SPARK3.example-tailnet.ts.net:8443/x", True),
    ("http://100.64.0.1:7000", True),
    ("http://100.100.100.100:7000", True),
    ("http://100.127.255.254:7000", True),
    ("http://100.128.0.1:7000", False),
    ("http://100.63.255.255:7000", False),
    ("http://192.168.1.20:7000", False),
    ("http://10.0.0.5:7000", False),
    ("https://example.com", False),
    ("https://ts.net", False),
    ("https://evilts.net", False),
    ("https://spark3.example-tailnet.ts.net.evil.com", False),
    ("https://user@evil.com#.ts.net", False),
])
def test_only_this_machine_and_the_tailnet_are_allowed(url, ok):
    assert fa.is_allowed(url) is ok


def test_a_spark_gets_a_longer_timeout_than_loopback():
    assert fa.timeout_for(LOCAL) < fa.timeout_for(SPARK)


# -- attention ---------------------------------------------------------------------------------------

def test_attention_reads_faustus_on_the_spark_when_it_is_not_on_this_pc(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    seen = []
    out = fa.report(tmp_path, token="t", transport=_transport({"spark3.example-tailnet.ts.net"}, seen=seen), clock=lambda: NOW)
    assert out["ok"] is True and out["url"] == SPARK and out["waiting_on_you"] == 1
    assert [r.url.host for r in seen] == ["127.0.0.1", "spark3.example-tailnet.ts.net"]
    assert seen[-1].headers["authorization"] == "Bearer t" and seen[-1].url.path == "/api/attention"


def test_attention_prefers_faustus_on_this_pc_and_never_asks_the_hub(tmp_path, monkeypatch):
    def hub_must_stay_silent(*a, **k):
        raise AssertionError("Faustus answered on this PC: no placement lookup")
    monkeypatch.setattr(where, "faustus_urls", hub_must_stay_silent)
    seen = []
    out = fa.report(tmp_path, token="t", transport=_transport({"127.0.0.1"}, seen=seen), clock=lambda: NOW)
    assert out["ok"] is True and out["url"] == LOCAL and len(seen) == 1


def test_attention_says_it_asked_both_when_neither_answers(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    out = fa.report(tmp_path, token="t", transport=_transport(set(), seen=[]), clock=lambda: NOW)
    assert out["ok"] is False and out["reason"] == "unreachable"
    assert out["tried"] == [LOCAL, SPARK] and "placed" in out["note"]


def test_attention_without_a_placement_is_the_old_behaviour(tmp_path, monkeypatch):
    _place(monkeypatch, "")
    out = fa.report(tmp_path, token="t", transport=_transport(set(), seen=[]), clock=lambda: NOW)
    assert out["reason"] == "unreachable" and out["tried"] == [LOCAL]


def test_attention_keeps_the_pinned_address_first_and_adds_the_placed_one(tmp_path, monkeypatch):
    monkeypatch.setenv("CASSANDRA_FAUSTUS_URL", "http://127.0.0.1:7777")
    _place(monkeypatch, SPARK)
    seen = []
    out = fa.report(tmp_path, token="t", transport=_transport({"spark3.example-tailnet.ts.net"}, seen=seen), clock=lambda: NOW)
    assert out["ok"] is True and [str(r.url) for r in seen][0].startswith("http://127.0.0.1:7777/")


def test_an_address_given_on_purpose_is_the_only_one_asked(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    seen = []
    out = fa.report(tmp_path, url="http://127.0.0.1:7001", token="t", transport=_transport(set(), seen=seen), clock=lambda: NOW)
    assert out["reason"] == "unreachable" and [r.url.port for r in seen] == [7001]


def test_attention_accepts_a_tailnet_address_as_the_configured_one(tmp_path):
    seen = []
    out = fa.report(tmp_path, url="http://100.101.102.103:7000", token="t",
                    transport=_transport({"100.101.102.103"}, seen=seen), clock=lambda: NOW)
    assert out["ok"] is True and seen[0].headers["authorization"] == "Bearer t"


def test_the_token_never_goes_to_a_placed_address_off_the_tailnet(tmp_path, monkeypatch):
    _place(monkeypatch, "http://192.168.1.20:7000")
    seen = []
    out = fa.report(tmp_path, token="secret", transport=_transport(set(), seen=seen), clock=lambda: NOW)
    assert out["ok"] is False
    assert all(r.url.host == "127.0.0.1" for r in seen)


def test_off_tailnet_pin_is_named_as_such(tmp_path):
    out = fa.report(tmp_path, url="https://example.com", token="t", transport=_transport({"example.com"}, seen=[]))
    assert out["ok"] is False and out["reason"] == "bad_url" and "tailnet" in out["note"]


def test_the_watcher_follows_faustus_to_the_spark(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    (tmp_path / "faustus-token").write_text("t\n", encoding="utf-8")
    sent = []
    watcher = fa.Watcher(tmp_path, wait_min=10, interval_s=60, emit=lambda name, data: sent.append((name, data)),
                         clock=lambda: NOW, transport=_transport({"spark3.example-tailnet.ts.net"}, seen=[]))
    out = watcher.tick()
    assert out["ok"] is True and out["url"] == SPARK
    assert sent and sent[0][0] == fa.EVENT and sent[0][1]["session_id"] == "s1"
    assert watcher.status()["url"] == SPARK


# -- farm --------------------------------------------------------------------------------------------

def test_farm_reads_the_state_from_the_spark(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    seen = []
    reader = ff.FarmReader(min_interval_s=0.0, transport=_transport({"spark3.example-tailnet.ts.net"}, seen=seen))
    out = ff.report(tmp_path, token="t", reader=reader, clock=lambda: NOW)
    assert out["ok"] is True and out["url"] == SPARK
    assert seen[-1].url.path == "/api/farm/state" and seen[-1].headers["authorization"] == "Bearer t"


def test_farm_etag_is_kept_for_the_address_that_answered(tmp_path, monkeypatch):
    """The refused PC address before the Spark one must not make every read a full download."""
    _place(monkeypatch, SPARK)
    seen = []
    reader = ff.FarmReader(min_interval_s=0.0, transport=_transport({"spark3.example-tailnet.ts.net"}, seen=seen))
    first = reader.read(tmp_path, token="t")
    second = reader.read(tmp_path, token="t")
    assert first["unchanged"] is False and second["unchanged"] is True and second["url"] == SPARK
    spark_calls = [r for r in seen if r.url.host == "spark3.example-tailnet.ts.net"]
    assert "if-none-match" not in spark_calls[0].headers and spark_calls[1].headers["if-none-match"] == 'W/"spark"'


def test_farm_returns_to_this_pc_when_faustus_is_back_here(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    alive = {"spark3.example-tailnet.ts.net"}
    seen = []

    def handler(request):
        return _transport(alive, seen=seen).handle_request(request)
    reader = ff.FarmReader(min_interval_s=0.0, transport=httpx.MockTransport(handler))
    assert reader.read(tmp_path, token="t")["url"] == SPARK
    alive.clear()
    alive.add("127.0.0.1")
    assert reader.read(tmp_path, token="t")["url"] == LOCAL


def test_farm_says_which_addresses_it_tried(tmp_path, monkeypatch):
    _place(monkeypatch, SPARK)
    out = ff.report(tmp_path, token="t", reader=ff.FarmReader(min_interval_s=0.0, transport=_transport(set(), seen=[])))
    assert out["reason"] == "unreachable" and out["tried"] == [LOCAL, SPARK]


def test_farm_never_sends_the_token_to_a_placed_address_off_the_tailnet(tmp_path, monkeypatch):
    _place(monkeypatch, "https://example.com")
    seen = []
    ff.report(tmp_path, token="secret", reader=ff.FarmReader(min_interval_s=0.0, transport=_transport(set(), seen=seen)))
    assert all(r.url.host == "127.0.0.1" for r in seen)


def test_farm_accepts_a_tailnet_pin(tmp_path):
    seen = []
    out = ff.report(tmp_path, url="https://spark3.example-tailnet.ts.net", token="t",
                    reader=ff.FarmReader(min_interval_s=0.0, transport=_transport({"spark3.example-tailnet.ts.net"}, seen=seen)))
    assert out["ok"] is True and len(seen) == 1
