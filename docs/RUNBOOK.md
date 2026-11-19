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

### [5-2] Service selector 오타로 외부 접속이 503 (2026-11-18 · 출제: 🔍 박찬솔 · 진단: 📘 한재윤(Claude 보조) · 복구: 🔍 · 복구 확인 17:02:44)
- **환경:** k3s 기본 Traefik Ingress, 호스트 `soc.1.201.110.71.nip.io` → Service `api`:80 → API Pod:8000. 정상일 때 `/healthz`는 HTTP 200.
- **장애 투입:** 출제자가 Service `api`의 selector를 `app: apii`로 바꿨다. Pod와 Ingress는 건드리지 않았다. 투입 시각은 기록하지 않았고(진단 첫 확인 16:58에는 이미 장애 중), 복구까지 걸린 시간은 측정하지 못했다.
- **증상:** 외부 `/healthz`가 **`503 Service Unavailable`**, 본문 `no available server`. API 파드는 계속 `1/1 Running`이라 파드만 보면 정상처럼 보인다.
- **확인 명령과 출력 (바깥 → 안쪽 순서):**
  ```text
  $ curl -i http://soc.1.201.110.71.nip.io/healthz
  HTTP/1.1 503 Service Unavailable
  no available server

  $ kubectl -n soc get pods -l app=api --show-labels
  api-5f4bd587d9-86j2m   1/1   Running   0   72m   app=api,pod-template-hash=5f4bd587d9

  $ kubectl -n soc exec deploy/api -- python -c "...urlopen('http://localhost:8000/healthz')..."
  b'{"status":"ok","backend":"real"}'              <- 파드 안의 API는 정상

  $ kubectl -n soc describe ingress api
  Host: soc.1.201.110.71.nip.io   Path: /   Backends: api:80 ()      <- 규칙은 맞지만 뒤의 ()가 비어 있음

  $ kubectl -n soc get svc api -o jsonpath='{.spec.selector}'
  {"app":"apii"}                                   <- 오타

  $ kubectl -n soc get endpointslices -l kubernetes.io/service-name=api
  api-c22fw   IPv4   <unset>   <unset>              <- 연결된 파드 0개
  ```
- **원인:** Service의 selector(`app: apii`)와 파드 label(`app: api`)이 달라 Service가 연결할 파드를 하나도 찾지 못했다(EndpointSlice 비어 있음). 그래서 Traefik이 보낼 곳이 없어 `no available server`를 돌려줬다. 파드·API 프로세스·Ingress 규칙은 모두 정상이었다.
- **안내 문서와 실제의 차이:** 안내 표에는 "이름표 오타, 준비된 파드 없음 → 502"로 되어 있지만 실제 응답은 **503**이었다. 연결 대상 자체가 없으면 503, 대상은 있는데 응답을 못 받으면 502로 구분해 읽는다.
- **조치:** 올바른 selector가 적힌 매니페스트를 다시 적용한다.
  ```bash
  kubectl apply -f infra/k8s/11-api.yaml
  kubectl -n soc get endpointslices -l kubernetes.io/service-name=api   # ENDPOINTS에 파드 IP가 보여야 함
  curl -i http://soc.1.201.110.71.nip.io/healthz                        # 200
  ```
- **복구 확인 (17:02:44):** 외부 `/healthz` 200, `/readyz` 200, selector `{"app":"api"}`, EndpointSlice `10.42.0.20:8000`. API 파드는 재시작 0회로 그대로였다(파드는 건드리지 않았다).
- **진단 후 나눔** (깨 보기 규칙 5~6번)
  - 진단자: 가장 오래 걸린 지점과 이유: (나눈 뒤 작성)
  - 출제자: 나라면 어디부터 봤을지: (나눈 뒤 작성)
  - 다음에 같은 증상을 보면 처음 칠 명령: (나눈 뒤 작성. 후보: `kubectl -n soc get endpointslices` — 한 번에 "Service에 연결된 파드가 있는가"가 보임)
- **재발 방지:** 한 줄씩 짚는 순서는 외부 응답 코드 → 파드 상태·label → Service selector → EndpointSlice. 이름표(label)는 손으로 치지 않고 매니페스트에서 복사해 쓰고, Service를 바꾼 뒤에는 `get endpointslices`로 파드가 연결됐는지 확인한다.
- **미확인:** 외부에서 승인 API(`POST /approvals/{alert_id}`) 호출은 이 기록 시점에 직접 확인하지 못했다(`/healthz`·`/readyz`·`GET /alerts/{id}` 조회까지만 확인).
- **고장 예상표와 비교:** (나눈 뒤 02 문서 9-2와 대조해 작성)

### [6-1] Job의 OPENSEARCH_URL 오타로 setup Job이 실패 (2026-11-19 · 출제: 🔍 박찬솔 · 진단: 📘 한재윤(Claude 보조) · 복구: 📘)
- **환경:** k3s `soc` 네임스페이스. 정상일 때 `setup` Job은 `soc.setup`을 실행해 OpenSearch 인덱스를 준비하고 `Complete 1/1`(약 7초)로 끝난다. 설정은 ConfigMap `app-config`의 `OPENSEARCH_URL=http://opensearch:9200`.
- **장애 투입:** 출제자가 실습용 Job `setup-break61`을 따로 만들고, 본 컨테이너의 `env`에 `OPENSEARCH_URL=http://opensearch-typo:9200`을 직접 넣었다. 기존 `setup` Job과 ConfigMap은 건드리지 않았다. 투입 시각은 기록하지 않았고, 복구까지 걸린 시간은 측정하지 못했다.
- **증상:** `setup-break61`이 `Running 0/1`인 채로 시도할 때마다 새 파드가 `Error`로 끝난다(`backoffLimit: 3`이라 시도가 끝나면 `BackoffLimitExceeded`). 파드는 `restartPolicy: Never`라 시도별로 따로 남는다.
- **확인 명령과 출력 (바깥 → 안쪽 순서):**
  ```text
  $ kubectl -n soc get jobs,pods
  job.batch/setup          Complete   1/1           7s
  job.batch/setup-break61  Running    0/1           56s
  pod/setup-break61-bkgmd  0/1   Error   0   56s
  pod/setup-break61-s7drk  0/1   Error   0   44s
  pod/setup-break61-gpdrz  0/1   Error   0   23s          <- 시도마다 새 파드, 모두 Error

  $ kubectl -n soc logs pod/setup-break61-bkgmd -c setup      (세 파드 모두 같은 마지막 줄)
  opensearchpy.exceptions.ConnectionError: ConnectionError(HTTPConnection(host='opensearch-typo', port=9200):
    Failed to resolve 'opensearch-typo' ([Errno -2] Name or service not known))   <- 이름 해석 실패

  $ kubectl -n soc describe job setup-break61
  Environment:  OPENSEARCH_URL:  http://opensearch-typo:9200                      <- 본 컨테이너 env에 직접 박힘

  $ kubectl -n soc get cm app-config -o jsonpath='{.data.OPENSEARCH_URL}'
  http://opensearch:9200                                                         <- 공유 설정은 정상
  $ kubectl -n soc get svc opensearch
  opensearch   ClusterIP   10.43.15.152   <none>   9200/TCP                       <- Service도 정상
  ```
- **원인:** Job 컨테이너의 `env`가 `OPENSEARCH_URL`을 `opensearch-typo`로 덮어썼다. `env`는 `envFrom`(ConfigMap)보다 우선하므로 ConfigMap이 정상이어도 소용이 없다. `opensearch-typo`라는 Service는 없어서 앱이 연결을 시도하기도 전에 DNS 해석에서 실패했다. OpenSearch, Service, ConfigMap은 모두 정상이었다.
- **왜 `DeadlineExceeded`가 아니라 `BackoffLimitExceeded`인가:** 대기용 initContainer(`wait-opensearch`)는 `envFrom`으로 ConfigMap 값만 읽기 때문에 정상 주소로 통과한다. 그다음 본 컨테이너만 오타 주소로 실패하므로 파드가 즉시 `Error`로 끝나고 재시도 횟수(`backoffLimit`)가 먼저 소진된다. 오타를 ConfigMap에 넣었다면 initContainer가 계속 기다리다가 `activeDeadlineSeconds`(300초)까지 가서 `DeadlineExceeded`가 되었을 것이다.
- **조치:** Job의 spec은 만든 뒤 바꿀 수 없으므로(`field is immutable`) 수정하지 않고 지운다. 실습용 Job이라 지워도 정상 Job과 데이터에 영향이 없다.
  ```bash
  kubectl -n soc delete job setup-break61      # 시도별 파드 3개도 함께 삭제됨
  kubectl -n soc get jobs,pods                 # setup, kb-ingest만 Complete로 남아야 함
  ```
- **복구 확인:** `setup`(1/1)과 `kb-ingest`(1/1)가 `Complete`로 남았고, API·생성기·워커·OpenSearch·Postgres 파드는 재시작 0회로 `Running`이었다. `kb-playbooks`는 20건 그대로, 알림·보고서 인덱스는 생성기가 계속 쓰고 있어 건수가 늘고 있었다.
- **이해할 점:** Job 실패는 Job이 아니라 **Job이 만든 파드의 로그**에서 원인이 보인다. `Error`가 여러 개 보이면 시도마다 파드가 새로 생긴 것이고, 로그는 파드별로 따로 남는다. 설정 오류인지 일시 오류인지는 모든 시도가 같은 이유로 실패하는지로 갈린다(여기서는 세 번 모두 같은 DNS 오류 → 재시도로 해결되지 않는 설정 오류).
- **진단 후 나눔** (깨 보기 규칙 5~6번)
  - 진단자: 가장 오래 걸린 지점과 이유: (나눔 완료 2026-11-19. 세부 답은 이 기록에 적지 않았다)
  - 출제자: 나라면 어디부터 봤을지: (나눔 완료 2026-11-19. 세부 답은 이 기록에 적지 않았다)
  - 다음에 같은 증상을 보면 처음 칠 명령: (나눔 완료 2026-11-19. 정한 명령은 이 기록에 적지 않았다. 후보: `kubectl -n soc logs job/<이름>` 또는 파드별 `logs` — 한 번에 실패 이유가 보임)
- **재발 방지:** 한 줄씩 짚는 순서는 Job 상태 → 시도별 파드 → 파드 로그의 마지막 오류 → Job의 `env`와 ConfigMap 값 대조 → 매니페스트. 주소는 손으로 치지 않고 ConfigMap 값을 쓰며, Job에 `env`로 같은 이름을 다시 정의하지 않는다. Job을 만든 뒤에는 `describe job`의 Environment 줄을 ConfigMap과 비교한다.
- **진단 방식에 대한 기록:** 이 기록의 관찰과 원인 정리는 진단자가 직접 찾지 않고 Claude가 읽기 전용 명령으로 수행한 결과를 바탕으로 한다. 따라서 "가장 오래 걸린 지점"은 실제 경험이 아니므로 나눔에서 별도로 확인한다.
- **고장 예상표와 비교:** (나눔 완료 2026-11-19. 대조 결과는 이 기록에 적지 않았다)

### [7-1] 새 API 파드 즉시 종료와 RollingUpdate 롤백 (D3-2 · 2026-11-19 · 출제: 📘 팀원 · 진단·복구: 🔍 박찬솔)
- **정상 배포 확인:** 커밋 `f64e4bc`의 GitHub Actions에서 test(32초), build(43초)가 성공했다. 로컬 전체 테스트는 25 passed였다. GHCR에 게시한 `ghcr.io/cccr-teamproj-02/edr-ai-triage-lab:f64e4bc`를 API에 적용했고, rollout 성공과 외부 `/healthz` 200(`backend: real`), `/readyz` 200(`ready`, `opensearch`, `postgres` 모두 true)을 확인했다.
- **배포 전 이미지:** `ghcr.io/hanjyoon01/edr-ai-triage-api:0.1.0`. 이번 장애 직전 정상 버전은 새 이미지 `f64e4bc`이며, 최초 이미지로 되돌리는 실험은 아니다. API에는 이미지 다운로드 인증용 `ghcr-pull`이 설정되어 있었다.
- **장애 재현 방식:** 팀원이 Deployment의 API 실행 명령을 `sh -c 'exit 1'`로 변경했다. 정상 이미지의 실행 명령을 덮어써 즉시 실패를 재현한 것으로, 이미지 자체에 결함을 넣은 실험은 아니다. describe에서 확인한 새 파드 시작 시각은 11:57:40 KST이며, 정확한 장애 투입·복구 소요 시간은 측정하지 않았다.
- **증상과 증거:**
  ```text
  Deployment api: READY 1/1, UP-TO-DATE 1, AVAILABLE 1
  api-66d6959bb4-7ghc9  0/1  CrashLoopBackOff  재시작 4회(이후 describe에서 5회)
  api-8576ff859f-dzjw5  1/1  Running           재시작 0회
  ```
  `UP-TO-DATE 1`은 새 설정의 파드가 생성됐다는 의미이며 준비 완료를 뜻하지 않는다. 기존 정상 파드가 남아 있는 동안 외부 `/healthz`는 200이었다.
- **진단 명령:**
  ```bash
  sudo kubectl -n soc get deployment api
  sudo kubectl -n soc get pods -l app=api -o wide
  sudo kubectl -n soc logs api-66d6959bb4-7ghc9 --previous --tail=50
  sudo kubectl -n soc describe pod api-66d6959bb4-7ghc9
  curl -i --max-time 10 http://soc.1.201.110.71.nip.io/healthz
  ```
  위 파드 이름은 이번 실험의 관측값이다. 재실습할 때는 get pods에서 현재 이름을 확인한다.
- **원인:** 이전 컨테이너 로그는 비어 있었다. describe에서 `Command: sh / -c / exit 1`, `Last State: Terminated`, `Reason: Error`, `Exit Code: 1`을 확인했다. 시작·종료 시각이 12:00:23 KST로 같았다. `exit 1`은 출력 없이 즉시 실패하므로 로그가 없었고, API가 뜨지 않아 readiness의 8000번 포트 연결도 `connection refused`로 실패했다. 이미지 접근은 성공했으므로 이미지 다운로드 실패가 아니다.
- **복구 절차:** 배포 이력을 확인하고 장애 직전 설정으로 롤백한다. 다른 배포가 사이에 들어갔다면 이력에서 정상 revision을 확인한 뒤 지정해야 한다. 이번 기록에는 revision 번호를 별도로 확보하지 않았다.
  ```bash
  sudo kubectl -n soc rollout history deployment/api
  sudo kubectl -n soc rollout undo deployment/api
  sudo kubectl -n soc rollout status deployment/api --timeout=180s
  sudo kubectl -n soc get pods -l app=api
  curl -i --max-time 10 http://soc.1.201.110.71.nip.io/readyz
  ```
- **복구 결과:** 사용자가 롤백 성공, API 파드 `1/1 Running`, 외부 `/readyz` 200을 확인했다. rollout undo는 이미지 주소만이 아니라 실행 명령을 포함한 이전 파드 템플릿으로 복원하는 조치다.
- **고장 예상표와 비교:** 새 파드가 정상 준비 상태가 되지 못해 교체가 완료되지 않는 동안 기존 파드가 서비스를 유지한다는 기대를 확인했다. 외부 응답 200만으로 새 배포 성공을 판단할 수 없으며, 새 파드 상태와 rollout 상태를 함께 봐야 한다.
- **재발 방지·확인 범위:** 로그가 비어 있으면 describe의 Command, Last State, Exit Code, Events를 확인한다. 배포 전 정상 이미지·revision을 기록하고 배포 후 rollout과 외부 health/ready 응답을 확인한다. kubectl로 바꾼 설정은 Git의 YAML에 자동 반영되지 않으므로 배포 매니페스트와 실제 설정을 별도로 맞춘다. 이번 확인은 API 배포·롤백 범위이며 Dify 실제 연결·검색 성공까지 의미하지 않는다.
- **진단 후 나눔:** 팀원이 장애를 넣고 기록 담당이 상태·로그·종료 코드를 확인해 롤백했다. 나눔은 2026-11-19에 했다. 가장 오래 걸린 지점과 설명한 내용은 이 기록에 적지 않았다.

### [D3-7-1] OpenSearch Service selector 오타로 외부가 모두 503 (D3-7 · 2026-11-19 · 출제: 📘 한재윤(Claude 보조) · 진단·복구: 🔍 박찬솔)
- **환경:** k3s `soc` 네임스페이스. 정상일 때 Service `opensearch`(ClusterIP 10.43.15.152, 9200)는 selector `app: opensearch`로 파드 `opensearch-0`(10.42.0.15)에 연결되고, 외부 `/healthz`·`/readyz`는 200이다. 종합 드릴이라 진단자에게는 몇 단계 문제인지 알리지 않았다.
- **장애 투입:** 출제자가 Service `opensearch`의 selector를 `app: opensearh`(오타)로 바꿨다(`kubectl patch`). StatefulSet 파드, PVC, 데이터, Secret, ConfigMap은 건드리지 않았다. 정상 설정(Service YAML, EndpointSlice, 파드 목록, `/readyz` 응답)은 투입 전에 기록해 출제자 PC에 보관했다(서버에 두면 단서가 되므로 서버에는 두지 않았다). 투입은 14:17~14:19 KST경이고, 진단 시작·종료 시각과 복구까지 걸린 시간은 측정하지 못했다.
- **한 번 더 만진 이유:** selector만 바꾸면 증상이 바로 나타나지 않았다. 이미 열려 있던 연결은 Service 변경 뒤에도 계속 동작해서 외부 `/healthz`·`/readyz`가 200이고 `worker`·`generator` 로그도 정상이었다(EndpointSlice는 이미 비어 있었다). 그래서 `api` 파드를 삭제하고 `worker`·`generator`를 rollout restart해 새 연결이 만들어지게 했다. 이 추가 조작이 진단자가 보는 파드 이력(재시작 횟수, 파드 이름)에 섞여 있다.
- **증상 (진단자에게 알려 준 것):** 외부 `/healthz`, `/readyz`, `/alerts`가 모두 **503 `no available server`**, 알림 처리가 진행되지 않음.
- **출제자가 확인한 증거 (바깥 → 안쪽):**
  ```text
  $ curl http://soc.1.201.110.71.nip.io/healthz          -> 503 no available server    (readyz, alerts도 같음)

  $ kubectl -n soc get pods
  api-b78459cf4-ws6gx         0/1  Running  1 (16s ago)   <- 파드는 Running인데 Ready가 아니고 재시작함
  worker-79b874fc48-c78mc     0/1  Running  0             <- 새 워커도 Ready 아님
  generator-d5c6884b7-m2ncr   1/1  Running  0
  opensearch-0                1/1  Running  0             <- OpenSearch 자체는 정상
  postgres-0                  1/1  Running  0

  $ kubectl -n soc logs deploy/generator --tail=3
  urllib3.exceptions.ConnectTimeoutError: ... host='opensearch', port=9200 ... Connection to opensearch timed out. (connect timeout=30)

  $ kubectl -n soc get endpointslices -l kubernetes.io/service-name=opensearch
  opensearch-5kh9c   IPv4   <unset>   <unset>              <- 연결된 파드 0개
  $ kubectl -n soc get svc opensearch -o jsonpath='{.spec.selector}'
  {"app":"opensearh"}                                      <- 오타
  ```
- **원인:** Service `opensearch`의 selector(`app: opensearh`)가 파드 label(`app: opensearch`)과 달라 연결 대상이 0개가 됐다(EndpointSlice 비어 있음). `api`는 시작할 때 OpenSearch에 연결하려다 `opensearch:9200`에서 타임아웃이 나 readiness(`/readyz`)가 통과하지 못했고, 연결을 기다리는 동안 liveness도 실패해 재시작을 반복했다. Ready인 `api` 파드가 없어 Ingress(Traefik)가 `no available server`를 돌려줬다. OpenSearch 파드, 데이터, Ingress, `api` 코드는 모두 정상이었다.
- **5-2와의 차이:** 5-2는 `api` Service의 selector 오타라 `api` 파드는 정상 기동했다. 이번에는 **API 앞이 아니라 API가 의존하는 Service**(`opensearch`)가 깨져서, 외부 503의 원인이 두 단계 안쪽(`api` 파드의 시작 실패)에 있고 그 원인은 한 단계 더 안쪽(OpenSearch Service)에 있다.
- **진단자의 결론 (전달받은 내용):** "Service selector 오타로 연결 대상이 없어졌습니다. API가 OpenSearch에 연결하지 못해 시작을 완료하지 못했습니다. selector만 정상 값으로 복구하겠습니다." 어느 Service인지 이름은 말하지 않았다.
- **조치:** selector만 정상 값으로 되돌린다. 파드와 데이터는 지우지 않는다.
  ```bash
  kubectl -n soc patch svc opensearch -p '{"spec":{"selector":{"app":"opensearch"}}}'
  kubectl -n soc get endpointslices -l kubernetes.io/service-name=opensearch   # ENDPOINTS에 10.42.0.15:9200이 보여야 함
  kubectl -n soc get pods                                                        # api, worker, generator가 1/1 Running
  curl -i http://soc.1.201.110.71.nip.io/readyz                                  # 200, opensearch·postgres true
  ```
- **복구 확인 (출제자가 읽기 전용으로 확인):** selector `{"app":"opensearch"}`, EndpointSlice `10.42.0.15:9200`, `api`·`generator`·`worker`·`opensearch-0`·`postgres-0` 모두 `1/1 Running`, 외부 `/healthz` 200, `/readyz` 200(`opensearch`·`postgres` true). `/stats`는 `new 0`, `completed 126`, `pending_approval 880`, `failed 1`(드릴 이전부터 있던 1건). 복구 시각은 기록하지 않았다.
- **장애 뒤에 남은 것:** 재시작 횟수가 `api` 6회, `generator` 3회, `worker` 3회로 늘었다(OpenSearch 연결을 기다리다 liveness가 실패해 반복 재시작). 정상 기준은 `generator` 1회(드릴 이전), 나머지 0회였다. 장애 동안 `generator`가 OpenSearch에 쓰지 못해 그 구간의 이벤트는 비어 있다. 데이터를 삭제하지는 않았다.
- **이해할 점:** 파드가 모두 `Running`이어도 `READY 0/1`이면 서비스를 받지 못한다. 외부가 503이면 바깥에서 안쪽으로 Ingress → Service/EndpointSlice → 파드 Ready → 파드 로그 → 의존하는 Service 순으로 내려간다. `api`의 EndpointSlice가 비어 있는 이유가 selector 오타가 아니라 파드가 Ready가 아니어서일 수 있다는 점이 5-2와 갈리는 지점이다. 또 Service를 고쳐도 이미 열린 연결은 바로 바뀌지 않으므로 증상이 늦게 나타나거나 늦게 사라질 수 있다.
- **진단 후 나눔** (깨 보기 규칙 5~6번)
  - 진단자: 가장 오래 걸린 지점과 이유: (나눈 뒤 작성)
  - 출제자: 나라면 어디부터 봤을지: (나눈 뒤 작성)
  - 다음에 같은 증상을 보면 처음 칠 명령: (나눈 뒤 작성. 후보: `kubectl -n soc get endpointslices` — 외부가 503일 때 `api`와 `opensearch` 두 Service에 연결된 파드가 있는지 한 번에 보임)
- **재발 방지:** Service 이름표(label)는 손으로 치지 않고 매니페스트에서 복사해 쓴다. Service를 바꾼 뒤에는 `get endpointslices`로 파드가 연결됐는지, `get pods`에서 READY가 `1/1`인지 확인한다. 의존하는 Service가 깨지면 `api`가 시작하지 못한다는 점을 기억하고, 외부 503이면 `api`뿐 아니라 `opensearch`, `postgres` Service의 EndpointSlice도 함께 본다.
- **미확인:** 진단자가 실제로 걸었던 경로와 가장 오래 걸린 지점은 이 기록에 없다(진단 과정을 출제자가 지켜보지 못했다). `api` 파드를 삭제하고 워커·생성기를 재시작한 조작이 진단 난이도에 준 영향도 확인하지 못했다.
- **고장 예상표와 비교:** (나눈 뒤 02 문서 9-2와 대조해 작성)
