# Rust Symbol Conflict Resolution

## Problem

When integrating the aic-sdk into projects that already contain Rust code (like Electron), you may encounter duplicate symbol errors:

```
lld-link: error: duplicate symbol: rust_eh_personality
>>> defined at aic.lib(aic.aic.94041bf2075ed70b-cgu.0.rcgu.o)
>>> defined at libstd_std.rlib(libstd_std.std.282db80be06cad44-cgu.11.rcgu.o)
```

This occurs because both the aic-sdk and the host project (e.g., Electron) include Rust standard library code, leading to duplicate definitions of Rust runtime symbols like `rust_eh_personality`.

## Solution Implemented

The build system now **renames Rust symbols** in the aic-sdk library to prevent conflicts. This is done by:

1. Downloading the original aic-sdk static library
2. Extracting all object files from the archive
3. Using `objcopy`/`llvm-objcopy` to rename Rust symbols with an `aic_` prefix
4. Recreating the archive with the renamed symbols

### Symbol Renaming

The following symbols are renamed:

| Original Symbol | Renamed Symbol |
|----------------|----------------|
| `rust_eh_personality` | `aic_rust_eh_personality` |
| `rust_begin_unwind` | `aic_rust_begin_unwind` |
| `rust_panic` | `aic_rust_panic` |
| `rust_oom` | `aic_rust_oom` |
| `__rust_alloc` | `aic___rust_alloc` |
| `__rust_dealloc` | `aic___rust_dealloc` |
| `__rust_realloc` | `aic___rust_realloc` |
| `__rust_alloc_zeroed` | `aic___rust_alloc_zeroed` |
| `__rust_alloc_error_handler` | `aic___rust_alloc_error_handler` |

DWARF debug reference symbols (e.g., `DW.ref.rust_eh_personality`) are also renamed accordingly.

## How It Works

### Build Process

The GN build configuration uses a two-step process:

```gn
# Step 1: Download the SDK
action("download_aic_sdk") {
  # Downloads original library to lib/aic.lib or lib/libaic.a
}

# Step 2: Rename Rust symbols
action("rename_rust_symbols") {
  script = "build/rename_rust_symbols.py"
  deps = [ ":download_aic_sdk" ]
  # Creates lib/aic_renamed.lib or lib/libaic_renamed.a
}

# Step 3: Link against renamed library
source_set("aic_c_sdk") {
  deps = [ ":rename_rust_symbols" ]
  libs = [ aic_lib_file_renamed ]  # Uses the renamed library
}
```

### Symbol Renaming Script

The `build/rename_rust_symbols.py` script:
- Works on all platforms (Linux, macOS, Windows)
- Requires `ar`/`llvm-ar` and `objcopy`/`llvm-objcopy` to be available
- Falls back to copying the library as-is if tools are not available
- Processes all object files in the static library archive

## Advantages Over Other Approaches

### ✅ This Approach (Symbol Renaming)
- **No global linker flags**: Doesn't affect other parts of the build
- **Complete isolation**: Symbols are truly separate, not just hidden
- **Works everywhere**: Same approach on Linux, macOS, and Windows
- **Safe**: No risk of using the wrong implementation

### ❌ Alternative: Global Linker Flags
- Affects entire link step
- May hide other legitimate errors
- Platform-specific behavior
- Risk of using wrong symbol implementation

### ❌ Alternative: Symbol Localization
- Symbols still present, just hidden
- May not work consistently across all linkers
- Still potential for conflicts in some scenarios

## Requirements

The symbol renaming requires these tools to be available:
- **Linux/macOS**: `ar` and `objcopy` (or `llvm-ar` and `llvm-objcopy`)
- **Windows**: `llvm-ar` and `llvm-objcopy` (part of LLVM/Clang installation)

These tools are typically available in:
- Chromium/Electron build environments (via depot_tools)
- Standard Linux development packages
- Xcode Command Line Tools on macOS
- LLVM installation on Windows

If the tools are not available, the script will fall back to using the original library (which may cause symbol conflicts).

## Testing

To verify the fix works in your Electron build:

1. Integrate this updated aic-gn into your Electron build
2. Build a target that links against both Electron's Rust code and the aic-sdk
3. The `rust_eh_personality` duplicate symbol error should no longer occur

### Manual Testing

You can manually test the symbol renaming:

```bash
# Download the SDK
python3 build/download_c_libaries.py 0.7.0 \
  --output /tmp/aic_test \
  --platform x86_64-unknown-linux-gnu \
  --versions-file VERSIONS.txt

# Rename symbols
python3 build/rename_rust_symbols.py \
  /tmp/aic_test/lib/libaic.a \
  /tmp/libaic_renamed.a \
  --prefix aic_

# Verify symbols were renamed
nm /tmp/libaic_renamed.a | grep rust_eh_personality
# Should show: aic_rust_eh_personality (not rust_eh_personality)
```

## Technical Details

### Why Symbol Conflicts Occur

- **`rust_eh_personality`**: Rust's exception handling personality function
- **Why it's duplicated**: Both aic-sdk and Electron link against Rust's `libstd`
- **Why it's a problem**: Linkers don't allow multiple definitions of the same symbol

### Why Symbol Renaming Works

- Creates completely separate symbol namespaces
- `aic_rust_eh_personality` and `rust_eh_personality` are different symbols
- Each Rust component uses its own runtime symbols
- No ambiguity for the linker

### Archive Processing

Static libraries (`.a` and `.lib` files) are archives containing multiple object files:
1. Extract: `ar x library.a` extracts all `.o` files
2. Rename: `objcopy --redefine-sym old=new file.o` renames symbols
3. Recreate: `ar rcs new_library.a *.o` creates new archive

## Troubleshooting

### Error: "objcopy/llvm-objcopy not found"

The build tools are not in your PATH. Solutions:
- **Electron builds**: Should already have these in depot_tools
- **Linux**: Install `binutils` package
- **macOS**: Install Xcode Command Line Tools
- **Windows**: Install LLVM or use Visual Studio's tools

### Symbols still conflicting

If you still see conflicts:
1. Verify the renamed library is being used (check build output)
2. Check that the symbol is actually renamed: `nm library.a | grep rust_eh_personality`
3. Ensure the build is using the `aic_c_sdk` target (not accidentally using original library)

### Build performance

The symbol renaming adds ~10-30 seconds to the build process (one-time cost during SDK download). This is a small price for avoiding symbol conflicts.
