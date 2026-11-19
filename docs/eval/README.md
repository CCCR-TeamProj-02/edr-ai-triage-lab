# D3-8 최종 평가 결과 (2026-11-19)

이 폴더의 파일은 3일차 최종 평가의 원본입니다.

| 파일 | 내용 |
|---|---|
| `rag_eval_final.json` | `python -m soc.eval.rag_eval --mode all --k 3` 결과 |
| `agent_eval_final.json` | `python -m soc.eval.agent_eval --n 12 --seed 42` 1회차 결과 (`summary`와 알림별 `rows`) |
| `agent_eval_final_run2.json` | 같은 조건으로 다시 돌린 2회차 결과. 1회차 파일은 그대로 두었다 |
| `server/` | **서버(k3s) 인덱스** RAG 평가 원본. 로컬 결과와 분리해서 보관 (`server/README.md` 참고) |

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

서버 인덱스 결과의 원본은 `server/`에 있다(콘솔 출력과 JSON). 처음 측정 때 저장하지 않은 것을 같은 서버 상태에서 다시 실행해 보관한 것이며 값은 같았다. Recall@1(합친 검색)은 별도 측정에서 0.667(14/21)이었고 이 폴더에는 원본이 없다. 문서별로 틀린 곳은 06번(스캔본, 청크 0개)과 08번(영어 문서)이다.

**로컬 결과와 서버 결과는 환경이 달라 직접 비교하지 않는다.** 서버가 기준점보다 높지만 임베딩(실제), 청킹, 적재 환경이 함께 달라서 청킹만의 효과로 단정할 수 없다.

## 에이전트 판정 (12건)
| 지표 | 2일차 기준점 | 최종 |
|---|---|---|
| 판정 정확도 | 0.667 (8/12) | **0.500 (6/12)** |
| 지어낸 근거 비율 | 0.0 | 0.0 |
| 승인 요청 비율 | 0.583 | 0.917 |
| 응답 속도 평균 / 최대 | 16.66초 / 19.86초 | 17.89초 / 23.66초 |
| 알림당 비용 | 0.00424 USD | 0.00438 USD |

### 재측정 (2회차, 코드·모델·프롬프트·인덱스 변경 없음)
첫 실행(`ff4f2bb`)과 재측정 시점의 `main`(`3d6e00e`) 사이에는 `docs/eval` 외에 변경이 없다(`src`, `tests`, `infra`, `Dockerfile`, `requirements.txt`). 같은 환경 변수, 같은 seed(42), 같은 알림 12건, 같은 로컬 인덱스를 썼다.

| 지표 | 2일차 기준점 | 1회차 | 2회차 |
|---|---|---|---|
| 판정 정확도 | 0.667 (8/12) | 0.500 (6/12) | **0.417 (5/12)** |
| 지어낸 근거 비율 | 0.0 | 0.0 | 0.0 |
| 승인 요청 비율 | 0.583 | 0.917 | 0.750 |
| 응답 속도 평균 / 최대 | 16.66초 / 19.86초 | 17.89초 / 23.66초 | 16.83초 / 23.09초 |
| 알림당 비용 | 0.00424 USD | 0.00438 USD | 0.00449 USD |

알림별 판정 비교 (같은 12건):
| 알림 | 시나리오 | 정답 | 1회차 | 2회차 |
|---|---|---|---|---|
| `al-e44004f618a7` | `it_inventory_script` | benign | malicious | malicious |
| `al-a30de1f7496b` | `it_inventory_script` | benign | malicious | malicious |
| `al-aa70d6243178` | `backup_rename` | benign | malicious | malicious |
| `al-094acf3e1f0a` | `backup_rename` | benign | malicious | **suspicious** (달라짐) |
| `al-7d833405272f` | `credential_dump` | malicious | suspicious | suspicious |
| `al-01e4dcec9bc5` | `lateral_psexec` | malicious | suspicious | suspicious |
| `al-3a04c6fef7b1` | `lateral_psexec` | malicious | malicious | **suspicious** (달라짐, 맞음 → 틀림) |
| `al-4240c625b52a` | `persistence_runkey` | malicious | malicious | malicious |
| `al-1afbbf06fac3` | `persistence_runkey` | malicious | malicious | malicious |
| `al-f15665f4c8d8` | `ransomware` | malicious | malicious | malicious |
| `al-3397dffcf023` | `lateral_psexec` | malicious | malicious | malicious |
| `al-4343c39ad371` | `phishing_macro_powershell` | malicious | malicious | malicious |

- 12건 중 **2건의 판정이 달라졌다**(둘 다 `suspicious`로). 같은 알림·같은 설정에서도 판정이 바뀐다는 것이 확인됐다. 그 결과 정확도가 6/12에서 5/12가 됐다.
- **정상(benign) 4건은 두 번 모두 정답(benign)을 맞히지 못했다.** 1회차는 4건 모두 `malicious`, 2회차는 3건 `malicious`와 1건 `suspicious`였다.
- 두 번 모두 기준점(8/12)보다 낮다. 다만 기준점은 한 번만 측정했고 그 값의 흔들림은 알 수 없으므로, 하락이 실제인지 측정 오차인지는 이 두 번의 측정만으로 확정하지 못한다.

### 1회차 틀린 사례 6건
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
- **판정 정확도가 내려간 원인은 확인하지 못했다. 아래는 미검증 가설이다.** 기준점 이후에 추가된 `get_network_connections`(D2-7)가 정상 알림에도 외부 통신 근거를 가져와 판정을 악성 쪽으로 밀었을 수 있다. 1회차 판정 이유 문구에 "외부 IP와의 네트워크 통신"이 나온 것만 보고 세운 가설이고, 도구를 끄고 다시 측정하는 등의 검증은 하지 않았다. 두 번 측정했어도 원인은 확정되지 않는다.
- **측정이 흔들린다.** D2-6에서 같은 알림, 같은 설정으로도 재실행하면 판정이 반대로 바뀌었다(`temperature=0`이어도). 이번 재측정에서도 12건 중 2건이 달라졌다. 판정 정확도가 0.500, 0.417로 같은 조건에서도 1건 차이가 났다.
- **고도화(D3-5, D3-6)를 하지 않았다.** 기준점 대비 달라진 숫자는 고도화가 아니라 실제 임베딩 전환, 청킹 700자, 이후 코드 변경(`get_network_connections` 등)의 효과다.
- 오탐 예외 규정은 06번 스캔본에 있는데 인덱스에 청크가 없고, 판정 노드가 `search_playbook`을 부르지 않는다(D2-6 사례 ①).
