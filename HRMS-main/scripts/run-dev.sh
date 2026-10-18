#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${APP_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop or Docker Engine with Compose v2." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required. Update Docker Desktop or install the Compose plugin." >&2
  exit 1
fi

if [[ ! -f "backend/.env" ]]; then
  echo "Missing backend/.env. Copy backend/.env.example to backend/.env and configure it first." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  case "$(uname -s)" in
    Darwin)
      if ! open -Ra Docker >/dev/null 2>&1; then
        echo "Docker Desktop was not found. Install it, then run this script again." >&2
        exit 1
      fi
      echo "Starting Docker Desktop..."
      open -a Docker
      ;;
    Linux)
      if ! command -v systemctl >/dev/null 2>&1; then
        echo "Docker is not running, and systemctl is unavailable to start it automatically." >&2
        echo "Start the Docker Engine service, then run this script again." >&2
        exit 1
      fi
      echo "Starting the Docker Engine service..."
      if ! systemctl start docker >/dev/null 2>&1; then
        if ! command -v sudo >/dev/null 2>&1; then
          echo "Could not start Docker. Run this script with permission to start the docker service." >&2
          exit 1
        fi
        sudo systemctl start docker
      fi
      ;;
    *)
      echo "Docker is not running. Start Docker Engine for this system, then run this script again." >&2
      exit 1
      ;;
  esac

  echo "Waiting up to three minutes for Docker to become ready..."
  for attempt in {1..90}; do
    if docker info >/dev/null 2>&1; then
      break
    fi
    if (( attempt == 90 )); then
      echo "Docker did not become ready within three minutes. Check Docker Desktop/Engine and try again." >&2
      exit 1
    fi
    if (( attempt % 10 == 0 )); then
      echo "Still waiting for Docker..."
    fi
    sleep 2
  done
fi

if [[ ! -f "backend/storage/hrms.db" ]]; then
  echo "No local database found. Migrations will create an empty database; this script will not seed or reset data." >&2
fi

echo "Building the API and web images..."
docker compose build

echo "Applying pending database migrations..."
docker compose run --rm --no-deps api alembic -c alembic.ini upgrade head

echo "Starting the API and web app. Press Ctrl+C to stop both services."
echo "Web: http://localhost:3000"
echo "API docs: http://localhost:8000/docs"
exec docker compose up --no-build --remove-orphans
