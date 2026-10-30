#!/usr/bin/env bash
# ==============================================================================
# Script de Build Multi-Arquitetura e Push para Docker Hub
# Repositório alvo: allinefreire/afiliados:<DOCKER_VERSION>
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Carrega DOCKER_USER, DOCKER_PASS e DOCKER_VERSION do .env (se não definidos no ambiente)
# utilizando o parser seguro do projeto sem expor segredos no terminal.
eval "$(python3 - <<'PY'
import os, shlex
from shopee.client import load_env
load_env()
for key in ("DOCKER_USER", "DOCKER_PASS", "DOCKER_VERSION"):
    val = os.environ.get(key, "")
    if val:
        print(f"export {key}={shlex.quote(val)}")
PY
)"

# Permite sobrescrever a versão via 1º argumento: ./publicar_docker.sh 1.0
if [[ $# -ge 1 && -n "${1:-}" ]]; then
    export DOCKER_VERSION="$1"
fi

DOCKER_VERSION="${DOCKER_VERSION:-1.0}"
IMAGE_REPO="allinefreire/afiliados"
PLATFORMS="${DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER_NAME="afiliados_multiarch_builder"

if [[ -z "${DOCKER_USER:-}" || -z "${DOCKER_PASS:-}" ]]; then
    echo "❌ Erro: DOCKER_USER e DOCKER_PASS devem estar definidos no ambiente ou no arquivo .env." >&2
    exit 1
fi

cleanup() {
    docker logout >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "============================================================"
echo "🐳 Iniciando publicação Docker Hub: ${IMAGE_REPO}:${DOCKER_VERSION}"
echo "   Usuário Docker Hub : ${DOCKER_USER}"
echo "   Arquiteturas alvo  : ${PLATFORMS}"
echo "============================================================"

# 1. Autenticação segura via stdin (sem expor a senha em ps aux)
echo "🔐 Autenticando no Docker Hub como '${DOCKER_USER}'..."
printf '%s' "${DOCKER_PASS}" | docker login -u "${DOCKER_USER}" --password-stdin

# 2. Configuração do builder multi-arquitetura (docker buildx)
if docker buildx version >/dev/null 2>&1; then
    docker buildx inspect --bootstrap >/dev/null 2>&1 || true

    echo ""
    echo "🚀 [1/2] Compilando e enviando container BACKEND..."
    echo "   Tags: ${IMAGE_REPO}:${DOCKER_VERSION}, ${IMAGE_REPO}:${DOCKER_VERSION}-backend, ${IMAGE_REPO}:latest, ${IMAGE_REPO}:latest-backend"
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file "${ROOT_DIR}/Dockerfile" \
        --tag "${IMAGE_REPO}:${DOCKER_VERSION}" \
        --tag "${IMAGE_REPO}:${DOCKER_VERSION}-backend" \
        --tag "${IMAGE_REPO}:latest" \
        --tag "${IMAGE_REPO}:latest-backend" \
        --push \
        "${ROOT_DIR}"

    echo ""
    echo "🚀 [2/2] Compilando e enviando container FRONTEND..."
    echo "   Tags: ${IMAGE_REPO}:${DOCKER_VERSION}-frontend, ${IMAGE_REPO}:latest-frontend"
    docker buildx build \
        --platform "${PLATFORMS}" \
        --file "${ROOT_DIR}/frontend/Dockerfile" \
        --tag "${IMAGE_REPO}:${DOCKER_VERSION}-frontend" \
        --tag "${IMAGE_REPO}:latest-frontend" \
        --push \
        "${ROOT_DIR}/frontend"
else
    echo "⚠️  docker buildx não encontrado; utilizando docker build + push padrão..."
    docker build -f "${ROOT_DIR}/Dockerfile" \
        -t "${IMAGE_REPO}:${DOCKER_VERSION}" \
        -t "${IMAGE_REPO}:${DOCKER_VERSION}-backend" \
        -t "${IMAGE_REPO}:latest" \
        -t "${IMAGE_REPO}:latest-backend" \
        "${ROOT_DIR}"
    docker push "${IMAGE_REPO}:${DOCKER_VERSION}"
    docker push "${IMAGE_REPO}:${DOCKER_VERSION}-backend"
    docker push "${IMAGE_REPO}:latest"
    docker push "${IMAGE_REPO}:latest-backend"

    docker build -f "${ROOT_DIR}/frontend/Dockerfile" \
        -t "${IMAGE_REPO}:${DOCKER_VERSION}-frontend" \
        -t "${IMAGE_REPO}:latest-frontend" \
        "${ROOT_DIR}/frontend"
    docker push "${IMAGE_REPO}:${DOCKER_VERSION}-frontend"
    docker push "${IMAGE_REPO}:latest-frontend"
fi

echo ""
echo "============================================================"
echo "✅ Publicação concluída com sucesso no Docker Hub!"
echo "   • ${IMAGE_REPO}:${DOCKER_VERSION} (Backend)"
echo "   • ${IMAGE_REPO}:${DOCKER_VERSION}-backend"
echo "   • ${IMAGE_REPO}:${DOCKER_VERSION}-frontend"
echo "============================================================"
