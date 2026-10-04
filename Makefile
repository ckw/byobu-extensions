PYTHON ?= python3

.PHONY: test
test:
	$(PYTHON) tests/test_window_picker.py
