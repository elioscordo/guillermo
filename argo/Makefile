.PHONY: help up down restart logs ps status recreate force-recreate free-ports

SHELL := /bin/bash
DOCKER_COMPOSE ?= docker compose
IB_DIR ?= $(or $(wildcard ../ib-gateway-docker),$(wildcard ../../ib-gateway-docker),$(wildcard ..//ib-gateway-docker),/home/elio/projects/ib-gateway-docker)

help:
	@echo "IB Gateway Docker management for Argo"
	@echo ""
	@echo "Available commands:"
	@echo "  make recreate       - Force recreate IB Gateway container (clears port conflicts and stuck instances)"
	@echo "  make force-recreate - Alias for recreate"
	@echo "  make free-ports     - Kill any lingering containers or processes holding ports 4001/4002"
	@echo "  make up             - Start the IB Gateway container"
	@echo "  make down           - Stop and remove the IB Gateway container"
	@echo "  make restart        - Restart the IB Gateway container"
	@echo "  make logs           - Follow IB Gateway container logs"
	@echo "  make status         - View IB Gateway container status"

free-ports:
	@echo "Freeing ports 4001 and 4002..."
	@docker rm -f $$(docker ps -aq --filter "publish=4001" 2>/dev/null) 2>/dev/null || true
	@docker rm -f $$(docker ps -aq --filter "publish=4002" 2>/dev/null) 2>/dev/null || true
	@fuser -k 4001/tcp 4002/tcp 2>/dev/null || true

recreate:
	@echo "Stopping stuck container and force recreating in $(IB_DIR)..."
	cd $(IB_DIR) && ($(DOCKER_COMPOSE) down --remove-orphans -t 2 2>/dev/null || $(DOCKER_COMPOSE) kill)
	@$(MAKE) free-ports
	cd $(IB_DIR) && $(DOCKER_COMPOSE) up -d --force-recreate
	@echo "IB Gateway container recreated successfully."

force-recreate: recreate

up:
	cd $(IB_DIR) && $(DOCKER_COMPOSE) up -d

down:
	cd $(IB_DIR) && $(DOCKER_COMPOSE) down

restart:
	cd $(IB_DIR) && $(DOCKER_COMPOSE) restart

logs:
	cd $(IB_DIR) && $(DOCKER_COMPOSE) logs -f

status:
	cd $(IB_DIR) && $(DOCKER_COMPOSE) ps

ps: status
