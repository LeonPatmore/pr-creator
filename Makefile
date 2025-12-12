IMAGE ?= cursor-cli
TAG ?= latest
DOCKER ?= docker

.PHONY: build-cursor-image
build-cursor-image:
	$(DOCKER) build -t $(IMAGE):$(TAG) .

