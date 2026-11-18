# Day2 팀원용 .env 변경 안내

기존 `.env`를 통째로 교체하지 말고 아래 항목만 수정합니다. 같은 `.env.example`에서 시작했어도 개인 설정은 다를 수 있습니다. `.env`와 개인 API 키는 Git에 올리지 않습니다.

## 1. 실제 도구 연결·평가용 설정

PC에서 Python을 실행하고, 프로젝트 Docker Compose의 OpenSearch·Postgres에 연결하는 기준입니다.

```dotenv
BACKEND=real
TELEMETRY_TOOLS=real
KB_TOOLS=real
FAKE_LLM=false
CHECKPOINTER=postgres
GUARDRAIL_ON_FAIL=retry
OPENSEARCH_URL=http://localhost:9200
```

| 항목 | 변경 이유 |
| --- | --- |
| `TELEMETRY_TOOLS` | `mock` → `real`: 실제 PC 기록 조회 |
| `KB_TOOLS` | `mock` → `real`: 실제 플레이북 검색. `true`는 잘못된 값이며 가짜 도구가 선택됨 |
| `FAKE_LLM` | `false`: 실제 LLM과 임베딩 사용. OpenAI 호출 비용 발생 |
| `CHECKPOINTER` | `postgres`: 승인 대기 상태를 저장하고 API 재시작 후 복원. `auto`도 `BACKEND=real`이면 Postgres 선택 |

다음 값은 각자의 환경을 유지하거나 확인합니다.

- `OPENAI_API_KEY`: 본인의 유효한 키. 서로 공유하지 않습니다.
- `POSTGRES_DSN`: 자신의 Postgres 사용자·비밀번호·DB·포트에 맞는 기존 연결 문자열 유지. 프로젝트 기본 포트는 5432이며, 깨 보기용 5433과 혼동하지 않습니다.
- `CHAT_MODEL`: 팀에서 합의한 모델 유지.
- `EMBED_MODEL`, `EMBED_DIM`: 문서 적재 때 사용한 모델과 차원을 검색에서도 동일하게 유지합니다.
- 현재 Compose는 인증 없는 HTTP OpenSearch입니다. 예전 HTTPS 환경에서만 쓰던 `OPENSEARCH_USERNAME`, `OPENSEARCH_PASSWORD`, `OPENSEARCH_CA_CERTS`가 남아 있다면 해당 줄을 제거하거나 비웁니다. 별도 보안 서버를 사용하는 경우에는 이 변경을 적용하지 않습니다.

`FAKE_LLM`은 LLM뿐 아니라 임베딩에도 적용됩니다. 실제 임베딩으로 적재한 인덱스를 `FAKE_LLM=true`의 가짜 벡터로 검색하지 않습니다.

## 2. API 승인 흐름만 테스트할 때

OpenSearch·Postgres는 실제로 쓰고, 조사 도구·문서 검색·LLM은 가짜로 사용합니다. `.env`를 반복해서 바꾸기보다 실행할 터미널에서만 덮어쓸 수 있습니다.

Mac/zsh — 프로젝트 루트에서 실행:

```bash
PYTHONPATH=src BACKEND=real CHECKPOINTER=postgres TELEMETRY_TOOLS=mock KB_TOOLS=mock FAKE_LLM=true .venv-kb/bin/python -m uvicorn soc.api.main:app --host 127.0.0.1 --port 8000
```

PowerShell — 필요한 패키지가 설치된 가상환경을 활성화한 뒤 실행:

```powershell
$env:PYTHONPATH = "src"
$env:BACKEND = "real"
$env:CHECKPOINTER = "postgres"
$env:TELEMETRY_TOOLS = "mock"
$env:KB_TOOLS = "mock"
$env:FAKE_LLM = "true"
python -m uvicorn soc.api.main:app --host 127.0.0.1 --port 8000
```

Mac 명령의 `.venv-kb`는 이번 검증에 사용한 환경 이름입니다. 팀원은 기존에 패키지가 준비된 환경을 사용하면 됩니다. PowerShell의 `$env:` 설정은 같은 터미널에 남으므로 실제 평가 전에 새 터미널을 열거나 해당 값을 실제 모드로 되돌립니다.

## 3. 적용 확인과 주의사항

- `.env` 변경 후 API와 워커를 재시작합니다. 실행 중인 프로그램에는 자동 반영되지 않습니다.
- 터미널 환경변수가 `.env`보다 우선합니다. 실제 모드로 바꿨는데 가짜 도구가 나오면 터미널의 임시 설정을 확인합니다.
- `http://127.0.0.1:8000/readyz`에서 `ready`, `opensearch`, `postgres`가 모두 `true`인지 확인합니다.
- 설정 파일을 Git에서 받는 것과 데이터 적재는 별개입니다. 각 PC의 OpenSearch에 로그와 플레이북 데이터가 있어야 합니다.
- 로컬 테스트에서 Python 3.14는 지정된 `unstructured==0.27.*`와 호환되지 않았습니다. PDF 적재는 기존 Python 3.12로 만든 `.venv-kb`에서 `requirements-kb.txt`를 설치해 수행했습니다. 이미 호환 환경이 있는 팀원은 그대로 재사용합니다. 공통 실행 패키지는 `requirements.txt`에 있습니다.
- 위 `localhost` 주소는 PC에서 Python을 실행할 때 기준입니다. Python 앱도 컨테이너 안에서 실행한다면 서비스 이름(`opensearch`, `postgres`)으로 연결해야 합니다.

## 4. 이번에 확인한 범위

- 실제 도구·검색·LLM으로 실습 알림 분석: 조회 기록과 판정 근거 일치, 문서 출처 포함.
- 승인·에이전트 뼈대 테스트: 5개 통과.
- Postgres 승인 대기 저장 → 프로그램/API 재시작 → 승인 후 리포트 및 `completed` 확인.
- API 거절 결과의 리포트 반영 확인.
- 승인 불필요 경로의 별도 테스트와 실제 평가 점수 측정은 후속 작업입니다.
