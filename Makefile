IMAGE ?= cursor-cli
TAG ?= latest
DOCKER ?= docker

.PHONY: build-cursor-image
build-cursor-image:
	$(DOCKER) build -t $(IMAGE):$(TAG) .

.PHONY: test-e2e
test-e2e:
	pipenv run pytest tests/test_cli_e2e.py -q

.PHONY: lint
lint:
	pipenv run flake8

.PHONY: format
format:
	pipenv run black .
