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

- External GitHub Actions used by this repository must track the latest stable release using the clearest reference that resolves to it.
- Prefer the highest stable major reference (`@vN`) when it resolves to the latest stable release's commit. If it lags behind, use the explicit latest stable minor or patch reference instead.
- Upstream references may be tags or branches. Check both before declaring a reference missing.
- When auditing updates, compare resolved commit SHAs, peeling annotated tags, and inspect relevant content changes. A more specific reference name alone does not prove an update.
