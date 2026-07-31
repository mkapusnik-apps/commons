# Commons

## Project

Repository for shared tools, github actions, AI agents, etc:
- Root-level action directories (`setup-flutter`, `tag`, `pull-request`, `git-ref`, `workflow-state`, and `tag-gate`) - shared actions reusable across similar products
- `agents` - opencode agents for unified development workflows and patterns
- `docs` - specifications of the features

## Branching Strategy

GitHub Actions validates pull requests and publishes one semantic release for
every qualifying push to `master`. Every pull request must add one
machine-readable release declaration. Trigger, ordering, declaration, retry,
and troubleshooting details are in [.github/workflows.md](.github/workflows.md).

## Shared Action Releases

Consumers use root-level action paths at floating major tags such as `mkapusnik-apps/commons/setup-flutter@v1`. The initial `v1.0` reference is fixed, while `v1` floats to compatible releases. Immutable releases and the compatibility contract are documented in [docs/actions/README.md](docs/actions/README.md).
