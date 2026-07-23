#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
ACTION_SCRIPT="$ROOT/.github/actions/tag-gate/tag-gate.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

assert_equals() {
  local expected="$1"
  local actual="$2"
  local message="$3"

  if [[ "$actual" != "$expected" ]]; then
    printf 'Assertion failed: %s\nExpected: %s\nActual:   %s\n' "$message" "$expected" "$actual" >&2
    exit 1
  fi
}

value_for() {
  local key="$1"
  local file="$2"
  awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2) }' "$file" | tail -n 1
}

run_gate() {
  local source_tag="$1"
  local target_tag="$2"
  local output_file="$3"
  local remote="${4:-$TMP_DIR/remote.git}"

  : >"$output_file"
  TAG_GATE_SOURCE_TAG="$source_tag" \
    TAG_GATE_TARGET_TAG="$target_tag" \
    TAG_GATE_REPOSITORY="mkapusnik/commons" \
    TAG_GATE_REMOTE="$remote" \
    GITHUB_OUTPUT="$output_file" \
    "$ACTION_SCRIPT" >/dev/null
}

remote_repo="$TMP_DIR/remote.git"
work_repo="$TMP_DIR/work"

git init --bare -b main "$remote_repo" >/dev/null
git init -b main "$work_repo" >/dev/null
git -C "$work_repo" config user.email test@example.com
git -C "$work_repo" config user.name 'Test User'
git -C "$work_repo" commit --allow-empty -m 'first' >/dev/null
first_sha="$(git -C "$work_repo" rev-parse HEAD)"
git -C "$work_repo" commit --allow-empty -m 'second' >/dev/null
second_sha="$(git -C "$work_repo" rev-parse HEAD)"
git -C "$work_repo" tag source "$second_sha"
git -C "$work_repo" tag same-target "$second_sha"
git -C "$work_repo" tag old-target "$first_sha"
git -C "$work_repo" tag -a annotated-source "$second_sha" -m 'annotated source'
git -C "$work_repo" tag -a annotated-same-target "$second_sha" -m 'annotated same target'
git -C "$work_repo" tag -a annotated-old-target "$first_sha" -m 'annotated old target'
git -C "$work_repo" push "$remote_repo" --tags >/dev/null

missing_source_output="$TMP_DIR/missing-source.out"
run_gate missing-source target "$missing_source_output"
assert_equals false "$(value_for should_run "$missing_source_output")" 'missing source should not run'
assert_equals source-missing "$(value_for reason "$missing_source_output")" 'missing source reason'
assert_equals '' "$(value_for source_sha "$missing_source_output")" 'missing source SHA is empty'

missing_target_output="$TMP_DIR/missing-target.out"
run_gate source missing-target "$missing_target_output"
assert_equals true "$(value_for should_run "$missing_target_output")" 'missing target should run'
assert_equals pending "$(value_for reason "$missing_target_output")" 'missing target reason'
assert_equals "$second_sha" "$(value_for source_sha "$missing_target_output")" 'missing target source SHA'
assert_equals '' "$(value_for target_sha "$missing_target_output")" 'missing target target SHA is empty'

same_output="$TMP_DIR/same.out"
run_gate source same-target "$same_output"
assert_equals false "$(value_for should_run "$same_output")" 'identical tags should not run'
assert_equals already-current "$(value_for reason "$same_output")" 'identical tags reason'
assert_equals "$second_sha" "$(value_for target_sha "$same_output")" 'identical target SHA'

different_output="$TMP_DIR/different.out"
run_gate source old-target "$different_output"
assert_equals true "$(value_for should_run "$different_output")" 'different tags should run'
assert_equals pending "$(value_for reason "$different_output")" 'different tags reason'
assert_equals "$first_sha" "$(value_for target_sha "$different_output")" 'different target SHA'

annotated_missing_target_output="$TMP_DIR/annotated-missing-target.out"
run_gate annotated-source missing-target "$annotated_missing_target_output"
assert_equals true "$(value_for should_run "$annotated_missing_target_output")" 'annotated source with missing target should run'
assert_equals pending "$(value_for reason "$annotated_missing_target_output")" 'annotated source with missing target reason'
assert_equals "$second_sha" "$(value_for source_sha "$annotated_missing_target_output")" 'annotated source peels to commit SHA'
assert_equals '' "$(value_for target_sha "$annotated_missing_target_output")" 'annotated source with missing target target SHA is empty'

annotated_same_output="$TMP_DIR/annotated-same.out"
run_gate annotated-source annotated-same-target "$annotated_same_output"
assert_equals false "$(value_for should_run "$annotated_same_output")" 'annotated tags at same commit should not run'
assert_equals already-current "$(value_for reason "$annotated_same_output")" 'annotated tags at same commit reason'
assert_equals "$second_sha" "$(value_for source_sha "$annotated_same_output")" 'annotated same source SHA'
assert_equals "$second_sha" "$(value_for target_sha "$annotated_same_output")" 'annotated same target SHA'

annotated_different_output="$TMP_DIR/annotated-different.out"
run_gate annotated-source annotated-old-target "$annotated_different_output"
assert_equals true "$(value_for should_run "$annotated_different_output")" 'annotated tags at different commits should run'
assert_equals pending "$(value_for reason "$annotated_different_output")" 'annotated tags at different commits reason'
assert_equals "$second_sha" "$(value_for source_sha "$annotated_different_output")" 'annotated different source SHA'
assert_equals "$first_sha" "$(value_for target_sha "$annotated_different_output")" 'annotated different target SHA'

invalid_output="$TMP_DIR/invalid.out"
if run_gate 'bad tag' target "$invalid_output" 2>"$TMP_DIR/invalid.err"; then
  printf 'Expected invalid tag name to fail.\n' >&2
  exit 1
fi
if ! grep -q 'not a valid Git tag name' "$TMP_DIR/invalid.err"; then
  printf 'Expected invalid tag error message.\n' >&2
  cat "$TMP_DIR/invalid.err" >&2
  exit 1
fi

invalid_remote_output="$TMP_DIR/invalid-remote.out"
if run_gate source target "$invalid_remote_output" '--upload-pack=malicious' 2>"$TMP_DIR/invalid-remote.err"; then
  printf 'Expected invalid remote to fail.\n' >&2
  exit 1
fi
if ! grep -q 'must not start with' "$TMP_DIR/invalid-remote.err"; then
  printf 'Expected invalid remote error message.\n' >&2
  cat "$TMP_DIR/invalid-remote.err" >&2
  exit 1
fi

printf 'OK tag-gate shell logic paths.\n'
