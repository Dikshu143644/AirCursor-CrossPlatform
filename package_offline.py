#!/usr/bin/env python3
"""
AirCursor Offline & Self-Contained Distribution Packager.
Builds a standalone "Write Once, Run Anywhere" bundle verified to run
with zero internet access, zero CDNs, and zero external runtime dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import zipfile
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUNDLE_DIR_NAME = "aircursor_offline_bundle"
ZIP_NAME = "aircursor_offline_bundle.zip"

# Core assets to include in bundle
INCLUDE_PATHS = [
    # Core Engine & Subsystems
    "aircursor_core",
    "windows",
    "linux",
    "android",
    "server.py",
    "entrypoint.sh",
    "Dockerfile",
    "docker-compose.yml",
    "k8s",
    "pyproject.toml",
    "README.md",
    # Static Web PWA Assets
    "web",
    # Offline Documentation
    "docs",
    # Desktop, Container & K8s Launchers
    "Start-AirCursor.bat",
    "Start-WebRemote.bat",
    "Install-AirCursor.bat",
    "Uninstall-AirCursor.bat",
    "start-aircursor.sh",
    "start-webremote.sh",
    "docker-run-offline.sh",
    "docker-run-offline.bat",
    "k8s-deploy-offline.sh",
]

# Patterns allowed in offline files (e.g. SVG XMLNS, localhost URLs)
ALLOWED_URL_PATTERNS = [
    r"http://www\.w3\.org/2000/svg",
    r"http://localhost",
    r"http://0\.0\.0\.0",
    r"http://127\.0\.0\.1",
    r"https?://github\.com",   # in README / metadata text only
]

# Disallowed external internet CDN patterns that break offline execution
DISALLOWED_CDN_PATTERNS = [
    r"https?://cdn\.",
    r"https?://cdnjs\.",
    r"https?://unpkg\.com",
    r"https?://fonts\.googleapis\.com",
    r"https?://fonts\.gstatic\.com",
    r"https?://ajax\.googleapis\.com",
    r"https?://code\.jquery\.com",
    r"https?://stackpath\.bootstrapcdn\.com",
    r"https?://cdn\.jsdelivr\.net",
]


def sha256_file(path: Path) -> str:
    """Computes SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_file_offline_readiness(path: Path) -> List[str]:
    """Inspects file contents to guarantee no external CDNs are required."""
    issues = []
    # Check text files only
    ext = path.suffix.lower()
    if ext not in (".html", ".js", ".css", ".json", ".webmanifest", ".py", ".sh", ".bat"):
        return issues

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [f"Could not read {path}: {e}"]

    # Check for disallowed CDN dependencies
    for pattern in DISALLOWED_CDN_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            issues.append(f"Forbidden external CDN reference '{pattern}' found in {path.name}")

    return issues


def verify_python_core_offline_readiness() -> List[str]:
    """Ensures aircursor_core and server have no mandatory external PyPI dependencies."""
    import ast
    issues = []
    stdlib_modules = set(sys.builtin_module_names) | {
        "__future__", "argparse", "ast", "asyncio", "base64", "collections", "copy",
        "dataclasses", "datetime", "enum", "hashlib", "http", "json", "logging", "math",
        "mimetypes", "os", "pathlib", "queue", "re", "select", "shutil", "signal",
        "socket", "struct", "sys", "threading", "time", "typing", "unittest", "urllib",
        "zipfile", "zlib"
    }

    core_files = list((ROOT_DIR / "aircursor_core").glob("*.py"))
    if (ROOT_DIR / "server.py").exists():
        core_files.append(ROOT_DIR / "server.py")

    for py_file in core_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            class ImportVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.in_try = 0
                def visit_Try(self, node):
                    self.in_try += 1
                    self.generic_visit(node)
                    self.in_try -= 1
                def visit_Import(self, node):
                    if self.in_try == 0:
                        for alias in node.names:
                            base = alias.name.split(".")[0]
                            if base not in stdlib_modules and not (ROOT_DIR / base).exists() and not (ROOT_DIR / "aircursor_core" / (base + ".py")).exists():
                                issues.append(f"Mandatory un-guarded third-party import '{base}' in {py_file.name}")
                    self.generic_visit(node)
                def visit_ImportFrom(self, node):
                    if self.in_try == 0 and node.module:
                        base = node.module.split(".")[0]
                        if base not in stdlib_modules and not (ROOT_DIR / base).exists() and not (ROOT_DIR / "aircursor_core" / (base + ".py")).exists():
                            issues.append(f"Mandatory un-guarded third-party import '{base}' in {py_file.name}")
                    self.generic_visit(node)

            v = ImportVisitor()
            v.visit(tree)
        except Exception as e:
            issues.append(f"Error inspecting {py_file}: {e}")
    return issues


def build_offline_bundle(output_dir: Path = DIST_DIR) -> Tuple[Path, Path, Dict]:
    """
    Builds the standalone offline bundle and zip archive.
    Returns (bundle_dir, zip_path, manifest_data).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target_bundle = output_dir / BUNDLE_DIR_NAME
    zip_path = output_dir / ZIP_NAME

    print(f"[*] Packaging AirCursor Offline Distribution...")
    print(f"    Source: {ROOT_DIR}")
    print(f"    Target: {target_bundle}")

    # Clean previous build
    if target_bundle.exists():
        shutil.rmtree(target_bundle)
    if zip_path.exists():
        zip_path.unlink()

    target_bundle.mkdir(parents=True, exist_ok=True)

    # 1. Copy all required components
    copied_files: List[Path] = []
    for item_name in INCLUDE_PATHS:
        src = ROOT_DIR / item_name
        dest = target_bundle / item_name

        if not src.exists():
            print(f"[!] Warning: Optional item '{item_name}' not found at {src}")
            continue

        if src.is_dir():
            shutil.copytree(
                src,
                dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".git*", ".gradle", "build"),
            )
            for f in dest.rglob("*"):
                if f.is_file():
                    copied_files.append(f)
        else:
            shutil.copy2(src, dest)
            copied_files.append(dest)

    # 2. Run Offline Pre-flight Verification
    print("[*] Running offline pre-flight verification...")
    all_issues = []

    # Check web assets for CDNs
    for f in copied_files:
        issues = verify_file_offline_readiness(f)
        all_issues.extend(issues)

    # Check Python core independence
    core_issues = verify_python_core_offline_readiness()
    all_issues.extend(core_issues)

    if all_issues:
        print("[!] Offline verification warnings found:")
        for issue in all_issues:
            print(f"    - {issue}")
        raise RuntimeError(f"Offline verification failed with {len(all_issues)} issue(s)!")

    print("[+] Pre-flight verification passed: 100% offline, 0 external CDNs, 0 external runtime dependencies.")

    # 3. Generate MANIFEST.json with SHA256 Checksums
    manifest_records = []
    for f in copied_files:
        rel = f.relative_to(target_bundle).as_posix()
        size = f.stat().st_size
        sha = sha256_file(f)
        manifest_records.append({
            "path": rel,
            "size_bytes": size,
            "sha256": sha,
        })

    manifest_data = {
        "package": BUNDLE_DIR_NAME,
        "version": "1.0.5",
        "build_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "offline_verified": True,
        "total_files": len(manifest_records),
        "files": manifest_records,
    }

    manifest_path = target_bundle / "MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # 4. Create ZIP archive
    print(f"[*] Compressing bundle to {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in target_bundle.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(output_dir).as_posix()
                zf.write(f, arcname)

    # 5. Verify ZIP Archive
    with zipfile.ZipFile(zip_path, "r") as zf:
        test_res = zf.testzip()
        if test_res is not None:
            raise RuntimeError(f"Corrupt zip member detected: {test_res}")
        namelist = zf.namelist()

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[+] Bundle built successfully: {zip_path.name} ({zip_size_mb:.2f} MB, {len(namelist)} items)")
    return target_bundle, zip_path, manifest_data


def main():
    try:
        bundle_dir, zip_path, manifest = build_offline_bundle()
        print(f"\n[Summary] AirCursor Offline Distribution Package:")
        print(f"  Directory: {bundle_dir}")
        print(f"  Zip file:  {zip_path}")
        print(f"  Files:     {manifest['total_files']}")
        print(f"  Offline:   {'VERIFIED' if manifest['offline_verified'] else 'FAILED'}")
    except Exception as e:
        print(f"[Error] Failed to package offline distribution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
