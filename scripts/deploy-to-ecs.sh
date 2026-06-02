#!/usr/bin/env bash
# Build frontend, upload to ECS, build/push image, compose up, install nginx.
# Usage: ./scripts/deploy-to-ecs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGISTRY="crpi-02k3y8iudey5q0vb.cn-shanghai.personal.cr.aliyuncs.com"
IMAGE="${REGISTRY}/mirror_ns/ai-dashboard:latest"
SERVICE="ai-dashboard"
SSH_HOST="${ECS_SSH:-ecs-main}"
REMOTE_DIR="/srv/apps/${SERVICE}"
NGINX_PREFIX="${NGINX_LOCATION_PREFIX:-/tools/ai-dashboard}"
PUBLIC_URL="http://47.116.180.173${NGINX_PREFIX}/"
HOST_PORT="${HOST_PORT:-8011}"
CSV_HOST_DIR="${CSV_HOST_DIR:-/srv/data/ai-dashboard/csv}"
CSV_CONTAINER_PATH="${CSV_CONTAINER_PATH:-/data/csv}"

echo "==> Build frontend (base ${NGINX_PREFIX}/)"
(
  cd "${ROOT}/frontend"
  # Git Bash 会把 /tools/... 转成 C:/Program Files/Git/tools/...，必须禁用
  export MSYS_NO_PATHCONV=1
  export MSYS2_ARG_CONV_EXCL='*'
  export VITE_BASE="${NGINX_PREFIX}/"
  export VITE_API_BASE="${NGINX_PREFIX}"
  npm run build
)

LOCAL_KEY=""
if [[ -f "${ROOT}/backend/.env" ]]; then
  LOCAL_KEY="$(grep '^DEEPSEEK_API_KEY=' "${ROOT}/backend/.env" | head -1 || true)"
fi

echo "==> Package and upload"
TAR="/tmp/ai-dashboard-deploy.tgz"
tar -czf "${TAR}" \
  --exclude=node_modules \
  --exclude=frontend/node_modules \
  --exclude=.git \
  --exclude=backend/.env \
  -C "${ROOT}" .
scp "${TAR}" "${SSH_HOST}:/tmp/ai-dashboard-deploy.tgz"
scp "${ROOT}/deploy/nginx-ai-dashboard-locations.conf" "${SSH_HOST}:/tmp/ai-dashboard-locations.conf"

echo "==> Build, push, compose up, nginx on ECS"
ssh "${SSH_HOST}" bash -s <<REMOTE
set -euo pipefail
REG='${IMAGE}'
BUILD=/tmp/ai-dashboard-build
rm -rf "\${BUILD}" && mkdir -p "\${BUILD}"
tar xzf /tmp/ai-dashboard-deploy.tgz -C "\${BUILD}"
cd "\${BUILD}"
docker build -t "\${REG}" .
docker push "\${REG}"
sudo mkdir -p ${REMOTE_DIR}
sudo mkdir -p ${CSV_HOST_DIR}
sudo cp deploy/compose.yaml ${REMOTE_DIR}/compose.yaml

# 首次迁移：把旧容器/项目内 CSV 拷到宿主机数据目录（不覆盖已有文件）
if [ -z "\$(sudo find ${CSV_HOST_DIR} -maxdepth 1 -name '*.csv' -print -quit 2>/dev/null)" ]; then
  if sudo test -d ${REMOTE_DIR}/data; then
    sudo cp -an ${REMOTE_DIR}/data/*.csv ${CSV_HOST_DIR}/ 2>/dev/null || true
  fi
  OLD_CID=\$(sudo docker ps -aq -f name=^${SERVICE}\$ | head -1 || true)
  if [ -n "\${OLD_CID}" ]; then
    sudo docker cp "\${OLD_CID}:/app/backend/data/." ${CSV_HOST_DIR}/ 2>/dev/null || true
  fi
  if [ -d "\${BUILD}/backend/data" ]; then
    sudo cp -an "\${BUILD}/backend/data/"*.csv ${CSV_HOST_DIR}/ 2>/dev/null || true
  fi
fi
sudo chmod 755 ${CSV_HOST_DIR}

PRESERVE_KEY=""
if sudo test -f ${REMOTE_DIR}/.env.runtime; then
  PRESERVE_KEY=\$(sudo grep '^DEEPSEEK_API_KEY=' ${REMOTE_DIR}/.env.runtime | head -1 || true)
fi
sudo tee ${REMOTE_DIR}/.env.runtime > /dev/null <<EOF
SERVICE_NAME=ai-dashboard
IMAGE=\${REG}
HOST_PORT=${HOST_PORT}
CONTAINER_PORT=8000
CSV_DATA_PATH=${CSV_CONTAINER_PATH}
CSV_HOST_DIR=${CSV_HOST_DIR}
EOF
if [[ -n "\${PRESERVE_KEY}" ]]; then
  echo "\${PRESERVE_KEY}" | sudo tee -a ${REMOTE_DIR}/.env.runtime > /dev/null
elif [[ -n "${LOCAL_KEY}" ]]; then
  echo "${LOCAL_KEY}" | sudo tee -a ${REMOTE_DIR}/.env.runtime > /dev/null
fi
sudo chmod 600 ${REMOTE_DIR}/.env.runtime
cd ${REMOTE_DIR} && sudo docker-compose --env-file .env.runtime -f compose.yaml pull
cd ${REMOTE_DIR} && sudo docker-compose --env-file .env.runtime -f compose.yaml up -d --remove-orphans
for i in \$(seq 1 30); do
  curl -fsS http://127.0.0.1:${HOST_PORT}/api/health && break
  sleep 2
done
install -m 644 /tmp/ai-dashboard-locations.conf /etc/nginx/snippets/ai-dashboard-locations.conf
if ! grep -q 'ai-dashboard-locations.conf' /etc/nginx/sites-enabled/default; then
  sed -i '/ecs-service-manage-generated-locations.conf/i\    include /etc/nginx/snippets/ai-dashboard-locations.conf;' /etc/nginx/sites-enabled/default
fi
python3 - <<'PY'
import json
path = "/opt/ecs_service_management/proxy-mappings.json"
entry = {
    "containerName": "ai-dashboard",
    "host": "47.116.180.173",
    "path": "/tools/ai-dashboard/",
    "targetPort": 8000,
    "listenPort": 80,
    "upstreamPath": "/",
}
with open(path, encoding="utf-8") as f:
    mappings = json.load(f)
idx = next((i for i, m in enumerate(mappings)
            if m.get("path") == entry["path"] or m.get("containerName") == entry["containerName"]), None)
(mappings.append(entry) if idx is None else mappings.__setitem__(idx, entry))
with open(path, "w", encoding="utf-8") as f:
    json.dump(mappings, f, indent=2)
    f.write("\n")
print("proxy-mappings updated:", entry["path"])
PY
nginx -t
systemctl reload nginx
curl -fsS http://127.0.0.1/tools/ai-dashboard/api/health
REMOTE

echo "Done."
echo "  Nginx: ${PUBLIC_URL}"
echo "  Direct: http://47.116.180.173:${HOST_PORT}/"
echo "  CSV (host): ${CSV_HOST_DIR} -> container ${CSV_CONTAINER_PATH}"
