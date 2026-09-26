.PHONY: up down build logs test migrate

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f api

test:
	docker compose up -d db redis
	pytest

migrate:
	alembic upgrade head
