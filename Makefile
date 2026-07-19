.PHONY: demo stop status logs seed backend-only fe-only install help

help:
	@echo "Targets:"
	@echo "  make demo         - clean → backend → seed → frontend (default)"
	@echo "  make backend-only - backend + seed, no frontend"
	@echo "  make fe-only      - frontend only (assumes backend already up)"
	@echo "  make seed         - re-run sourcing seeder against live backend"
	@echo "  make stop         - stop everything"
	@echo "  make status       - show what's running"
	@echo "  make logs         - tail logs (Ctrl-C to exit)"
	@echo "  make install      - one-time setup (.venv + frontend deps)"

demo:
	@./scripts/demo.sh

backend-only:
	@./scripts/demo.sh --no-fe

fe-only:
	@cd frontend && npm run dev -- -p 3001

seed:
	@./scripts/demo.sh seed

stop:
	@./scripts/demo.sh stop

status:
	@./scripts/demo.sh status

logs:
	@./scripts/demo.sh logs

install:
	@test -d .venv || python3 -m venv .venv
	@.venv/bin/pip install -q -r requirements.txt
	@cd frontend && npm install --silent
	@echo "ok — now run: make demo"
