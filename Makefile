.PHONY: run test

run:
	uv run python manage.py runserver

test:
	uv run python manage.py test analyzer
