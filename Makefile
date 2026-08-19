# GeoVision developer shortcuts. Run `make help` for the list.
SHELL := /bin/bash
MOBILE := mobile
BACKEND := backend

.PHONY: help autodev dev mobile-dev setup simulator test logs stop analyze mobile-test l10n ios android backend-run backend-test format clean doctor

help:
	@echo "GeoVision make targets:"
	@echo "  make autodev       Run the full Mac build/verify loop (START_AUTODEV_MAC.command)"
	@echo "  make setup         Prepare and start the local IoT stack"
	@echo "  make dev           Start the GeoVision IoT Docker stack"
	@echo "  make simulator     Start the real-protocol sensor simulator"
	@echo "  make test          Run backend, frontend and firmware checks"
	@echo "  make logs          Follow local stack logs"
	@echo "  make stop          Stop the local stack (data is preserved)"
	@echo "  make mobile-dev    Run the Flutter app on a simulator/emulator"
	@echo "  make analyze       flutter analyze"
	@echo "  make mobile-test   Run Flutter tests"
	@echo "  make l10n          Regenerate localisations"
	@echo "  make ios           Build iOS Simulator (debug)"
	@echo "  make android       Build Android debug APK"
	@echo "  make backend-run   Start the FastAPI backend locally"
	@echo "  make backend-test  Run backend pytest"
	@echo "  make doctor        flutter doctor"

autodev:
	./START_AUTODEV_MAC.command

setup:
	./start_geovision_iot.command

dev:
	docker compose --env-file .env.iot up -d

mobile-dev:
	./scripts/run_mobile_dev.sh

analyze:
	cd $(MOBILE) && flutter pub get && flutter analyze

mobile-test:
	cd $(MOBILE) && flutter test

test: backend-test mobile-test
	npm test --if-present

simulator:
	docker compose --env-file .env.iot --profile simulator up -d --build simulator

logs:
	docker compose --env-file .env.iot logs -f --tail=200

stop:
	docker compose --env-file .env.iot down

l10n:
	cd $(MOBILE) && flutter gen-l10n

ios:
	cd $(MOBILE) && flutter build ios --simulator --debug

android:
	cd $(MOBILE) && flutter build apk --debug

# --- Real (non-demo) builds/runs: hit a real backend, no mock data ---
mobile-real:   ## Run the app NON-DEMO against a real backend (default: local 8010)
	cd $(MOBILE) && flutter run --dart-define-from-file=dart_defines/real-local.json

android-release: ## Build a production (non-demo) release APK
	cd $(MOBILE) && flutter build apk --release --dart-define-from-file=dart_defines/production.json

ios-release:   ## Build a production (non-demo) iOS app
	cd $(MOBILE) && flutter build ios --release --dart-define-from-file=dart_defines/production.json

format:
	cd $(MOBILE) && dart format lib test

backend-run:
	cd $(BACKEND) && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python start.py

backend-test:
	cd $(BACKEND) && if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest -q; elif [ -x .venv-test/bin/python ]; then .venv-test/bin/python -m pytest -q; else python3 -m pytest -q; fi

doctor:
	flutter doctor -v

clean:
	cd $(MOBILE) && flutter clean
