IMAGE ?= leonpatmore2/cursor-agent
APP_IMAGE ?= pr-creator
TAG ?= latest
DOCKER ?= docker

.PHONY: build-cursor-image
build-cursor-image:
	$(DOCKER) build -f docker/cursor/Dockerfile -t $(IMAGE):$(TAG) .

.PHONY: build-app-image
build-app-image:
	$(DOCKER) build -t $(APP_IMAGE):$(TAG) .

.PHONY: test-e2e
test-e2e:
	pipenv run pytest -s -o log_cli=true --log-cli-level=INFO tests/test_cli_e2e.py

.PHONY: lint
lint:
	pipenv run flake8

.PHONY: format
format:
	pipenv run black .
