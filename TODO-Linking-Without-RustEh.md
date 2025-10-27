# Cross-Platform Options for Excluding Duplicate Symbols in GN Builds

## Problem Summary

The current solution uses `objcopy` and `ar` to rename Rust symbols, but these tools are not reliably available on Windows. We need a cross-platform approach to handle duplicate Rust runtime symbols (like `rust_eh_personality`) when linking against both the aic-sdk and other Rust code (e.g., Electron).

## Research Findings

### Option 1: Linker Flags to Ignore/Allow Duplicate Symbols

#### Windows (MSVC Linker)

**`/FORCE:MULTIPLE`**
- Tells the linker to create an output file even if duplicate symbols are defined
- The linker will use the first definition it encounters
- **Pros**: Simple, no preprocessing needed
- **Cons**: 
  - Generates warnings for all duplicates (noisy)
  - Risk of using wrong symbol implementation
  - May hide legitimate errors
  - Not granular - applies to all duplicates

**Usage in GN:**
```gn
if (is_win) {
  ldflags = [ "/FORCE:MULTIPLE" ]
}
```

**`/IGNORE:4006`**
- Suppresses the specific warning for duplicate symbols (LNK4006)
- Must be combined with `/FORCE:MULTIPLE`
- **Pros**: Silences warnings
- **Cons**: Same risks as `/FORCE:MULTIPLE`, just quieter

#### Linux/macOS (GNU ld / lld / ld64)

**`-z muldefs`** (GNU ld, lld)
- Allows multiple definitions of symbols
- Uses first definition encountered
- **Pros**: Simple linker flag
- **Cons**:
  - Not supported on macOS (ld64 doesn't support `-z` options)
  - Risk of wrong implementation being used
  - Masks legitimate errors

**`-Wl,--allow-multiple-definition`** (GNU ld)
- Alternative syntax for allowing multiple definitions
- **Pros**: More explicit than `-z muldefs`
- **Cons**: Same as `-z muldefs`, plus not supported on macOS

**macOS Specific:**
- macOS's `ld64` linker doesn't have an equivalent flag
- By default, it may silently use the first definition in some cases
- Can use `-Wl,-w` to suppress warnings, but doesn't solve the problem

**Usage in GN:**
```gn
if (is_linux) {
  ldflags = [ "-Wl,-z,muldefs" ]
} else if (is_win) {
  ldflags = [ "/FORCE:MULTIPLE" ]
}
# No good option for macOS
```

**Assessment:**
- ⚠️ **Platform-inconsistent**: Different behavior on each platform
- ⚠️ **Risky**: May use wrong symbol implementation
- ⚠️ **Not recommended**: Can mask real linking errors

### Option 2: Strip Symbols Using Windows-Compatible Tools

#### Microsoft's lib.exe

**`lib.exe /REMOVE:object.obj library.lib`**
- Can remove specific object files from a static library
- **Pros**: Native Windows tool, always available with MSVC
- **Cons**:
  - Can only remove entire object files, not individual symbols
  - Rust symbols are spread across multiple object files
  - Would need to identify which objects are safe to remove
  - Very likely to break the library

**Assessment:**
- ❌ **Not viable**: Too coarse-grained, would break library functionality

#### LLVM Tools (Cross-Platform)

**`llvm-objcopy` and `llvm-ar`**
- Part of LLVM toolchain
- **Availability**:
  - Chromium/Electron: Included in depot_tools
  - Standalone: Can be installed via LLVM releases
  - Windows: Available in LLVM installer or Visual Studio
- **Pros**: 
  - Same tool/syntax across all platforms
  - Fine-grained symbol manipulation
  - Already implemented in current solution
- **Cons**:
  - Requires LLVM to be installed/available
  - Extra dependency outside of base build tools

**`llvm-strip --strip-symbol=symbol_name`**
- Can remove specific symbols from object files
- **Pros**: Precise symbol removal
- **Cons**: 
  - Must be applied to individual object files, not archives directly
  - Still requires extracting/recreating archives with `llvm-ar`
  - Same availability concerns as `llvm-objcopy`

**Assessment:**
- ✅ **Best tool-based option**: Cross-platform, precise
- ⚠️ **Availability concern**: Requires LLVM installation

#### Windows Lib.exe + Custom Tooling

**Extract, Modify, Recreate Strategy**
```bash
# Windows (using lib.exe)
lib.exe /LIST library.lib > objects.txt
lib.exe /EXTRACT:object.obj library.lib
# ... modify objects somehow ...
lib.exe /OUT:new.lib object1.obj object2.obj ...
```

- **Pros**: Uses native Windows tools
- **Cons**:
  - Still need a way to modify symbols in `.obj` files
  - No native Windows tool for symbol manipulation without full toolchain
  - Complex and fragile

**Assessment:**
- ❌ **Not viable**: No good Windows-native way to modify symbols in objects

### Option 3: Configure Build System to Exclude/Isolate Symbols

#### GN `libs` vs `public_deps` Strategy

**Isolate Static Libraries**
- Use `libs` (not `public_deps`) to prevent symbol propagation
- Current BUILD.gn already does this correctly

**Example:**
```gn
source_set("aic_c_sdk") {
  libs = [ "path/to/libaic.a" ]  # Symbols not propagated
  # vs
  # public_deps = [ ":other_target" ]  # Symbols ARE propagated
}
```

**Assessment:**
- ✅ **Already implemented**: Current BUILD.gn uses this correctly
- ⚠️ **Doesn't solve duplicate symbols**: Just controls propagation, not conflicts

#### Partial Linking / Object File Filtering

**`ld -r` (Relocatable Link)**
- Create a partially linked object that excludes certain symbols
- **Pros**: Can manually exclude objects
- **Cons**:
  - Complex to set up in GN
  - Platform-specific behavior
  - May break internal library references
  - Not well-supported in GN's action() system

**Assessment:**
- ❌ **Too complex**: Not worth the maintenance burden

#### Weak Symbols (Not Applicable)

**`__attribute__((weak))` or `/ALTERNATENAME`**
- Allows multiple definitions, uses "strong" definition over "weak"
- **Cons**:
  - Requires recompiling the Rust code (not possible with prebuilt binaries)
  - Not under our control

**Assessment:**
- ❌ **Not viable**: Can't modify prebuilt binaries

### Option 4: Separate Link Units with Dynamic Loading

**Runtime Loading Strategy**
- Load aic-sdk as a shared library (.dll/.so/.dylib) instead of static
- Each shared library has its own symbol namespace

**Implementation:**
```gn
# Have aic-sdk distributed as shared library instead
shared_library("aic_shared") {
  # ...
}
```

**Pros:**
- Complete symbol isolation
- No symbol conflicts possible
- Works on all platforms

**Cons:**
- Requires changing SDK distribution format
- Not under our control (external SDK)
- Runtime dependency management more complex
- Performance overhead from dynamic linking

**Assessment:**
- ✅ **Would work perfectly**
- ❌ **Not viable**: Requires SDK vendor to change distribution format

### Option 5: Link Time Optimization (LTO) + Internalization

**LTO with Symbol Internalization**
- Use LTO to make symbols internal/hidden after optimization
- Symbols become local to their compilation unit

**GN Configuration:**
```gn
config("lto_config") {
  if (is_win) {
    cflags = [ "/GL" ]          # Whole program optimization
    ldflags = [ "/LTCG" ]       # Link-time code generation
  } else {
    cflags = [ "-flto" ]
    ldflags = [ "-flto" ]
  }
}
```

**Pros:**
- May inline or internalize duplicate symbols automatically
- Performance benefits from optimization

**Cons:**
- Significantly increases build time
- Not guaranteed to solve symbol conflicts
- May not work with pre-built static libraries (depends on LTO format)
- Rust's LTO may conflict with C/C++ LTO

**Assessment:**
- ⚠️ **Experimental**: May help but not reliable
- ❌ **Not recommended**: Too many unknowns and downsides

## Recommended Solutions (Ranked)

### 1. ✅ Ensure LLVM Tools Available (Best Long-Term)

**Strategy:** Make `llvm-objcopy` and `llvm-ar` available on all build machines

**Implementation:**
- For Chromium/Electron builds: Already available via depot_tools
- For Windows standalone: Add LLVM to build requirements
- Update BUILD.gn to verify tools exist and fail gracefully

**Advantages:**
- Cross-platform consistency
- Fine-grained control
- Safe (renamed symbols are isolated)
- Already implemented

**Actions:**
```gn
# In BUILD.gn, add verification
action("verify_llvm_tools") {
  script = "build/verify_build_tools.py"
  outputs = [ "$target_gen_dir/tool_check.stamp" ]
}

action("rename_rust_symbols") {
  deps = [ ":verify_llvm_tools", ":download_aic_sdk" ]
  # ... rest of existing action ...
}
```

**Documentation needed:**
- Add clear requirements to README
- Provide LLVM installation instructions for Windows
- Add build-time error messages if tools missing

### 2. ⚠️ Linker Flags as Fallback (Use Carefully)

**Strategy:** Use platform-specific linker flags if symbol renaming unavailable

**Implementation:**
```gn
config("allow_duplicate_rust_symbols") {
  # Only apply if symbol renaming failed
  if (is_win) {
    ldflags = [ 
      "/FORCE:MULTIPLE",
      "/IGNORE:4006",  # Suppress duplicate symbol warnings
    ]
  } else if (is_linux) {
    ldflags = [ "-Wl,-z,muldefs" ]
  }
  # Note: No good option for macOS
}

source_set("aic_c_sdk") {
  # Only add this config if rename_rust_symbols failed
  if (!can_rename_symbols) {
    configs += [ ":allow_duplicate_rust_symbols" ]
  }
  # ...
}
```

**Advantages:**
- Works when LLVM tools unavailable
- Simple to implement
- No preprocessing needed

**Disadvantages:**
- Risk of using wrong symbol implementation
- May mask legitimate link errors
- Doesn't work on macOS
- Platform-specific behavior

**When to use:**
- As a fallback only
- With clear warnings to user
- For development/testing builds only

### 3. ⚠️ Hybrid Approach (Most Practical)

**Strategy:** Try symbol renaming first, fall back to linker flags if unavailable

**Implementation Flow:**
1. Try to find `llvm-objcopy` and `llvm-ar`
2. If found: Rename symbols (current approach)
3. If not found: 
   - Emit warning
   - Copy library as-is
   - Add linker flags to allow duplicates
   - Document that symbols may conflict

**Code:**
```python
# In rename_rust_symbols.py
def rename_symbols_in_archive(lib_path, output_path, prefix="aic_"):
    objcopy = find_objcopy_tool()
    ar = find_ar_tool()
    
    if not objcopy or not ar:
        print("WARNING: LLVM tools not found. Symbols will NOT be renamed.")
        print("Build may use duplicate symbol linker flags as fallback.")
        shutil.copy2(lib_path, output_path)
        
        # Create marker file to signal fallback needed
        marker = output_path.parent / ".needs_linker_fallback"
        marker.touch()
        return
    
    # ... rest of renaming logic ...
```

```gn
# In BUILD.gn
action("rename_rust_symbols") {
  # ... existing action ...
  
  # Output both the library and potentially a fallback marker
  outputs = [
    aic_lib_file_renamed,
    "$target_gen_dir/lib/.needs_linker_fallback",  # May or may not be created
  ]
}

# Check if fallback is needed
needs_symbol_renaming_fallback = 
    exec_script("build/check_fallback_marker.py",
                [ rebase_path("$target_gen_dir/lib/.needs_linker_fallback") ],
                "value")

source_set("aic_c_sdk") {
  deps = [ ":rename_rust_symbols" ]
  
  # Add fallback linker flags if symbol renaming failed
  if (needs_symbol_renaming_fallback) {
    configs += [ ":allow_duplicate_rust_symbols" ]
  }
  
  # ... rest of target ...
}
```

**Advantages:**
- Best of both worlds
- Graceful degradation
- Works even without LLVM tools
- Safe when tools available

**Disadvantages:**
- More complex build logic
- Still has fallback risks
- Fallback doesn't work on macOS

## Summary Table

| Approach | Cross-Platform | Safe | Complexity | Recommended |
|----------|----------------|------|------------|-------------|
| **LLVM Tools (current)** | ✅ Yes | ✅ Safe | Medium | ✅ Yes (with better docs) |
| **Linker Flags** | ⚠️ Partial (not macOS) | ⚠️ Risky | Low | ⚠️ Fallback only |
| **Hybrid (LLVM + flags)** | ⚠️ Partial | ✅ Safe (when LLVM available) | High | ✅ Yes |
| **Windows lib.exe** | ❌ Windows only | ❌ Too coarse | Medium | ❌ No |
| **Shared library** | ✅ Yes | ✅ Safe | N/A | ❌ Not under our control |
| **Partial linking** | ⚠️ Partial | ⚠️ Complex | Very High | ❌ No |
| **LTO internalization** | ✅ Yes | ⚠️ Unreliable | Medium | ❌ No |

## Recommendations

### Immediate Actions

1. **Document LLVM Requirements**
   - Update README with clear LLVM installation instructions
   - Specify minimum LLVM version
   - Provide download links for Windows users

2. **Add Build-Time Verification**
   - Check for LLVM tools before attempting symbol rename
   - Print clear error message with installation instructions
   - Provide link to documentation

3. **Implement Fallback Option**
   - Add linker flags config for when tools unavailable
   - Add marker file system to track when fallback is used
   - Log warning when fallback is active

### Long-Term Improvements

1. **Upstream Solution**
   - Contact aic-sdk maintainers about symbol conflicts
   - Request either:
     - Shared library distribution option
     - Pre-renamed symbols in static builds
     - `-fvisibility=hidden` compilation for Rust symbols

2. **Alternative: Weak Symbol Builds**
   - Request SDK builds with weak symbols for Rust runtime
   - Would allow multiple definitions naturally

3. **Build System Improvements**
   - Create GN helper functions for symbol management
   - Make approach reusable for other Rust libraries

## Implementation Priority

**Phase 1 (Immediate):**
- [ ] Add `verify_build_tools.py` script
- [ ] Update README with LLVM requirements
- [ ] Add better error messages when tools missing

**Phase 2 (Short-term):**
- [ ] Implement linker flag fallback
- [ ] Add marker file system for fallback detection
- [ ] Test fallback on Windows without LLVM

**Phase 3 (Long-term):**
- [ ] Contact SDK maintainers about upstream solutions
- [ ] Consider contributing build system improvements to GN
- [ ] Document patterns for other projects

## Windows-Specific Notes

### LLVM Installation Options for Windows

1. **Visual Studio 2022**
   - Includes LLVM tools (Clang/LLVM toolchain component)
   - Path: `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\x64\bin`

2. **LLVM Official Releases**
   - Download from: https://github.com/llvm/llvm-project/releases
   - Install to: `C:\Program Files\LLVM`
   - Add to PATH: `C:\Program Files\LLVM\bin`

3. **Chromium depot_tools**
   - Already includes LLVM tools
   - Automatically in PATH when depot_tools is configured

4. **Chocolatey Package Manager**
   ```powershell
   choco install llvm
   ```

### Verifying LLVM Tools on Windows

```powershell
# Check if tools are available
where llvm-ar
where llvm-objcopy

# Should output paths like:
# C:\Program Files\LLVM\bin\llvm-ar.exe
# C:\Program Files\LLVM\bin\llvm-objcopy.exe
```

## Conclusion

The **hybrid approach** is most practical:
1. Continue using LLVM tools for symbol renaming (safest, most reliable)
2. Add fallback linker flags when LLVM unavailable (graceful degradation)
3. Document requirements clearly
4. Provide helpful error messages

This gives us:
- ✅ Works on all platforms (Windows, Linux, macOS)
- ✅ Safe when LLVM available (preferred path)
- ✅ Graceful fallback when LLVM unavailable
- ✅ Clear communication to users about build state
- ⚠️ Requires documenting LLVM as a dependency

The current `objcopy`/`ar` approach is actually the right one - we just need to ensure LLVM's versions are available and document this requirement clearly.
