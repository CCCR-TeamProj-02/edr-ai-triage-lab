# D3-8 최종 평가 결과 (2026-11-19)

이 폴더의 파일은 3일차 최종 평가의 원본입니다.

| 파일 | 내용 |
|---|---|
| `rag_eval_final.json` | `python -m soc.eval.rag_eval --mode all --k 3` 결과 |
| `agent_eval_final.json` | `python -m soc.eval.agent_eval --n 12 --seed 42` 결과 (`summary`와 알림별 `rows`) |

## 실행 환경
| 항목 | 값 |
|---|---|
| 측정한 PC | 2일차 기준점을 측정한 PC (한재윤) |
| 실행 커밋 | `ff4f2bb` (이 시점의 `main`. 이후 `main`이 바뀌어도 이 숫자는 이 커밋의 결과) |
| 채팅 모델 / 임베딩 | `gpt-4o-mini` / `text-embedding-3-small` (기준점과 같은 채팅 모델) |
| 프롬프트 버전 | `v1` |
| 검색 방식 | 합친 검색 (키워드 + 벡터, RRF) |
| 설정 | `BACKEND=real`, `TELEMETRY_TOOLS=real`, `KB_TOOLS=real`, `FAKE_LLM=false`, `PARSE_STRATEGY=fast` |
| 평가 알림 | 12건, `--seed 42` (기준점과 같음, 악성 8 + 정상 4) |
| OpenSearch | 로컬 Docker (`docker compose`) |

환경 보정: 로컬 `.env`의 `OPENSEARCH_URL`이 `http://localhost:92006`(없는 포트)이어서, 이번 실행에서만 `http://localhost:9200`으로 덮어썼다. `.env` 파일은 수정하지 않았다. 로컬 Docker가 꺼져 있어 `postgres`와 `opensearch`를 먼저 올렸다.

## 청크 크기
| 대상 | 값 |
|---|---|
| 설정값 (`CHUNK_MAX_CHARACTERS`) | 700 |
| **로컬 검색 인덱스** (이 평가에 쓴 것) | 청크 19개, 최대 길이 1052자, 평균 730자. **적재할 때 쓴 값은 확인하지 못했다.** 800과 1200 실험의 청크 수가 같고 최대 길이가 800을 넘어서 1200 실험일 수도 있다. 이 PC에서는 `python -m soc.kb.ingest`가 Segmentation fault로 죽어 다시 적재하지 못했다(인덱스는 그대로). |
| **서버(k3s) 인덱스** | 700자로 적재, 청크 20개 (`kb-ingest` Job) |

기준점은 800자였다. 로컬 인덱스의 RAG 결과가 기준점과 세 방식 모두 같아서, 로컬은 사실상 기준점과 같은 상태의 인덱스로 보인다.

## RAG 검색 (Recall@3)
| 방식 | 2일차 기준점 | 로컬 인덱스 (이 폴더의 JSON) | 서버 인덱스 (700자, 실제 임베딩, 별도 측정) |
|---|---|---|---|
| 키워드 | 0.905 | 0.905 | 0.905 |
| 벡터 | 0.762 | 0.762 | 0.857 |
| 합친 검색 | 0.857 (18/21) | 0.857 (18/21) | 0.905 (19/21) |

서버 인덱스 결과는 이 폴더에 JSON이 없다. 서버에서 `rag_eval --mode all`을 돌린 터미널 출력 기준이고, Recall@1(합친 검색)은 0.667(14/21)이었다. 문서별로 틀린 곳은 06번(스캔본, 청크 0개)과 08번(영어 문서)이다.

## 에이전트 판정 (12건)
| 지표 | 2일차 기준점 | 최종 |
|---|---|---|
| 판정 정확도 | 0.667 (8/12) | **0.500 (6/12)** |
| 지어낸 근거 비율 | 0.0 | 0.0 |
| 승인 요청 비율 | 0.583 | 0.917 |
| 응답 속도 평균 / 최대 | 16.66초 / 19.86초 | 17.89초 / 23.66초 |
| 알림당 비용 | 0.00424 USD | 0.00438 USD |

### 틀린 사례 6건
| 알림 | 정답 | 판정 |
|---|---|---|
| `al-e44004f618a7` `it_inventory_script` | benign | malicious |
| `al-a30de1f7496b` `it_inventory_script` | benign | malicious |
| `al-aa70d6243178` `backup_rename` | benign | malicious |
| `al-094acf3e1f0a` `backup_rename` | benign | malicious |
| `al-7d833405272f` `credential_dump` | malicious | suspicious |
| `al-01e4dcec9bc5` `lateral_psexec` | malicious | suspicious |

틀린 6건 중 4건은 정상 알림을 악성으로 본 오탐이다. `it_inventory_script`의 판정 이유에는 "ExecutionPolicy Bypass"와 "외부 IP와의 네트워크 통신"이 들어 있다.

## 해석할 때 주의할 점
- **판정 정확도가 내려간 원인은 확인하지 못했다.** 가설은 기준점 이후에 추가된 `get_network_connections`(D2-7)가 정상 알림에도 외부 통신 근거를 가져와 판정을 악성 쪽으로 밀었다는 것이다. 판정 이유 문구만 보고 세운 가설이며 검증하지 않았다.
- **측정이 흔들린다.** D2-6에서 같은 알림, 같은 설정으로도 재실행하면 판정이 반대로 바뀌었다(`temperature=0`이어도). 12건 한 번의 0.667과 0.500의 차이(2건)는 이 흔들림 안에 들 수 있다. 같은 조건으로 한 번 더 돌려야 변화를 확정할 수 있다.
- **고도화(D3-5, D3-6)를 하지 않았다.** 기준점 대비 달라진 숫자는 고도화가 아니라 실제 임베딩 전환, 청킹 700자, 이후 코드 변경(`get_network_connections` 등)의 효과다.
- 오탐 예외 규정은 06번 스캔본에 있는데 인덱스에 청크가 없고, 판정 노드가 `search_playbook`을 부르지 않는다(D2-6 사례 ①).
