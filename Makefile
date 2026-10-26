PY ?= python
RAW ?= data/raw
WAREHOUSE ?= warehouse/iceberg
DB ?= warehouse/lake.duckdb
OFFLINE ?=
TODAY ?= $(shell $(PY) -c "import datetime; print(datetime.date.today())")
DBT_BIN ?= dbt
PULL = $(PY) ingestion/pull.py --raw $(RAW) --warehouse $(WAREHOUSE) --db $(DB) $(OFFLINE)

.PHONY: all pull export dbt test fixture-all canary clean

all: pull export dbt test   ## live ONS + BoE pulls (cached), write-audit-publish, dbt, tests

pull:   ## every GDP release, the last 13 CPIH releases, today's BoE rates; each through write-audit-publish
	$(PULL) ons --dataset gdp-to-four-decimal-places --versions all
	$(PULL) ons --dataset cpih01 --versions last:13
	$(PULL) boe --today $(TODAY)

export:
	$(PULL) export

dbt:
	cd dbt && DUCKDB_PATH=../$(DB) $(DBT_BIN) build --profiles-dir .

test:
	$(PY) -m pytest -q tests

fixture-all:   ## synthetic ONS/BoE-format files, offline, through the same pipeline (CI)
	$(PY) tests/fixtures/make_fixture.py --raw data/fixture/raw
	$(MAKE) pull export dbt test RAW=data/fixture/raw WAREHOUSE=warehouse/fixture_iceberg DB=warehouse/fixture.duckdb \
	  OFFLINE=--offline TODAY=2025-01-01

canary:   ## the latest live release only, into a throwaway lakehouse: catches upstream format changes
	$(PY) ingestion/pull.py --raw data/canary/raw --warehouse warehouse/canary_iceberg --db warehouse/canary.duckdb \
	  ons --dataset gdp-to-four-decimal-places --versions latest
	$(PY) ingestion/pull.py --raw data/canary/raw --warehouse warehouse/canary_iceberg --db warehouse/canary.duckdb boe

clean:
	rm -rf warehouse dbt/target dbt/logs data/fixture data/canary
