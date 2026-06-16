install:
	cd backend && make install
	cd frontend && npm install
	test -f .env || cp .env.example .env
	for dir in $$(ls backend/mcps); do \
		(cd backend/mcps/$$dir && make install); \
		ln -sf ../../../.env backend/mcps/$$dir/.env; \
	done

run-backend:
	cd backend && make run

run-frontend:
	cd frontend && npm run dev

run-db:
	docker compose up -d

stop-db:
	docker compose down

reset-db:
	docker compose down --volumes
	docker compose up -d

test:
	cd backend && make test
	for dir in $$(ls backend/mcps); do \
		cd backend/mcps/$$dir && make test; \
	done

lint:
	uvx lefthook run pre-commit --all-files
