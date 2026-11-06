"""Write the manifest that describes a published set of CI evidence files.

The evidence set is the raw vulnerability report, the build manifest and the
SBOM of one candidate image. The manifest states what produced them, so the
files can be read as evidence rather than as anonymous attachments: it names
the source revision, the image, the scanner and the exact bytes of every file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--scanner-name", required=True)
    parser.add_argument("--scanner-version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.source_sha) is None:
        raise SystemExit("source SHA must be a full 40- or 64-character Git object ID")
    if re.fullmatch(r"[0-9]+", args.run_id) is None:
        raise SystemExit("run id must be numeric")
    files: dict[str, dict[str, object]] = {}
    for path in args.input:
        if not path.is_file():
            raise SystemExit(f"evidence input does not exist: {path}")
        data = path.read_bytes()
        files[path.name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    if not files:
        raise SystemExit("no evidence file was described")
    payload = {
        "schemaVersion": 1,
        "source": {
            "repository": args.repository,
            "sha": args.source_sha,
            "workflow": args.workflow,
            "runId": args.run_id,
            "runAttempt": args.run_attempt,
        },
        "image": {
            "ref": args.image_ref,
            "platform": "linux/amd64",
        },
        "scanner": {
            "name": args.scanner_name,
            "version": args.scanner_version,
        },
        "files": files,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
