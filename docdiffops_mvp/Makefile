.PHONY: check test test-forensic coverage mypy quality demo clean-demo

VENV    = .venv/bin
FORENSIC = docdiffops/forensic.py \
           docdiffops/forensic_schema.py \
           docdiffops/forensic_actions.py \
           docdiffops/forensic_delta.py \
           docdiffops/forensic_trend.py \
           docdiffops/forensic_cli.py \
           docdiffops/forensic_correlations.py \
           docdiffops/forensic_note.py

check: test-forensic mypy

test:
	$(VENV)/python -m pytest tests/ -q

test-forensic:
	$(VENV)/python -m pytest tests/unit/test_forensic*.py \
	  tests/unit/test_forensic_cli.py \
	  tests/unit/test_forensic_pipeline_integration.py \
	  tests/integration/test_forensic_api.py -q

coverage:
	bash scripts/forensic_quality_check.sh

mypy:
	$(VENV)/python -m mypy $(FORENSIC) --config-file mypy.ini || true

quality:
	bash scripts/forensic_quality_check.sh

demo:
	@mkdir -p /tmp/forensic_demo
	$(VENV)/python -c "from docdiffops.forensic import build_forensic_bundle; \
	from docdiffops.forensic_actions import apply_actions_to_bundle; \
	from docdiffops.forensic_render import render_v8_xlsx, render_v8_docx_explanatory, render_v8_docx_redgreen, render_v8_pdf_summary; \
	docs=[{'id':'D01','code':'FZ_115','rank':1,'title':'115-ФЗ','type':'law'},{'id':'D02','code':'FZ_109','rank':1,'title':'109-ФЗ','type':'law'}]; \
	pairs=[{'id':'P1','left':'D01','right':'D02','events':[{'status':'partial'}]}]; \
	b=apply_actions_to_bundle(build_forensic_bundle(documents=docs, pairs=pairs, events=[], amendment_graph={}), corpus='migration_v8'); \
	render_v8_xlsx(b, '/tmp/forensic_demo/demo.xlsx'); \
	render_v8_docx_explanatory(b, '/tmp/forensic_demo/demo_explanatory.docx'); \
	render_v8_docx_redgreen(b, '/tmp/forensic_demo/demo_redgreen.docx'); \
	render_v8_pdf_summary(b, '/tmp/forensic_demo/demo_summary.pdf'); \
	print('Demo artifacts written to /tmp/forensic_demo/')"

clean-demo:
	rm -rf /tmp/forensic_demo
