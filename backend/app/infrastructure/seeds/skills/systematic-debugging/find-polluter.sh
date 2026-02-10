#!/usr/bin/env bash
# Bisection script to find which test creates unwanted files/state
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: ./find-polluter.sh '.git' 'src/**/*.test.ts'

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <file_to_check> <test_pattern>"
  echo "Example: $0 '.git' 'src/**/*.test.ts'"
  exit 1
fi

POLLUTION_CHECK="$1"
TEST_PATTERN="$2"

echo "🔍 Searching for test that creates: $POLLUTION_CHECK"
echo "Test pattern: $TEST_PATTERN"
echo ""

# Get list of test files matching glob pattern (supports **)
TEST_FILES=()
if command -v rg >/dev/null 2>&1; then
  while IFS= read -r -d '' TEST_FILE; do
    TEST_FILES+=("$TEST_FILE")
  done < <(rg --files -0 -g "$TEST_PATTERN" | sort -z)
else
  while IFS= read -r -d '' TEST_FILE; do
    REL_PATH="${TEST_FILE#./}"
    if [[ "$REL_PATH" == $TEST_PATTERN ]]; then
      TEST_FILES+=("$REL_PATH")
    fi
  done < <(find . -type f -print0 | sort -z)
fi

TOTAL=${#TEST_FILES[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "No test files matched pattern: $TEST_PATTERN"
  exit 1
fi

echo "Found $TOTAL test files"
echo ""

COUNT=0
for TEST_FILE in "${TEST_FILES[@]}"; do
  COUNT=$((COUNT + 1))

  # Skip if pollution already exists
  if [ -e "$POLLUTION_CHECK" ]; then
    echo "⚠️  Pollution already exists before test $COUNT/$TOTAL"
    echo "   Skipping: $TEST_FILE"
    continue
  fi

  echo "[$COUNT/$TOTAL] Testing: $TEST_FILE"

  # Run the test
  npm test "$TEST_FILE" > /dev/null 2>&1 || true

  # Check if pollution appeared
  if [ -e "$POLLUTION_CHECK" ]; then
    echo ""
    echo "🎯 FOUND POLLUTER!"
    echo "   Test: $TEST_FILE"
    echo "   Created: $POLLUTION_CHECK"
    echo ""
    echo "Pollution details:"
    ls -la "$POLLUTION_CHECK"
    echo ""
    echo "To investigate:"
    printf "  npm test %q    # Run just this test\n" "$TEST_FILE"
    printf "  cat %q         # Review test code\n" "$TEST_FILE"
    exit 1
  fi
done

echo ""
echo "✅ No polluter found - all tests clean!"
exit 0
