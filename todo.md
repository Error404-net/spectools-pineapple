### Feature: Hak5 Pager Payload Installer & Waterfall Viewer

**Overview**
Design a payload-based installation and execution workflow tailored for the Hak5 Pager. The system should follow the standard Hak5 payload model: users upload files, navigate via hardware buttons, and execute scripts directly on-device.

---

### Installer Payload (SpecTools Deployment)

**Purpose**
Enable simple, repeatable installation of SpecTools binaries using the Pager’s native payload system.

**Workflow**

1. **Payload Transfer**

   * User uploads a folder named `specctools-payload` to the Pager via SCP.
   * Payload structure:

     ```
     /payloads/specctools/
       ├── install.sh
       ├── bin/
       ├── config/
       └── assets/
     ```

2. **On-Device Navigation**

   * User uses Pager hardware buttons to:

     * Navigate to `Payloads → Specctools`
     * Select `install.sh`

3. **Execution**

   * `install.sh` performs:

     * Validation of environment (storage, permissions, dependencies)
     * Copying binaries to appropriate system paths (e.g., `/opt/specctools/`)
     * Setting executable permissions
     * Creating config directories (e.g., `/etc/specctools/`)
     * Registering the app in the Pager menu (if applicable)

4. **Feedback**

   * Display progress on screen:

     * “Installing…”
     * “Copying binaries…”
     * “Complete” or error messages

---

### Waterfall Viewer Payload

**Purpose**
Provide a visual RF waterfall display similar to observation/monitoring screens, accessible as a standalone payload script.

**Workflow**

1. **Payload Structure**

   ```
   /payloads/specctools-waterfall/
     ├── waterfall.sh
     ├── renderer/
     └── configs/
   ```

2. **Execution**

   * User navigates:

     * `Payloads → Specctools Waterfall → waterfall.sh`
   * Script initializes:

     * RF interface (e.g., SDR or supported radio module)
     * Rendering engine for waterfall display

3. **Display**

   * Real-time waterfall visualization:

     * Frequency vs time (vertical scroll)
     * Signal strength via color gradient
   * Optimized for Pager screen constraints (low-res, efficient rendering)

4. **Controls (via buttons)**

   * Up/Down: Adjust frequency range or zoom
   * Left/Right: Change gain or sensitivity
   * Select: Pause/Resume
   * Back: Exit to menu

---

### Key Requirements

* Must follow Hak5 payload conventions (drop-in, script-driven execution)
* No external UI dependencies beyond Pager display
* Fast startup and low resource usage
* Clear on-device feedback and error handling
* Modular: Installer and Waterfall operate as separate payloads

---

### Goal

Deliver a **plug-and-play experience** where:

* Users SCP payloads → run via buttons → tools install and operate immediately
* Feels native to Hak5 ecosystem while enabling advanced RF tooling
