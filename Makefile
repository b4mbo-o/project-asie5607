PREFIX ?= /usr/local
LIBDIR ?= $(PREFIX)/lib/project-asie5607
BINDIR ?= $(PREFIX)/bin
SYSCONFDIR ?= /etc
SYSTEMD_UNIT_DIR ?= /etc/systemd/system
UDEV_RULES_DIR ?= /etc/udev/rules.d
SHAREDIR ?= $(PREFIX)/share/doc/project-asie5607
DESTDIR ?=

.PHONY: all test clean install install-firmware uninstall

all:
	$(MAKE) -C tools/hduc_ctl

test: all
	python3 -m compileall -q scripts tests
	python3 -m unittest discover -s tests -v
	bash tests/smoke.sh

clean:
	$(MAKE) -C tools/hduc_ctl clean
	find scripts tests -type d -name __pycache__ -prune -exec rm -rf {} +

install: all
	install -d "$(DESTDIR)$(LIBDIR)/scripts" "$(DESTDIR)$(LIBDIR)/tools/hduc_ctl"
	install -d "$(DESTDIR)$(LIBDIR)/data" "$(DESTDIR)$(LIBDIR)/templates" "$(DESTDIR)$(LIBDIR)/firmware"
	install -d "$(DESTDIR)$(BINDIR)" "$(DESTDIR)$(SYSTEMD_UNIT_DIR)" "$(DESTDIR)$(UDEV_RULES_DIR)"
	install -d "$(DESTDIR)$(SHAREDIR)/examples"
	find scripts -maxdepth 1 -type f -exec install -m 0755 {} "$(DESTDIR)$(LIBDIR)/scripts/" \;
	install -m 0755 tools/hduc_ctl/hduc_ctl "$(DESTDIR)$(LIBDIR)/tools/hduc_ctl/hduc_ctl"
	install -m 0644 data/*.json "$(DESTDIR)$(LIBDIR)/data/"
	install -m 0644 templates/*.json "$(DESTDIR)$(LIBDIR)/templates/"
	install -m 0644 README.md LICENSE NOTICE NOTICE.md "$(DESTDIR)$(LIBDIR)/"
	install -m 0644 docs/*.md "$(DESTDIR)$(SHAREDIR)/"
	install -m 0644 examples/*.yml "$(DESTDIR)$(SHAREDIR)/examples/"
	ln -sfn "$(LIBDIR)/scripts/hducd" "$(DESTDIR)$(BINDIR)/hducd"
	ln -sfn "$(LIBDIR)/scripts/u3d" "$(DESTDIR)$(BINDIR)/u3d"
	ln -sfn "$(LIBDIR)/scripts/recpt1-hduc" "$(DESTDIR)$(BINDIR)/recpt1-hduc"
	ln -sfn "$(LIBDIR)/scripts/recpt1-u3" "$(DESTDIR)$(BINDIR)/recpt1-u3"
	ln -sfn "$(LIBDIR)/scripts/extract_as11loader_firmware.py" "$(DESTDIR)$(BINDIR)/asie5607-extract-firmware"
	install -m 0644 deploy/systemd/asie5607-hduc.service "$(DESTDIR)$(SYSTEMD_UNIT_DIR)/"
	install -m 0644 deploy/systemd/asie5607-u3.service "$(DESTDIR)$(SYSTEMD_UNIT_DIR)/"
	install -m 0644 deploy/udev/70-asie5607.rules "$(DESTDIR)$(UDEV_RULES_DIR)/"
	install -d "$(DESTDIR)$(SYSCONFDIR)/default"
	@test -e "$(DESTDIR)$(SYSCONFDIR)/default/asie5607-hduc" || \
		install -m 0644 deploy/default/asie5607-hduc "$(DESTDIR)$(SYSCONFDIR)/default/asie5607-hduc"
	@test -e "$(DESTDIR)$(SYSCONFDIR)/default/asie5607-u3" || \
		install -m 0644 deploy/default/asie5607-u3 "$(DESTDIR)$(SYSCONFDIR)/default/asie5607-u3"
	@echo "Installed without vendor firmware. Run 'make install-firmware FIRMWARE=/path/to/generated.bin'."

install-firmware:
	@test -n "$(FIRMWARE)" || { echo "FIRMWARE=/path/to/as11loader_decrypted_full.bin is required" >&2; exit 2; }
	@test "$$(sha256sum "$(FIRMWARE)" | cut -d' ' -f1)" = "f4848c8c091634897f9829e50d2ff8e5dc28792c6b20cf095d38d40379518c7a" || \
		{ echo "refusing firmware with an unknown SHA-256" >&2; exit 2; }
	install -d "$(DESTDIR)$(LIBDIR)/firmware"
	install -m 0644 "$(FIRMWARE)" "$(DESTDIR)$(LIBDIR)/firmware/as11loader_decrypted_full.bin"

uninstall:
	rm -f "$(DESTDIR)$(BINDIR)/hducd" "$(DESTDIR)$(BINDIR)/u3d"
	rm -f "$(DESTDIR)$(BINDIR)/recpt1-hduc" "$(DESTDIR)$(BINDIR)/recpt1-u3"
	rm -f "$(DESTDIR)$(BINDIR)/asie5607-extract-firmware"
	rm -f "$(DESTDIR)$(SYSTEMD_UNIT_DIR)/asie5607-hduc.service"
	rm -f "$(DESTDIR)$(SYSTEMD_UNIT_DIR)/asie5607-u3.service"
	rm -f "$(DESTDIR)$(UDEV_RULES_DIR)/70-asie5607.rules"
	rm -rf "$(DESTDIR)$(LIBDIR)"
	rm -rf "$(DESTDIR)$(SHAREDIR)"
