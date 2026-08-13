# Notice

This is an independent interoperability research project for owner-operated
hardware. It is not affiliated with or endorsed by SKNET, ASICEN, VidzMedia,
ARIB, or any broadcaster.

The repository contains independently written source and normalized
interoperability data. It does **not** contain or redistribute:

- runtime firmware or encrypted firmware payloads
- Windows drivers, DLLs, applications, installers, or decompiler output
- USBPcap/pcapng recordings, transport streams, or broadcast content
- driver memory/context dumps
- B-CAS card responses, card identifiers, or an ARIB STD-B25 implementation
- source or binaries copied from third-party projects

Users must supply their own supported 32-bit `SKNET_AS11Loader.sys`. The local
extraction utility derives and verifies the device RAM image from that file;
it does not download the driver or firmware. The supplied driver and generated
image are ignored by Git and should remain local. Providing the utility does
not grant any right to obtain, use, or redistribute vendor files.

The normalized U3 template contains host-issued USB setup/OUT values only;
captured USB/card IN payloads were removed. Its retained card OUT commands are
limited to fixed startup exchanges and are covered by a regression audit.

`recpt1-hduc` and `recpt1-u3` implement a small, independently written
command-line compatibility surface (`channel rectime destfile`). They do not
contain source from recpt1.

Product and company names identify compatible hardware only. No affiliation
or warranty is implied. Users are responsible for complying with applicable
law, software terms, broadcast contracts, and card terms.

No open-source license has been selected yet. Unless and until a license is
added, source reuse remains subject to the copyright holder's permission and
applicable law.
