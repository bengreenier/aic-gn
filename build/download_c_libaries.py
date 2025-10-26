#!/usr/bin/env python3
"""
Download and extract AIC SDK C libraries for a specified platform.

This script replicates the download logic from CMakeLists.txt, providing
a Python implementation for downloading platform-specific AIC SDK binaries.
"""

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from typing import Dict, Tuple


def load_platform_config(versions_file: Path) -> Dict[str, Dict[str, Tuple[str, str]]]:
    """
    Load platform configuration from VERSIONS.txt file.
    
    Returns a nested dict: {version: {platform: (archive_ext, hash)}}
    """
    config = {}
    
    if not versions_file.exists():
        raise RuntimeError(f"VERSIONS.txt file not found: {versions_file}")
    
    with open(versions_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            try:
                parts = line.split('\t')
                if len(parts) != 2:
                    raise ValueError("Expected format: version\\tplatform, ext, hash")
                
                version = parts[0].strip()
                platform_info = parts[1].strip()
                
                # Parse platform info: "platform, ext, hash"
                platform_parts = [p.strip() for p in platform_info.split(',')]
                if len(platform_parts) != 3:
                    raise ValueError("Expected format: platform, ext, hash")
                
                platform_triplet, archive_ext, hash_value = platform_parts
                
                if version not in config:
                    config[version] = {}
                
                config[version][platform_triplet] = (archive_ext, hash_value)
                
            except Exception as e:
                raise RuntimeError(f"Error parsing VERSIONS.txt line {line_num}: {e}")
    
    return config


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def download_file(url: str, dest_path: Path) -> None:
    """Download a file from URL to destination path."""
    print(f"Downloading {url}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"Downloaded to {dest_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")


def verify_hash(file_path: Path, expected_hash: str) -> None:
    """Verify the SHA256 hash of a downloaded file."""
    print(f"Verifying SHA256 hash...")
    actual_hash = calculate_file_hash(file_path)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Hash verification failed!\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}"
        )
    print("Hash verification passed")


def extract_archive(archive_path: Path, extract_to: Path) -> None:
    """Extract archive (zip or tar.gz) to destination directory."""
    print(f"Extracting {archive_path} to {extract_to}...")
    
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    elif archive_path.suffix == ".gz" and archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(extract_to)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path}")
    
    print(f"Extracted to {extract_to}")


def download_aic_sdk(version: str, output_dir: Path, platform_triplet: str, versions_file: Path) -> None:
    """
    Download and extract AIC SDK for the specified platform.
    
    Args:
        version: SDK version to download (e.g., "0.7.0")
        output_dir: Directory to extract the SDK to
        platform_triplet: Platform triplet (required)
        versions_file: Path to VERSIONS.txt file
    """
    print(f"Platform: {platform_triplet}")
    
    # Load platform configuration
    config = load_platform_config(versions_file)
    
    if version not in config:
        raise RuntimeError(f"Version {version} not found in {versions_file}")
    
    if platform_triplet not in config[version]:
        raise RuntimeError(f"Platform {platform_triplet} not supported for version {version}")
    
    archive_ext, expected_hash = config[version][platform_triplet]
    
    # Construct download URL
    filename = f"aic-sdk-{platform_triplet}-{version}.{archive_ext}"
    url = f"https://github.com/ai-coustics/aic-sdk-c/releases/download/{version}/{filename}"
    
    print(f"Download URL: {url}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download to temporary file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / filename
        download_file(url, temp_path)
        
        # Verify hash
        verify_hash(temp_path, expected_hash)
        
        # Extract to output directory
        extract_archive(temp_path, output_dir)
    
    print(f"AIC SDK {version} successfully downloaded and extracted to {output_dir}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download and extract AIC SDK C libraries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 0.7.0 --output ./sdk --platform x86_64-unknown-linux-gnu
  %(prog)s 0.7.0 --output ./sdk --platform x86_64-pc-windows-msvc
        """
    )
    
    parser.add_argument(
        "version",
        help="AIC SDK version to download (e.g., 0.7.0)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Output directory to extract the SDK to"
    )
    
    parser.add_argument(
        "--platform", "-p",
        required=True,
        help="Platform triplet (e.g., x86_64-unknown-linux-gnu)"
    )
    
    parser.add_argument(
        "--versions-file", "-v",
        type=Path,
        default=Path("VERSIONS.txt"),
        help="Path to VERSIONS.txt file (default: VERSIONS.txt)"
    )
    
    args = parser.parse_args()
    
    try:
        download_aic_sdk(args.version, args.output, args.platform, args.versions_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
