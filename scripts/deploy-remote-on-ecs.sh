#!/usr/bin/env bash
set -euo pipefail
REG='crpi-02k3y8iudey5q0vb.cn-shanghai.personal.cr.aliyuncs.com/mirror_ns/ai-dashboard:latest'
BUILD=/tmp/ai-dashboard-build
REMOTE_DIR=/srv/apps/ai-dashboard
CSV_HOST_DIR=/srv/data/ai-dashboard/csv
CSV_CONTAINER_PATH=/data/csv
HOST_PORT=8011
SERVICE=ai-dashboard

rm -rf "${BUILD}" && mkdir -p "${BUILD}"
tar xzf /tmp/ai-dashboard-deploy.tgz -C "${BUILD}"
cd "${BUILD}"
docker build -t "${REG}" .
docker push "${REG}"
sudo mkdir -p "${REMOTE_DIR}" "${CSV_HOST_DIR}"
sudo cp deploy/compose.yaml "${REMOTE_DIR}/compose.yaml"
sudo chmod 755 "${CSV_HOST_DIR}"

PRESERVE_KEY=""
if sudo test -f "${REMOTE_DIR}/.env.runtime"; then
  PRESERVE_KEY="$(sudo grep '^DEEPSEEK_API_KEY=' "${REMOTE_DIR}/.env.runtime" | head -1 || true)"
fi
sudo tee "${REMOTE_DIR}/.env.runtime" > /dev/null <<EOF
SERVICE_NAME=ai-dashboard
IMAGE=${REG}
HOST_PORT=${HOST_PORT}
CONTAINER_PORT=8000
CSV_DATA_PATH=${CSV_CONTAINER_PATH}
CSV_HOST_DIR=${CSV_HOST_DIR}
EOF
if [[ -n "${PRESERVE_KEY}" ]]; then
  echo "${PRESERVE_KEY}" | sudo tee -a "${REMOTE_DIR}/.env.runtime" > /dev/null
fi
sudo chmod 600 "${REMOTE_DIR}/.env.runtime"
cd "${REMOTE_DIR}" && sudo docker-compose --env-file .env.runtime -f compose.yaml pull
cd "${REMOTE_DIR}" && sudo docker-compose --env-file .env.runtime -f compose.yaml up -d --remove-orphans
for i in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:${HOST_PORT}/api/health" && break
  sleep 2
done
sudo install -m 644 /tmp/ai-dashboard-locations.conf /etc/nginx/snippets/ai-dashboard-locations.conf
sudo nginx -t
sudo systemctl reload nginx
curl -fsS http://127.0.0.1/tools/ai-dashboard/api/health
echo "Deploy OK"
