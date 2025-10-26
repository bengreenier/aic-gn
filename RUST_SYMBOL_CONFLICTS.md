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

The `BUILD.gn` file now includes a `aic_link_config` configuration that adds platform-specific linker flags to resolve this issue:

### Windows (lld-link)
```gn
ldflags += [ "-Wl,--allow-multiple-definition" ]
```

This tells the linker to allow multiple definitions of the same symbol and use the first one it encounters. When Electron invokes lld-link through clang-cl, it should accept this Unix-style linker flag.

### Linux/macOS
```gn
ldflags += [ "-Wl,--exclude-libs,ALL" ]
```

This prevents symbols from static libraries (including the aic-sdk) from being exported, which avoids the conflict entirely by keeping the Rust symbols local to the library.

## How It Works

The `aic_link_config` is added to the `public_configs` of the `aic_c_sdk` target:

```gn
source_set("aic_c_sdk") {
  public_configs = [ 
    ":aic_c_config",
    ":aic_link_config",  # <-- This propagates the linker flags
  ]
  # ...
}
```

This ensures that any target depending on `aic_c_sdk` (including Electron's targets) will automatically receive these linker flags during the final link step.

## Alternative Solutions

If the primary solution doesn't work in your environment, here are alternatives:

### Alternative 1: Windows-specific MSVC flag

If the Unix-style flag doesn't work with lld-link, try using the MSVC-style equivalent:

```gn
ldflags += [ "/FORCE:MULTIPLE" ]
```

Change line 76 in `BUILD.gn` from:
```gn
ldflags += [ "-Wl,--allow-multiple-definition" ]
```
to:
```gn
ldflags += [ "/FORCE:MULTIPLE" ]
```

### Alternative 2: Use dynamic linking

If possible, modify the aic-sdk build to produce a dynamic library (`.dll`/`.dylib`/`.so`) instead of a static library. This would naturally isolate the symbols.

### Alternative 3: Symbol renaming

Use `objcopy` or similar tools to rename conflicting symbols in the aic library before linking:

```bash
objcopy --redefine-sym rust_eh_personality=aic_rust_eh_personality libaic.a libaic_renamed.a
```

This is more complex but provides complete isolation.

## Testing

To verify the fix works in your Electron build:

1. Integrate this updated aic-gn into your Electron build
2. Build a target that links against both Electron's Rust code and the aic-sdk
3. The `rust_eh_personality` duplicate symbol error should no longer occur

## Technical Details

- **`rust_eh_personality`**: This is Rust's exception handling personality function, part of the Rust panic handling mechanism
- **Why it's duplicated**: Both aic-sdk and Electron link against the Rust standard library (`libstd`)
- **Why the solution works**: 
  - On Linux/macOS: `--exclude-libs` makes symbols local, preventing export
  - On Windows: `--allow-multiple-definition` permits duplicates and uses the first definition

## Additional Notes

- The linker flags are only applied when building executables, not intermediate libraries
- The flags are propagated through GN's `public_configs` mechanism
- This solution is compatible with GN-based build systems like Chromium/Electron
