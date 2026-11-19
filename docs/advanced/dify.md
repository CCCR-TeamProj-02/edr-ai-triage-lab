# Dify 연동 (D3-3, DIFY-1)

같은 플레이북 검색을 **코드로 만든 에이전트**와 **노코드 플랫폼 Dify**에서 각각 써 보고 비교했다.

## 연결 구성
- **우리 쪽:** API의 `POST /dify/retrieval` (`src/soc/api/dify.py`). Dify의 External Knowledge API 규격을 따른다.
- **DIFY-1 (점수 정규화):** `search_playbook`의 RRF 점수(1/61 ≈ 0.016 근처)를 그대로 주면 Dify의 `score_threshold`(예: 0.5)에 모두 걸러진다. 그래서 검색 결과의 최대 점수를 1.0으로 두고 나머지를 비례로 바꾼다(`normalize_scores`). 점수는 **상대값**이라 최상위 결과가 항상 1.0이다.
- **Dify 쪽:** Knowledge → External Knowledge API에 `http://soc.1.201.110.71.nip.io/dify`를 등록한다. 끝에 `/retrieval`은 붙이지 않는다(Dify가 붙인다). 그 지식 베이스를 Chatbot의 Context에 연결했다.
- **인증:** `Authorization: Bearer <DIFY_API_KEY>`. 서버 Secret `app-secrets`의 `DIFY_API_KEY`와 Dify에 입력한 값이 같아야 한다. 올바른 키는 200, 틀린 키와 옛 기본값 `change-me`는 403인 것을 확인했다.
- **측정 조건:** 700자 청킹, 실제 임베딩(`text-embedding-3-small`), 실제 LLM(`gpt-4o-mini`), `KB_TOOLS=real`.

## 연동하며 겪은 것
| 증상 | 원인 | 조치 |
|---|---|---|
| Dify에서 External Knowledge API 추가가 실패 | Dify에 새 키를 넣었는데 서버는 아직 기본값 `change-me`를 써서 검증 요청이 403 | 서버 Secret에 `DIFY_API_KEY`를 넣고 API를 재시작한 뒤 Dify의 키도 같은 값으로 맞춤 |
| 서버에 키가 없는데도 요청이 통과 | `config.py`의 `dify_api_key` 기본값이 `change-me`라 Secret이 없으면 그 값이 쓰인다 | 무작위 키로 교체. 기본값에 의존하지 않는다 |

## 같은 질문 비교
### ① LSASS 덤프
- **Dify 질문:** "LSASS 덤프가 의심되면 격리는 누가 승인해?"
- **Dify 답:** 호스트 네트워크 격리는 SOC 팀장이 승인한다. 대상이 서버(SRV-)라면 서비스 담당자의 추가 동의도 필요하다. 인용: `02_playbook_credential_dump.pdf`, `09_response_matrix_complex_tables.pdf`, `01_response_policy_tables.pdf`.
- **우리 에이전트:** 알림 `al-2085ed5a51f5`(WS-003, `comsvcs.dll` MiniDump로 LSASS 메모리 덤프 의심). 판정 `malicious`(신뢰도 0.9), 기법 `T1003.001`, 근거 `event_id` 4개. 조치 `collect_forensics`와 `isolate_host`, 승인권자 `Security Team Lead`, 출처 `02_playbook_credential_dump.pdf`. 상태는 `pending_approval`.

### ② 랜섬웨어
- **Dify 질문:** "랜섬웨어 의심 시 첫 조치는?"
- **Dify 답:** 감염 의심 호스트의 네트워크 격리를 최우선으로 한다. SOC 팀장 승인이 필요하고(critical이면 승인 요청과 동시에 팀장에게 전화 보고), 승인 대기 중에는 감염 호스트가 접근한 공유 드라이브 목록을 확보한다. 인용: `03_playbook_ransomware_header_footer.pdf`, `02_playbook_credential_dump.pdf`.
- **우리 에이전트:** 알림 `al-a6074c7feb9c`(WS-006, `invoice_viewer.exe`가 20개 파일을 단시간에 이름 변경, critical). 판정 `malicious`(0.9), 기법 `T1486`, 근거 `event_id` 6개. 조치 `isolate_host`(승인권자 SOC 팀장), `collect_forensics`(승인권자 없음). 출처 `03_playbook_ransomware_header_footer.pdf`. 상태는 `pending_approval`.

## 비교
| | Dify 챗봇 | 우리 에이전트 |
|---|---|---|
| 입력 | 사람이 쓴 한 줄 질문 | 실제 알림과 그 호스트의 PC 기록 |
| 근거 | 플레이북 PDF 검색 | PC 기록 조회 + 플레이북 검색 |
| 결과 | 규정에 대한 설명 | 판정, 신뢰도, 기법, **근거 `event_id`**, 승인권자가 붙은 조치 |
| 출처 | PDF 이름 인용 | 조치마다 `source`, 판정마다 `event_id` |
| 승인 | 승인권자를 **알려 줌** | 승인권자를 붙이고 `pending_approval`에서 **멈춤** |
| 확신도 | 구조화된 값 없음 | `confidence` 숫자 |
| 만드는 데 드는 일 | 노코드. 등록과 연결만 | 도구, 가드레일, 체크포인트 등 코드 |

- **정책 답은 같은 방향이다.** 두 질문 모두 격리는 팀장 승인이 필요하다고 본다. Dify는 "서버면 서비스 담당자 추가 동의" 같은 문서 속 예외까지 풀어 주고, 에이전트는 알림 호스트가 워크스테이션이라 해당하는 규정만 조치에 붙인다.
- **층위가 다르다.** Dify는 "무엇이 규정인가"에 답한다. 에이전트는 "이 알림에 무엇을 하라"에 답하고, 그러려면 PC 기록을 조사해야 한다. Dify는 PC 기록을 볼 수 없다.
- **Dify가 나은 점:** 한 줄 질문에 빠르게 답하고 문서 인용 화면이 이미 있다. 코드 없이 바로 쓸 수 있다.
- **에이전트가 나은 점:** 판정의 근거를 `event_id`까지 추적할 수 있고, 사람 승인 전에 멈춰서 실행하지 않는다.

## 한계와 확인하지 못한 것
- **서로 다른 입력으로 비교했다.** Dify는 질문이고 에이전트는 알림이라 같은 입력에 대한 답의 정확도 비교는 아니다. 두 질문마다 에이전트에게 같은 문장을 던진 것이 아니라, 같은 주제(LSASS 덤프, 랜섬웨어)의 알림 한 건씩을 골랐다.
- **알림은 한 건씩만 봤다.** 판정이 항상 같다는 뜻이 아니다. 에이전트의 판정 정확도(정답 대비)는 최종 평가(D3-8)에서 따로 잰다.
- **검색 점수는 상대값이다.** 최상위가 항상 1.0이라 "얼마나 관련 있는가"의 절대 척도가 아니다. `score_threshold`를 올려도 결과가 걸러지지 않는다. 낮은 관련도 결과를 거르려면 정규화 방식을 바꿔야 한다.
- **Dify 응답 품질은 Dify 쪽 LLM 설정에 달려 있다.** 우리 서버의 LLM과 별개이다.
- 두 질문 외에 한국어 질문이 영어 문서(08번)를 찾는 경우는 확인하지 않았다.
