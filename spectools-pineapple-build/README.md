# Spectools for Pineapple Pager

Successfully compiled spectools for **Pineapple Pager 24.10.1** (ramips/mt76x8, mipsel_24kc)

## Contents

### Binaries (`bin/`)
- **spectool_raw** - Raw spectrum analyzer tool
- **spectool_net** - Network spectrum analyzer server

### Libraries (`lib/`)
- libusb-0.1.so.4.4.4 - USB compatibility library
- libusb-1.0.so.0.4.0 - Modern USB library

## Installation on Pineapple Pager

### Option 1: Quick Install
```bash
# Copy files to your Pineapple Pager
scp -r bin/* root@pager:/usr/bin/
scp -r lib/* root@pager:/usr/lib/

# Make binaries executable
ssh root@pager "chmod +x /usr/bin/spectool_*"

# Test
ssh root@pager "spectool_raw --help"
```

### Option 2: Manual Install
1. Copy this entire directory to your Pineapple Pager
2. On the device:
```bash
cp bin/* /usr/bin/
cp lib/* /usr/lib/
chmod +x /usr/bin/spectool_*
ldconfig  # Update library cache
```

## Usage

### spectool_raw
Raw spectrum analyzer - captures spectrum data from USB devices
```bash
spectool_raw [options]
```

### spectool_net
Network server mode - allows remote connections to view spectrum data
```bash
spectool_net [options]
```

## Dependencies
The binaries depend on the following (should be present on Pineapple Pager):
- `libc.so` (musl C library)
- `libgcc_s.so.1` (GCC support library)
- `libpthread.so` (POSIX threads)
- `libm.so` (math library)

The custom-compiled USB libraries are included in the `lib/` directory.

## Build Information
- **Target**: ramips/mt76x8
- **Architecture**: mipsel_24kc
- **ABI**: o32, MIPS32r2, soft-float
- **Toolchain**: OpenWrt SDK GCC 14.3.0 with musl
- **Build Date**: January 2, 2026

## Supported Hardware
- Wi-Spy devices
- Ubertooth U1
- Other USB spectrum analyzers supported by spectools

## Notes
- GTK and curses interfaces were not compiled (headless target)
- The binaries are stripped for minimal size
- All libraries are compiled with matching ABI for compatibility

## Troubleshooting

If you get "library not found" errors:
```bash
export LD_LIBRARY_PATH=/usr/lib:$LD_LIBRARY_PATH
```

To verify the binaries:
```bash
file /usr/bin/spectool_raw
ldd /usr/bin/spectool_raw
```
