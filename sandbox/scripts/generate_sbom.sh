#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/app/artifacts}"
mkdir -p "${OUTPUT_DIR}"

PYTHON_SBOM="${OUTPUT_DIR}/sbom-python.json"
NPM_SBOM="${OUTPUT_DIR}/sbom-npm.json"

if command -v cyclonedx-bom >/dev/null 2>&1; then
  cyclonedx-bom -o "${PYTHON_SBOM}" --format json || true
fi

if command -v cyclonedx-npm >/dev/null 2>&1; then
  cyclonedx-npm --output-file "${NPM_SBOM}" --output-format json --omit dev || true
fi

echo "SBOM artifacts written to ${OUTPUT_DIR}"
