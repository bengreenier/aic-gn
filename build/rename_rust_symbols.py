#!/usr/bin/env python3
"""
Rename Rust runtime symbols in a static library to prevent conflicts.

This script renames Rust runtime symbols (like rust_eh_personality) to
library-specific names (like aic_rust_eh_personality) to prevent conflicts
when linking with other Rust code.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# Rust runtime symbols that commonly cause conflicts
# These will be renamed from "symbol" to "aic_symbol"
RUST_SYMBOLS_TO_RENAME = [
    "rust_eh_personality",
    "rust_begin_unwind",
    "rust_panic",
    "rust_oom",
    "__rust_alloc",
    "__rust_dealloc",
    "__rust_realloc",
    "__rust_alloc_zeroed",
    "__rust_alloc_error_handler",
]


def find_objcopy_tool():
    """Find an appropriate objcopy tool (llvm-objcopy or objcopy)."""
    candidates = [
        "llvm-objcopy",
        "llvm-objcopy-18",
        "llvm-objcopy-17",
        "llvm-objcopy-16",
        "objcopy",
    ]
    
    for tool in candidates:
        if shutil.which(tool):
            return tool
    
    return None


def find_ar_tool():
    """Find an appropriate ar tool (llvm-ar or ar)."""
    candidates = [
        "llvm-ar",
        "llvm-ar-18",
        "llvm-ar-17",
        "llvm-ar-16",
        "ar",
    ]
    
    for tool in candidates:
        if shutil.which(tool):
            return tool
    
    return None


def rename_symbols_in_archive(lib_path: Path, output_path: Path, prefix: str = "aic_") -> None:
    """
    Rename Rust symbols in a static library (.a or .lib).
    
    This works by:
    1. Extracting all object files from the archive
    2. Renaming symbols in each object file
    3. Recreating the archive with renamed objects
    
    Args:
        lib_path: Path to input static library
        output_path: Path to output static library
        prefix: Prefix to add to renamed symbols
    """
    objcopy = find_objcopy_tool()
    ar = find_ar_tool()
    
    if not objcopy or not ar:
        print(f"Error: Required tools not found.", file=sys.stderr)
        print(f"  objcopy: {objcopy or 'NOT FOUND'}", file=sys.stderr)
        print(f"  ar: {ar or 'NOT FOUND'}", file=sys.stderr)
        print(f"Cannot rename symbols. Copying library as-is.", file=sys.stderr)
        shutil.copy2(lib_path, output_path)
        return
    
    print(f"Using {ar} and {objcopy} to rename Rust symbols...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            # Step 1: Extract all object files from the archive
            print(f"Extracting objects from {lib_path}...")
            result = subprocess.run(
                [ar, "x", str(lib_path.absolute())],
                cwd=temp_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Step 2: Find all extracted object files
            obj_files = list(temp_path.glob("*.o")) + \
                       list(temp_path.glob("*.obj")) + \
                       list(temp_path.glob("*.rcgu.o"))  # Rust codegen units
            
            if not obj_files:
                print("Warning: No object files found in archive", file=sys.stderr)
                shutil.copy2(lib_path, output_path)
                return
            
            print(f"Found {len(obj_files)} object files")
            
            # Step 3: Build redefine arguments for objcopy
            redefine_args = []
            for symbol in RUST_SYMBOLS_TO_RENAME:
                new_symbol = f"{prefix}{symbol}"
                redefine_args.extend(["--redefine-sym", f"{symbol}={new_symbol}"])
                # Also rename DWARF debug reference symbols
                redefine_args.extend(["--redefine-sym", f"DW.ref.{symbol}=DW.ref.{new_symbol}"])
            
            # Step 4: Rename symbols in each object file
            print(f"Renaming Rust symbols in object files...")
            renamed_count = 0
            
            for obj_file in obj_files:
                result = subprocess.run(
                    [objcopy] + redefine_args + [str(obj_file)],
                    capture_output=True,
                    text=True,
                    check=False  # Some objects might not have these symbols
                )
                if result.returncode == 0:
                    renamed_count += 1
            
            print(f"Processed {renamed_count} object files")
            
            # Step 5: Recreate the archive with renamed objects
            print(f"Creating new archive {output_path}...")
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Remove output if it exists
            if output_path.exists():
                output_path.unlink()
            
            # Create new archive
            obj_file_strs = [str(f.name) for f in obj_files]  # Use relative names
            result = subprocess.run(
                [ar, "rcs", str(output_path.absolute())] + obj_file_strs,
                cwd=temp_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"✓ Successfully renamed Rust symbols in {output_path}")
            print(f"  Symbols renamed: {', '.join([f'{s} → {prefix}{s}' for s in RUST_SYMBOLS_TO_RENAME[:3]])}...")
            
        except subprocess.CalledProcessError as e:
            print(f"Error processing archive: {e}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            print("Falling back to copying library as-is.", file=sys.stderr)
            shutil.copy2(lib_path, output_path)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            shutil.copy2(lib_path, output_path)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Rename Rust symbols in a static library to prevent conflicts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script renames Rust runtime symbols in a static library to prevent
conflicts when linking with other Rust code. For example:
  rust_eh_personality → aic_rust_eh_personality

Examples:
  %(prog)s input.a output.a
  %(prog)s aic.lib aic_renamed.lib --prefix aic_
        """
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="Input static library file (.a or .lib)"
    )
    
    parser.add_argument(
        "output",
        type=Path,
        help="Output static library file"
    )
    
    parser.add_argument(
        "--prefix",
        default="aic_",
        help="Prefix to add to renamed symbols (default: aic_)"
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    try:
        rename_symbols_in_archive(args.input, args.output, args.prefix)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
