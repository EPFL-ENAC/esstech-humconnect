install:
	cd backend && make install
	cd frontend && npm install
	test -f .env || cp .env.example .env
	for dir in $$(ls mcps); do \
		(cd mcps/$$dir && make install); \
		ln -sf ../../.env mcps/$$dir/.env; \
	done

run-backend:
	cd backend && make run

run-frontend:
	cd frontend && npm run dev

test:
	cd backend && make test
	for dir in $$(ls mcps); do \
		cd mcps/$$dir && make test; \
	done

lint:
	uvx lefthook run pre-commit --all-files
