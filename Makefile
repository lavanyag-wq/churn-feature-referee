.PHONY: lint test experiments receipts verify

lint:
	ruff check src tests tools experiments

test:
	pytest --junitxml=reports/junit.xml --cov=churn_feature_referee --cov-report=json:reports/coverage.json --cov-report=term

experiments:
	python experiments/exp_attribution.py
	python experiments/exp_blindspot.py
	python experiments/exp_leak_magnitude.py

receipts:
	python tools/collect_metrics.py --skip-tests
	python tools/check_numbers.py

verify: lint test experiments receipts
