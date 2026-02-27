.PHONY: test lint format

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

lint:
	@echo "No linter configured yet"

format:
	@echo "No formatter configured yet"
