# Reusable GitHub Actions

This catalog documents the reusable GitHub Actions published from root-level directories in `mkapusnik-apps/commons`.

## Catalog

| Action | Local path | Consumer reference | Use when | Documentation |
| --- | --- | --- | --- | --- |
| Setup Flutter for CI | `setup-flutter` | `mkapusnik-apps/commons/setup-flutter@v1` | Install and configure the shared stable Flutter toolchain for CI. | [setup-flutter.md](setup-flutter.md) |
| Set Git Tag | `tag` | `mkapusnik-apps/commons/tag@v1` | Preserve the existing lightweight-tag interface. Prefer Set Git Ref for new work. | [tag.md](tag.md) |
| Create or Update Pull Request | `pull-request` | `mkapusnik-apps/commons/pull-request@v1` | Reuse one promotion or automation pull request for a stable head/base pair. | [pull-request.md](pull-request.md) |
| Set Git Ref | `git-ref` | `mkapusnik-apps/commons/git-ref@v1` | Create or move any full Git ref, including branch and tag refs. | [git-ref.md](git-ref.md) |
| Set Workflow State | `workflow-state` | `mkapusnik-apps/commons/workflow-state@v1` | Enable or disable a GitHub Actions workflow through the GitHub API. | [workflow-state.md](workflow-state.md) |
| Lifecycle Tag Gate | `tag-gate` | `mkapusnik-apps/commons/tag-gate@v1` | Decide whether a lifecycle workflow should run by comparing source and target tags. | [tag-gate.md](tag-gate.md) |

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

## Versioning and pinning

- `v1.0.0` is an immutable release tag for the initial stable root-level action interfaces.
- `v1.0` is a fixed minor-series reference to `v1.0.0` and does not move.
- `v1` is a floating major tag that points to the latest compatible v1 release.
- Breaking action path, input, output, runtime, or behavior changes require a new major release and floating major tag rather than moving `v1` to the incompatible implementation.
- A reviewed full commit SHA is stricter pinning than `v1` because it cannot move when a compatible release is published.
- Do not pin production consumers to a moving branch such as `master`.

Release and floating-major tags must be published only after review and merge, and must point to the merged implementation that contains the documented action paths. Local workflows in this repository may use relative paths such as `./git-ref`.

The repository's semantic-version publication, bootstrap, and floating-major contract is defined in [semantic-releases.md](semantic-releases.md). Consumers may use a floating major such as `v1` for compatible updates, the fixed initial minor reference `v1.0`, or a full version such as `v1.0.0` when an immutable release is required.

## Historical context

The earlier product note for the initial ref and workflow-state work remains in [git-ref-and-workflow-state.md](git-ref-and-workflow-state.md). The pages in this catalog are the consumer-facing contract documentation for the current actions.
