# Research QA pipeline (Marvin + Milly)
# Usage:
#   make research-check TICKER=QDEL
#   make research-check-all
#   make milly-repass TICKER=QDEL

PYTHON ?= python
SCRIPTS := _system/scripts

TICKER ?=

.PHONY: research-check research-check-all evidence milly-repass short-scan

research-check:
ifndef TICKER
	$(error Set TICKER= e.g. make research-check TICKER=QDEL)
endif
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py $(TICKER)
	$(PYTHON) $(SCRIPTS)/lint_deep_dive.py $(TICKER) --milly
	@echo OK: $(TICKER) research-check

research-check-all:
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py
	$(PYTHON) $(SCRIPTS)/lint_deep_dive.py --milly
	$(PYTHON) $(SCRIPTS)/lint_adversarial.py
	@echo OK: portfolio research-check-all

evidence:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py $(TICKER)

milly-repass:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/milly_repass.py $(TICKER)

short-scan:
	$(PYTHON) $(SCRIPTS)/short_scan_batch.py
