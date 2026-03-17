#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TARGET_FILES=(
  "src/components/settings/AgentSettings.vue"
  "src/components/settings/ModelSettings.vue"
  "src/components/connectors/CustomApiForm.vue"
  "src/components/connectors/CustomMcpForm.vue"
)

missing_count=0

for relative_path in "${TARGET_FILES[@]}"; do
  full_path="${ROOT_DIR}/${relative_path}"
  if [[ ! -f "${full_path}" ]]; then
    continue
  fi

  violations="$(perl -0777 -ne '
    while (/<(input|select|textarea)\b(?![^>]*\b(?:id|name)\s*=)[^>]*>/g) {
      my $line = 1 + (substr($_, 0, $-[0]) =~ tr/\n//);
      my $tag = $&;
      $tag =~ s/\s+/ /g;
      print "$line:$tag\n";
    }
  ' "${full_path}")"

  if [[ -n "${violations}" ]]; then
    missing_count=$((missing_count + 1))
    echo "Missing id/name form controls in ${relative_path}:"
    echo "${violations}"
    echo
  fi
done

if [[ ${missing_count} -gt 0 ]]; then
  echo "Form control guard failed. Add id and name attributes to each input/select/textarea."
  exit 1
fi

echo "Form control guard passed."
