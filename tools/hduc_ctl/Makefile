CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2 -g
LIBS := $(shell pkg-config --cflags --libs libusb-1.0)

hduc_ctl: hduc_ctl.c
	$(CC) $(CFLAGS) -o $@ $< $(LIBS)

clean:
	rm -f hduc_ctl

.PHONY: clean
