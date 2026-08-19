.PHONY: help setup sync run docker-build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Run interactive package rename (scripts/setup.sh)
	@bash scripts/setup.sh

sync: ## Install dependencies with uv
	uv sync

run: ## Run the package entrypoint
	uv run auto_job_apply

docker-build: ## Build the Docker image
	docker build -t auto_job_apply .
