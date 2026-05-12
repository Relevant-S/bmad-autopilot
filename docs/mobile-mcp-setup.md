# Mobile MCP Setup

Operator-facing setup guide for the mobile MCP server the BMAD Agent Development Automator drives via the QA specialist on `project_type: mobile` BMAD projects (Phase 1.5 — ADR-007, see `_bmad-output/planning-artifacts/architecture.md` lines 604–659).

If `/bmad-automation init` halted on a mobile project with `mobile-blocked` (sub_classification `init-unavailable`) and the verbatim diagnostic `"Mobile MCP required for mobile projects. See docs/mobile-mcp-setup.md."`, follow this guide to install the mobile MCP, connect a device, and re-run `init`. The mobile MCP itself is `@mobilenext/mobile-mcp` v0.0.54+ (Apache-2.0 licensed; GitHub `mobile-next/mobile-mcp`).

## Prerequisites

The mobile MCP runs as an `npx`-managed stdio process Claude Code launches on demand; it does NOT spawn a separate dev server. The operator-side prerequisites:

- **node.js v22+** (the mobile MCP's runtime baseline). Check with `node --version`.
- **For iOS targets:** Xcode + Xcode Command Line Tools (`xcode-select --install`); an iOS Simulator booted (`xcrun simctl boot <device-id>`) OR a USB-connected iOS device.
- **For Android targets:** Android Platform Tools (`adb`) on `$PATH`; an Android emulator running (`emulator -avd <name>`) OR a USB-connected Android device with USB debugging enabled.
- **For iOS *physical* devices specifically** (per the upstream `mobile-next/mobile-mcp` GitHub issue #19 thread — practitioner-encountered failure mode): install `go-ios` (`npm install -g go-ios`), start a tunnel (`sudo ios tunnel start`), and forward port 8100 (`ios forward 8100 8100`). The mobile MCP cannot reach a physical iOS device without these three steps. The upstream wiki at `https://github.com/mobile-next/mobile-mcp/wiki` documents this end-to-end.

## Install + connect

Install via the canonical Claude Code MCP-add command (per architecture.md line 633 / ADR-007 Consequence 6 — verbatim):

```
claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest
```

This registers the mobile MCP with Claude Code over stdio (the default transport; SSE is available but not required for the Automator). The `-y` flag pre-accepts the npx package-fetch prompt.

### Verify the install

Invoke a no-side-effect mobile-mcp tool to confirm the install succeeded AND a device is reachable. The canonical smoke probe is `mobile_get_screen_size` — a read-only tool that succeeds iff the MCP is reachable AND a device is connected (this is the same probe `MobileMcpAvailabilityProbe.is_available()` runs at init time per `skills/bmad-automation/steps/qa-driver-mobile.md` line 45). From a Claude Code session, ask Claude to call `mobile_get_screen_size`; a clean tool-call return (a `width × height` pair) verifies the setup.

## Re-run `bmad-automation init`

With the mobile MCP installed and a device connected, re-run `/bmad-automation init` from the project root. The init flow's precondition substrate (Story 7.3's `run_init_preconditions`) re-probes the `mobile-mcp` dependency. On a clean probe-True return, the `mobile-blocked: init-unavailable` total-block emission does NOT fire; init proceeds and writes `project_type: mobile` to `_bmad/automation/config.yaml` (Story 9.2 contract). The Automator is then ready to run mobile-QA loops via `/bmad-automation run <story-id>`.

## Troubleshooting

### `mobile-blocked: init-unavailable` despite the install succeeding

Likely cause: the install completed but no device is currently reachable (Simulator not booted; physical device unplugged; iOS tunnel not started). Verify with `mobile_get_screen_size`; if that errors, walk the Prerequisites list above for the targeted platform. The iOS-physical-device case in particular requires the `go-ios` + tunnel + forward triple — re-check those three steps. Upstream reference: `https://github.com/mobile-next/mobile-mcp/wiki` and GitHub issue #19.

### `mobile-blocked: init-unavailable` because the probe times out

Likely cause: cold-start latency on the npx-stdio process. `MobileMcpAvailabilityProbe.is_available()` returns `False` on ANY tool-error, tool-absence, or timeout (per `qa-driver-mobile.md` line 45's documented behavior). Warm-start the mobile-mcp process by invoking it once from a terminal (`npx -y @mobilenext/mobile-mcp@latest` — the same command the install registers, run standalone); cancel after the process announces readiness. Subsequent Automator launches reuse the cached npm package; the cold-start latency disappears.

### The mobile MCP installs but the device is not detected

Likely causes:
- **iOS Simulator vs physical device mismatch.** The mobile MCP picks one target (Simulator OR device); if you have BOTH a booted Simulator AND a connected device, the resolution is mobile-mcp-version-specific. Boot only one at a time during initial setup. Reference: Apple Developer docs on `xcrun simctl` and Xcode Simulator management.
- **Android emulator not running OR `adb` not on `$PATH`.** Confirm `adb devices` lists at least one entry (Simulator OR device); start an emulator from Android Studio or via `emulator -avd <name>` if not. Reference: Android Studio Emulator documentation.
- **macOS / Linux / Windows host quirks.** The mobile MCP supports macOS + Linux at the v0.0.54 baseline; Windows support is host-environment-dependent. Check the upstream wiki for current platform-support matrix.

## Setup verification checklist

Run through this checklist before re-running `/bmad-automation init` to confirm the mobile MCP is correctly installed and a device is reachable:

- [ ] `node --version` reports v22 or higher.
- [ ] `claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest` completed without error.
- [ ] A device is ready: iOS Simulator booted (`xcrun simctl list devices | grep Booted`) OR Android emulator running (`emulator -list-avds`; `adb devices` lists one entry) OR physical device connected and unlocked.
- [ ] For iOS physical devices only: `go-ios` installed, tunnel running (`sudo ios tunnel start`), port forwarded (`ios forward 8100 8100`).
- [ ] Claude Code's MCP list shows `mobile-mcp` registered (`/mcp` command in a Claude Code session).
- [ ] `mobile_get_screen_size` smoke probe returns a width × height pair (confirms both MCP reachability AND device connectivity in one call).
- [ ] No other Claude Code session is holding an exclusive lock on the mobile MCP stdio process — only one session can drive the MCP at a time.

If all seven checks pass and `mobile-blocked: init-unavailable` still fires, check the Automator's `_bmad/automation/config.yaml` to confirm `project_type: mobile` is set — `run_init_preconditions` only probes `mobile-mcp` for mobile project types per NFR-I3.

## Cross-references

- ADR-007 — `_bmad-output/planning-artifacts/architecture.md` lines 604–659. The source-of-truth for the mobile MCP server choice (`@mobilenext/mobile-mcp`), the version floor pinning (`0.0.54`), and the init-vs-runtime failure-profile asymmetry.
- `schemas/dependencies.yaml` — the canonical dependency declaration `run_init_preconditions` reads. The `mobile-mcp.by_project_type.mobile.profiles.init.diagnostic` literal references THIS file by path.
- `schemas/marker-taxonomy.yaml` `mobile-blocked` entry (schema_version 1.5+) — the closed-set enumeration carrying `sub_classifications: [init-unavailable, mid-run-unavailable]` Story 9.5 landed.
- `skills/bmad-automation/steps/qa-driver-mobile.md` — the LLM-runtime binding contract for the QA wrapper's mobile-mcp tool surface composition (the ten `MobileDriver` Protocol methods ↔ mobile-mcp tool mappings).
- `skills/bmad-automation/steps/qa-mobile-heuristics.md` — the LLM-runtime binding contract for the mobile exploratory heuristics Story 9.4 landed.
