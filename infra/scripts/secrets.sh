#!/usr/bin/env bash
# 인프라 3단계: 비밀값을 클러스터에만 만듭니다. 이 스크립트에는 비밀값이 들어 있지 않습니다.
#
#   KUBECONFIG=~/.kube/edr-team2.yaml ./secrets.sh      (노트북, Git Bash)
#   KUBECTL="sudo kubectl" ./secrets.sh                  (서버에서 직접)
#
# 값은 환경변수로 주거나, 없으면 물어봅니다 (입력은 화면에 보이지 않습니다).
#   OPENAI_API_KEY     없이 Enter를 누르면 빈 값 (FAKE_LLM=true인 동안은 쓰지 않음)
#   POSTGRES_PASSWORD  비우면 임의로 만듭니다
# 만든 Secret은 `kubectl -n soc get secret app-secrets -o yaml`로 보면 base64로 보입니다.
# base64는 암호화가 아니라 인코딩입니다. 누구나 되돌릴 수 있으니 이 출력을 공유하지 마세요.
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
NS=soc

OPENAI_API_KEY="${OPENAI_API_KEY-__ask__}"
if [[ "$OPENAI_API_KEY" == "__ask__" ]]; then
  read -r -s -p "OPENAI_API_KEY (없으면 Enter): " OPENAI_API_KEY || OPENAI_API_KEY=""; echo
fi

# Secret이 이미 있으면 그 비밀번호를 그대로 씁니다. Postgres는 처음 기동할 때의 비밀번호를 데이터에
# 저장하므로, 다시 실행하면서 비밀번호만 새로 만들면 DB와 어긋납니다 (깨 보기 3-2와 같은 장애).
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  existing="$($KUBECTL -n "$NS" get secret app-secrets -o jsonpath='{.data.POSTGRES_PASSWORD}' 2>/dev/null || true)"
  if [[ -n "$existing" ]]; then
    POSTGRES_PASSWORD="$(printf '%s' "$existing" | base64 -d)"
    echo "기존 Secret의 POSTGRES_PASSWORD를 그대로 씁니다"
  fi
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  read -r -s -p "POSTGRES_PASSWORD (비우면 임의 생성): " POSTGRES_PASSWORD || POSTGRES_PASSWORD=""; echo
  if [[ -z "$POSTGRES_PASSWORD" ]]; then
    POSTGRES_PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
    echo "임의 비밀번호를 만들었습니다 (화면에 출력하지 않습니다)"
  fi
fi

# 비밀번호에 @ : / 같은 문자가 있으면 DSN이 깨지므로 영숫자만 허용합니다
if [[ ! "$POSTGRES_PASSWORD" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "POSTGRES_PASSWORD는 영문자와 숫자만 쓰세요 (DSN에 그대로 들어가기 때문)" >&2
  exit 1
fi

# DSN의 호스트는 Service 이름 `postgres`입니다. localhost가 아닙니다.
POSTGRES_DSN="postgresql://soc:${POSTGRES_PASSWORD}@postgres:5432/soc"

# --dry-run | apply: 이미 있어도 오류 없이 갱신됩니다 (여러 번 실행해도 같은 상태)
$KUBECTL -n "$NS" create secret generic app-secrets \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=POSTGRES_DSN="${POSTGRES_DSN}" \
  --dry-run=client -o yaml | $KUBECTL apply -f -

echo "Secret app-secrets 준비됨. 키만 확인:"
$KUBECTL -n "$NS" get secret app-secrets -o jsonpath='{.data}' | grep -o '"[A-Z_]*"' | tr -d '"'
