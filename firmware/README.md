# Firmware preparation

This directory intentionally contains no vendor firmware.

Obtain the supported **32-bit** `SKNET_AS11Loader.sys` from software supplied
for hardware that you own. The primary package identifier is the HDUC driver
released on **2009-11-10**, `091110_Driver.zip`, Driver Ver.1.9.10.20. The U3
package released on 2009-11-27, `091127_Driver_U3.zip`, contains the same
loader file. Its internal PE timestamp is 2009-09-24 03:24:08 UTC.

Then generate the local runtime image from the repository root:

```bash
python3 scripts/extract_as11loader_firmware.py \
  /path/to/SKNET_AS11Loader.sys
```

Supported input SHA-256:

```text
9abd9c8cd901d36235d96e8361ab51d7b8538bdc39a38a03d4c2d7c1b6ecfbe0
```

The resulting `as11loader_decrypted_full.bin` is written here and is ignored
by Git. Keep both the driver and generated image local. The script does not
download either file and refuses unknown driver builds.
