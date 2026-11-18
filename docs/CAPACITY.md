# 용량 산정 (16GB 서버 기준)

> 2일차 인프라 2단계를 시작하기 전에 계산합니다. 2단계 운전자(🔍 기록 담당)가 주도하고, 📘 문서 담당이 검토합니다.

## 서버 실측

`ssh ubuntu@edr-team2`에서 확인한 값 (k3s 설치 전):

| 항목 | 값 |
|---|---|
| vCPU (`nproc`) | 4 |
| 메모리 (`free -h`) | 총 15Gi, 사용 514Mi, 사용 가능 15Gi |
| swap | 0B (없음) |

## 초기 자원 배분 계획

아래 값은 실제 사용량이 아닌 초기 계획값입니다. 모든 상시 서비스는 각각 1개, kb-ingest Job은 동시에 최대 1개 실행하는 기준입니다. 기존 API 배포 설정을 유지하며, 배포 후 사용량을 측정하여 조정합니다.

| 워크로드 | 종류 | CPU req | Mem req / limit | 힙 | 근거 |
|---|---|---|---|---|---|
| OS + k3s + Traefik | 시스템 예산 | 500m 예산 | 2Gi 예산 (req/limit 설정 아님) | - | 운영체제와 클러스터 운영용 여유. 설치 후 실측으로 보정 |
| opensearch | StatefulSet | 1000m | 2Gi / 4Gi | 2Gi | 로그·문서 검색 담당. 힙은 메모리 limit의 약 50%이며 limit 안에 포함 |
| postgres | StatefulSet | 250m | 512Mi / 1Gi | - | 승인 대기 상태와 체크포인트 저장 |
| api | Deployment | 100m | 256Mi / 768Mi | - | 기존 infra/k8s/11-api.yaml 설정 유지 |
| worker | Deployment | 500m | 512Mi / 1Gi | - | 알림 분석 실행. 초기 워커 1개 기준 |
| generator | Deployment | 100m | 128Mi / 256Mi | - | 실습용 로그 생성 |
| kb-ingest (일시적) | Job | 500m | 1Gi / 2Gi | - | fast 방식 PDF 파싱·임베딩 적재, 청킹 최대 길이 700자 기준. hi_res는 별도 측정 필요 |
| **합계 / 여유** | Job 포함 | **req 2450m, 시스템 예산 포함 2950m / 4코어 대비 1050m 여유** | **req 4.375Gi / limit 9Gi. 시스템 예산 2Gi 포함 11Gi, 총 15Gi 대비 약 4Gi 여유** | 2Gi (OpenSearch limit에 포함) | 서비스 복제 수를 늘리거나 Job을 동시에 여러 개 실행하면 다시 계산 |

## 적용 및 확인 기준

- CPU 1000m는 1코어입니다. CPU request 합계는 사용 상한이 아닙니다.
- request는 쿠버네티스가 배치할 때 사용하는 자원 기준이고, 메모리 limit은 컨테이너의 사용 상한입니다.
- 시스템 예산은 계산용이며 별도의 Pod request/limit 설정이 아닙니다. Traefik 등 시스템 Pod의 실제 설정과 사용량을 확인합니다.
- 실제 배치 가능 여부는 서버 총량뿐 아니라 노드의 Allocatable과 이미 배치된 Pod의 requests를 기준으로 확인합니다.
- OpenSearch에는 requests.cpu=1000m, requests.memory=2Gi, limits.memory=4Gi와 OPENSEARCH_JAVA_OPTS="-Xms2g -Xmx2g"를 적용합니다.
- 배포 후 `kubectl top nodes`, `kubectl top pods -A`, `kubectl describe node`로 사용량과 할당량을 확인합니다. 메트릭이 제공되지 않으면 metrics-server 상태부터 확인합니다.
- 현재 서버 실측은 k3s 설치 전 값이므로 설치 후 `free -h`와 위 명령의 결과를 추가 기록합니다. 아직 측정하지 않은 값을 실측값으로 적지 않습니다.
