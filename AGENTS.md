# Repository Guidelines

## Project Structure & Module Organization
Source lives in the repo root as paired `.c` and `.h` files. `spectool_gtk_*` implements the GTK visualizer, `spectool_net_*` handles the network daemon, while `wispy_hw_*` and `ubertooth_hw_u1.*` adapt specific radios. Autotools inputs (`configure.in`, `Makefile.in`, `config.h.in`) define the portable build. The `spectools-pineapple-build/` subtree is a prebuilt toolchain drop for the Pineapple Pager target—keep it untouched unless you regenerate binaries following its `README.md`.

## Build, Test, and Development Commands
Run `./configure` to detect GTK, libusb, and localization paths; pass `--disable-gtk` for headless builds or `--host=<triplet>` when cross-compiling. Invoke `make` to compile all binaries, and `make install` to deploy into the configured prefix. Developers typically iterate with `make clean && make` after dependency changes. To sanity-check locally, run `./spectool_raw --list` to confirm device discovery or `./spectool_gtk` for the UI build.

## Coding Style & Naming Conventions
Match the existing K&R-style C with hard tabs for indentation and brace placement on the same line as control statements. Public symbols follow the `Spectool_*` or `wispy_*` prefixes; keep new modules consistent. Macros and constants stay uppercase with underscores. Include headers from the local project via quotes, and prefer existing helper APIs over ad-hoc platform calls.

## Testing Guidelines
There is no automated test harness. Validate changes by exercising `spectool_raw` against supported hardware, watching for regressions in the reported frequency ranges and sample rates. For Pineapple builds, confirm binaries in `spectools-pineapple-build/bin/` still execute under `ldd` on-target and that USB access remains intact. Document manual test steps in the PR when they go beyond the default smoke checks.

## Commit & Pull Request Guidelines
Use concise, action-oriented commit messages ("Fix libusb timeout handling"), mirroring the short style in `git log`. Squash fixup commits before opening a PR. Each PR should describe the rationale, list manual verification, and link to related issues or firmware tickets. Attach screenshots or console captures when UI output or device enumeration changes.

## Hardware & Deployment Notes
If you ship new binaries, refresh the instructions in `spectools-pineapple-build/README.md` and verify the bundled `libusb` versions. Remind reviewers of any required udev rule updates (`99-wispy.rules`) whenever USB permissions are impacted.
