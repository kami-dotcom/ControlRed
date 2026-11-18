# Control de red — Network Control

Download for Windows: [ControlRed.exe](https://github.com/kami-dotcom/ControlRed/releases/download/v4.1/ControlRed.exe) · [All release files](https://github.com/kami-dotcom/ControlRed/releases/tag/v4.1). Install [Npcap](https://npcap.com/#download) separately.

[Español](LEEME.md) · [Deutsch](docs/README.de.md) · [Français](docs/README.fr.md) · [简体中文](docs/README.zh.md) · [Português](docs/README.pt.md) · [Русский](docs/README.ru.md)

A local Windows dashboard for discovering devices, identifying MAC manufacturers, and managing device access with manual blocking or a per-network allowlist.

## Version 4.1

- Discovery runs once at startup or adapter selection, then only when you click **Refresh network**. Passive observation and periodic block maintenance continue. Refresh if a device is missing.
- Closing or suspending the browser tab no longer releases blocks. Keep the PC and executable running; **Unblock**, **Pause list and unblock all**, or **Exit** stops the corresponding control. A missed scan response no longer releases an existing block.
- Restoration frames use the controller’s Ethernet source MAC while retaining the correct peer MAC inside ARP/NDP, preventing source learning from moving peer MACs to the controller port. Real-network throughput still needs validation.

- A language bar switches between Spanish, English, German, French, Simplified Chinese, Portuguese and Russian.
- Navigation, dialogs, device states, errors and activity history are localized.
- Language selection is saved in the browser. The first visit uses a supported browser language, with English as fallback.
- Dates and times follow the selected locale. Device aliases, actual hostnames, adapter names and registered manufacturer names retain their original spelling.
- Changing the language does not change access rules, restart the worker or pause active controls.
- Translation files are bundled locally; no translation service or internet connection is required.

## Single-file release

For end users, distribute **ControlRed.exe** by itself, or the Windows ZIP containing only that executable. The app embeds Python, the dashboard, all seven language catalogs and the manufacturer registry. No source-code folders or separate Python installation are needed.

Npcap must be installed separately once. On first use, the app creates a datos folder beside the executable for names, permissions, recovery information and logs. Keep that folder when updating if you want to retain your settings. The versioned executable ControlRed-v4.1.exe is the same application.

The GitHub source package remains separate. The build script already uses PyInstaller's single-file mode.

## Run on Windows

1. Install [Npcap from its official website](https://npcap.com/#download). It is not bundled with this project.
2. Close an older version using its **Exit** button.
3. Run **ControlRed-v4.1.exe**. Use **Run as administrator** if the installed Npcap configuration requires it.
4. Choose your physical Ethernet or Wi-Fi adapter. Keep the PC and executable running; the browser tab can be closed.
5. Use the language bar at the top of the dashboard.

Demostracion.cmd opens simulated devices and performs no network blocking.

### Access modes

- **Manual blocking:** select devices individually.
- **Allowlist:** a block is requested for each detected device without permission. Choose **Allow**, or pre-authorize a MAC address using **Add allowed MAC**.
- **Pause list and unblock all:** stops requesting blocks and retains saved permissions.
- **Resume allowlist:** re-applies the saved policy.
- **Exit:** sends restoration messages before shutting down.

The router and this PC are protected. Permissions are saved by router MAC and device MAC. A new IP retains the same policy; a different private MAC is a new identity.

## Scope

The engine sends bidirectional ARP messages and targeted IPv6 neighbor advertisements on the selected physical link. A “Block requested” state does not prove that internet access has stopped. Router protections, client behavior, IPv6 discovery and other connections can affect the result. This is not a router firewall or an Android app.

Automatic control begins after a device is detected. It continues without an open browser tab. Network errors still trigger restoration and pause the allowlist for that session. Exiting the executable restores connections; stopping the PC also stops enforcement. Reopening the program restores its saved mode. Abrupt termination leaves a recovery journal for the next launch on the same network.

Use this tool only on networks you own or are authorized to administer.

## Run from source

Python 3.10 or later is sufficient; application code uses the standard library.

~~~powershell
python app.py
python app.py --demo
python app.py --demo --no-browser --port 8766 --lang en
~~~

The --lang option selects the console language. The dashboard remembers its language separately in browser storage. Valid codes are es, en, de, fr, zh, pt and ru.

## Tests and Windows build

~~~powershell
python -m unittest discover -s tests -v
node --test tests/i18n.test.cjs
node --check web/app.js
node --check web/i18n.js
~~~

Tests use simulated network operations. Node.js 18 or later is needed only for JavaScript tests.

~~~powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
~~~

The build script generates dist/ControlRed-v4.1.exe. It includes the web assets, all language catalogs and the offline manufacturer registry.

## Project layout

- app.py — authenticated loopback HTTP API and launcher.
- engine.py, access.py — serialized control worker, restoration and access policies.
- network.py, npcap.py, frames.py — discovery, Npcap binding and packet construction.
- vendors.py, data/manuf.gz — offline manufacturer lookup.
- i18n.py, web/i18n.js, web/locales/ — shared message catalogs and browser language selection.
- tests/ — network, controller, API and localization tests.

The API listens on 127.0.0.1 only and requires a per-launch session token. The project does not collect telemetry.

## Publishing to GitHub

Upload the contents of the prepared source package. It excludes live datos/ and datos-demo/ directories, session tokens, device aliases, access rules, logs, caches and executables. The .gitignore file protects these runtime paths in future commits. Windows executables can be distributed separately as release assets.

No project license has been selected in this source package. Add the license you choose before presenting the project as licensed open-source software. Third-party component information is in [THIRD_PARTY.md](THIRD_PARTY.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for translation changes.
