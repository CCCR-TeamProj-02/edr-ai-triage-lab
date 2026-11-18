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
