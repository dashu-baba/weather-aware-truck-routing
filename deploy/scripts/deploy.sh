#!/usr/bin/env bash
# Usage: IMAGE_TAG=sha-<commit> ./deploy.sh   (registry login is done by the caller)
set -euo pipefail
cd "$(dirname "$0")"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
export IMAGE_TAG

docker compose pull
docker compose run --rm --no-deps backend python manage.py migrate --noinput
docker compose up -d --remove-orphans

status=starting
for _ in $(seq 1 45); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q backend)")
  [ "$status" = healthy ] && break
  sleep 2
done
if [ "$status" != healthy ]; then
  docker compose logs --tail=80 backend
  exit 1
fi

echo "$IMAGE_TAG" > DEPLOYED_TAG
docker image prune -f >/dev/null
echo "Deployed $IMAGE_TAG"
