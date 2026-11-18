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
