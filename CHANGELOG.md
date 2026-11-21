# Changelog

## v0.1.0 (First public installer prerelease)

- Guided installer with compatibility checks, before-and-after verification, and rollback to the saved Offroad setting.
- Offline checks passed. The installer is untested on Windows and against a live head unit.

## Earlier local development builds

### v0.2.2 (Local guided installer preview)

- Identify the tested D-Link adapter by its label and check the Windows Ethernet route before connecting.
- Show the editable head-unit IP default.

### v0.2.1 (Local installer preview)

- Explain the wired service connection, unit address, and recovery code in English and Turkish.
- Show the verified Offroad setting and request final confirmation before changing it.
- Check cancellation and settings that change between the initial read and final approval in offline tests.

### v0.2.0 (Local guided installer preview)

- Add an English and Turkish terminal guide for the reviewed Delphi head unit, with the owner's IPv4 address and manual compatibility and service-access confirmation.
- Record the initial Offroad setting in a private recovery receipt and restore that value on explicit rollback.
- Add offline checks for missing or damaged receipts, interrupted writes, repeated operations, and local locking.

### Earlier standalone prototype

- Prepare the standalone Offroad / Compass correction for the reviewed Delphi 874B navigation-equipped configuration.
- Verify the stock configuration with pinned SHA-256 digests and preserve all menu settings outside the Offroad bit.
- Verify the installer and one-bit behavior offline with synthetic configuration fixtures. Original in-vehicle evidence covers normal reboot and menu operation.
