ROOT_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
IMAGE_NAME := ghcr.io/jo-hoe/doctorlib-navigator
IMAGE_VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")

.DEFAULT_GOAL := start-docker
.PHONY: init venv update save-dependencies test start-docker \
        start-cluster push-k3d start-k3d stop-k3d restart-k3d \
        generate-helm-docs

## init: set up the local virtual environment
init: venv update

venv:
	python -m venv .venv

## update: install/update dependencies
update:
	.venv/Scripts/pip install -r requirements.txt 2>/dev/null || .venv/bin/pip install -r requirements.txt

## save-dependencies: freeze requirements
save-dependencies:
	.venv/Scripts/pip freeze > requirements.txt 2>/dev/null || .venv/bin/pip freeze > requirements.txt

## test: run pytest
test:
	pytest

## start-docker: build and run with Docker Compose
start-docker:
	docker compose up --build

## start-cluster: create the k3d cluster
start-cluster:
	k3d cluster create --config k3d/cluster.yaml

## push-k3d: build and push image to local k3d registry
push-k3d:
	docker build -t localhost:5000/doctorlib-navigator:$(IMAGE_VERSION) .
	docker push localhost:5000/doctorlib-navigator:$(IMAGE_VERSION)

## start-k3d: deploy full stack into k3d cluster
start-k3d: push-k3d
	helm upgrade --install doctorlib-navigator charts/doctorlib-navigator \
		--namespace doctorlib-navigator \
		--create-namespace \
		--values dev/k3d-values.yaml

## stop-k3d: stop and delete the k3d cluster
stop-k3d:
	k3d cluster delete doctorlib-navigator

## restart-k3d: recreate the k3d cluster
restart-k3d: stop-k3d start-cluster start-k3d

## generate-helm-docs: regenerate chart README
generate-helm-docs:
	docker run --rm -v "$(ROOT_DIR):/helm-docs" jnorwood/helm-docs:latest
