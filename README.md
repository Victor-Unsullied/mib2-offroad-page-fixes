# MIB2 Offroad Page Fixes

Show the factory **Offroad / Compass** page on a supported Delphi MIB2 by changing its visibility setting.

**Experimental v0.1.0 prerelease. The installer has not been tested on Windows or against a live head unit.**

![Offroad information page on a Delphi MIB2 head unit](docs/offroad-gauges.jpg)

*Offroad page on the project car during earlier development. The installer changes whether this page is visible.*

## Before you start

- Check the unit's system information. This installer supports the navigation-equipped **Delphi 874B** with software train **MST2_EU_VW_P0635D** and MU **0757** on the reviewed vehicle configuration.
- Check the label of the adapter plugged into the head unit for **D-Link DUB-E100**. Connect its Ethernet cable to your computer. Windows can check its own Ethernet connection and route to the supplied IP. Check the model on the label because the adapter plugs into the head unit. The head unit’s maintenance service (DebugSPI, TCP port 15001) must already be available. [D-Link connection guide](https://utkulekesiz.com/en/blog/mib2-dlink-connection/)
- Have the IP address displayed in the head unit’s service menu ready. The wizard offers **192.168.1.4** as a default. Press Enter only if it matches the unit, or type the address shown on the unit. Use Python 3.10 or later.
- Park the vehicle. Keep the head unit powered and the cable connected until the installer finishes verifying the setting.

## Install

Download and extract the installer ZIP. On Windows, double-click `Install.cmd` to start the wizard. To check the package or read the instructions first, open PowerShell in the extracted folder. [GitHub prerelease](https://github.com/Victor-Unsullied/mib2-offroad-page-fixes/releases/tag/v0.1.0)

```powershell
py -3 -B install.py --check
py -3 -B install.py --plan
py -3 -B install.py
```

1. Press Enter for English or type `tr` for Turkish. Confirm the model and software versions, then enter the IPv4 address from the unit's service menu.
2. Enter a code unique to your head unit, such as its serial number. This lets the installer match your saved setting during rollback. The recovery file stores a fingerprint of the code. Keep the code and the `state/` folder private.
3. The installer checks that the connected unit's vehicle configuration matches the reviewed setup. It reads the Offroad setting and shows its current value before asking to change it. Press Enter at a confirmation to exit. When you confirm, the installer saves the original setting before changing it and reads the setting again to verify the result.
4. Restart the head unit normally and check that the page opens in the car's menus.

To check the current setting, run the read-only inspection. It uses the same connection and IPv4 address and keeps the recovery file as it is.

```powershell
py -3 -B install.py --inspect
```

## Roll back

Use the same physical unit, IPv4 address, private code and recovery folder.

```powershell
py -3 -B install.py --rollback
```

The installer shows the current setting and the saved setting it would restore. If they already match, it reports the verified result with no change to the unit. If an earlier operation stopped after a possible change, restart the unit normally and read its current setting with `--inspect` before attempting rollback. Keep the recovery folder available until you finish. See [RUNBOOK.txt](RUNBOOK.txt) for details and legacy commands.

## Offline checks

```powershell
py -3 -B -m unittest discover -s tests -p 'test_*.py' -v
py -3 -B tests/check_portability.py
```

The tests use simulated unit data. They cover cancellation, rollback, interrupted writes, and preservation of the Think Blue Trainer setting. The original correction was checked in a vehicle through a normal reboot. The guided installer was checked offline on macOS. Windows, live head-unit behavior, and persistence after full power removal remain unverified.

Report a bug or share a compatibility result in GitHub Issues. Include your head-unit model, Train, MU and project version. Share only reviewed error text or screenshots. [Open an issue](https://github.com/Victor-Unsullied/mib2-offroad-page-fixes/issues/new/choose)
