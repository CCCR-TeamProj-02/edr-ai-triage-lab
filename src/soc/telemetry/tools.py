"""🔍 조사 도구: 에이전트가 PC 기록을 조사할 때 부르는 함수들.

도구 계약 (docs/CONTRACT.md)
- 모든 결과의 기록 하나하나에 `event_id`가 있다 → 가드레일이 판정 근거를 검증하는 데 씀
- 명령줄은 앞부분만 (요약) → LLM에게 넘기는 글자 수가 곧 비용과 속도

함수의 설명(docstring)은 LLM이 '어떤 도구를 부를지' 고를 때 읽는 글입니다. 신경 써서 쓰세요.

    pytest tests/test_telemetry_tools.py -q
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta

from langchain_core.tools import tool

from ..config import settings
from ..osclient import get_client

EVENTS = f"{settings.index_events}-*"
CMD_MAX = 120           # 명령줄 요약 길이
MAX_ANCESTORS = 5
TIMELINE_LIMIT = 100


def _search(body: dict) -> list[dict]:
    res = get_client().search(index=EVENTS, body=body)
    return [h["_source"] for h in res["hits"]["hits"]]


def summarize(e: dict) -> dict:
    """기록 하나를 LLM에게 넘길 모양으로 줄입니다. (이미 만들어 둔 도우미)"""
    p = e.get("process", {})
    out = {"event_id": e["event_id"], "ts": e["ts"], "type": e["type"],
           "pid": p.get("pid"), "ppid": p.get("ppid"), "name": p.get("name"),
           "cmdline": (p.get("cmdline") or "")[:CMD_MAX], "user": p.get("user"), "signed": p.get("signed")}
    if e.get("network"):
        n = e["network"]
        out["detail"] = f"{n['dst_ip']}:{n['dst_port']} ({n.get('bytes_out', 0)} bytes)"
    elif e.get("file"):
        f = e["file"]
        out["detail"] = f"{f['action']} {f['path']}" + (f" → {f['new_path']}" if f.get("new_path") else "")
    elif e.get("registry"):
        out["detail"] = f"{e['registry']['key']} = {e['registry']['value']}"
    elif e.get("script_text"):
        out["detail"] = e["script_text"][:200]
    return out


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _find_process(host: str, pid: int) -> dict | None:
    """host에서 pid를 가진 '프로세스 생성' 기록 하나."""
    rows = _search({"size": 1, "sort": [{"ts": "desc"}], "query": {"bool": {"filter": [
        {"term": {"host": host}}, {"term": {"type": "process"}}, {"term": {"process.pid": pid}}]}}})
    return rows[0] if rows else None


def get_process_tree(host: str, pid: int) -> dict:
    """프로세스의 족보를 봅니다: 누가 이 프로세스를 실행했는지(부모, 조부모 …)와 이 프로세스가 실행한 자식들.
    '누가 실행했나', '정상 프로그램이 띄운 것인가'를 확인할 때 씁니다.

    Args:
        host: PC 이름 (예: WS-007)
        pid: 프로세스 번호 (알림의 pid)
    """
    process = _find_process(host, pid)
    if process is None:
        return {"host": host, "pid": pid, "process": None, "ancestors": [], "children": [],
                "note": f"{host}에서 대상 프로세스(pid={pid})의 생성 기록을 찾을 수 없습니다."}
    ancestors = []
    note = None
    current = process
    seen = {pid}
    for _ in range(MAX_ANCESTORS):
        parent_pid = current.get("process", {}).get("ppid")
        if parent_pid is None or parent_pid in seen:
            break
        seen.add(parent_pid)
        current = _find_process(host, parent_pid)
        if current is None:
            note = f"{host}에서 부모 프로세스(pid={parent_pid})의 생성 기록을 찾을 수 없어 조상 조회를 중단했습니다."
            break
        ancestors.append(summarize(current))

    children = _search({"size": 50, "sort": [{"ts": "asc"}], "query": {"bool": {"filter": [
        {"term": {"host": host}}, {"term": {"type": "process"}}, {"term": {"process.ppid": pid}}]}}})
    result = {"host": host, "pid": pid, "process": summarize(process),
              "ancestors": ancestors, "children": [summarize(e) for e in children]}
    if note is not None:
        result["note"] = note
    return result


def get_process_activity(host: str, pid: int) -> dict:
    """한 프로세스가 한 일을 시간순으로 봅니다: 네트워크 연결, 파일 생성·변경, 레지스트리 변경, 실행한 스크립트.
    '이 프로세스가 무엇을 남겼나(파일, 통신)'를 확인할 때 씁니다.

    Args:
        host: PC 이름 (예: WS-007)
        pid: 프로세스 번호
    """
    rows = _search({"size": 50, "sort": [{"ts": "asc"}], "query": {"bool": {"filter": [
        {"term": {"host": host}}, {"term": {"process.pid": pid}},
        {"terms": {"type": ["network", "file", "registry", "script"]}}]}}})
    return {"host": host, "pid": pid, "events": [summarize(e) for e in rows]}


def get_host_timeline(host: str, around_ts: str, minutes: int = 10) -> dict:
    """특정 시각 앞뒤로 그 PC에서 일어난 모든 일을 시간순으로 봅니다.
    알림 직전·직후에 다른 수상한 활동(다른 프로그램, 다른 통신)이 있었는지 넓게 볼 때 씁니다.

    Args:
        host: PC 이름 (예: WS-007)
        around_ts: 시간대가 포함된 기준 시각 (ISO 형식, 예: 2026-11-16T09:12:02Z). 보통 알림 시각
        minutes: 기준 시각 앞뒤로 몇 분까지 볼지 (0 이상의 정수, 기본 10)
    """
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
        raise ValueError("minutes는 0 이상의 정수여야 합니다.")
    around = _parse_ts(around_ts)
    if around.utcoffset() is None:
        raise ValueError("around_ts에는 시간대 정보가 포함되어야 합니다.")
    window = timedelta(minutes=minutes)
    start, end = _iso(around - window), _iso(around + window)
    rows = _search({"size": TIMELINE_LIMIT + 1, "sort": [{"ts": "asc"}], "query": {"bool": {"filter": [
        {"term": {"host": host}}, {"range": {"ts": {"gte": start, "lte": end}}}]}}})
    return {"host": host, "from": start, "to": end,
            "events": [summarize(e) for e in rows[:TIMELINE_LIMIT]], "truncated": len(rows) > TIMELINE_LIMIT}


# 사내 주소(RFC 1918 사설망, 루프백, 링크 로컬)는 '외부'에서 뺍니다.
# ipaddress의 is_private는 문서용 대역(203.0.113.0/24 등)도 사설로 보므로 쓰지 않습니다.
_INTERNAL = tuple(ipaddress.ip_network(n) for n in
                  ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16"))
NETWORK_FETCH_LIMIT = 1000    # 한 번에 읽을 통신 기록 수 (넘으면 truncated)
NETWORK_TOP = 10              # 돌려줄 목적지 수
NETWORK_SAMPLES = 5           # 목적지마다 근거로 쓸 수 있게 남기는 기록 수
PERIODIC_MIN_COUNT = 5        # 이 횟수 이상이고
PERIODIC_MAX_CV = 0.2         # 간격의 변동계수(표준편차/평균)가 이보다 작으면 '규칙적'. 탐지 룰 R008과 같은 기준


def _is_external(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not any(addr in net for net in _INTERNAL)


def get_network_connections(host: str, minutes: int = 60, around_ts: str | None = None) -> dict:
    """한 PC가 외부 IP와 주고받은 통신을 (프로세스, 목적지 IP)별로 요약합니다: 연결 횟수, 연결 간격, 규칙성(looks_periodic).
    같은 프로세스가 같은 외부 IP에 일정한 간격으로 반복해서 연결하는 주기적 통신(C2 비콘)이 의심될 때 씁니다.
    기록을 하나씩 나열하지 않고 묶어 주므로, 통신이 많은 PC에서 '어디로 얼마나 규칙적으로 나갔나'를 볼 때 알맞습니다.
    규칙적인 통신(looks_periodic)이 맨 앞에 옵니다.

    Args:
        host: PC 이름 (예: WS-009)
        minutes: 기준 시각에서 과거로 몇 분까지 볼지 (1 이상의 정수, 기본 60)
        around_ts: 시간대가 포함된 기준 시각 (ISO 형식, 예: 2026-11-16T09:12:02Z). 보통 알림 시각.
            생략하면 그 PC의 가장 마지막 통신 시각을 기준으로 함
    """
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
        raise ValueError("minutes는 1 이상의 정수여야 합니다.")
    base = [{"term": {"host": host}}, {"term": {"type": "network"}}]
    if around_ts is None:
        last = _search({"size": 1, "sort": [{"ts": "desc"}], "query": {"bool": {"filter": base}}})
        if not last:
            return {"host": host, "from": None, "to": None, "connections": [], "truncated": False,
                    "note": f"{host}에서 통신 기록을 찾을 수 없습니다."}
        end = _parse_ts(last[0]["ts"])
    else:
        end = _parse_ts(around_ts)
        if end.utcoffset() is None:
            raise ValueError("around_ts에는 시간대 정보가 포함되어야 합니다.")
    start = end - timedelta(minutes=minutes)
    rows = _search({"size": NETWORK_FETCH_LIMIT + 1, "sort": [{"ts": "asc"}], "query": {"bool": {"filter": base + [
        {"range": {"ts": {"gte": _iso(start), "lte": _iso(end)}}}]}}})
    truncated = len(rows) > NETWORK_FETCH_LIMIT
    rows = rows[:NETWORK_FETCH_LIMIT]

    # 프로세스와 목적지 IP를 한 쌍으로 묶습니다 (탐지 룰 R008과 같은 방식).
    # IP로만 묶으면 같은 IP에 접속하는 다른 프로세스의 통신이 섞여 간격이 흐트러집니다.
    groups: dict[tuple[int, str], list[dict]] = {}
    internal = 0
    for e in rows:
        ip = (e.get("network") or {}).get("dst_ip")
        if not ip or not _is_external(ip):
            internal += 1
            continue
        groups.setdefault((e["process"]["pid"], ip), []).append(e)

    conns = []
    for (pid, ip), evs in groups.items():
        times = [_parse_ts(e["ts"]) for e in evs]
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        item = {"dst_ip": ip, "pid": pid, "process": evs[0]["process"]["name"], "count": len(evs),
                "ports": sorted({e["network"]["dst_port"] for e in evs}),
                "bytes_out": sum(e["network"].get("bytes_out", 0) for e in evs),
                "first_ts": evs[0]["ts"], "last_ts": evs[-1]["ts"]}
        if gaps:
            mean = sum(gaps) / len(gaps)
            cv = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5 / mean if mean > 0 else None
            item["avg_interval_sec"] = round(mean, 1)
            item["interval_cv"] = None if cv is None else round(cv, 3)
            item["looks_periodic"] = bool(cv is not None and len(evs) >= PERIODIC_MIN_COUNT and cv < PERIODIC_MAX_CV)
        else:
            item["avg_interval_sec"], item["interval_cv"], item["looks_periodic"] = None, None, False
        head, tail = evs[:3], evs[3:][-(NETWORK_SAMPLES - 3):]
        item["samples"] = [{"event_id": e["event_id"], "ts": e["ts"]} for e in head + tail]
        conns.append(item)
    # 규칙적인 통신을 맨 앞에 둡니다. 정상 통신(횟수는 많지만 간격이 들쭉날쭉)에 묻히지 않게 하기 위해서입니다.
    conns.sort(key=lambda c: (not c["looks_periodic"], -c["count"], c["dst_ip"]))
    return {"host": host, "from": _iso(start), "to": _iso(end), "connections": conns[:NETWORK_TOP],
            "omitted_destinations": max(len(conns) - NETWORK_TOP, 0), "internal_skipped": internal,
            "truncated": truncated}


TELEMETRY_TOOLS = [tool(get_process_tree), tool(get_process_activity), tool(get_host_timeline),
                   tool(get_network_connections)]
