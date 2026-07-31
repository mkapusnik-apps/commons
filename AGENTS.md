# Commons

## Project

Repository for shared tools, github actions, AI agents, etc:
- Root-level action directories (`setup-flutter`, `tag`, `pull-request`, `git-ref`, `workflow-state`, and `tag-gate`) - shared actions reusable across similar products
- `agents` - opencode agents for unified development workflows and patterns
- `docs` - specifications of the features

## Branching Strategy

CI/CD workflow is leveraging GitHub Actions, detailed implementation described in [.github/workflows.md](.github/workflows.md)

## Shared Action Releases

Consumers use root-level action paths at floating major tags such as `mkapusnik-apps/commons/setup-flutter@v1`. Immutable releases and the compatibility contract are documented in [docs/actions/README.md](docs/actions/README.md).
