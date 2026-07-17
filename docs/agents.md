# OpenCode Agents

The `agents` directory is the canonical source for the global OpenCode agent definitions used by the home-lab OpenCode service.

## Contents

The directory contains only loadable OpenCode agent Markdown files:

- `developer.md`
- `devops.md`
- `product.md`
- `reviewer.md`
- `team.md`
- `tester.md`
- `ux.md`

Do not add a `README.md` or other documentation below `agents`. OpenCode discovers `agents/**/*.md` recursively and would interpret every Markdown file as an agent definition. Keep module documentation under `docs` instead.

## Runtime Mount

The `mkapusnik/home` repository deploys `tools/opencode` with the GlusterFS `devel` volume mounted at `/devel`. The same volume is mounted a second time with `commons/agents` as its volume subpath:

```text
/devel/commons/agents -> /app/.config/opencode/agents
```

The global agent mount is read-only inside the OpenCode configuration directory. Edit definitions through the writable repository checkout at `/devel/commons/agents`, not through `/app/.config/opencode/agents`.

The runtime checkout at `/devel/commons` must remain a clean, current `master` checkout. Use a separate branch checkout or Git worktree for changes so an OpenCode restart cannot load unmerged definitions.

## Update Workflow

1. Create a branch or worktree from the current `origin/master`.
2. Update files under `agents`.
3. Validate the OpenCode configuration and every changed agent.
4. Commit and open a pull request against `master`.
5. After merge, update `/devel/commons` to the merged `master` commit.
6. Redeploy or restart `tools/opencode` because agent definitions are loaded at startup.

## Validation

Run these checks in the OpenCode container after updating the runtime checkout:

```sh
opencode debug config
opencode debug agent developer
opencode debug agent devops
opencode debug agent product
opencode debug agent reviewer
opencode debug agent team
opencode debug agent tester
opencode debug agent ux
```

Also verify that `agents` contains exactly the expected agent files and no credentials or generated artifacts.

## Rollback

The OpenCode `conf` volume retains the previous `/app/.config/opencode/agents` directory underneath the nested read-only mount. Removing the `commons/agents` subpath mount from the service and redeploying exposes the previous definitions again.
