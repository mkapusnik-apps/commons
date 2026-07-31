# Set Git Ref

Create or update a full Git ref with the GitHub REST refs API. The action works for branch refs, tag refs, and other full refs such as `refs/heads/nightly` or `refs/tags/nightly` without requiring checkout, local fetches, or `git push`.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `repository` | No | Current workflow repository | Target repository in `owner/repo` form. |
| `ref` | Yes | None | Full ref name, for example `refs/heads/nightly` or `refs/tags/nightly`. Short names are rejected. |
| `commit_sha` | No | Current workflow SHA | Target commit SHA. Omit it to use `github.sha`. |
| `token` | Yes | None | Token authorized to create or update refs in the target repository. |
| `force` | No | `true` | Force-update an existing ref. Set to `false` to let GitHub reject non-fast-forward updates. |
| `create_if_missing` | No | `true` | Create the ref when it does not exist. |
| `noop_if_unchanged` | No | `true` | Skip the update when the ref already points to `commit_sha`. |

## Outputs

| Output | Description |
| --- | --- |
| `changed` | `true` when the ref was created or moved; otherwise `false`. |
| `previous_sha` | Previous object SHA for the ref, or an empty string when the ref did not exist. |
| `new_sha` | Target commit SHA after a successful run. |
| `ref` | Full ref name that was evaluated. |

## Permissions

The token needs `contents: write` in the target repository. The default `GITHUB_TOKEN` can update refs in the current repository when workflow permissions allow it. Cross-repository updates usually require a fine-grained PAT or GitHub App token with access to the target repository.

## Examples

Move a reusable nightly tag and branch to the current commit:

```yaml
permissions:
  contents: write

steps:
  - name: Move nightly tag
    uses: mkapusnik-apps/commons/git-ref@v1
    with:
      ref: refs/tags/nightly
      token: ${{ github.token }}

  - name: Move nightly branch
    uses: mkapusnik-apps/commons/git-ref@v1
    with:
      ref: refs/heads/nightly
      commit_sha: ${{ github.sha }}
      token: ${{ github.token }}
```

Fail instead of creating a missing ref:

```yaml
- name: Update existing release pointer
  uses: mkapusnik-apps/commons/git-ref@v1
  with:
    ref: refs/tags/latest
    commit_sha: ${{ github.sha }}
    create_if_missing: 'false'
    token: ${{ secrets.RELEASE_TOKEN }}
```

Updating multiple refs is not atomic. If a workflow moves more than one ref, handle partial failures explicitly.

For external consumers, use the floating `v1` tag for compatible v1 updates or pin a reviewed immutable commit SHA for stricter reproducibility. Do not use a moving branch.
