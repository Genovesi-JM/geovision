# GeoVision developer shortcuts. Run `make help` for the list.
SHELL := /bin/bash
MOBILE := mobile
BACKEND := backend

.PHONY: help autodev dev analyze test l10n ios android backend-run backend-test format clean doctor

help:
	@echo "GeoVision make targets:"
	@echo "  make autodev       Run the full Mac build/verify loop (START_AUTODEV_MAC.command)"
	@echo "  make dev           Run the app on a simulator/emulator (demo mode)"
	@echo "  make analyze       flutter analyze"
	@echo "  make test          flutter test"
	@echo "  make l10n          Regenerate localisations"
	@echo "  make ios           Build iOS Simulator (debug)"
	@echo "  make android       Build Android debug APK"
	@echo "  make backend-run   Start the FastAPI backend locally"
	@echo "  make backend-test  Run backend pytest"
	@echo "  make doctor        flutter doctor"

autodev:
	./START_AUTODEV_MAC.command

dev:
	cd $(MOBILE) && flutter run --dart-define=GV_FLAVOR=dev

analyze:
	cd $(MOBILE) && flutter pub get && flutter analyze

test:
	cd $(MOBILE) && flutter test

l10n:
	cd $(MOBILE) && flutter gen-l10n

ios:
	cd $(MOBILE) && flutter build ios --simulator --debug

android:
	cd $(MOBILE) && flutter build apk --debug

format:
	cd $(MOBILE) && dart format lib test

backend-run:
	cd $(BACKEND) && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python start.py

backend-test:
	cd $(BACKEND) && . .venv/bin/activate 2>/dev/null; pytest -q

doctor:
	flutter doctor -v

clean:
	cd $(MOBILE) && flutter clean
