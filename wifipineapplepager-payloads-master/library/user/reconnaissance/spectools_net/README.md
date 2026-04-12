# Spectools Net Payload

Simple WiFi Pineapple Pager payload that launches `spectool_net` in the background. It verifies connected hardware with `spectool_raw --list`, then exposes the TCP server (default port `30569`) so you can connect from a desktop `spectool_gtk` client.

## Usage

```bash
./payload start    # start spectool_net in the background
./payload status   # check PID and listening socket
./payload stop     # stop the server and clean up the PID file
```

Override the listener port by exporting `SPECTOOL_NET_PORT=XXXX` before running the script. Additional CLI flags for `spectool_net` can be passed via `SPECTOOL_NET_FLAGS`.
