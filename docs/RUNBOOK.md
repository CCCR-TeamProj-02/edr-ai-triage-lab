# 런북: 우리가 겪은 장애와 찾는 법

> 02 문서 8장의 **'좋은 런북'** 형식으로 씁니다. 새벽 당번이 이것만 보고 해결할 수 있게, **실제로 친 명령과 실제 출력**을 남깁니다.

## 공통 1차 확인
```bash
kubectl -n soc get pods,svc,ingress,pvc,jobs
kubectl -n soc get events --sort-by=.lastTimestamp | tail -20
```

## 장애 기록

### [1-1] 이미지 태그 오타  (출제: 📘 · 진단: 📘 · 복구까지 걸린 시간: 약 4분, 장애 투입 14:48경 → 복구 14:52)
- **증상:** 이미지를 바꾸고 나니 새 Pod가 `0/1 ErrImagePull`, 잠시 뒤 `ImagePullBackOff`. 이전 Pod는 `1/1 Running`으로 남아 있어 API는 계속 응답함 (롤링 업데이트가 새 Pod가 준비될 때까지 이전 Pod를 지우지 않기 때문).
- **확인 명령과 출력:**
  ```
  $ kubectl -n soc get pods
  api-8b8857667-592nz   0/1   ErrImagePull   0   10s     <- 새 Pod
  api-f68657946-dqxks   1/1   Running        0   10m     <- 이전 Pod

  $ kubectl -n soc get events --sort-by=.lastTimestamp
  Warning  Failed  pod/api-8b8857667-592nz  Failed to pull image "ghcr.io/hanjyoon01/edr-ai-triage-api:0.1.O":
           rpc error: code = NotFound ... failed to resolve reference ".../edr-ai-triage-api:0.1.O": ... not found
  ```
  `describe pod`의 `Image:`가 `...:0.1.O`(알파벳 O)였고, 정상 Pod는 `...:0.1.0`(숫자 0).
- **원인:** 이미지 태그의 `0`이 알파벳 `O`로 바뀌어 레지스트리에 없는 태그를 요청함. 오류 문구가 `not found`이므로 인증 문제(`unauthorized`, 깨 보기 1-2)와 구분됨.
- **조치:** 올바른 태그가 적힌 매니페스트를 다시 적용.
  ```
  kubectl apply -f infra/k8s/11-api.yaml
  kubectl -n soc rollout status deploy/api
  ```
  잘못된 새 Pod는 `Terminating`으로 정리되고 이전 Pod가 그대로 유지됨.
- **진단 후 나눔** (깨 보기 규칙 5~6번)
  - 진단자: 가장 오래 걸린 지점과 이유: (찬솔님과 나눈 뒤 작성)
  - 출제자: 나라면 어디부터 봤을지: (찬솔님과 나눈 뒤 작성)
  - 다음에 같은 증상을 보면 처음 칠 명령: (찬솔님과 정한 뒤 작성. 후보: `kubectl -n soc get events --sort-by=.lastTimestamp`)
- **재발 방지:** 이미지를 `kubectl set image`로 손으로 바꾸지 말고 매니페스트(`11-api.yaml`)를 고쳐 `apply`한다. 태그를 복사해 붙여 넣고 직접 치지 않는다. 배포 뒤 `rollout status`로 새 Pod가 준비됐는지 확인한다.
- **고장 예상표와 비교:** (찬솔님과 나눈 뒤 02 문서 9-2와 대조해 작성)


### [2-1] vm.max_map_count 부족 경고 (2026-11-18 · 실행·진단: 🔍 기록 담당)

- **환경:** 팀 서버 Ubuntu 24.04, k3s, OpenSearch 2.17.1. StatefulSet 1개, `discovery.type=single-node`, 힙 2Gi / 메모리 limit 4Gi. `local-path` PVC 10Gi 사용.
- **사전 정상 확인:** `opensearch-0`이 `1/1 Running`, StatefulSet이 `1/1`, PVC `data-opensearch-0`이 `Bound`인 것을 확인했다. 테스트 인덱스 `d2-storage-check`에 기록 1건을 넣고 파드를 삭제·재생성한 뒤에도 `count: 1`이 유지됐다.
- **기대와 실제:** 지침에서는 낮은 `vm.max_map_count`로 시작 실패 및 `CrashLoopBackOff`를 예상했다. 실제로는 부족 경고만 발생하고 파드는 `1/1 Running`, 재시작 0회로 실행을 유지했다. **경고 재현 / 시작 실패 미재현**으로 기록한다.
- **장애 투입 명령:** 서버의 현재 커널 설정만 변경했으며 영구 설정 파일은 수정하지 않았다.
  ```bash
  sudo sysctl -w vm.max_map_count=65530
  sudo kubectl -n soc delete pod opensearch-0
  ```
  첫 명령 출력: `vm.max_map_count = 65530`
- **확인 명령과 실제 출력 발췌:**
  ```text
  $ sudo kubectl -n soc get pod opensearch-0
  NAME           READY   STATUS    RESTARTS   AGE
  opensearch-0   1/1     Running   0          49s

  $ sudo kubectl -n soc logs opensearch-0 --tail=100
  [2026-11-18T06:29:58,999][WARN ][o.o.b.BootstrapChecks] ... max virtual memory areas vm.max_map_count [65530] is too low, increase to at least [262144]
  [2026-11-18T06:29:59,144][INFO ][o.o.n.Node] ... started

  $ sudo kubectl -n soc logs opensearch-0 --previous --tail=60
  Error from server (BadRequest): previous terminated container "opensearch" in pod "opensearch-0" not found
  ```
  `--previous` 오류는 이 파드에 종료된 이전 컨테이너가 없다는 뜻이다. 파드 삭제 전의 로그를 조회하는 명령은 아니다. 위 로그 시각은 원문 그대로이며, 로컬 시각으로 변환하지 않았다.
- **CrashLoopBackOff 미재현 사유:** 서버 값을 65530으로 낮춰 부족 경고는 발생했으나, 현재 `discovery.type=single-node` 구성에서는 해당 시작 검사(bootstrap check)가 강제 실패가 아닌 경고로 처리됐다. 로그의 `WARN` 다음에 `started`가 나오고 파드가 `1/1 Running`, 재시작 0회인 점이 이를 뒷받침한다. 컨테이너가 종료되지 않아 반복 재시작과 재시도 대기 상태인 `CrashLoopBackOff`로 이어지지 않았다. 모든 시작 검사가 생략되거나 낮은 값이 적절하다는 뜻은 아니므로 정상값 262144로 복구했다.
- **설명 근거:** [OpenSearch 공식 Docker 문서](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/)의 `single-node`와 bootstrap checks 설명을 실제 설정·로그와 함께 확인했다. 처음 안내에서 시작 실패를 예상한 것은 단일 노드 설정의 영향을 고려하지 못한 것이었다.
- **팀 공유 자료:** [D2-12 OpenSearch 명령어 핵심 정리 PDF](teachback/D2-12_OpenSearch_명령어_핵심정리.pdf).
- **복구 명령:**
  ```bash
  sudo sysctl -w vm.max_map_count=262144
  sysctl vm.max_map_count
  sudo kubectl -n soc exec opensearch-0 -- curl -sS 'http://localhost:9200/d2-storage-check/_count'
  ```
- **복구 확인:** 실행자가 `vm.max_map_count = 262144`와 `count: 1`을 확인했다. PVC는 삭제하지 않았다. 복구까지 걸린 시간은 측정하지 않았다.
- **재발 방지:** 배포 전 서버의 `vm.max_map_count`를 확인한다. 파드의 `Running` 표시만으로 설정이 적절하다고 판단하지 않고 readiness와 시작 로그도 함께 확인한다. 실습 후 변경한 서버 설정을 반드시 복구한다.
- **진단 후 나눔:** 팀원과 공유 예정. 공유할 핵심은 “경고가 발생해도 실행될 수 있으므로 예상 결과와 실제 관찰을 구분한다”이다. 가장 오래 걸린 지점과 상대방의 진단 순서는 실제 대화 후 추가한다.
- **고장 예상표와 비교:** 예상은 시작 실패, 실제는 부족 경고 후 정상 기동이었다. CrashLoopBackOff를 재현했다고 표시하지 않는다. 시작 실패까지 재현해야 하는지는 강사와 확인한다.

### [3-2] Secret의 비밀번호만 바꿨더니 API가 DB에 못 붙음 (2026-11-18 · 출제·진단: 📘 한재윤(Claude 보조) · 복구까지 걸린 시간: 약 50초, 15:45:12 투입 → 15:45:59 복구 확인)
- **증상:** `kubectl rollout restart` 뒤 새 API 파드가 `0/1 Running`에서 `Ready`가 되지 않음. 이전 파드는 `1/1`로 남아 있어 서비스는 끊기지 않았고, 새 파드는 얼마 뒤 liveness 실패로 재시작(`RESTARTS 1`)됨. 파드 이벤트에는 `Readiness/Liveness probe failed: ... connection refused`만 보임 (원인이 아니라 결과).
- **확인 명령과 출력:**
  ```
  $ kubectl -n soc get events --sort-by=.lastTimestamp | tail
  Warning  Unhealthy  pod/api-547975bbf7-l7kz9  Readiness probe failed: Get ".../readyz": dial tcp ...:8000: connect: connection refused

  $ kubectl -n soc logs api-547975bbf7-l7kz9 --tail=6
  psycopg.pool error connecting in 'pool-1': connection failed: connection to server at "10.43.111.166", port 5432 failed:
  FATAL:  password authentication failed for user "soc"

  $ kubectl -n soc logs postgres-0 --tail=4
  FATAL:  password authentication failed for user "soc"
  DETAIL:  Connection matched file ".../pg_hba.conf" line 128: "host all all all scram-sha-256"
  ```
  연결은 됐고(서버 주소와 5432 포트에 도달) **인증에서** 거절됨. 그래서 네트워크·Service·DSN 호스트 문제가 아님. `connection refused`(프로브)는 API가 시작 중 DB 연결에 막혀 8000 포트를 아직 열지 못해서 나온 결과.
- **원인:** 공식 `postgres` 이미지의 `POSTGRES_PASSWORD`는 **데이터 디렉터리가 비어 있는 첫 기동 때만** 쓰인다. 비밀번호는 PVC의 데이터 안에 저장돼 있어서, Secret만 바꿔도 DB의 비밀번호는 그대로다. API는 새 Secret(DSN)으로 접속하니 불일치.
- **조치:** 바꾸기 전 비밀번호로 Secret을 되돌리고 API를 다시 시작.
  ```
  OPENAI_API_KEY="" POSTGRES_PASSWORD=<원래 값> bash infra/scripts/secrets.sh
  kubectl -n soc rollout restart deploy/api
  kubectl -n soc rollout status deploy/api
  curl .../readyz   ->  {"ready":true,"opensearch":true,"postgres":true} [200]
  ```
  (비밀번호를 정말 바꿔야 한다면 Secret만이 아니라 DB 안에서도 `ALTER USER soc PASSWORD '...'`로 바꿔야 한다.)
- **진단 후 나눔** (깨 보기 규칙 5~6번)
  - 이번 기록은 출제와 진단을 같은 쪽(📘)이 했으므로 규칙 5~6번의 나눔으로 인정되지 않는다. 찬솔님과 다시 나눈 뒤 채운다.
  - 진단자: 가장 오래 걸린 지점과 이유: (나눈 뒤 작성)
  - 출제자: 나라면 어디부터 봤을지: (나눈 뒤 작성)
  - 다음에 같은 증상을 보면 처음 칠 명령: 후보 `kubectl -n soc logs <새 파드>` (이벤트는 `connection refused`만 알려 줘서 원인이 안 보임. 로그에 `password authentication failed`가 있음)
- **재발 방지:** `secrets.sh`는 Secret이 이미 있으면 기존 `POSTGRES_PASSWORD`를 재사용한다(새로 만들지 않음). 비밀번호를 바꾸는 절차는 Secret 변경 + DB 안의 `ALTER USER` + API 재시작을 한 묶음으로 한다. Secret을 바꾼 뒤에는 `rollout restart` 후 `rollout status`와 `/readyz`로 확인한다.
- **고장 예상표와 비교:** 02 문서 9-1에서 풀어 본 바로 그 장애(`password authentication failed`)와 같다. 예상한 단서는 로그의 인증 실패였고 실제로 그대로 나왔다. 다만 파드 이벤트가 `connection refused`만 보여 주기 때문에 이벤트를 1순위 단서로 보는 습관(1-1)이 여기서는 원인까지 가지 못했다. 로그를 봐야 했다.


### [4-3] 워커가 없어 미처리 알림이 쌓임 (2026-11-18 · 출제: 📘 팀원 · 진단·복구: 🔍 박찬솔)

- **환경:** 생성기·워커는 기존 앱 이미지 `0.1.0`과 ConfigMap·Secret을 재사용한다. 저장소는 실제 OpenSearch·Postgres이고, 조사·문서 도구는 mock, LLM은 가짜 모드다. 이 실험은 처리 흐름 검증이며 분석 품질 검증은 아니다.
- **사전 정상 상태:** 생성기와 워커 배포 성공. 워커 로그에서 `completed`와 `pending_approval` 처리를 확인했고, `status=new` 알림 개수는 0건이었다.
- **장애 투입:** 팀원이 워커를 0개로 축소했다고 전달했다. 생성기는 유지했다. 이후 진단자의 조회에서도 worker `0/0`과 워커 파드 부재를 확인했다. 아래는 해당 상태를 만드는 명령이다.
  ```bash
  sudo kubectl -n soc scale deployment/worker --replicas=0
  ```
- **증상과 진단 근거:** 남아 있는 파드는 모두 `1/1 Running`이지만 미처리 알림이 0건에서 3건으로 증가했다. 생성기는 계속 기록을 만들고 OpenSearch 저장 요청도 성공했다.
  ```text
  $ sudo kubectl -n soc get deployments,pods
  deployment.apps/api         1/1
  deployment.apps/generator   1/1
  deployment.apps/worker      0/0
  ```
  위 출력은 READY 항목 발췌다. 파드 목록에는 api·generator·opensearch·postgres만 있었고 워커 파드는 없었다.
- **미처리 알림 확인 명령:**
  ```bash
  sudo kubectl -n soc exec opensearch-0 -- curl -sS     'http://localhost:9200/edr-alerts/_count'     -H 'Content-Type: application/json'     -d '{"query":{"term":{"status":"new"}}}'
  ```
  실제 결과: 장애 전 `count: 0`, 워커 중지 후 `count: 3`.
- **생성기 확인:**
  ```bash
  sudo kubectl -n soc logs deployment/generator --tail=20
  ```
  실제 로그 발췌: `2026-11-18 07:28:54,162 generator 기록 12건, 새 알림 0건`. 같은 시각대 저장 요청은 `status:200`이었다. 이 로그의 0건은 해당 생성 주기에 새로 만든 알림 수이고, 누적 미처리 알림 3건과는 다른 값이다.
- **원인:** 생성·저장 단계는 정상이나 알림을 가져갈 워커가 0개라 처리 단계가 멈췄다. 원하는 복제 수 자체가 0이므로 쿠버네티스가 자동으로 워커를 1개로 늘려 주지 않는다.
- **복구 절차:**
  ```bash
  sudo kubectl -n soc scale deployment/worker --replicas=1
  sudo kubectl -n soc rollout status deployment/worker --timeout=180s
  ```
  이후 위 `_count` 조회를 다시 실행한다.
- **복구 확인:** 진단자가 워커 복구 후 `count: 0`을 확인했다. 미처리 알림 변화는 **0 → 3 → 0건**이다. `new`가 0이라는 것은 미처리 알림이 없다는 뜻이며, 모든 알림이 승인까지 완료됐다는 뜻은 아니다. 복구 소요 시간은 측정하지 않았다.
- **재발 방지·다음 확인 순서:** 파드 상태만 보지 말고 `get deployments,pods`로 필요한 워커가 존재하는지 먼저 확인한다. 이어서 미처리 알림 수와 생성기·워커 로그를 비교해 생성·저장·처리 중 어느 단계가 멈췄는지 찾는다.
- **진단 후 나눔:** 공유할 핵심은 “파드 오류가 없어도 처리할 워커가 없으면 알림이 쌓인다”이다. 팀원과의 나눔 완료 여부는 아직 확인하지 않았다. 가장 오래 걸린 지점과 출제자의 진단 순서는 실제 대화 후 추가한다.
- **고장 예상표와 비교:** 워커 중지 시 `new`가 쌓이고 복구 후 줄어든다는 예상과 실제 결과가 일치했다. 이번에는 아직 가져가지 않은 알림을 처리한 것이며, 처리 중 중단된 알림의 체크포인트 재개(4-5)를 검증한 것은 아니다.


### [4-5] 새 워커에서 체크포인트 재개 (2026-11-18 · 중단 상태 준비: 📘 팀원 · 파드 삭제·검증: 🔍 박찬솔)

- **목적:** 워커 파드가 교체된 뒤 다른 워커가 같은 알림의 저장된 단계부터 이어 처리하는지 확인한다.
- **실험 방식과 범위:** 가짜 LLM의 처리 시간이 약 0.1초라 실제 분석 도중 삭제 시점을 확보하기 어려웠다. 팀원이 알림 `al-brk45-aca686`의 중단 상태와 다음 단계 `guardrail`인 체크포인트를 미리 구성했다. 이후 기존 파드를 삭제하고 새 파드에서 재개를 확인한 **중단 시점 재현 방식**이다. 실제 처리 중 강제 중단, 종료 유예 120초의 동작, 중단 전 부수 효과의 중복 여부까지 검증한 것은 아니다. 중단 상태를 구성한 구체적인 명령은 팀원 확인 후 보완한다.
- **준비된 조건:** 팀원이 전달한 lease 만료 시각은 `2026-11-18 07:45:31 UTC`(한국 시각 16:45:31). 삭제하지 않아도 기존 워커가 만료 후 가져갈 수 있으므로, 먼저 기존 파드를 삭제해 재개 주체가 바뀌었는지 확인했다.
- **실행 명령:**
  ```bash
  sudo kubectl -n soc delete pod worker-585c4d4754-wn5sb
  sudo kubectl -n soc get pods -l app=worker
  date -u
  sudo kubectl -n soc logs worker-585c4d4754-rfp2n --since=20m | grep -E '워커 시작|al-brk45-aca686'
  ```
- **새 파드 확인:** 기존 `worker-585c4d4754-wn5sb` 삭제 후 `worker-585c4d4754-rfp2n`이 `1/1 Running`, 재시작 0회로 실행됐다. `07:40:07 UTC` 조회 시에는 아직 lease 만료 전이라 재개 로그가 없었다.
- **실제 로그 (UTC):**
  ```text
  2026-11-18 07:37:46,853 worker 워커 시작: worker-585c4d4754-rfp2n
  2026-11-18 07:45:32,908 worker 이어서 처리: al-brk45-aca686 (수첩에 저장된 단계: ('guardrail',))
  2026-11-18 07:45:32,943 worker al-brk45-aca686 [깨 보기 4-5] powershell.exe → 198.51.100.23 주기적 연결 (C2 비컨 의심, 간격≈30s) → pending_approval (0.0초)
  ```
  같은 시각 해당 알림의 보고서 저장 요청은 `status:201`, 알림 갱신 요청은 `status:200`이었다.
- **결과:** lease 만료 직후 새 워커가 **동일 alert_id**를 다시 가져와 Postgres 체크포인트의 `guardrail` 단계부터 실행했고, 보고서를 저장한 뒤 `pending_approval`로 전환했다. 승인 대기는 정상 흐름이며, 사람의 승인이나 실제 대응 조치 실행까지 끝난 것은 아니다.
- **이해할 점:** 파드가 다시 Running인 것만으로는 이어 처리를 입증할 수 없다. 기존·신규 파드 이름, 동일 알림 ID, `이어서 처리` 로그와 저장된 다음 단계, 최종 상태를 함께 확인해야 한다. 새 워커가 즉시 처리하지 않더라도 lease 만료 전인지 먼저 확인한다.
- **실험 후 상태:** 새 워커는 실행 중이며 실험 알림은 승인 대기 상태다. 이 절차에서는 lease를 강제로 만료시키지 않고 안내된 만료 시각까지 기다렸다.
- **진단 후 나눔:** 공유할 핵심은 “파드와 무관하게 저장된 체크포인트와 lease를 이용해 다른 워커가 이어 처리한다”이다. 팀원과의 나눔 완료 여부 및 가장 오래 걸린 지점은 실제 대화 후 추가한다.
- **고장 예상표와 비교:** 다른 워커가 저장된 단계부터 재개한다는 기대는 확인했다. 다만 중단 상태를 미리 구성한 재개 검증이므로, 실제 분석 도중 삭제로 중단 상태가 생성되는 과정까지 재현했다고 기록하지 않는다.
