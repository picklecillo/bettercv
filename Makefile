.PHONY: up down build logs run test

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose up --build -d

logs:
	docker compose logs -f

run:
	uv run python manage.py runserver

test:
	uv run python manage.py test
