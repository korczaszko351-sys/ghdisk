.PHONY: help install dev test lint demo clean

help:
	@echo "ghdisk — dostępne cele:"
	@echo "  make install   zainstaluj pakiet (z FUSE)"
	@echo "  make dev       zainstaluj z zależnościami deweloperskimi"
	@echo "  make test      uruchom testy"
	@echo "  make demo      demo na backendzie lokalnym (bez GitHuba)"
	@echo "  make clean     usuń artefakty budowania"

install:
	pip install -e ".[fuse]"

dev:
	pip install -e ".[fuse,dev]"

test:
	python3 -m pytest -q

demo:
	bash scripts/demo.sh

clean:
	rm -rf build dist *.egg-info .pytest_cache .coverage htmlcov
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
