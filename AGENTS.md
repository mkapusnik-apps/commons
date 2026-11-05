# Commons

## Project

Repository for shared tools, GitHub Actions, and their specifications:
- Root-level action directories (`setup-flutter`, `tag`, `pull-request`, `workflow-state`, `tag-gate`, `release-notes`, and `next-version`) - shared actions reusable across similar products
- `docs` - specifications of the features

## Branching Strategy

GitHub Actions validates action metadata. A `master` push publishes the next
patch when exposed action content changed. An operator may publish the next
major from current `master`. Release scope, retry, and troubleshooting details
are in [.github/workflows.md](.github/workflows.md).

## Shared Action Releases

Consumers use root-level action paths at floating major tags such as `mkapusnik-apps/commons/setup-flutter@v1`. The initial `v1.0` reference is fixed, while `v1` floats to compatible releases. Immutable releases and the compatibility contract are documented in [docs/actions/README.md](docs/actions/README.md).

## External Action References

- External GitHub Actions used by this repository must use the highest available stable major reference (`@vN`). Do not replace it with a minor, patch, or commit-SHA pin unless explicitly authorized.
- An upstream major reference may be a tag or a branch. Check both before declaring a reference missing.
- When auditing updates, compare resolved commit SHAs, peeling annotated tags, and inspect the relevant content changes. A more specific reference name does not prove an update.
- If a major reference lags behind a newer release in the same major, report the upstream limitation; do not bypass this policy by narrowing the pin.
