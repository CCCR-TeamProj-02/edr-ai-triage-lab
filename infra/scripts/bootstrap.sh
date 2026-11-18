#!/usr/bin/env bash
# 서버 초기 설정 + k3s 설치 (인프라 1단계). 서버(Ubuntu 24.04)에서 sudo로 실행합니다.
#
#   sudo ./bootstrap.sh <내 공인 IP> <서버 공인 IP>
#   예) sudo ./bootstrap.sh 203.0.113.7 1.201.110.71
#
# 여러 번 실행해도 같은 상태가 되도록(멱등) 썼습니다. 처음 실행에서 중간에 멈췄다면 다시 실행하면 됩니다.
set -euo pipefail

ADMIN_IP="${1:?사용법: sudo $0 <내 공인 IP> <서버 공인 IP>}"
SERVER_IP="${2:?사용법: sudo $0 <내 공인 IP> <서버 공인 IP>}"

if [[ $EUID -ne 0 ]]; then
  echo "sudo로 실행하세요" >&2
  exit 1
fi

echo "== 1/4 방화벽 (ufw)"
# 순서가 중요합니다. 22번을 먼저 허용하고 나서 켜야, 켜는 순간 내 SSH 접속이 끊기지 않습니다.
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'ssh'
ufw allow 80/tcp comment 'http (Ingress)'
ufw allow 443/tcp comment 'https (Ingress)'
# 6443은 쿠버네티스 API, 곧 클러스터를 조종하는 문입니다. 전 세계에 열면 누구나 조종을 시도할 수 있으니
# 내 IP에서 오는 것만 허용합니다. IP가 바뀌면(집/강의장) 이 줄의 허용 규칙을 새 IP로 바꿔야 합니다.
ufw allow from "$ADMIN_IP" to any port 6443 proto tcp comment 'k8s api (admin only)'
# k3s 문서의 권장: 파드 대역(10.42.0.0/16)과 서비스 대역(10.43.0.0/16)의 내부 통신은 막으면 안 됩니다.
ufw allow from 10.42.0.0/16 to any comment 'k3s pods'
ufw allow from 10.43.0.0/16 to any comment 'k3s services'
ufw --force enable
ufw status verbose

echo "== 2/4 커널 설정: vm.max_map_count"
# OpenSearch가 요구하는 값(262144 이상). /etc/sysctl.d/ 에 적어 두면 재부팅 후에도 유지됩니다.
# sysctl -w 로만 바꾸면 재부팅하면 원래 값으로 돌아갑니다. (2단계 깨 보기 2-1의 원인)
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-opensearch.conf
sysctl --system >/dev/null
echo "현재 값: $(sysctl -n vm.max_map_count)"

echo "== 3/4 swap 끄기"
# 쿠버네티스(kubelet)는 swap이 켜져 있으면 기본적으로 시작을 거부합니다. 메모리 requests/limits 계산이
# swap 때문에 어긋나는 것을 막으려는 설계입니다. 재부팅 후에 다시 켜지지 않도록 /etc/fstab의 swap 줄도 주석 처리합니다.
swapoff -a
sed -i.bak '/\sswap\s/ s/^\([^#]\)/#\1/' /etc/fstab
echo "swap 항목: $(swapon --show | wc -l)줄 (0이면 꺼짐)"

echo "== 4/4 k3s 설치"
if command -v k3s >/dev/null 2>&1; then
  echo "k3s가 이미 설치돼 있어 건너뜁니다: $(k3s --version | head -1)"
else
  # --tls-san: API 서버 인증서에 서버의 공인 IP를 넣습니다. 안 넣으면 노트북에서 접속할 때
  # "x509: certificate is valid for ..., not 1.201.110.71" 인증서 오류가 납니다.
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --tls-san ${SERVER_IP}" sh -
fi

echo
echo "== 확인"
k3s kubectl get nodes
echo
echo "다음: 노트북에서 kubectl을 쓰려면 /etc/rancher/k3s/k3s.yaml 을 복사하고,"
echo "      그 안의 server: https://127.0.0.1:6443 을 https://${SERVER_IP}:6443 으로 바꿉니다."
