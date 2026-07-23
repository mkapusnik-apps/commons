#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'tag-gate: %s\n' "$1" >&2
  exit 1
}

require_non_empty() {
  local name="$1"
  local value="$2"

  if [[ -z "${value//[[:space:]]/}" ]]; then
    fail "Input \"$name\" must be a non-empty string"
  fi
}

validate_repository() {
  local repository="$1"

  if [[ ! "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    fail 'Input "repository" must use owner/repo format'
  fi
}

validate_tag() {
  local input_name="$1"
  local tag="$2"

  require_non_empty "$input_name" "$tag"

  if [[ "$tag" == refs/* ]]; then
    fail "Input \"$input_name\" must be a tag name without refs/tags/ prefix"
  fi
  if [[ "$tag" == -* ]]; then
    fail "Input \"$input_name\" must not start with '-'"
  fi
  if ! git check-ref-format --allow-onelevel "refs/tags/$tag" >/dev/null 2>&1; then
    fail "Input \"$input_name\" is not a valid Git tag name"
  fi
}

read_tag_sha() {
  local remote="$1"
  local tag="$2"
  local output
  local status
  local direct_sha=""
  local peeled_sha=""
  local sha=""
  local ref=""

  set +e
  output=$(git ls-remote --exit-code "$remote" "refs/tags/$tag" "refs/tags/$tag^{}" 2>&1)
  status=$?
  set -e

  case "$status" in
    0)
      while read -r sha ref; do
        case "$ref" in
          "refs/tags/$tag")
            direct_sha="$sha"
            ;;
          "refs/tags/$tag^{}")
            peeled_sha="$sha"
            ;;
        esac
      done <<<"$output"

      printf '%s\n' "${peeled_sha:-$direct_sha}"
      ;;
    2)
      printf '\n'
      ;;
    *)
      fail "Failed to read tag \"$tag\" from remote \"$remote\": $output"
      ;;
  esac
}

set_output() {
  local name="$1"
  local value="$2"

  printf '%s=%s\n' "$name" "$value" >>"$GITHUB_OUTPUT"
}

source_tag="${TAG_GATE_SOURCE_TAG:-}"
target_tag="${TAG_GATE_TARGET_TAG:-}"
repository="${TAG_GATE_REPOSITORY:-}"
remote="${TAG_GATE_REMOTE:-origin}"

require_non_empty source_tag "$source_tag"
require_non_empty target_tag "$target_tag"
require_non_empty repository "$repository"
require_non_empty remote "$remote"
require_non_empty GITHUB_OUTPUT "${GITHUB_OUTPUT:-}"

validate_repository "$repository"
validate_tag source_tag "$source_tag"
validate_tag target_tag "$target_tag"

if [[ "$remote" == -* ]]; then
  fail "Input \"remote\" must not start with '-'"
fi

source_sha="$(read_tag_sha "$remote" "$source_tag")"

if [[ -z "$source_sha" ]]; then
  set_output should_run false
  set_output source_sha ''
  set_output target_sha ''
  set_output short_sha ''
  set_output reason source-missing
  printf 'Source tag "%s" is missing in %s; lifecycle workflow should not run.\n' "$source_tag" "$repository"
  exit 0
fi

target_sha="$(read_tag_sha "$remote" "$target_tag")"
short_sha="${source_sha:0:12}"

set_output source_sha "$source_sha"
set_output target_sha "$target_sha"
set_output short_sha "$short_sha"

if [[ "$source_sha" == "$target_sha" ]]; then
  set_output should_run false
  set_output reason already-current
  printf 'Target tag "%s" already matches source tag "%s" at %s.\n' "$target_tag" "$source_tag" "$source_sha"
  exit 0
fi

set_output should_run true
set_output reason pending

if [[ -z "$target_sha" ]]; then
  printf 'Source tag "%s" exists at %s and target tag "%s" is missing; lifecycle workflow is pending.\n' "$source_tag" "$source_sha" "$target_tag"
else
  printf 'Source tag "%s" (%s) differs from target tag "%s" (%s); lifecycle workflow is pending.\n' "$source_tag" "$source_sha" "$target_tag" "$target_sha"
fi
