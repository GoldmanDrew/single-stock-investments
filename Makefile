# Research QA pipeline (Marvin + Milly)
# Usage:
#   make research-check TICKER=KEWL DATE=2026-06-01
#   make research-check-all
#   make milly-repass TICKER=QDEL
#   make batch-refresh DATE=2026-06-02

PYTHON ?= python3
SCRIPTS := _system/scripts
DATE ?= $(shell date +%Y-%m-%d)

TICKER ?=
DATE ?= $(shell date +%Y-%m-%d)

.PHONY: research-check research-check-all depth-check depth-audit evidence milly-repass book-estimate book-estimate-all holdco-uplift short-scan activist-scan activist-scan-all activist-triage activist-triage-check activist-feed activist-feed-check activist-registry-audit filing-resolve filing-sentinel-gold-check filing-sentinel-workflow-check filing-sentinel-mine filing-sentinel-batch filing-sentinel-raw-batch filing-sentinel-packets event-triage event-triage-check hk-scan hk-cross-check-all hk-extract-refresh third-party-scan-all cross-check-all transcript-sync batch-refresh evidence-check darwin-pit-check darwin-build darwin-roth darwin-ira darwin-pit-audit darwin-sync-external darwin-explore darwin-sp500-refresh persona-lens persona-insights persona-check document-registry document-catalog-search document-sync-drive document-sync-drive-letters document-sync-drive-general document-drive-plan document-drive-migrate document-drive-cleanup document-drive-audit research-memory specialist-13f-ingest tracked-funds-13f-ingest reddit-ingest biotech-quant-lib biotech-spend biotech-insider biotech-insider-fetch biotech-issuer-mcap biotech-short biotech-clinical biotech-paper biotech-composite biotech-validate sumzero-index letter-import-drive letter-extract-text letter-backfill letter-rebuild letter-repair-dates letter-date-check vault-setup vault-check podcasts-refresh podcasts-backfill podcasts-check warrant-refresh warrant-discover warrant-check

warrant-refresh:
	$(PYTHON) $(SCRIPTS)/refresh_warrant_universe.py --refresh-market --capture-cohort
	$(PYTHON) $(SCRIPTS)/resolve_warrant_outcomes.py
	$(PYTHON) $(SCRIPTS)/build_warrant_dashboard.py
	$(PYTHON) $(SCRIPTS)/check_warrant_universe.py

warrant-discover:
	$(PYTHON) $(SCRIPTS)/refresh_warrant_universe.py --discover --discover-days 14 --discover-limit 50
	$(PYTHON) $(SCRIPTS)/build_warrant_dashboard.py

warrant-check:
	$(PYTHON) $(SCRIPTS)/check_warrant_universe.py --strict

filing-sentinel-gold-check:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py validate --require-gold
	$(PYTHON) -m unittest $(SCRIPTS)/test_filing_sentinel_gold.py
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py evaluate --predictions $(SCRIPTS)/fixtures/filing_sentinel_perfect_predictions.jsonl --strict
	@echo OK: filing-sentinel-gold-check

filing-sentinel-workflow-check:
	$(PYTHON) -m unittest $(SCRIPTS)/test_filing_sentinel_gold.py $(SCRIPTS)/test_filing_sentinel_workflow.py $(SCRIPTS)/test_filing_sentinel_raw_discovery.py
	@echo OK: filing-sentinel-workflow-check

filing-sentinel-mine:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py mine --as-of $(DATE) --limit $(or $(LIMIT),100)
	@echo OK: filing-sentinel-mine $(DATE)

filing-sentinel-batch:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_workflow.py build-batch --as-of $(DATE) --limit $(or $(LIMIT),100) --output _system/reviews/pending/filing_sentinel_candidates_$(DATE).jsonl
	@echo OK: filing-sentinel-batch $(DATE)

filing-sentinel-raw-batch:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_raw_discovery.py --as-of $(DATE) --since $(or $(SINCE),2023-01-01) --forms $(or $(FORMS),10-Q) --per-ticker $(or $(PER_TICKER),1) --max-issuers $(or $(MAX_ISSUERS),25) --issuer-offset $(or $(ISSUER_OFFSET),0) --limit $(or $(LIMIT),100) --output _system/reviews/pending/filing_sentinel_raw_candidates_$(DATE).jsonl
	@echo OK: filing-sentinel-raw-batch $(DATE)

filing-sentinel-packets:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_workflow.py create-packets --candidates _system/reviews/pending/filing_sentinel_candidates_$(DATE).jsonl --batch-id $(DATE) --output-dir _system/reviews/pending/filing_sentinel_$(DATE)_packets
	@echo OK: filing-sentinel-packets $(DATE)

persona-lens:
	$(PYTHON) $(SCRIPTS)/fetch_superinvestor_letters.py --all --build
	$(PYTHON) $(SCRIPTS)/persona_lens.py --all
	$(PYTHON) $(SCRIPTS)/append_persona_memory.py --date $(DATE)
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: persona-lens pipeline

persona-fetch-letters:
	$(PYTHON) $(SCRIPTS)/fetch_superinvestor_letters.py --all --build
	@echo OK: persona-fetch-letters

podcasts-refresh:
	$(PYTHON) $(SCRIPTS)/podcast_cloud_refresh.py --date $(DATE) --all-watchlist --whisper-batch 20
	@echo OK: podcasts-refresh

# Overnight / one-shot: every watchlist RSS item, published first, then Whisper batch.
WHISPER_BATCH ?= 50
podcasts-backfill:
	$(PYTHON) $(SCRIPTS)/podcast_cloud_refresh.py --date $(DATE) --backfill --all-watchlist --whisper-batch $(WHISPER_BATCH)
	@echo OK: podcasts-backfill

podcasts-check:
	$(PYTHON) -m unittest _system/scripts/test_podcast_pipeline.py
	$(PYTHON) $(SCRIPTS)/check_podcast_no_audio.py
	@echo OK: podcasts-check

letter-import-drive:
	$(PYTHON) $(SCRIPTS)/import_drive_letter_orphans.py --all --build
	$(PYTHON) $(SCRIPTS)/import_drive_letter_orphans.py --skip-download --build
	@echo OK: letter-import-drive

letter-extract-text:
	$(PYTHON) $(SCRIPTS)/import_drive_letter_orphans.py --skip-download --build
	@echo OK: letter-extract-text

letter-repair-dates:
	$(PYTHON) $(SCRIPTS)/repair_letter_dates.py --apply
	@echo OK: letter-repair-dates

letter-date-check:
	$(PYTHON) $(SCRIPTS)/calibrate_letter_dates.py --gold
	$(PYTHON) -m unittest _system/scripts/test_letter_date_parser.py _system/scripts/test_fund_registry_date.py
	@echo OK: letter-date-check

letter-coverage-check:
	$(PYTHON) $(SCRIPTS)/check_letter_drive_coverage.py --since-year $$(($$(date +%Y)-1))
	@echo OK: letter-coverage-check

letter-rebuild:
	$(PYTHON) $(SCRIPTS)/build_security_master.py --refresh-sec
	$(PYTHON) $(SCRIPTS)/build_superinvestor_insights.py
	$(PYTHON) $(SCRIPTS)/repair_letter_dates.py --apply
	$(PYTHON) $(SCRIPTS)/auto_resolve_filing_events.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_letter_drive_links.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: letter-rebuild

letter-backfill:
	$(PYTHON) $(SCRIPTS)/import_drive_letter_orphans.py --all
	$(PYTHON) $(SCRIPTS)/import_drive_letter_orphans.py --skip-download
	$(PYTHON) $(SCRIPTS)/build_security_master.py --refresh-sec
	$(PYTHON) $(SCRIPTS)/build_superinvestor_insights.py
	$(PYTHON) $(SCRIPTS)/repair_letter_dates.py --apply
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/sync_pdf_store_google_drive.py --root-key hedge_fund_letters
	$(PYTHON) $(SCRIPTS)/build_letter_drive_links.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: letter-backfill

persona-insights:
	$(PYTHON) $(SCRIPTS)/fetch_terminalvalue_sources.py
	$(PYTHON) $(SCRIPTS)/build_sumzero_index.py
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	$(PYTHON) $(SCRIPTS)/validate_dashboard_data.py
	@echo OK: persona-insights

document-registry:
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: document-registry

document-catalog-search:
	$(PYTHON) $(SCRIPTS)/test_document_catalog_search.py
	@echo OK: document-catalog-search

document-drive-plan:
	$(PYTHON) $(SCRIPTS)/plan_drive_reorg.py
	$(PYTHON) $(SCRIPTS)/migrate_drive_pdf_store_layout.py --dry-run
	$(PYTHON) $(SCRIPTS)/cleanup_drive_pdf_store.py --dry-run --trash-legacy-folders --trash-empty-duplicates
	@echo OK: document-drive-plan

document-drive-migrate:
	$(PYTHON) $(SCRIPTS)/migrate_drive_pdf_store_layout.py --apply
	$(PYTHON) $(SCRIPTS)/audit_drive_pdf_store.py
	@echo OK: document-drive-migrate

document-drive-cleanup:
	$(PYTHON) $(SCRIPTS)/cleanup_drive_pdf_store.py --apply --trash-legacy-folders --trash-empty-duplicates
	$(PYTHON) $(SCRIPTS)/dedupe_drive_pdf_store.py --dry-run
	$(PYTHON) $(SCRIPTS)/audit_drive_pdf_store.py
	@echo OK: document-drive-cleanup

document-drive-audit:
	$(PYTHON) $(SCRIPTS)/audit_drive_pdf_store.py
	$(PYTHON) $(SCRIPTS)/plan_drive_reorg.py
	@echo OK: document-drive-audit

document-sync-drive:
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/sync_pdf_store_google_drive.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: document-sync-drive

document-sync-drive-letters:
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/sync_pdf_store_google_drive.py --root-key hedge_fund_letters
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: document-sync-drive-letters

document-sync-drive-general:
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/sync_pdf_store_google_drive.py --root-key general_pdfs
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: document-sync-drive-general

research-memory:
	$(PYTHON) $(SCRIPTS)/build_document_registry.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/validate_research_memory.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: research-memory

specialist-13f-ingest:
	$(PYTHON) $(SCRIPTS)/ingest_specialist_13f.py --offline
	$(PYTHON) $(SCRIPTS)/enrich_cusip_ticker_map.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	$(PYTHON) $(SCRIPTS)/build_biotech_issuer_mcap.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_spend_value.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_insider_scores.py
	$(PYTHON) $(SCRIPTS)/build_biotech_short_interest.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_clinical_profiles.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_composite.py
	$(PYTHON) $(SCRIPTS)/build_biotech_paper_book.py
	$(PYTHON) $(SCRIPTS)/build_biotech_knowledge_delta.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	$(PYTHON) $(SCRIPTS)/validate_biotech_quant.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: specialist-13f-ingest

tracked-funds-13f-ingest:
	$(PYTHON) $(SCRIPTS)/ingest_tracked_funds_13f.py
	$(PYTHON) $(SCRIPTS)/build_tracked_funds_signals.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	$(PYTHON) $(SCRIPTS)/validate_dashboard_data.py
	@echo OK: tracked-funds-13f-ingest

reddit-ingest:
	$(PYTHON) $(SCRIPTS)/fetch_reddit_mentions.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	$(PYTHON) $(SCRIPTS)/validate_dashboard_data.py
	@echo OK: reddit-ingest

biotech-quant-lib:
	$(PYTHON) $(SCRIPTS)/extract_biotech_quant_text.py
	@echo OK: biotech-quant-lib

biotech-issuer-mcap:
	$(PYTHON) $(SCRIPTS)/build_biotech_issuer_mcap.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	@echo OK: biotech-issuer-mcap

biotech-spend:
	$(PYTHON) $(SCRIPTS)/build_biotech_spend_value.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	@echo OK: biotech-spend

biotech-insider-fetch:
	$(PYTHON) $(SCRIPTS)/fetch_insider_transactions.py --quant-universe
	@echo OK: biotech-insider-fetch

biotech-insider:
	$(PYTHON) $(SCRIPTS)/build_biotech_insider_scores.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	@echo OK: biotech-insider

biotech-short:
	$(PYTHON) $(SCRIPTS)/build_biotech_short_interest.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	@echo OK: biotech-short

biotech-clinical:
	$(PYTHON) $(SCRIPTS)/build_biotech_clinical_profiles.py
	$(PYTHON) $(SCRIPTS)/build_specialist_13f_signals.py
	@echo OK: biotech-clinical

biotech-paper:
	$(PYTHON) $(SCRIPTS)/build_biotech_composite.py
	$(PYTHON) $(SCRIPTS)/build_biotech_paper_book.py
	$(PYTHON) $(SCRIPTS)/build_biotech_knowledge_delta.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	@echo OK: biotech-paper

biotech-composite:
	$(PYTHON) $(SCRIPTS)/build_biotech_short_interest.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_clinical_profiles.py --offline
	$(PYTHON) $(SCRIPTS)/build_biotech_composite.py
	$(PYTHON) $(SCRIPTS)/build_biotech_paper_book.py
	$(PYTHON) $(SCRIPTS)/build_research_memory.py
	@echo OK: biotech-composite

biotech-validate:
	$(PYTHON) $(SCRIPTS)/validate_biotech_quant.py
	@echo OK: biotech-validate

sumzero-index:
	$(PYTHON) $(SCRIPTS)/build_sumzero_index.py
	@echo OK: sumzero-index

persona-check:
	$(PYTHON) $(SCRIPTS)/lint_persona_lens.py --portfolio
	@echo OK: persona-check

darwin-sp500-refresh:
	$(PYTHON) $(SCRIPTS)/darwin/refresh_sp500_constituents.py
	$(PYTHON) $(SCRIPTS)/darwin/refresh_sp500_enriched.py
	$(PYTHON) $(SCRIPTS)/darwin/refresh_sp500_liquidity.py

darwin-sp500-liquidity:
	$(PYTHON) $(SCRIPTS)/darwin/refresh_sp500_liquidity.py

darwin-options-cache:
	$(PYTHON) $(SCRIPTS)/darwin/refresh_darwin_options_cache.py --import-etf-only

darwin-options-cache-live:
	$(PYTHON) $(SCRIPTS)/darwin/refresh_darwin_options_cache.py --from-weights

darwin-cc-test:
	$(PYTHON) $(SCRIPTS)/darwin/test_covered_call_bcd.py

sp500-onboard-batch:
	$(PYTHON) $(SCRIPTS)/bulk_sp500_onboard.py --batch-size $(or $(BATCH),8) --offset $(or $(OFFSET),0) --trigger-deep-dive --git-commit --git-push

sp500-onboard-loop:
	$(PYTHON) $(SCRIPTS)/bulk_sp500_onboard.py --batch-size $(or $(BATCH),8) --offset 0 --sleep 0.5 --trigger-deep-dive --git-commit --git-push --loop-until-done

darwin-build:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast --account all
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py

darwin-roth:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast --account roth

darwin-ira: darwin-roth

darwin-sync-external:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --sync-external

darwin-explore:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py

darwin-pit-audit:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --pit-audit --fast

darwin-pit-check:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast
	$(PYTHON) $(SCRIPTS)/check_darwin_pit.py

research-check:
ifndef TICKER
	$(error Set TICKER= e.g. make research-check TICKER=KEWL DATE=2026-06-01)
endif
	$(PYTHON) $(SCRIPTS)/marvin_cloud_refresh.py $(TICKER) --date $(DATE) --skip-milly --strict-evidence
	@echo OK: $(TICKER) research-check

research-check-all:
	$(PYTHON) $(SCRIPTS)/batch_portfolio_refresh.py --date $(DATE) --strict-evidence
	$(PYTHON) $(SCRIPTS)/lint_adversarial.py
	@echo OK: portfolio research-check-all

depth-check:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/lint_deep_dive_depth.py $(TICKER) --strict
	@echo OK: $(TICKER) depth-check

depth-audit:
	$(PYTHON) $(SCRIPTS)/audit_deep_dive_depth.py --portfolio --date $(DATE)
	@echo OK: depth-audit $(DATE)

batch-refresh:
	$(PYTHON) $(SCRIPTS)/batch_portfolio_refresh.py --date $(DATE) --strict-evidence
	@echo OK: batch-refresh $(DATE)

evidence-check:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/check_evidence_completeness.py $(TICKER)
	@echo OK: $(TICKER) evidence-check

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

book-estimate:
ifndef TICKER
	$(error Set TICKER= e.g. make book-estimate TICKER=FRMO)
endif
	$(PYTHON) $(SCRIPTS)/current_book_estimate.py $(TICKER) --write
	@echo OK: $(TICKER) book-estimate

book-estimate-all:
	$(PYTHON) $(SCRIPTS)/current_book_estimate.py --all --write
	@echo OK: book-estimate-all

holdco-uplift:
ifndef TICKER
	$(error Set TICKER= e.g. make holdco-uplift TICKER=FRMO)
endif
	$(PYTHON) $(SCRIPTS)/holdco_uplift_build.py $(TICKER) --write
	@echo OK: $(TICKER) holdco-uplift

short-scan:
	$(PYTHON) $(SCRIPTS)/short_scan_batch.py

activist-scan:
ifndef TICKER
	$(PYTHON) $(SCRIPTS)/scan_activist_sources.py --fetch-sec
else
	$(PYTHON) $(SCRIPTS)/scan_activist_sources.py --ticker $(TICKER) --fetch-sec
endif
	@echo OK: activist-scan

activist-scan-all:
	$(PYTHON) $(SCRIPTS)/scan_activist_sources.py --reconcile --fetch-sec
	$(PYTHON) $(SCRIPTS)/short_scan_batch.py
	$(PYTHON) $(SCRIPTS)/activist_registry_audit.py
	@echo OK: activist-scan-all

activist-triage:
	$(PYTHON) $(SCRIPTS)/activist_triage.py --apply --fetch-sec
	$(PYTHON) $(SCRIPTS)/build_activist_feed.py
	@echo OK: activist-triage

filing-resolve:
	$(PYTHON) $(SCRIPTS)/auto_resolve_filing_events.py
	@echo OK: filing-resolve

filing-sentinel-gold-check:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py validate --require-gold
	$(PYTHON) -m unittest $(SCRIPTS)/test_filing_sentinel_gold.py
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py evaluate --predictions $(SCRIPTS)/fixtures/filing_sentinel_perfect_predictions.jsonl --strict
	@echo OK: filing-sentinel-gold-check

filing-sentinel-workflow-check:
	$(PYTHON) -m unittest $(SCRIPTS)/test_filing_sentinel_gold.py $(SCRIPTS)/test_filing_sentinel_workflow.py $(SCRIPTS)/test_filing_sentinel_raw_discovery.py
	@echo OK: filing-sentinel-workflow-check

filing-sentinel-mine:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_gold.py mine --as-of $(DATE) --limit $(or $(LIMIT),100)
	@echo OK: filing-sentinel-mine $(DATE)

filing-sentinel-batch:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_workflow.py build-batch --as-of $(DATE) --limit $(or $(LIMIT),100) --output _system/reviews/pending/filing_sentinel_candidates_$(DATE).jsonl
	@echo OK: filing-sentinel-batch $(DATE)

filing-sentinel-raw-batch:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_raw_discovery.py --as-of $(DATE) --since $(or $(SINCE),2023-01-01) --forms $(or $(FORMS),10-Q) --per-ticker $(or $(PER_TICKER),1) --max-issuers $(or $(MAX_ISSUERS),25) --issuer-offset $(or $(ISSUER_OFFSET),0) --limit $(or $(LIMIT),100) --output _system/reviews/pending/filing_sentinel_raw_candidates_$(DATE).jsonl
	@echo OK: filing-sentinel-raw-batch $(DATE)

filing-sentinel-packets:
	$(PYTHON) $(SCRIPTS)/filing_sentinel_workflow.py create-packets --candidates _system/reviews/pending/filing_sentinel_candidates_$(DATE).jsonl --batch-id $(DATE) --output-dir _system/reviews/pending/filing_sentinel_$(DATE)_packets
	@echo OK: filing-sentinel-packets $(DATE)

activist-freshness-check:
	$(PYTHON) $(SCRIPTS)/check_activist_freshness.py
	@echo OK: activist-freshness-check

activist-registry-audit:
	$(PYTHON) $(SCRIPTS)/activist_registry_audit.py
	@echo OK: activist-registry-audit

activist-triage-check:
	$(PYTHON) -m unittest _system/scripts/test_activist_triage.py _system/scripts/test_activist_feed.py _system/scripts/test_activist_coverage.py _system/scripts/test_activist_taxonomy.py
	@echo OK: activist-triage-check

event-triage:
	$(PYTHON) $(SCRIPTS)/event_triage.py --date $(DATE)
	$(PYTHON) $(SCRIPTS)/sync_pages_docs.py
	@echo OK: event-triage

event-triage-check:
	$(PYTHON) -m unittest _system/scripts/test_event_materiality.py _system/scripts/test_event_triage.py
	@echo OK: event-triage-check

activist-feed:
	$(PYTHON) $(SCRIPTS)/build_activist_feed.py
	@echo OK: activist-feed

activist-feed-check:
	$(PYTHON) $(SCRIPTS)/test_activist_filer_date.py
	@echo OK: activist-feed-check

activist-text:
ifndef TICKER
	$(PYTHON) $(SCRIPTS)/extract_activist_text.py --all
else
	$(PYTHON) $(SCRIPTS)/extract_activist_text.py $(TICKER)
endif
	@echo OK: activist-text

activist-reconcile:
ifndef TICKER
	$(PYTHON) $(SCRIPTS)/milly_activist_reconcile.py --date $(or $(DATE),$(shell date +%Y-%m-%d))
else
	$(PYTHON) $(SCRIPTS)/milly_activist_reconcile.py --ticker $(TICKER) --date $(or $(DATE),$(shell date +%Y-%m-%d))
endif
	$(PYTHON) $(SCRIPTS)/build_activist_feed.py
	@echo OK: activist-reconcile

activist-cleanup:
	$(PYTHON) $(SCRIPTS)/cleanup_activist_false_positives.py
	$(PYTHON) $(SCRIPTS)/build_activist_feed.py
	@echo OK: activist-cleanup

hk-scan:
ifndef TICKER
	$(error Set TICKER= e.g. make hk-scan TICKER=TPL)
endif
	$(PYTHON) $(SCRIPTS)/scan_hk_sources.py $(TICKER) --write-references --strict
	$(PYTHON) $(SCRIPTS)/check_hk_cross_checks.py $(TICKER)
	@echo OK: $(TICKER) hk-scan

hk-cross-check-all:
	$(PYTHON) $(SCRIPTS)/check_hk_cross_checks.py
	@echo OK: hk-cross-check-all

hk-extract-refresh:
	$(PYTHON) $(SCRIPTS)/refresh_hk_extracts.py
	@echo OK: hk-extract-refresh

third-party-scan-all:
	$(PYTHON) $(SCRIPTS)/scan_third_party_sources.py --all --with-hk --date $(or $(DATE),$(shell date +%Y-%m-%d))
	@echo OK: third-party-scan-all

cross-check-all:
	$(PYTHON) $(SCRIPTS)/check_cross_checks.py $(if $(STRICT),--strict,)
	@echo OK: cross-check-all

transcript-sync:
	$(PYTHON) $(SCRIPTS)/download_transcripts.py --register-legacy $(if $(TICKER),$(TICKER),)
	$(PYTHON) $(SCRIPTS)/transcript_gap_report.py
	@echo OK: transcript-sync

pages-sync:
	$(PYTHON) $(SCRIPTS)/sync_pages_docs.py
	@echo OK: pages-sync (dashboard/ copied to docs/ for GitHub Pages)

vault-check:
	PYTHONPATH=$(SCRIPTS) $(PYTHON) $(SCRIPTS)/test_vault_paths.py
	RESEARCH_VAULT_ROOT="$${RESEARCH_VAULT_ROOT:-../research-vault}" PYTHONPATH=$(SCRIPTS) $(PYTHON) -c "from vault_paths import vault_status; import json, sys; s=vault_status(); print(json.dumps(s, indent=2)); sys.exit(0 if s.get('letters_exists') else 1)"
	@echo OK: vault-check

vault-extract:
	bash $(SCRIPTS)/migrate_extract_vault.sh
	@echo OK: vault-extract — push ../research-vault to GitHub, then make vault-remove-ops

vault-remove-ops:
	bash $(SCRIPTS)/migrate_remove_vault_from_ops.sh
	@echo OK: vault-remove-ops
