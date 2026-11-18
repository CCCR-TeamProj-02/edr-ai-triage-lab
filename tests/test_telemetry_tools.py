"""🔍 조사 도구 테스트 (TODO[REC-1] ~ [REC-4]).

    pytest tests/test_telemetry_tools.py -q

샘플 기록(data/telemetry/sample_events.jsonl)의 WS-007 이야기를 씁니다 (01 문서의 예시 알림).
  cmd.exe(pid 19329, evt-…22) → rundll32.exe(pid 40702, evt-…23) → C:\\Windows\\Temp\\d.dmp 생성(evt-…24)
"""
import copy

import pytest

from soc.config import ROOT, settings
from soc.osclient import get_client
from soc.telemetry import tools
from soc.telemetry.index_template import apply_template, index_events, load_jsonl

SAMPLE = ROOT / "data" / "telemetry" / "sample_events.jsonl"


@pytest.fixture(scope="module", autouse=True)
def loaded():
    client = get_client()
    client.indices.delete(index=f"{settings.index_events}-*", ignore_unavailable=True)
    apply_template(client)
    events = load_jsonl(SAMPLE)
    # 함정: 다른 PC(WS-099)에 같은 pid 40702가 있습니다. host 조건을 빼먹으면 섞입니다.
    twin = copy.deepcopy(next(e for e in events if e["event_id"] == "evt-00000023"))
    twin.update(event_id="evt-twin-0001", host="WS-099")
    twin["process"].update(name="notepad.exe", cmdline="notepad.exe", ppid=1234, parent_name="explorer.exe")
    try:
        index_events(events + [twin], client)
    except Exception as e:  # noqa: BLE001  진짜 OpenSearch: 템플릿이 strict라 매핑에 없는 칸이 오면 기록이 거절됨
        first = (getattr(e, "errors", None) or [{}])[0]
        reason = next(iter(first.values()), {}).get("error", {}).get("reason", str(e)[:200])
        pytest.fail(f"TODO[REC-1]: 템플릿 매핑에 없는 칸이 있어 OpenSearch가 기록을 거절했습니다 (dynamic: strict). "
                    f"{len(getattr(e, 'errors', []) or [])}건 실패, 첫 이유: {reason}", pytrace=False)
    yield


def _ids(rows):
    return [r["event_id"] for r in rows]


def test_process_tree_parent_and_note():
    r = tools.get_process_tree("WS-007", 40702)
    assert r["process"]["event_id"] == "evt-00000023"
    assert r["process"]["name"] == "rundll32.exe"
    assert _ids(r["ancestors"]) == ["evt-00000022"]          # 바로 위 부모: cmd.exe
    assert r["children"] == []


def test_process_tree_does_not_mix_hosts():
    r = tools.get_process_tree("WS-099", 40702)
    assert r["process"]["event_id"] == "evt-twin-0001"
    assert "evt-00000022" not in _ids(r["ancestors"])         # WS-007의 cmd.exe가 섞이면 안 됨


def test_process_tree_children():
    r = tools.get_process_tree("WS-007", 19329)                # cmd.exe의 자식 = rundll32.exe
    assert _ids(r["children"]) == ["evt-00000023"]


def test_process_activity_finds_dump_file():
    r = tools.get_process_activity("WS-007", 40702)
    assert _ids(r["events"]) == ["evt-00000024"]
    assert "d.dmp" in r["events"][0]["detail"]


def test_host_timeline_window():
    narrow = tools.get_host_timeline("WS-007", "2026-11-16T09:12:02Z", minutes=1)
    assert _ids(narrow["events"]) == ["evt-00000022", "evt-00000023", "evt-00000024"]
    wide = tools.get_host_timeline("WS-007", "2026-11-16T09:12:02Z", minutes=5)
    assert "evt-00000017" in _ids(wide["events"])               # 09:14:01의 outlook.exe
    assert wide["truncated"] is False


def test_results_are_summarized_with_event_id():
    r = tools.get_host_timeline("WS-002", "2026-11-16T09:05:00Z", minutes=10)
    assert r["events"], "WS-002의 기록이 하나도 없습니다"
    for e in r["events"]:
        assert e["event_id"]
        assert len(e["cmdline"]) <= tools.CMD_MAX


def test_tools_have_docstrings():
    for t in tools.TELEMETRY_TOOLS:
        assert t.description and len(t.description) > 30, f"{t.name}의 설명(docstring)이 너무 짧습니다"


@pytest.mark.skipif(settings.backend != "real", reason="매핑은 진짜 OpenSearch에서만 확인할 수 있습니다")
def test_mapping_types():
    m = get_client().indices.get_mapping(index=f"{settings.index_events}-*")
    props = next(iter(m.values()))["mappings"]["properties"]
    assert props["host"]["type"] == "keyword"
    assert props["ts"]["type"] == "date"
    assert props["process"]["properties"]["pid"]["type"] == "long"
    assert props["process"]["properties"]["cmdline"]["type"] == "text"
    assert "keyword" in props["process"]["properties"]["cmdline"]["fields"]


# ---------------------------------------------------------------- get_network_connections (2일차 D2-7)
def _net_event(i, host, ts, ip, port=443, pid=7001, name="powershell.exe", out=300):
    return {"event_id": f"evt-net-{i:04d}", "ts": ts, "host": host, "type": "network",
            "process": {"pid": pid, "ppid": 1, "name": name, "cmdline": name, "parent_name": "explorer.exe",
                        "signed": True, "user": "kim"},
            "network": {"dst_ip": ip, "dst_port": port, "proto": "tcp", "bytes_out": out}}


@pytest.fixture(scope="module")
def net_hosts():
    """WS-NET1: 30초 간격 비콘(6회) + 들쭉날쭉한 정상 통신 + 사내 통신. WS-NET2: 같은 IP를 다른 프로세스가 섞어 부름."""
    evs = [_net_event(i, "WS-NET1", f"2026-11-16T10:{m:02d}:{s:02d}Z", "198.51.100.23")
           for i, (m, s) in enumerate([(0, 0), (0, 30), (1, 0), (1, 30), (2, 0), (2, 30)])]
    evs += [_net_event(10 + i, "WS-NET1", f"2026-11-16T10:{m:02d}:00Z", "203.0.113.10", pid=7002, name="chrome.exe")
            for i, m in enumerate([0, 1, 5, 6, 20, 21])]                      # 간격이 불규칙한 정상 통신
    evs += [_net_event(20, "WS-NET1", "2026-11-16T10:03:00Z", "10.0.0.5"),         # 사내 주소는 빠짐
            _net_event(21, "WS-NET1", "2026-11-16T10:03:30Z", "192.168.1.9")]
    evs += [_net_event(30 + i, "WS-NET2", f"2026-11-16T10:0{i}:00Z", "198.51.100.23", pid=8001) for i in range(6)]
    evs += [_net_event(40, "WS-NET2", "2026-11-16T10:02:20Z", "198.51.100.23", port=8443, pid=8002, name="updater.exe")]
    index_events(evs, get_client())
    return evs


def _conn(r, ip, pid=None):
    return next(c for c in r["connections"] if c["dst_ip"] == ip and (pid is None or c["pid"] == pid))


def test_network_connections_finds_periodic_beacon(net_hosts):
    r = tools.get_network_connections("WS-NET1", minutes=60)
    c = _conn(r, "198.51.100.23")
    assert c["count"] == 6 and c["avg_interval_sec"] == 30.0 and c["looks_periodic"] is True
    assert r["connections"][0]["dst_ip"] == "198.51.100.23"          # 규칙적인 통신이 맨 앞
    assert _conn(r, "203.0.113.10")["looks_periodic"] is False        # 횟수가 같아도 불규칙하면 아님


def test_network_connections_skips_internal_addresses(net_hosts):
    r = tools.get_network_connections("WS-NET1", minutes=60)
    ips = {c["dst_ip"] for c in r["connections"]}
    assert "10.0.0.5" not in ips and "192.168.1.9" not in ips
    assert r["internal_skipped"] == 2


def test_network_connections_does_not_mix_processes(net_hosts):
    r = tools.get_network_connections("WS-NET2", minutes=60)
    assert _conn(r, "198.51.100.23", pid=8001)["looks_periodic"] is True   # 다른 프로세스(8002)가 간격을 깨면 안 됨
    assert _conn(r, "198.51.100.23", pid=8002)["count"] == 1


def test_network_connections_samples_have_event_id(net_hosts):
    r = tools.get_network_connections("WS-NET1", minutes=60)
    c = _conn(r, "198.51.100.23")
    assert 1 <= len(c["samples"]) <= tools.NETWORK_SAMPLES
    assert all(s["event_id"].startswith("evt-net-") for s in c["samples"])


def test_network_connections_window_and_empty(net_hosts):
    r = tools.get_network_connections("WS-NET1", minutes=1, around_ts="2026-11-16T10:02:30Z")
    assert _conn(r, "198.51.100.23")["count"] == 3                         # 10:01:30 ~ 10:02:30
    none = tools.get_network_connections("WS-NOPE")
    assert none["connections"] == [] and "찾을 수 없습니다" in none["note"]


def test_network_connections_rejects_bad_input(net_hosts):
    with pytest.raises(ValueError):
        tools.get_network_connections("WS-NET1", minutes=0)
    with pytest.raises(ValueError):
        tools.get_network_connections("WS-NET1", minutes=5, around_ts="2026-11-16T10:00:00")
