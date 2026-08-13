.PHONY: all test clean

all:
	$(MAKE) -C tools/hduc_ctl

test: all
	python3 -m compileall -q scripts tests
	python3 -m unittest discover -s tests -v
	bash tests/smoke.sh

clean:
	$(MAKE) -C tools/hduc_ctl clean
	find scripts tests -type d -name __pycache__ -prune -exec rm -rf {} +
