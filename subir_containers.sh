#!/usr/bin/env bash
set -e

# Garante que a rede 'containers' exista conforme diretriz obrigatória
if ! docker network inspect containers >/dev/null 2>&1; then
  echo "Criando rede 'containers'..."
  docker network create containers
fi

echo "Iniciando containers do Afiliados Multi-Channel Hub..."
docker compose up -d --build

echo ""
echo "Containers em execução:"
docker compose ps
echo ""
echo "Frontend: http://localhost:4200"
echo "Backend:  http://localhost:8000"
echo "Swagger:  http://localhost:8000/docs"
