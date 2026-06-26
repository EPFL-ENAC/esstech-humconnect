env_path=../.env

install:
	uv venv --python 3.13 --allow-existing
	uv pip install -e .[dev]

run:
	uv run dotenv -f "$(env_path)" run uvicorn api.main:app --reload

test:
	uv run dotenv -f "$(env_path)" run pytest tests

db-upgrade:
	uv run dotenv -f "$(env_path)" run alembic upgrade head

db-downgrade:
	uv run dotenv -f "$(env_path)" run alembic downgrade -1

db-revision:
	uv run dotenv -f "$(env_path)" run alembic revision --autogenerate -m "$(name)"

typecheck:
	uvx lefthook run pre-commit --command backend-typecheck --all-files

lint:
	uvx lefthook run pre-commit --command backend-lint --all-files

format:
	uvx lefthook run pre-commit --command backend-format --all-files
