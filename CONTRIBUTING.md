# Contributing

Contributions are welcome. Bug fixes, hardware support, protocol research,
tests, documentation, and operational improvements may all be submitted as
issues or pull requests.

Unless you explicitly state otherwise, any contribution intentionally
submitted for inclusion in this project is licensed under the Apache License,
Version 2.0, as described by section 5 of [LICENSE](LICENSE). By submitting a
contribution, you confirm that you have the right to provide it under those
terms. No separate contributor license agreement is currently required.

Please do not submit:

- vendor drivers, DLLs, applications, installers, or firmware;
- PCAP/USBPcap captures or recorded broadcast transport streams;
- B-CAS responses, card identifiers, private keys, or credentials;
- decompiler output or source copied from incompatibly licensed projects.

Protocol facts and independently written implementations are welcome. When a
change was informed by another project, document the reference and preserve
any license and attribution required by material that is actually reused.

Run `make test` before submitting a pull request. Hardware-dependent changes
should explain the device, channel/system, test conditions, and non-sensitive
validation results without attaching private captures.
