.PHONY: build serve

build:
	python3 ../scripts/build_data.py

serve: build
	python3 -m http.server 8765
