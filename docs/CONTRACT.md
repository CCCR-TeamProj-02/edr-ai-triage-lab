# 도구 계약

> 1일차에 함께 정합니다. **혼자 바꾸지 않습니다.** 바꾸려면 상대에게 먼저 말하고, 이 표와 `src/soc/mocks.py`를 같이 고친 뒤 변경 이력에 적습니다.

🔍 기록 담당: 박찬솔  📘 문서 담당: 한재윤  (둘 다 이름을 적으면 계약 성립)

## 도구 목록

| 도구 | 만드는 사람 | 입력 | 출력 (꼭 있어야 하는 칸) | 결과 개수 상한 | 실패하면 |
|---|---|---|---|---|---|
| `get_process_tree(host, pid)` | 🔍 | `host`: 조사할 PC 이름(문자열), `pid`: 조사할 프로세스 번호(정수) | `host`, `pid`, `process`, `ancestors`, `children`. 반환하는 각 기록에 `event_id` 포함. 기록 누락 시 `note`에 사유 표시 | 대상 프로세스 1건, 부모·조상은 최대 5단계. 자식은 최대 50건 | 대상 기록이 없으면 `process: None`, `ancestors: []`, `children: []`와 사유(`note`)를 반환. 부모 기록이 중간에 없으면 찾은 기록까지 반환하고 사유 표시. OpenSearch 연결 실패 등 검색 오류는 빈 결과로 처리하지 않고 별도 오류로 알림 |
| `get_process_activity(host, pid)` | 🔍 | `host`: 조사할 PC 이름(문자열), `pid`: 조사할 프로세스 번호(정수) | `host`, `pid`, `events`. 같은 PC·프로세스의 통신(`network`)·파일(`file`)·레지스트리(`registry`)·스크립트(`script`) 기록을 시간 오름차순으로 반환. 각 기록에 `event_id` 포함 | 최대 50건 | 조건에 맞는 기록이 없으면 `events: []` 반환. OpenSearch 연결 실패 등 검색 오류는 빈 결과로 처리하지 않고 별도 오류로 알림 |
| `get_host_timeline(host, around_ts, minutes)` | 🔍 | `host`: 조사할 PC 이름(문자열), `around_ts`: 기준 시각(시간대가 포함된 ISO 8601 문자열, 예: `2026-11-16T09:12:02Z`), `minutes`: 기준 시각 앞뒤 조회 범위(분 단위 정수, 기본 10, 0 이상) | `host`, `from`, `to`, `events`, `truncated`. 기준 시각 ± `minutes` 범위(양 끝 포함)의 해당 PC 기록을 시간 오름차순으로 반환. 각 기록에 `event_id` 포함 | 최대 100건. 일치하는 기록이 100건을 초과해 일부만 반환하면 `truncated: True` | 기록이 없으면 `events: []`, `truncated: False`와 조회 범위(`from`, `to`) 반환. 시각 형식 오류·음수 조회 범위 등 잘못된 입력이나 OpenSearch 검색 오류는 빈 결과로 처리하지 않고 별도 오류로 알림 |
| `get_network_connections(host, minutes, around_ts)` | 📘 (🔍 영역에 추가, 리뷰 🔍) | `host`: 조사할 PC 이름(문자열), `minutes`: 기준 시각에서 과거로 거슬러 볼 범위(분 단위 정수, 기본 60, 1 이상), `around_ts`: 기준 시각(시간대가 포함된 ISO 8601 문자열, 선택. 생략하면 그 PC의 가장 마지막 통신 시각) | `host`, `from`, `to`, `connections`, `omitted_destinations`, `internal_skipped`, `truncated`. `connections`는 외부 IP로 간 통신을 **(프로세스 pid, 목적지 IP)별**로 묶은 목록: `dst_ip`, `pid`, `process`, `count`, `ports`, `bytes_out`, `first_ts`, `last_ts`, `avg_interval_sec`, `interval_cv`, `looks_periodic`, `samples`. `samples`의 각 항목에 `event_id` 포함(가드레일이 근거로 인정). 규칙적인 통신(`looks_periodic: True`: 5회 이상, 간격의 변동계수 0.2 미만. 탐지 룰 R008과 같은 기준)이 맨 앞 | 목적지 묶음은 최대 10개(나머지는 `omitted_destinations`로 개수만), 묶음마다 `samples`는 최대 5건. 통신 기록은 범위 안에서 최대 1000건까지 읽고 넘으면 `truncated: True`. 사내 주소(10.x, 172.16~31.x, 192.168.x, 127.x, 169.254.x)는 빼고 `internal_skipped`에 개수만 표시 | 통신 기록이 없으면 `connections: []`와 `note`(기준 시각을 못 구하면 `from`, `to`는 `null`). `minutes`가 1 미만이거나 정수가 아니거나 `around_ts`에 시간대가 없는 등 잘못된 입력, OpenSearch 검색 오류는 빈 결과로 처리하지 않고 별도 오류로 알림 |
| `search_playbook(query, k)` | 📘 | `query`: 찾을 내용(한국어 질문, 문자열), `k`: 돌려받을 조각 수(정수, 기본 3) | 목록 `[{source, page, category, text, score}]`. 각 항목에 `source`(파일 이름, 예: `01_response_policy_tables.pdf`) 포함. `page`는 알 수 없으면 `null`. `score`는 검색 방식마다 의미가 달라(합친 검색은 RRF 점수, 최대 약 0.03) 크기로 판단하지 않음 | 최대 `k`개. `text`는 청크 길이를 따르며 최대 700자(`max_characters` 기준) | 관련 조각이 없으면 `[]`. OpenSearch 연결 실패 등 검색 오류는 빈 결과로 처리하지 않고 별도 오류로 알림 (다른 도구와 같은 방식) |

## 꼭 합의할 것
- 🔍 텔레메트리 도구의 모든 결과에는 **`event_id`**가 있다. → 가드레일이 판정 근거를 추적하는 데 씁니다 (2일차 `G-1`).
- 📘 플레이북 검색 결과에는 **`source`(파일 이름)**가 있다. → 권고에 출처를 붙이는 데 씁니다.

## 변경 이력

| 바꾼 것 | 이유 | 둘 다 동의 |
|---|---|---|
| `get_process_tree` 입력·출력·조회 상한·실패 처리 초안 작성 | 견본과 구현 안내를 바탕으로 사용 방식을 명시. | 둘 다 동의 |
| 기록 담당 조사 도구 3개의 계약 초안 완성 | 활동 조회 최대 50건·타임라인 최대 100건은 기존 구현 안내 반영. 트리 자식 최대 50건과 실패·입력 오류 처리 규칙은 합의용 제안이며 구현 시 반영 필요 | 둘 다 동의 |
| `search_playbook` 입력·출력·결과 개수 상한·실패 처리 초안 작성 | `mocks.py`와 `search.py`의 반환 모양에 맞춤. | 둘 다 동의 |
| `search_playbook`의 `text` 길이를 "표 청크는 더 길 수 있음"에서 "최대 800자"로 정정 | 청킹 구현 결과 `max_characters=800`이 상한이고 실제 청크는 557~746자. `score` 의미(RRF 최대 약 0.03, 크기로 판단 안 함)는 그대로 | 둘 다 동의 |
| `search_playbook`의 `text` 길이 상한을 "최대 800자"에서 "최대 700자"로 변경 (2일차 D2-8) | 청킹 실험 결과 `max_characters`를 800에서 700으로 정함 (`DECISIONS.md` 청킹 참고). 상한이 줄어드는 것이라 기존 사용 방식에는 영향 없음 | 한재윤 변경, 박찬솔은 실험자로 결과 확인 |
| 새 도구 `get_network_connections(host, minutes, around_ts)` 추가 (2일차 교차 작업 D2-7) | 외부 IP별 연결 횟수·간격을 요약해 주기적 통신(C2 비콘)을 찾기 위함. 입력에 `around_ts`(선택)를 더했다: 기록이 실습 데이터의 고정 시각이라 "지금부터 최근 N분"은 쓸 수 없고, 알림 시각을 기준으로 삼아야 하기 때문. 묶는 기준은 R008처럼 (프로세스, 목적지 IP). IP로만 묶으면 같은 IP에 접속하는 다른 프로세스의 통신이 섞여 규칙성이 깨지는 것을 실제 데이터(WS-010)에서 확인해 고침. 모든 요약에 `event_id`가 있는 `samples`를 넣어 가드레일이 근거로 인정하게 함 | 한재윤 작성, 박찬솔 리뷰 후 기록 |
