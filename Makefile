.PHONY: help smoke-public smoke-public-core smoke-public-multilang smoke-public-multilang-core smoke-public-api smoke-public-both

help:
	@echo "Available targets:"
	@echo "  make smoke-public       # browser/public trimmed smoke"
	@echo "  make smoke-public-core  # browser/public core smoke"
	@echo "  make smoke-public-multilang       # browser/public multilingual trimmed smoke"
	@echo "  make smoke-public-multilang-core  # browser/public multilingual core smoke"
	@echo "  make smoke-public-api   # api-client / Cloudflare policy smoke"
	@echo "  make smoke-public-both  # browser + api smoke"

smoke-public:
	./scripts/run_public_smoke.sh browser

smoke-public-core:
	./scripts/run_public_smoke.sh browser-core

smoke-public-multilang:
	./scripts/run_public_smoke.sh browser-multilang

smoke-public-multilang-core:
	./scripts/run_public_smoke.sh browser-multilang-core

smoke-public-api:
	./scripts/run_public_smoke.sh api

smoke-public-both:
	./scripts/run_public_smoke.sh both
