# Reusable GitHub Actions

This catalog documents the local reusable GitHub Actions implemented under `.github/actions/` for workflow consumers.

## Catalog

| Action | Local path | Use when | Documentation |
| --- | --- | --- | --- |
| Set Git Ref | `.github/actions/git-ref` | Create or move any full Git ref, including branch and tag refs. | [git-ref.md](git-ref.md) |
| Set Workflow State | `.github/actions/workflow-state` | Enable or disable a GitHub Actions workflow through the GitHub API. | [workflow-state.md](workflow-state.md) |
| Create or Update Pull Request | `.github/actions/pull-request` | Reuse one promotion or automation pull request for a stable head/base pair. | [pull-request.md](pull-request.md) |
| Lifecycle Tag Gate | `.github/actions/tag-gate` | Decide whether a lifecycle workflow should run by comparing source and target tags. | [tag-gate.md](tag-gate.md) |
| Set Git Tag | `.github/actions/tag` | Preserve legacy lightweight-tag behavior for existing callers. Prefer Set Git Ref for new work. | [tag.md](tag.md) |

## Common expectations

- Inputs are strings supplied through `with:` blocks. Boolean-like inputs are documented per action because not every action parses them the same way.
- Outputs are GitHub Actions step outputs and are always strings.
- API-based actions use `actions/github-script@v8`.
- Refs, workflow state changes, and pull requests are not transactional across multiple action calls. If a workflow changes more than one repository resource, handle partial failure explicitly.

## Permissions and tokens

Grant only the permissions required by the action in the target repository:

- Ref and tag writers need `contents: write`.
- Tag gate reads need repository tag access; same-repository workflows commonly use `contents: read` with checkout.
- Workflow state updates need `actions: write`.
- Pull request creation or update needs `pull-requests: write`; auto-merge also requires repository settings and branch protection to allow auto-merge for the token.

The default `GITHUB_TOKEN` is usually enough only for the current repository when workflow permissions allow the requested operation. Cross-repository writes generally require a fine-grained PAT or GitHub App token with access to the target repository.

## Pinning guidance

Consumers outside this repository should pin shared actions to a release tag or immutable commit SHA rather than a moving branch. Local workflows in this repository may use relative paths such as `./.github/actions/git-ref`.

## Historical context

The earlier product note for the initial ref and workflow-state work remains in [git-ref-and-workflow-state.md](git-ref-and-workflow-state.md). The pages in this catalog are the consumer-facing contract documentation for the current actions.
