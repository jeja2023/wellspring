"""Keep this bootstrap OUTSIDE the untrusted bundle; distribute through a trusted channel."""
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    raise SystemExit("Run with python -I; untrusted bundle modules must not be imported")

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re


def main():
    if not sys.flags.isolated:
        raise SystemExit("Run the trusted bootstrap with python -I")
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--loaded", action="store_true")
    args = parser.parse_args()
    expected = args.manifest_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit("Invalid trusted manifest SHA-256")
    root = args.bundle.resolve(strict=True)
    if Path(__file__).resolve().parent == root:
        raise SystemExit("Trusted bootstrap must be stored outside the bundle")
    manifest_path, verifier_path = root / "manifest.json", root / "verify_bundle.py"
    for path in (manifest_path, verifier_path):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) or not path.is_file() or path.resolve().parent != root:
            raise SystemExit("Manifest/verifier must be regular files in the bundle")
    manifest_bytes = manifest_path.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(manifest_bytes).hexdigest(), expected):
        raise SystemExit("Manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    verifier_bytes = verifier_path.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(verifier_bytes).hexdigest(), manifest["files"]["verify_bundle.py"]):
        raise SystemExit("Verifier hash mismatch: no bundle code was executed")
    # Execute the exact verified bytes, avoiding a second path read / module shadowing.
    sys.argv = [str(verifier_path), "--manifest-sha256", expected] + (["--loaded"] if args.loaded else [])
    exec(compile(verifier_bytes, str(verifier_path), "exec"), {"__name__": "__main__", "__file__": str(verifier_path)})


if __name__ == "__main__":
    main()
