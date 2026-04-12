# Repository Guidelines

## Project Structure & Module Organization
- Core sources live in the repo root as paired `.c` and `.h` files; look for `spectool_gtk_*` for GTK UI, `spectool_net_*` for daemon networking, and `wispy_hw_*`/`ubertooth_hw_u1.*` for hardware adapters.
- Autotools control files (`configure.in`, `Makefile.in`, `config.h.in`) define portable builds—update them together when introducing new modules.
- Treat `spectools-pineapple-build/` as read-only unless you are regenerating Pineapple binaries per its `README.md`.

## Build, Test, and Development Commands
- `./configure [--disable-gtk | --host=<triplet>]`: detect GTK, libusb, i18n paths; add switches for headless or cross builds.
- `make` / `make clean && make`: compile everything; clean first when dependencies or headers change.
- `make install`: stage binaries into the configured prefix for packaging.
- `./spectool_raw --list`: quick hardware discovery smoke test.
- `./spectool_gtk`: launches the visual analyzer; confirm rendering before shipping UI changes.

## Coding Style & Naming Conventions
- Follow K&R C with hard tabs for indentation; braces share the control line (`if (...) {`).
- Exported symbols use `Spectool_*` or `wispy_*`; internal helpers stay static or lower-case snake_case.
- Keep macros uppercase with underscores and include local headers with quotes. Reuse existing abstraction layers instead of ad-hoc OS calls.

## Testing Guidelines
- No automated suite—exercise `spectool_raw` on each supported radio to verify frequency ranges and sample rates remain stable.
- For Pineapple targets, run `ldd spectools-pineapple-build/bin/<binary>` on-device and confirm USB permissions through existing udev rules (`99-wispy.rules`).
- Document any extended manual matrix in your PR notes so reviewers can replay the checks.

## Commit & Pull Request Guidelines
- Write concise, action-oriented commits (e.g., `Fix libusb timeout handling`) and squash fixups before review.
- PRs should explain the motivation, list manual validation, link related firmware/issues, and include console logs or screenshots when outputs change.
- Flag udev or deployment impacts explicitly so downstream integrators can update their environments.
