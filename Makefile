.PHONY: install run test demo

install:
	python -m venv .venv
	.venv/Scripts/pip install -r requirements.txt || .venv/bin/pip install -r requirements.txt
	.venv/Scripts/python -m playwright install chromium || .venv/bin/python -m playwright install chromium
	cd frontend && npm install

run:
	cd backend && uvicorn app.main:app --reload --port 8001

test:
	pytest backend/tests -v

demo:
	cd backend && python -m app.scripts.demo_payment
