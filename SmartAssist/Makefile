# SmartAssist Makefile
# Common development and deployment tasks

.PHONY: help install test lint format clean deploy

# Default target
help:
	@echo "SmartAssist Makefile"
	@echo "===================="
	@echo ""
	@echo "Available targets:"
	@echo "  install        - Install all dependencies"
	@echo "  install-dev    - Install development dependencies"
	@echo "  test           - Run all tests"
	@echo "  test-coverage  - Run tests with coverage report"
	@echo "  lint           - Run linters (flake8, mypy)"
	@echo "  format         - Format code with Black"
	@echo "  format-check   - Check code formatting"
	@echo "  clean          - Remove generated files"
	@echo "  deploy         - Deploy to production"
	@echo "  services-start - Start all systemd services"
	@echo "  services-stop  - Stop all systemd services"
	@echo "  services-status - Check service status"
	@echo "  logs           - View all service logs"

# Installation
install:
	@echo "Installing SmartAssist dependencies..."
	pip3 install -r requirements.txt
	pip3 install -r pipeline/requirements.txt
	pip3 install -r services/can-server/requirements.txt
	@echo "Installation complete!"

install-dev: install
	@echo "Installing development dependencies..."
	pip3 install pytest pytest-cov black flake8 mypy
	@echo "Development dependencies installed!"

# Testing
test:
	@echo "Running tests..."
	pytest tests/ -v

test-coverage:
	@echo "Running tests with coverage..."
	pytest tests/ --cov=pipeline --cov=models --cov=services --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

# Code quality
lint:
	@echo "Running linters..."
	@echo "=== Flake8 ==="
	flake8 pipeline/ models/ services/ --max-line-length=120 --exclude=__pycache__,*.egg-info,.git
	@echo "=== MyPy ==="
	mypy pipeline/src/ --ignore-missing-imports || true

format:
	@echo "Formatting code with Black..."
	black pipeline/ models/ services/
	@echo "Formatting complete!"

format-check:
	@echo "Checking code formatting..."
	black --check pipeline/ models/ services/

# Cleanup
clean:
	@echo "Cleaning up generated files..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage
	@echo "Cleanup complete!"

# Deployment
deploy:
	@echo "Deploying SmartAssist..."
	@echo "WARNING: This will restart services!"
	@read -p "Continue? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	sudo systemctl stop smartassist-pipeline smartassist-can-server
	git pull origin main
	git lfs pull
	pip3 install -r requirements.txt --upgrade
	sudo systemctl daemon-reload
	sudo systemctl start smartassist-can-server smartassist-pipeline
	@echo "Deployment complete!"

# Service management
services-start:
	@echo "Starting SmartAssist services..."
	sudo systemctl start smartassist-can-server
	sudo systemctl start smartassist-camera-init
	sudo systemctl start smartassist-pipeline
	@echo "Services started!"

services-stop:
	@echo "Stopping SmartAssist services..."
	sudo systemctl stop smartassist-pipeline
	sudo systemctl stop smartassist-camera-init
	sudo systemctl stop smartassist-can-server
	@echo "Services stopped!"

services-restart:
	@echo "Restarting SmartAssist services..."
	sudo systemctl restart smartassist-can-server
	sudo systemctl restart smartassist-camera-init
	sudo systemctl restart smartassist-pipeline
	@echo "Services restarted!"

services-status:
	@echo "SmartAssist service status:"
	@echo ""
	sudo systemctl status smartassist-can-server --no-pager || true
	@echo ""
	sudo systemctl status smartassist-camera-init --no-pager || true
	@echo ""
	sudo systemctl status smartassist-pipeline --no-pager || true

# Logging
logs:
	@echo "Viewing SmartAssist logs (Ctrl+C to exit)..."
	sudo journalctl -u smartassist-* -f

logs-pipeline:
	sudo journalctl -u smartassist-pipeline -f

logs-can:
	sudo journalctl -u smartassist-can-server -f

logs-camera:
	sudo journalctl -u smartassist-camera-init -f

# Development
dev-run:
	@echo "Running pipeline in development mode..."
	cd pipeline/src && python3 main.py

can-server-run:
	@echo "Running CAN server in development mode..."
	cd services/can-server/src && python3 main.py

# Validation
validate-configs:
	@echo "Validating configuration files..."
	python3 -c "import yaml; yaml.safe_load(open('pipeline/config/pipeline_config.yaml'))"
	python3 -c "import yaml; yaml.safe_load(open('pipeline/config/logging_config.yaml'))"
	python3 -c "import yaml; yaml.safe_load(open('models/nozzlenet/config/nozzlenet_config.yaml'))"
	python3 -c "import yaml; yaml.safe_load(open('models/csi/config/csi_config.yaml'))"
	python3 -c "import json; json.load(open('pipeline/config/camera_config.json'))"
	@echo "All configurations valid!"

# Documentation
docs-build:
	@echo "Building documentation..."
	cd docs && make html
	@echo "Documentation built: docs/_build/html/index.html"

docs-serve:
	@echo "Serving documentation on http://localhost:8000"
	cd docs/_build/html && python3 -m http.server 8000