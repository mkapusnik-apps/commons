'use strict';

const childProcess = require('node:child_process');
const fs = require('node:fs');

const SCOPE_PATH = '.github/semantic-release/actions.json';
const VERSION_PATTERN = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const SHA_PATTERN = /^[0-9a-f]{40}$/;
const VERIFY_ATTEMPTS = 6;

function fail(message, cause = null) {
  throw new Error(message, cause ? { cause } : undefined);
}

function exactKeys(path, value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${path} must contain a JSON object`);
  if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...keys].sort())) {
    fail(`${path} must contain exactly these keys: ${[...keys].sort().join(', ')}`);
  }
}

function parseScope(content, path = SCOPE_PATH) {
  let value;
  try {
    value = JSON.parse(content);
  } catch (error) {
    fail(`${path} is not valid JSON: ${error.message}`);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${path} must contain a JSON object`);
  }

  if (value.schema === 1) {
    exactKeys(path, value, ['schema', 'actionDirectories']);
    value = { ...value, sharedPaths: [] };
  } else {
    exactKeys(path, value, ['schema', 'actionDirectories', 'sharedPaths']);
    if (value.schema !== 2) fail(`${path} schema must be 1 or 2`);
  }
  if (!Array.isArray(value.actionDirectories) || value.actionDirectories.length === 0) {
    fail(`${path} actionDirectories must be a non-empty array`);
  }
  if (!Array.isArray(value.sharedPaths)) fail(`${path} sharedPaths must be an array`);

  const directoryPattern = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;
  for (const directory of value.actionDirectories) {
    if (typeof directory !== 'string' || !directoryPattern.test(directory)) {
      fail(`${path} has invalid root-level action directory ${JSON.stringify(directory)}`);
    }
  }
  for (const sharedPath of value.sharedPaths) {
    if (typeof sharedPath !== 'string' || sharedPath.startsWith('.') || sharedPath.startsWith('/')
      || sharedPath.includes('..') || sharedPath.endsWith('/')) {
      fail(`${path} has invalid shared path ${JSON.stringify(sharedPath)}`);
    }
  }
  for (const [name, items] of Object.entries({ actionDirectories: value.actionDirectories, sharedPaths: value.sharedPaths })) {
    if (JSON.stringify(items) !== JSON.stringify([...items].sort())) fail(`${path} ${name} must be sorted`);
    if (new Set(items).size !== items.length) fail(`${path} ${name} must not contain duplicates`);
  }
  return { actionDirectories: value.actionDirectories, sharedPaths: value.sharedPaths };
}

function versionFromTag(tag) {
  const match = VERSION_PATTERN.exec(tag);
  return match ? { tag, major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) } : null;
}

function compareVersions(left, right) {
  return left.major - right.major || left.minor - right.minor || left.patch - right.patch;
}

function formatVersion(version) {
  return `v${version.major}.${version.minor}.${version.patch}`;
}

function runGit(args) {
  try {
    return childProcess.execFileSync('git', args, {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 16 * 1024 * 1024,
    });
  } catch (error) {
    fail(`git ${args.join(' ')} failed: ${error.stderr?.toString().trim() || error.message}`);
  }
}

async function resolveCommit(github, props, object) {
  let current = object;
  for (let depth = 0; depth < 5; depth += 1) {
    if (current.type === 'commit') return current.sha;
    if (current.type !== 'tag') fail(`Tag object ${current.sha} has unsupported type ${current.type}`);
    current = (await github.rest.git.getTag({ ...props, tag_sha: current.sha })).data.object;
  }
  fail(`Tag object ${object.sha} has excessive annotation depth`);
}

async function getRef(github, props, ref) {
  try {
    return (await github.rest.git.getRef({ ...props, ref })).data;
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function loadTree(github, props, sha) {
  const commit = await github.rest.git.getCommit({ ...props, commit_sha: sha });
  const response = await github.rest.git.getTree({ ...props, tree_sha: commit.data.tree.sha, recursive: 'true' });
  if (response.data.truncated) fail(`Repository tree for ${sha} is truncated`);
  return new Map(response.data.tree.map((entry) => [entry.path, entry]));
}

async function readTreeFile(github, props, tree, path) {
  const entry = tree.get(path);
  if (!entry || entry.type !== 'blob') fail(`${path} is missing or is not a regular file`);
  const blob = await github.rest.git.getBlob({ ...props, file_sha: entry.sha });
  if (blob.data.encoding !== 'base64') fail(`${path} has unsupported encoding ${blob.data.encoding}`);
  return Buffer.from(blob.data.content, 'base64').toString('utf8');
}

function inScope(path, scope) {
  return scope.actionDirectories.some((directory) => path === directory || path.startsWith(`${directory}/`))
    || scope.sharedPaths.some((sharedPath) => path === sharedPath || path.startsWith(`${sharedPath}/`));
}

function validateHeadScope(tree, scope) {
  for (const directory of scope.actionDirectories) {
    const metadata = tree.get(`${directory}/action.yml`);
    if (!metadata || metadata.type !== 'blob') fail(`Exposed action ${directory} must contain action.yml`);
  }
  for (const path of scope.sharedPaths) {
    if (!tree.has(path) && ![...tree.keys()].some((entry) => entry.startsWith(`${path}/`))) {
      fail(`Shared runtime path ${path} does not exist`);
    }
  }
}

async function exposedContentChanged(github, props, baseSha, headSha) {
  const [baseTree, headTree] = await Promise.all([loadTree(github, props, baseSha), loadTree(github, props, headSha)]);
  const [baseScope, headScope] = await Promise.all([
    readTreeFile(github, props, baseTree, SCOPE_PATH).then((content) => parseScope(content, `${SCOPE_PATH} at ${baseSha}`)),
    readTreeFile(github, props, headTree, SCOPE_PATH).then((content) => parseScope(content, `${SCOPE_PATH} at ${headSha}`)),
  ]);
  validateHeadScope(baseTree, baseScope);
  validateHeadScope(headTree, headScope);
  const paths = new Set([...baseTree.keys(), ...headTree.keys()]);
  const changedPaths = [...paths].filter((path) => {
    const before = inScope(path, baseScope) ? baseTree.get(path) : undefined;
    const after = inScope(path, headScope) ? headTree.get(path) : undefined;
    if (!before && !after) return false;
    return !before || !after || before.sha !== after.sha || before.mode !== after.mode || before.type !== after.type;
  }).sort();
  return { changed: changedPaths.length > 0, changedPaths };
}

async function releaseState(github, props) {
  const [refs, releaseItems] = await Promise.all([
    github.paginate(github.rest.git.listMatchingRefs, { ...props, ref: 'tags/v', per_page: 100 }),
    github.paginate(github.rest.repos.listReleases, { ...props, per_page: 100 }),
  ]);
  const immutable = [];
  for (const ref of refs) {
    const tag = ref.ref.replace('refs/tags/', '');
    const version = versionFromTag(tag);
    if (version) immutable.push({ ...version, sha: await resolveCommit(github, props, ref.object) });
  }
  immutable.sort(compareVersions);
  const releases = new Map();
  for (const release of releaseItems) {
    if (!versionFromTag(release.tag_name)) continue;
    if (releases.has(release.tag_name)) fail(`Multiple releases use ${release.tag_name}`);
    releases.set(release.tag_name, release);
  }
  const published = immutable.filter((item) => {
    const release = releases.get(item.tag);
    if (!release) return false;
    if (release.prerelease) fail(`${item.tag} must not be a prerelease`);
    return !release.draft;
  });
  for (const [tag, release] of releases) {
    if (!immutable.some((item) => item.tag === tag)) fail(`Release ${tag} has no immutable tag`);
    if (release.prerelease) fail(`${tag} must not be a prerelease`);
  }
  if (published.length === 0) fail('No published stable semantic release exists');
  return { immutable, releases, published, latest: published.at(-1) };
}

async function requireMaster(github, props, sha) {
  const master = await getRef(github, props, 'heads/master');
  if (!master) fail('refs/heads/master is missing');
  const actual = await resolveCommit(github, props, master.object);
  if (actual !== sha) fail(`Target ${sha} is not current master ${actual}`);
}

async function createRef(github, props, tag, sha) {
  try {
    await github.rest.git.createRef({ ...props, ref: `refs/tags/${tag}`, sha });
  } catch (error) {
    if (error.status !== 422) throw error;
    const existing = await getRef(github, props, `tags/${tag}`);
    if (!existing || await resolveCommit(github, props, existing.object) !== sha) {
      fail(`Tag ${tag} already exists at another revision`, error);
    }
  }
}

async function ensureDraft(github, props, state, tag, sha, mode) {
  const existing = state.releases.get(tag);
  if (existing) return existing;
  try {
    return (await github.rest.repos.createRelease({
      ...props, tag_name: tag, target_commitish: sha, name: tag,
      body: `${mode} release of ${sha}.`, draft: true, prerelease: false,
    })).data;
  } catch (error) {
    if (error.status !== 422) throw error;
    for (let attempt = 0; attempt < VERIFY_ATTEMPTS; attempt += 1) {
      const refreshed = await releaseState(github, props);
      if (refreshed.releases.has(tag)) return refreshed.releases.get(tag);
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    fail(`Release ${tag} conflicted but did not become readable`, error);
  }
}

async function moveFloating(github, props, target, sha, state) {
  const tag = `v${target.major}`;
  const existing = await getRef(github, props, `tags/${tag}`);
  if (!existing) return createRef(github, props, tag, sha);
  const currentSha = await resolveCommit(github, props, existing.object);
  if (currentSha === sha) return;
  const currentRelease = state.published.find((item) => item.major === target.major && item.sha === currentSha);
  if (!currentRelease) fail(`${tag} points to unrecognized revision ${currentSha}`);
  if (compareVersions(currentRelease, target) >= 0) fail(`Refusing to move ${tag} backward from ${currentRelease.tag} to ${target.tag}`);
  const localHead = runGit(['rev-parse', 'HEAD']).trim();
  if (localHead !== sha) fail(`Checked-out revision ${localHead} does not match target ${sha}`);
  try {
    childProcess.execFileSync('git', [
      'push', '--porcelain', `--force-with-lease=refs/tags/${tag}:${currentSha}`,
      'origin', `HEAD:refs/tags/${tag}`,
    ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (error) {
    const current = await getRef(github, props, `tags/${tag}`);
    if (current && await resolveCommit(github, props, current.object) === sha) return;
    fail(`Concurrent update prevented the leased move of ${tag}`, error);
  }
}

async function verifyCompleted(github, props, target) {
  const state = await releaseState(github, props);
  const item = state.published.find((release) => release.tag === target.tag && release.sha === target.sha);
  if (!item) fail(`${target.tag} is not published at ${target.sha}`);
  const floating = await getRef(github, props, `tags/v${target.major}`);
  if (!floating || await resolveCommit(github, props, floating.object) !== target.sha) {
    fail(`Floating tag v${target.major} does not identify ${target.tag}`);
  }
  if (target.minor === 0 && target.patch === 0) {
    const fixed = await getRef(github, props, `tags/v${target.major}.0`);
    if (!fixed || await resolveCommit(github, props, fixed.object) !== target.sha) {
      fail(`Fixed tag v${target.major}.0 does not identify ${target.tag}`);
    }
  }
}

async function publishTarget({ github, context, core, mode }) {
  const sha = mode === 'major' ? (process.env.RELEASE_TARGET_SHA || '').trim() : context.sha;
  const props = { owner: context.repo.owner, repo: context.repo.repo };
  if (!SHA_PATTERN.test(sha)) fail('Target must be a full lowercase 40-character SHA');
  if (context.sha !== sha) fail(`Workflow revision ${context.sha} does not match target ${sha}`);
  if (mode === 'major') {
    if (context.eventName !== 'workflow_dispatch' || context.ref !== 'refs/heads/master') fail('Major publication requires workflow_dispatch from master');
    if (process.env.RELEASE_CONFIRMATION !== `PUBLISH NEXT MAJOR AT ${sha}`) {
      fail(`confirmation must exactly equal PUBLISH NEXT MAJOR AT ${sha}`);
    }
  } else if (context.eventName !== 'push' || context.ref !== 'refs/heads/master') {
    fail('Patch publication requires a push to master');
  }
  await requireMaster(github, props, sha);

  let state = await releaseState(github, props);
  const alreadyPublished = state.published.filter((item) => item.sha === sha).at(-1);
  const completedMajorRetry = mode === 'major' && alreadyPublished
    && alreadyPublished.tag === state.latest.tag
    && alreadyPublished.minor === 0 && alreadyPublished.patch === 0;
  if (alreadyPublished && (mode === 'patch' || completedMajorRetry)) {
    if (alreadyPublished.tag !== state.latest.tag) fail(`${sha} is an older published revision ${alreadyPublished.tag}`);
    await verifyCompleted(github, props, { ...alreadyPublished, sha });
    core.info(`revision=${sha} outcome=already-published version=${alreadyPublished.tag}`);
    return;
  }

  const version = mode === 'major'
    ? { major: state.latest.major + 1, minor: 0, patch: 0 }
    : { major: state.latest.major, minor: state.latest.minor, patch: state.latest.patch + 1 };
  const target = { ...version, tag: formatVersion(version), sha };
  const incomplete = state.immutable.filter((item) => !state.published.some((published) => published.tag === item.tag));
  if (incomplete.some((item) => item.tag !== target.tag || item.sha !== sha)) {
    fail(`Incomplete release ${incomplete[0].tag} at ${incomplete[0].sha} blocks publication`);
  }

  if (mode === 'patch') {
    const scope = await exposedContentChanged(github, props, state.latest.sha, sha);
    if (!scope.changed && incomplete.length === 0) {
      core.info(`revision=${sha} outcome=no-action-change baseline=${state.latest.tag}`);
      await core.summary.addHeading('Action release').addRaw(`No exposed action content changed from \`${state.latest.tag}\`.`).write();
      return;
    }
    core.info(`revision=${sha} outcome=patch version=${target.tag} changed=${scope.changedPaths.join(',')}`);
  } else {
    core.info(`revision=${sha} outcome=major version=${target.tag}`);
  }

  const conflict = state.immutable.find((item) => item.tag === target.tag && item.sha !== sha);
  if (conflict) fail(`${target.tag} already points to ${conflict.sha}`);
  await createRef(github, props, target.tag, sha);
  if (mode === 'major') await createRef(github, props, `v${target.major}.0`, sha);
  state = await releaseState(github, props);
  const release = await ensureDraft(github, props, state, target.tag, sha, mode === 'major' ? 'Manual major' : 'Automatic patch');
  if (!release.draft) {
    await verifyCompleted(github, props, target);
    core.info(`revision=${sha} outcome=already-published version=${target.tag}`);
    return;
  }
  state = await releaseState(github, props);
  await moveFloating(github, props, target, sha, state);
  await github.rest.repos.updateRelease({
    ...props, release_id: release.id, tag_name: target.tag, target_commitish: sha,
    name: target.tag, body: release.body, draft: false, prerelease: false,
  });
  await verifyCompleted(github, props, target);
  core.info(`revision=${sha} outcome=published version=${target.tag}`);
  await core.summary.addHeading('Action release').addTable([
    [{ data: 'Revision', header: true }, sha],
    [{ data: 'Version', header: true }, target.tag],
    [{ data: 'Mode', header: true }, mode],
  ]).write();
}

function localTree(revision) {
  const rows = runGit(['ls-tree', '-r', '-z', revision]).split('\0').filter(Boolean);
  return new Map(rows.map((row) => {
    const match = /^(\d+) (\w+) ([0-9a-f]+)\t(.+)$/.exec(row);
    if (!match) fail(`Unexpected ls-tree row ${row}`);
    return [match[4], { mode: match[1], type: match[2], sha: match[3] }];
  }));
}

function localScopeDiff(base, head) {
  const baseTree = localTree(base);
  const headTree = localTree(head);
  const baseScope = parseScope(runGit(['show', `${base}:${SCOPE_PATH}`]), `${SCOPE_PATH} at ${base}`);
  const headScope = parseScope(runGit(['show', `${head}:${SCOPE_PATH}`]), `${SCOPE_PATH} at ${head}`);
  validateHeadScope(baseTree, baseScope);
  validateHeadScope(headTree, headScope);
  const paths = new Set([...baseTree.keys(), ...headTree.keys()]);
  const changed = [...paths].filter((path) => {
    const before = inScope(path, baseScope) ? baseTree.get(path) : null;
    const after = inScope(path, headScope) ? headTree.get(path) : null;
    return JSON.stringify(before) !== JSON.stringify(after);
  }).sort();
  process.stdout.write(`Exposed action content changed: ${changed.length > 0}\nChanged paths: ${changed.join(', ') || '(none)'}\n`);
}

module.exports = {
  exposedContentChanged,
  parseScope,
  publishMajor: (args) => publishTarget({ ...args, mode: 'major' }),
  publishPatch: (args) => publishTarget({ ...args, mode: 'patch' }),
};

if (require.main === module) {
  const [command, base, head] = process.argv.slice(2);
  try {
    if (command === 'scope-diff' && base && head) localScopeDiff(base, head);
    else if (command === 'validate-scope' && !base && !head) {
      const scope = parseScope(fs.readFileSync(SCOPE_PATH, 'utf8'));
      validateHeadScope(localTree('HEAD'), scope);
      process.stdout.write('Release scope is valid.\n');
    } else {
      fail('Usage: semantic-release.js validate-scope | scope-diff <base> <head>');
    }
  } catch (error) {
    process.stderr.write(`Semantic release validation failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}
