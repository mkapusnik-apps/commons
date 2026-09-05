'use strict';

const childProcess = require('node:child_process');
const fs = require('node:fs');

const REGISTRY_PATH = '.github/semantic-release/actions.json';
const DECLARATION_DIRECTORY = '.github/semantic-release/declarations/';
const PUBLISH_WORKFLOW_PATH = '.github/workflows/publish-semantic-release.yml';
const BASELINE_AUTHORIZATION_PATH = '.github/semantic-release/release-baseline-reset-2026.json';
const BASELINE_CONFIRMATION = 'RESET RELEASE BASELINE TO V1.0.4';
const IMMUTABLE_TAG_PATTERN = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const ZERO_SHA_PATTERN = /^0+$/;
const RELEASE_STATE_VERIFICATION_ATTEMPTS = 6;
const RELEASE_STATE_VERIFICATION_DELAY_MS = 2000;

function fail(message, cause = null) {
  throw new Error(message, cause ? { cause } : undefined);
}

function parseJson(path, content) {
  try {
    return JSON.parse(content);
  } catch (error) {
    fail(`${path} is not valid JSON: ${error.message}`);
  }
}

function requireExactKeys(path, value, expectedKeys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${path} must contain a JSON object`);
  }

  const actual = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    fail(`${path} must contain exactly these keys: ${expected.join(', ')}`);
  }
}

function validateRegistry(content, path = REGISTRY_PATH) {
  const registry = parseJson(path, content);
  requireExactKeys(path, registry, ['schema', 'actionDirectories']);
  if (registry.schema !== 1) fail(`${path} schema must be 1`);
  if (!Array.isArray(registry.actionDirectories) || registry.actionDirectories.length === 0) {
    fail(`${path} actionDirectories must be a non-empty array`);
  }

  const directories = registry.actionDirectories;
  for (const directory of directories) {
    if (typeof directory !== 'string' || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(directory)) {
      fail(`${path} contains invalid root-level action directory ${JSON.stringify(directory)}`);
    }
  }

  const sorted = [...directories].sort();
  if (JSON.stringify(directories) !== JSON.stringify(sorted)) {
    fail(`${path} actionDirectories must be sorted lexicographically`);
  }
  if (new Set(directories).size !== directories.length) {
    fail(`${path} actionDirectories must not contain duplicates`);
  }
  return directories;
}

function validateDeclaration(content, path) {
  const declaration = parseJson(path, content);
  requireExactKeys(path, declaration, ['schema', 'apiChange']);
  if (declaration.schema !== 1) fail(`${path} schema must be 1`);
  if (typeof declaration.apiChange !== 'boolean') {
    fail(`${path} apiChange must be a JSON boolean`);
  }
  return declaration;
}

function versionFromTag(tag) {
  const match = IMMUTABLE_TAG_PATTERN.exec(tag);
  if (!match) return null;
  return {
    tag,
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

function compareVersions(left, right) {
  return left.major - right.major || left.minor - right.minor || left.patch - right.patch;
}

function nextVersion(previous, outcome) {
  if (outcome === 'major') return { major: previous.major + 1, minor: 0, patch: 0 };
  if (outcome === 'minor') return { major: previous.major, minor: previous.minor + 1, patch: 0 };
  return { major: previous.major, minor: previous.minor, patch: previous.patch + 1 };
}

function formatVersion(version) {
  return `v${version.major}.${version.minor}.${version.patch}`;
}

function validateBaselineAuthorization(content, path = BASELINE_AUTHORIZATION_PATH) {
  const authorization = parseJson(path, content);
  requireExactKeys(path, authorization, [
    'schema',
    'authorization',
    'historicalTip',
    'resetAnchor',
    'bridgeTree',
    'historicalReleases',
    'previousRelease',
    'fixedMinor',
    'expectedClassification',
    'expectedTag',
    'expiresAt',
  ]);
  if (authorization.schema !== 1) fail(`${path} schema must be 1`);
  if (authorization.authorization !== 'release-baseline-reset-2026') {
    fail(`${path} has an unexpected authorization identifier`);
  }
  for (const key of ['historicalTip', 'resetAnchor', 'bridgeTree']) {
    if (!/^[0-9a-f]{40}$/.test(authorization[key])) fail(`${path} ${key} must be a full lowercase SHA`);
  }
  requireExactKeys(`${path} previousRelease`, authorization.previousRelease, ['tag', 'sha']);
  requireExactKeys(`${path} fixedMinor`, authorization.fixedMinor, ['tag', 'sha']);
  if (!Array.isArray(authorization.historicalReleases) || authorization.historicalReleases.length !== 4) {
    fail(`${path} historicalReleases must contain exactly four releases`);
  }
  const historicalTags = [];
  for (const [index, release] of authorization.historicalReleases.entries()) {
    const releasePath = `${path} historicalReleases[${index}]`;
    requireExactKeys(releasePath, release, ['tag', 'sha']);
    if (!versionFromTag(release.tag) || !/^[0-9a-f]{40}$/.test(release.sha)) {
      fail(`${releasePath} must contain an immutable version tag and full lowercase SHA`);
    }
    historicalTags.push(release.tag);
  }
  if (historicalTags.join(',') !== 'v1.0.0,v1.0.1,v1.0.2,v1.0.3') {
    fail(`${path} historicalReleases must list v1.0.0 through v1.0.3 in order`);
  }
  if (authorization.previousRelease.tag !== 'v1.0.3' || !/^[0-9a-f]{40}$/.test(authorization.previousRelease.sha)) {
    fail(`${path} must authorize previous release v1.0.3 at a full lowercase SHA`);
  }
  const lastHistorical = authorization.historicalReleases.at(-1);
  if (lastHistorical.tag !== authorization.previousRelease.tag || lastHistorical.sha !== authorization.previousRelease.sha) {
    fail(`${path} previousRelease must equal the last historical release`);
  }
  if (authorization.fixedMinor.tag !== 'v1.0' || !/^[0-9a-f]{40}$/.test(authorization.fixedMinor.sha)) {
    fail(`${path} must identify fixed tag v1.0 at a full lowercase SHA`);
  }
  if (authorization.expectedClassification !== 'patch' || authorization.expectedTag !== 'v1.0.4') {
    fail(`${path} must authorize only patch release v1.0.4`);
  }
  if (formatVersion(nextVersion(versionFromTag(lastHistorical.tag), 'patch')) !== authorization.expectedTag) {
    fail(`${path} expectedTag must be the patch after previousRelease`);
  }
  if (authorization.fixedMinor.sha !== authorization.historicalReleases[0].sha) {
    fail(`${path} fixedMinor must remain at the v1.0.0 revision`);
  }
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(authorization.expiresAt)) {
    fail(`${path} expiresAt must be an exact UTC timestamp`);
  }
  const expiresAt = Date.parse(authorization.expiresAt);
  if (!Number.isFinite(expiresAt)) fail(`${path} expiresAt is invalid`);
  if (new Date(expiresAt).toISOString().replace('.000Z', 'Z') !== authorization.expiresAt) {
    fail(`${path} expiresAt must identify a real UTC date and second`);
  }
  return { ...authorization, expiresAtMilliseconds: expiresAt };
}

function classifyChangeSet({ changedPaths, pathExistsAtBase, pathExistsAtHead, readAtBase, readAtHead }) {
  if (!pathExistsAtHead(REGISTRY_PATH)) fail(`Required action registry ${REGISTRY_PATH} is missing`);
  const currentDirectories = validateRegistry(readAtHead(REGISTRY_PATH));
  for (const directory of currentDirectories) {
    const metadataPath = `${directory}/action.yml`;
    if (!pathExistsAtHead(metadataPath)) {
      fail(`Registered action directory ${directory} is missing ${metadataPath}`);
    }
  }

  let previousDirectories = [];
  let registryChanged = false;
  if (pathExistsAtBase(REGISTRY_PATH)) {
    previousDirectories = validateRegistry(readAtBase(REGISTRY_PATH), `${REGISTRY_PATH} at base revision`);
    registryChanged = JSON.stringify(previousDirectories) !== JSON.stringify(currentDirectories);
  }

  const changedDeclarations = changedPaths.filter((path) => path.startsWith(DECLARATION_DIRECTORY));
  for (const path of changedDeclarations) {
    if (!/^\.github\/semantic-release\/declarations\/[a-z0-9][a-z0-9-]*\.json$/.test(path)) {
      fail(`Declaration path ${path} must use ${DECLARATION_DIRECTORY}<lowercase-slug>.json`);
    }
    if (pathExistsAtBase(path) || !pathExistsAtHead(path)) {
      fail(`Release declarations are append-only; ${path} must be a newly added file`);
    }
  }
  if (changedDeclarations.length === 0) {
    fail('At least one new release declaration is required; found 0');
  }

  const declarations = changedDeclarations.map((path) => ({
    path,
    value: validateDeclaration(readAtHead(path), path),
  }));
  const apiChange = declarations.some((declaration) => declaration.value.apiChange);
  if (registryChanged && !apiChange) {
    fail('Changing the published action registry requires at least one declaration with apiChange: true');
  }

  const knownDirectories = new Set([...previousDirectories, ...currentDirectories]);
  const affectedActions = [...knownDirectories]
    .filter((directory) => changedPaths.some((path) => path === directory || path.startsWith(`${directory}/`)))
    .sort();

  const outcome = apiChange ? 'major' : affectedActions.length >= 2 ? 'minor' : 'patch';
  return {
    outcome,
    apiChange,
    affectedActions,
    declarationPaths: declarations.map((declaration) => declaration.path),
    registryChanged,
  };
}

function runGit(args, options = {}) {
  try {
    return childProcess.execFileSync('git', args, {
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
      ...options,
    });
  } catch (error) {
    const detail = error.stderr ? error.stderr.toString().trim() : error.message;
    fail(`git ${args.join(' ')} failed: ${detail}`);
  }
}

function localPathExists(revision, path) {
  try {
    childProcess.execFileSync('git', ['cat-file', '-e', `${revision}:${path}`], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function validateLocal(baseSha, headSha) {
  if (!/^[0-9a-f]{40}$/i.test(baseSha) || !/^[0-9a-f]{40}$/i.test(headSha)) {
    fail('validate requires full 40-character base and head commit SHAs');
  }

  const comparisonBase = runGit(['merge-base', baseSha, headSha]).trim();
  if (!/^[0-9a-f]{40}$/i.test(comparisonBase)) {
    fail(`Could not determine a merge base for ${baseSha} and ${headSha}`);
  }
  const changedPaths = runGit(['diff', '--name-only', '-z', comparisonBase, headSha, '--'])
    .split('\0')
    .filter(Boolean);
  const readAt = (revision, path) => runGit(['show', `${revision}:${path}`]);
  const result = classifyChangeSet({
    changedPaths,
    pathExistsAtBase: (path) => localPathExists(comparisonBase, path),
    pathExistsAtHead: (path) => localPathExists(headSha, path),
    readAtBase: (path) => readAt(comparisonBase, path),
    readAtHead: (path) => readAt(headSha, path),
  });

  process.stdout.write([
    'Semantic release declaration is valid.',
    `Base revision: ${comparisonBase}`,
    `Head revision: ${headSha}`,
    `Outcome: ${result.outcome}`,
    `API change: ${result.apiChange}`,
    `Affected actions: ${result.affectedActions.join(', ') || '(none)'}`,
    `Declarations: ${result.declarationPaths.join(', ')}`,
    '',
  ].join('\n'));
  return result;
}

function validateWorktree(baseSha) {
  if (!/^[0-9a-f]{40}$/i.test(baseSha)) {
    fail('validate-worktree requires a full 40-character base commit SHA');
  }

  const changedPaths = new Set(
    runGit(['diff', '--name-only', '-z', baseSha, '--']).split('\0').filter(Boolean),
  );
  for (const path of runGit(['ls-files', '--others', '--exclude-standard', '-z']).split('\0').filter(Boolean)) {
    changedPaths.add(path);
  }

  const worktreePathExists = (path) => {
    try {
      return fs.statSync(path).isFile();
    } catch {
      return false;
    }
  };
  const result = classifyChangeSet({
    changedPaths: [...changedPaths].sort(),
    pathExistsAtBase: (path) => localPathExists(baseSha, path),
    pathExistsAtHead: worktreePathExists,
    readAtBase: (path) => runGit(['show', `${baseSha}:${path}`]),
    readAtHead: (path) => fs.readFileSync(path, 'utf8'),
  });

  process.stdout.write([
    'Semantic release worktree declaration is valid.',
    `Base revision: ${baseSha}`,
    'Head revision: (working tree)',
    `Outcome: ${result.outcome}`,
    `API change: ${result.apiChange}`,
    `Affected actions: ${result.affectedActions.join(', ') || '(none)'}`,
    `Declarations: ${result.declarationPaths.join(', ')}`,
    '',
  ].join('\n'));
  return result;
}

async function loadTree(github, props, sha) {
  const commit = await github.rest.git.getCommit({ ...props, commit_sha: sha });
  const response = await github.rest.git.getTree({
    ...props,
    tree_sha: commit.data.tree.sha,
    recursive: 'true',
  });
  if (response.data.truncated) fail(`Repository tree for ${sha} is truncated; refusing incomplete classification`);
  return new Map(response.data.tree.map((entry) => [entry.path, entry]));
}

async function readTreeFile(github, props, tree, path) {
  const entry = tree.get(path);
  if (!entry || entry.type !== 'blob') fail(`Required file ${path} is missing or is not a regular file`);
  const blob = await github.rest.git.getBlob({ ...props, file_sha: entry.sha });
  if (blob.data.encoding !== 'base64') fail(`Unsupported encoding for ${path}: ${blob.data.encoding}`);
  return Buffer.from(blob.data.content, 'base64').toString('utf8');
}

function changedTreePaths(baseTree, headTree) {
  const paths = new Set([...baseTree.keys(), ...headTree.keys()]);
  return [...paths].filter((path) => {
    const before = baseTree.get(path);
    const after = headTree.get(path);
    return !before || !after || before.sha !== after.sha || before.mode !== after.mode || before.type !== after.type;
  }).sort();
}

async function classifyApiRange(github, props, baseSha, headSha) {
  const comparison = await github.rest.repos.compareCommitsWithBasehead({
    ...props,
    basehead: `${baseSha}...${headSha}`,
    per_page: 1,
  });
  if (comparison.data.status !== 'ahead') {
    fail(`Publication range ${baseSha}...${headSha} must be a forward-only change; status is ${comparison.data.status}`);
  }

  const [baseTree, headTree] = await Promise.all([
    loadTree(github, props, baseSha),
    loadTree(github, props, headSha),
  ]);
  const changedPaths = changedTreePaths(baseTree, headTree);
  const changedDeclarations = changedPaths.filter((path) => path.startsWith(DECLARATION_DIRECTORY));
  const baseContents = new Map();
  const headContents = new Map();
  if (baseTree.has(REGISTRY_PATH)) {
    baseContents.set(REGISTRY_PATH, await readTreeFile(github, props, baseTree, REGISTRY_PATH));
  }
  for (const path of [REGISTRY_PATH, ...changedDeclarations]) {
    if (headTree.has(path)) {
      headContents.set(path, await readTreeFile(github, props, headTree, path));
    }
  }
  return classifyChangeSet({
    changedPaths,
    pathExistsAtBase: (path) => baseTree.has(path),
    pathExistsAtHead: (path) => headTree.has(path),
    readAtBase: (path) => baseContents.get(path),
    readAtHead: (path) => headContents.get(path),
  });
}

async function revisionRelation(github, props, baseSha, headSha) {
  const comparison = await github.rest.repos.compareCommitsWithBasehead({
    ...props,
    basehead: `${baseSha}...${headSha}`,
    per_page: 1,
  });
  return comparison.data.status;
}

async function latestPublishedAncestor(github, props, published, sha) {
  for (const publication of [...published].reverse()) {
    const status = await revisionRelation(github, props, publication.sha, sha);
    if (status === 'ahead' || status === 'identical') return publication;
  }
  return null;
}

async function resolveObjectToCommit(github, props, object) {
  let current = object;
  for (let depth = 0; depth < 5; depth += 1) {
    if (current.type === 'commit') return current.sha;
    if (current.type !== 'tag') fail(`Tag object ${current.sha} resolves to unsupported type ${current.type}`);
    const tag = await github.rest.git.getTag({ ...props, tag_sha: current.sha });
    current = tag.data.object;
  }
  fail(`Tag object ${object.sha} has excessive annotation depth`);
}

async function loadReleaseState(github, props) {
  const [refs, releases] = await Promise.all([
    github.paginate(github.rest.git.listMatchingRefs, { ...props, ref: 'tags/v', per_page: 100 }),
    github.paginate(github.rest.repos.listReleases, { ...props, per_page: 100 }),
  ]);

  const immutable = [];
  for (const ref of refs) {
    const tag = ref.ref.replace(/^refs\/tags\//, '');
    const version = versionFromTag(tag);
    if (!version) continue;
    immutable.push({
      ...version,
      sha: await resolveObjectToCommit(github, props, ref.object),
    });
  }
  immutable.sort(compareVersions);

  const releasesByTag = new Map();
  for (const release of releases) {
    if (!versionFromTag(release.tag_name)) continue;
    if (releasesByTag.has(release.tag_name)) fail(`Multiple GitHub releases use ${release.tag_name}`);
    releasesByTag.set(release.tag_name, release);
  }

  const published = immutable.filter((item) => {
    const release = releasesByTag.get(item.tag);
    if (!release) return false;
    if (release.prerelease) fail(`Immutable release ${item.tag} must not be a prerelease`);
    return !release.draft;
  });
  for (const [tag, release] of releasesByTag) {
    if (!release.draft && !immutable.some((item) => item.tag === tag)) {
      fail(`Published GitHub release ${tag} has no immutable tag`);
    }
  }
  return { immutable, releasesByTag, published };
}

function uniqueItem(items, description) {
  if (items.length > 1) fail(`Ambiguous release state: multiple ${description}`);
  return items[0] || null;
}

async function getRefOrNull(github, props, ref) {
  try {
    return (await github.rest.git.getRef({ ...props, ref })).data;
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function requireRefAt(github, props, ref, expectedSha) {
  const value = await getRefOrNull(github, props, ref);
  if (!value) fail(`Required ref ${ref} is missing`);
  const actualSha = await resolveObjectToCommit(github, props, value.object);
  if (actualSha !== expectedSha) fail(`Ref ${ref} points to ${actualSha}, expected ${expectedSha}`);
  return value;
}

function verifyInProgressRelease(state, publication) {
  const immutable = state.immutable.find((item) => (
    item.tag === publication.tag && item.sha === publication.sha
  ));
  if (!immutable) {
    fail(`In-progress release ${publication.tag} has no matching immutable tag at ${publication.sha}`);
  }

  const release = state.releasesByTag.get(publication.tag);
  if (!release || !release.draft || release.prerelease) {
    fail(`In-progress release ${publication.tag} must have a stable draft GitHub release`);
  }
}

async function verifyCompletedRelease(github, props, state, publication, allowedInProgress = null) {
  const release = state.releasesByTag.get(publication.tag);
  if (!release || release.draft || release.prerelease) {
    fail(`Release ${publication.tag} is not a published stable GitHub release`);
  }

  const highestInMajor = state.published
    .filter((item) => item.major === publication.major)
    .sort(compareVersions)
    .at(-1);
  if (!highestInMajor) fail(`No published release exists for major v${publication.major}`);

  const floating = await getRefOrNull(github, props, `tags/v${publication.major}`);
  if (!floating) fail(`Floating tag v${publication.major} is missing`);
  const floatingSha = await resolveObjectToCommit(github, props, floating.object);
  if (floatingSha === highestInMajor.sha) return;

  if (
    allowedInProgress
    && highestInMajor.tag === publication.tag
    && allowedInProgress.major === publication.major
    && floatingSha === allowedInProgress.sha
    && compareVersions(publication, allowedInProgress) < 0
  ) {
    verifyInProgressRelease(state, allowedInProgress);
    return;
  }

  fail(`Floating tag v${publication.major} points to ${floatingSha}, expected latest published ${highestInMajor.tag} at ${highestInMajor.sha}`);
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function awaitReleaseState(github, props, predicate, failureMessage, failureCause = null) {
  for (let attempt = 1; attempt <= RELEASE_STATE_VERIFICATION_ATTEMPTS; attempt += 1) {
    const state = await loadReleaseState(github, props);
    if (predicate(state)) return state;
    if (attempt < RELEASE_STATE_VERIFICATION_ATTEMPTS) {
      await sleep(RELEASE_STATE_VERIFICATION_DELAY_MS);
    }
  }
  fail(failureMessage, failureCause);
}

function githubApiErrorDetail(error) {
  const status = error.status || error.response?.status;
  const message = error.message || error.response?.data?.message || 'unknown error';
  return `${status ? `HTTP ${status}: ` : ''}${message}`;
}

async function awaitPredecessor(github, props, beforeSha, currentSha, core) {
  const relation = await revisionRelation(github, props, beforeSha, currentSha);
  if (relation !== 'ahead') {
    fail(`Push range ${beforeSha}...${currentSha} must be forward-only; status is ${relation}`);
  }
  const beforeTree = await loadTree(github, props, beforeSha);
  const crossesActivationGap = !beforeTree.has(PUBLISH_WORKFLOW_PATH);
  const attempts = 106;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const state = await loadReleaseState(github, props);
    const currentImmutable = uniqueItem(
      state.immutable.filter((item) => item.sha === currentSha),
      `immutable tags for revision ${currentSha}`,
    );
    const currentPublished = uniqueItem(
      state.published.filter((item) => item.sha === currentSha),
      `published immutable releases for revision ${currentSha}`,
    );
    if (currentPublished) return { state, completed: currentPublished };

    if (state.published.length === 0) {
      fail('No successful immutable release exists; create the prerequisite v1.0.0 release and v1 tag before enabling automatic publication');
    }

    const incompleteForOtherRevision = state.immutable.find((item) => (
      !state.published.some((published) => published.tag === item.tag)
      && item.sha !== currentSha
    ));

    const predecessor = uniqueItem(
      state.published.filter((item) => item.sha === beforeSha),
      `published immutable releases for predecessor ${beforeSha}`,
    );
    if (predecessor) {
      const latest = await latestPublishedAncestor(github, props, state.published, currentSha);
      if (!latest || predecessor.tag !== latest.tag) {
        const detail = latest ? `${latest.tag} at ${latest.sha}` : '(none)';
        fail(`Predecessor ${beforeSha} is ${predecessor.tag}, but latest successful release in ${currentSha}'s history is ${detail}; refusing an out-of-order publication`);
      }
      if (incompleteForOtherRevision) {
        fail(`Incomplete immutable tag ${incompleteForOtherRevision.tag} belongs to ${incompleteForOtherRevision.sha}; refusing to allocate another version`);
      }
      await verifyCompletedRelease(github, props, state, predecessor, currentImmutable);
      return { state, predecessor };
    }

    if (crossesActivationGap) {
      if (incompleteForOtherRevision) {
        fail(`Incomplete immutable tag ${incompleteForOtherRevision.tag} belongs to ${incompleteForOtherRevision.sha}; refusing to cross the activation gap while another publication is incomplete`);
      }
      const latest = await latestPublishedAncestor(github, props, state.published, currentSha);
      if (!latest) {
        fail(`No successful immutable release is an ancestor of activation revision ${currentSha}`);
      }
      await verifyCompletedRelease(github, props, state, latest, currentImmutable);
      core.info(`Revision ${currentSha} crosses the publication activation gap after ${beforeSha}; using ${latest.tag} at ${latest.sha}`);
      return { state, predecessor: latest, activationGap: true };
    }

    if (attempt === attempts) {
      fail(`Timed out waiting for predecessor revision ${beforeSha} to publish before ${currentSha}`);
    }
    if (attempt === 1 || attempt % 15 === 0) {
      core.info(`Revision ${currentSha} is waiting for predecessor ${beforeSha} (${attempt}/${attempts})`);
    }
    await sleep(20000);
  }
  fail(`Unexpected predecessor wait outcome for ${currentSha}`);
}

async function createImmutableRef(github, props, tag, sha) {
  const fullRef = `refs/tags/${tag}`;
  try {
    await github.rest.git.createRef({ ...props, ref: fullRef, sha });
    return;
  } catch (error) {
    if (error.status !== 422) throw error;
  }

  const existing = await getRefOrNull(github, props, `tags/${tag}`);
  if (!existing) fail(`Creation of immutable ${tag} conflicted, but the ref cannot be read`);
  const existingSha = await resolveObjectToCommit(github, props, existing.object);
  if (existingSha !== sha) {
    fail(`Immutable tag conflict: ${tag} already points to ${existingSha}, not ${sha}`);
  }
}

async function ensureDraftRelease(github, props, state, tag, sha) {
  const existing = state.releasesByTag.get(tag);
  if (existing) {
    if (existing.prerelease) fail(`Existing release ${tag} is unexpectedly a prerelease`);
    return null;
  }

  try {
    await github.rest.repos.createRelease({
      ...props,
      tag_name: tag,
      target_commitish: sha,
      name: tag,
      body: `Automatic release of ${sha}.`,
      draft: true,
      prerelease: false,
    });
    return null;
  } catch (error) {
    if (error.status !== 422) throw error;
    return error;
  }
}

async function setFloatingMajor(github, props, target, sha, state) {
  const name = `v${target.major}`;
  const refName = `tags/${name}`;
  const existing = await getRefOrNull(github, props, refName);
  if (!existing) {
    try {
      await github.rest.git.createRef({ ...props, ref: `refs/tags/${name}`, sha });
      return;
    } catch (error) {
      if (error.status !== 422) throw error;
    }
  }

  const current = await getRefOrNull(github, props, refName);
  if (!current) fail(`Floating tag ${name} conflicted and cannot be read`);
  const currentSha = await resolveObjectToCommit(github, props, current.object);
  if (currentSha === sha) {
    verifyInProgressRelease(state, target);
    return;
  }

  const currentPublication = uniqueItem(
    state.published.filter((item) => item.major === target.major && item.sha === currentSha),
    `published releases for floating tag ${name} at ${currentSha}`,
  );
  if (!currentPublication) {
    fail(`Floating tag ${name} points to unrecognized revision ${currentSha}; refusing to move it`);
  }
  if (compareVersions(currentPublication, target) >= 0) {
    fail(`Floating tag ${name} points to ${currentPublication.tag}; refusing to move it backward to ${target.tag}`);
  }
  await github.rest.git.updateRef({ ...props, ref: refName, sha, force: true });
}

function baselineAuditBody(authorization, targetSha, context) {
  return [
    'One-time semantic release baseline bridge.',
    '',
    `- Release: ${authorization.expectedTag}`,
    `- Classification: ${authorization.expectedClassification}`,
    `- Target master: ${targetSha}`,
    `- Historical tip: ${authorization.historicalTip}`,
    `- Reset anchor: ${authorization.resetAnchor}`,
    `- Bridge tree: ${authorization.bridgeTree}`,
    `- Previous release: ${authorization.previousRelease.tag} at ${authorization.previousRelease.sha}`,
    `- Authorization: ${authorization.authorization}`,
    `- Authorization expiry: ${authorization.expiresAt}`,
    `- Workflow run: ${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
    `- Initiated by: @${context.actor}`,
  ].join('\n');
}

function verifyBaselineAuditBody(body, authorization, targetSha) {
  const required = [
    `Release: ${authorization.expectedTag}`,
    `Classification: ${authorization.expectedClassification}`,
    `Target master: ${targetSha}`,
    `Historical tip: ${authorization.historicalTip}`,
    `Reset anchor: ${authorization.resetAnchor}`,
    `Bridge tree: ${authorization.bridgeTree}`,
    `Previous release: ${authorization.previousRelease.tag} at ${authorization.previousRelease.sha}`,
    `Authorization: ${authorization.authorization}`,
    `Authorization expiry: ${authorization.expiresAt}`,
    'Workflow run:',
    'Initiated by:',
  ];
  for (const value of required) {
    if (!body?.includes(value)) fail(`Release audit metadata is missing ${JSON.stringify(value)}`);
  }
}

async function inspectBaselineState(github, props, authorization, targetSha) {
  const state = await loadReleaseState(github, props);
  for (const historical of authorization.historicalReleases) {
    const immutable = state.immutable.find((item) => item.tag === historical.tag);
    if (!immutable || immutable.sha !== historical.sha) {
      fail(`Historical immutable tag ${historical.tag} must remain at ${historical.sha}`);
    }
    const release = state.releasesByTag.get(historical.tag);
    if (!release || release.draft || release.prerelease) {
      fail(`Historical release ${historical.tag} must remain published and stable`);
    }
  }
  const allowedReleaseTags = new Set([
    ...authorization.historicalReleases.map((item) => item.tag),
    authorization.expectedTag,
  ]);
  const unexpectedImmutable = state.immutable.find((item) => !allowedReleaseTags.has(item.tag));
  if (unexpectedImmutable) fail(`Unexpected immutable semantic tag ${unexpectedImmutable.tag} exists`);
  const unexpectedRelease = [...state.releasesByTag.keys()].find((tag) => !allowedReleaseTags.has(tag));
  if (unexpectedRelease) fail(`Unexpected semantic GitHub release ${unexpectedRelease} exists`);
  const previous = state.immutable.find((item) => item.tag === authorization.previousRelease.tag);
  if (!previous || previous.sha !== authorization.previousRelease.sha) {
    fail(`${authorization.previousRelease.tag} must remain at ${authorization.previousRelease.sha}`);
  }
  const previousRelease = state.releasesByTag.get(authorization.previousRelease.tag);
  if (!previousRelease || previousRelease.draft || previousRelease.prerelease) {
    fail(`${authorization.previousRelease.tag} must remain a published stable GitHub release`);
  }

  await requireRefAt(github, props, `tags/${authorization.fixedMinor.tag}`, authorization.fixedMinor.sha);
  const targetImmutable = state.immutable.find((item) => item.tag === authorization.expectedTag) || null;
  if (targetImmutable && targetImmutable.sha !== targetSha) {
    fail(`${authorization.expectedTag} points to ${targetImmutable.sha}, expected ${targetSha}`);
  }
  const laterImmutable = state.immutable.find((item) => compareVersions(item, versionFromTag(authorization.expectedTag)) > 0);
  if (laterImmutable) fail(`Unexpected later immutable release tag ${laterImmutable.tag} exists`);

  const release = state.releasesByTag.get(authorization.expectedTag) || null;
  if (release?.prerelease) fail(`${authorization.expectedTag} must not be a prerelease`);
  if (release && !targetImmutable) fail(`${authorization.expectedTag} release exists without its immutable tag`);
  if (release) verifyBaselineAuditBody(release.body, authorization, targetSha);

  const floating = await getRefOrNull(github, props, 'tags/v1');
  if (!floating) fail('Floating tag v1 is missing');
  const floatingSha = await resolveObjectToCommit(github, props, floating.object);
  if (![authorization.previousRelease.sha, targetSha].includes(floatingSha)) {
    fail(`Floating tag v1 points to unauthorized revision ${floatingSha}`);
  }

  let stage = 'initial';
  if (targetImmutable && !release && floatingSha === authorization.previousRelease.sha) stage = 'tag-created';
  else if (targetImmutable && release?.draft && floatingSha === authorization.previousRelease.sha) stage = 'draft-created';
  else if (targetImmutable && release?.draft && floatingSha === targetSha) stage = 'major-moved';
  else if (targetImmutable && release && !release.draft && floatingSha === targetSha) stage = 'complete';
  else if (!(targetImmutable === null && release === null && floatingSha === authorization.previousRelease.sha)) {
    fail('Release baseline resources form an unauthorized partial state');
  }

  return { state, release, stage };
}

async function verifyBridgeCommit(github, props, sha, expectedTree, description) {
  const commit = await github.rest.git.getCommit({ ...props, commit_sha: sha });
  if (commit.data.tree.sha !== expectedTree) {
    fail(`${description} ${sha} has tree ${commit.data.tree.sha}, expected ${expectedTree}`);
  }
  return commit.data;
}

async function bootstrapBaseline({ github, context, core }) {
  const targetSha = (process.env.BASELINE_TARGET_SHA || '').trim();
  const confirmation = process.env.BASELINE_CONFIRMATION || '';
  const outcomePrefix = `baseline-target=${targetSha || '(missing)'}`;
  try {
    if (context.eventName !== 'workflow_dispatch' || context.ref !== 'refs/heads/master') {
      fail(`Only workflow_dispatch on refs/heads/master is authorized; event=${context.eventName}, ref=${context.ref}`);
    }
    if (!/^[0-9a-f]{40}$/.test(targetSha)) fail('target_sha must be a full lowercase 40-character SHA');
    if (confirmation !== BASELINE_CONFIRMATION) fail(`confirmation must exactly equal ${BASELINE_CONFIRMATION}`);
    if (context.sha !== targetSha) fail(`Dispatched workflow SHA ${context.sha} does not match target_sha ${targetSha}`);

    const authorization = validateBaselineAuthorization(fs.readFileSync(BASELINE_AUTHORIZATION_PATH, 'utf8'));
    const props = { owner: context.repo.owner, repo: context.repo.repo };
    await requireRefAt(github, props, 'heads/master', targetSha);

    // A completed exact publication is a safe no-op even though the reset severed ancestry.
    let inspected = await inspectBaselineState(github, props, authorization, targetSha);
    if (inspected.stage === 'complete') {
      core.info(`${outcomePrefix} outcome=already-complete version=${authorization.expectedTag}`);
      return;
    }

    const historical = await verifyBridgeCommit(
      github, props, authorization.historicalTip, authorization.bridgeTree, 'Historical tip',
    );
    const reset = await verifyBridgeCommit(
      github, props, authorization.resetAnchor, authorization.bridgeTree, 'Reset anchor',
    );
    if (reset.parents.length !== 0) fail(`Reset anchor ${authorization.resetAnchor} must be a root commit`);
    if (historical.sha === reset.sha) fail('Historical tip and reset anchor must be distinct commits');
    if (targetSha !== authorization.resetAnchor) {
      const relation = await revisionRelation(github, props, authorization.resetAnchor, targetSha);
      if (relation !== 'ahead') fail(`Current master must descend from reset anchor; status is ${relation}`);
    }

    if (Date.now() > authorization.expiresAtMilliseconds && inspected.stage === 'initial') {
      fail(`Authorization expired at ${authorization.expiresAt}; a new publication cannot start`);
    }

    const target = { ...versionFromTag(authorization.expectedTag), sha: targetSha };
    const auditBody = baselineAuditBody(authorization, targetSha, context);
    if (inspected.stage === 'initial') {
      await createImmutableRef(github, props, authorization.expectedTag, targetSha);
      inspected = await inspectBaselineState(github, props, authorization, targetSha);
      if (inspected.stage !== 'tag-created') fail('Immutable tag creation did not reach the authorized state');
    }
    if (inspected.stage === 'tag-created') {
      let creationError = null;
      try {
        await github.rest.repos.createRelease({
          ...props,
          tag_name: authorization.expectedTag,
          target_commitish: targetSha,
          name: authorization.expectedTag,
          body: auditBody,
          draft: true,
          prerelease: false,
        });
      } catch (error) {
        if (error.status !== 422) throw error;
        creationError = error;
      }
      inspected = await awaitReleaseState(
        github,
        props,
        (state) => state.releasesByTag.has(authorization.expectedTag),
        creationError
          ? `Draft release ${authorization.expectedTag} was not readable after createRelease returned ${githubApiErrorDetail(creationError)}`
          : `Draft release ${authorization.expectedTag} did not become readable`,
        creationError,
      ).then(() => inspectBaselineState(github, props, authorization, targetSha));
      if (inspected.stage !== 'draft-created') fail('Draft creation did not reach the authorized state');
    }
    if (inspected.stage === 'draft-created') {
      await github.rest.git.updateRef({ ...props, ref: 'tags/v1', sha: targetSha, force: true });
      inspected = await inspectBaselineState(github, props, authorization, targetSha);
      if (inspected.stage !== 'major-moved') fail('Floating tag update did not reach the authorized state');
    }
    if (inspected.stage === 'major-moved') {
      await github.rest.repos.updateRelease({
        ...props,
        release_id: inspected.release.id,
        tag_name: authorization.expectedTag,
        target_commitish: targetSha,
        name: authorization.expectedTag,
        body: auditBody,
        draft: false,
        prerelease: false,
      });
    }

    const completed = await awaitReleaseState(
      github,
      props,
      (state) => state.published.some((item) => item.tag === authorization.expectedTag && item.sha === targetSha),
      `Release ${authorization.expectedTag} did not verify as published at ${targetSha}`,
    );
    await verifyCompletedRelease(github, props, completed, target);
    inspected = await inspectBaselineState(github, props, authorization, targetSha);
    if (inspected.stage !== 'complete') fail('Release baseline postconditions are incomplete');
    core.info(`${outcomePrefix} outcome=published version=${authorization.expectedTag}`);
    await core.summary
      .addHeading('Semantic release baseline')
      .addTable([
        [{ data: 'Target', header: true }, targetSha],
        [{ data: 'Version', header: true }, authorization.expectedTag],
        [{ data: 'Classification', header: true }, authorization.expectedClassification],
        [{ data: 'Bridge tree', header: true }, authorization.bridgeTree],
        [{ data: 'Outcome', header: true }, 'published'],
      ])
      .write();
  } catch (error) {
    core.error(`${outcomePrefix} outcome=failed message=${error.message}`);
    throw error;
  }
}

async function publish({ github, context, core }) {
  const sha = context.sha;
  const beforeSha = context.payload.before;
  const outcomePrefix = `revision=${sha}`;
  try {
    if (context.eventName !== 'push' || context.ref !== 'refs/heads/master') {
      fail(`Non-qualifying event ${context.eventName} on ${context.ref} cannot publish`);
    }
    if (!/^[0-9a-f]{40}$/i.test(sha) || !/^[0-9a-f]{40}$/i.test(beforeSha) || ZERO_SHA_PATTERN.test(beforeSha)) {
      fail(`Push requires non-zero full before/after SHAs; before=${beforeSha}, after=${sha}`);
    }
    if (context.payload.after !== sha) fail(`Push after SHA ${context.payload.after} does not match workflow SHA ${sha}`);

    const props = { owner: context.repo.owner, repo: context.repo.repo };
    const initialState = await loadReleaseState(github, props);
    const alreadyCompleted = uniqueItem(
      initialState.published.filter((item) => item.sha === sha),
      `published immutable releases for revision ${sha}`,
    );
    if (alreadyCompleted) {
      await verifyCompletedRelease(github, props, initialState, alreadyCompleted);
      core.info(`${outcomePrefix} outcome=already-complete version=${alreadyCompleted.tag}`);
      return;
    }
    const gate = await awaitPredecessor(github, props, beforeSha, sha, core);
    if (gate.completed) {
      await verifyCompletedRelease(github, props, gate.state, gate.completed);
      core.info(`${outcomePrefix} outcome=already-complete version=${gate.completed.tag}`);
      await core.summary
        .addHeading('Semantic release publication')
        .addRaw(`Revision \`${sha}\` was already completely published as \`${gate.completed.tag}\`.`)
        .write();
      return;
    }

    const existingForSha = uniqueItem(
      gate.state.immutable.filter((item) => item.sha === sha),
      `immutable tags for revision ${sha}`,
    );
    const classification = await classifyApiRange(github, props, gate.predecessor.sha, sha);
    const allocated = nextVersion(gate.predecessor, classification.outcome);
    const tag = formatVersion(allocated);
    const target = { ...allocated, tag, sha };
    if (existingForSha && existingForSha.tag !== tag) {
      fail(`Revision ${sha} already has partial immutable tag ${existingForSha.tag}, but deterministic classification requires ${tag}`);
    }

    const conflictingTag = gate.state.immutable.find((item) => item.tag === tag && item.sha !== sha);
    if (conflictingTag) fail(`Immutable tag ${tag} already points to ${conflictingTag.sha}, not ${sha}`);

    core.info(`${outcomePrefix} outcome=${classification.outcome} version=${tag} declarations=${classification.declarationPaths.join(',')} actions=${classification.affectedActions.join(',') || 'none'}`);
    await createImmutableRef(github, props, tag, sha);
    const stateAfterTag = await loadReleaseState(github, props);
    const draftCreationError = await ensureDraftRelease(github, props, stateAfterTag, tag, sha);
    const draftVerificationFailure = draftCreationError
      ? `Release ${tag} was not readable after createRelease returned ${githubApiErrorDetail(draftCreationError)}`
      : `Release ${tag} was not readable after ensuring its draft`;
    const stateWithRelease = await awaitReleaseState(
      github,
      props,
      (state) => state.releasesByTag.has(tag),
      draftVerificationFailure,
      draftCreationError,
    );
    const release = stateWithRelease.releasesByTag.get(tag);
    if (!release.draft) {
      await verifyCompletedRelease(github, props, stateWithRelease, target);
      core.info(`${outcomePrefix} outcome=already-complete version=${tag}`);
      return;
    }

    verifyInProgressRelease(stateWithRelease, target);
    await setFloatingMajor(github, props, target, sha, stateWithRelease);
    const immutableRef = await getRefOrNull(github, props, `tags/${tag}`);
    const floatingRef = await getRefOrNull(github, props, `tags/v${target.major}`);
    if (!immutableRef || await resolveObjectToCommit(github, props, immutableRef.object) !== sha) {
      fail(`Immutable tag ${tag} did not verify at ${sha}`);
    }
    if (!floatingRef || await resolveObjectToCommit(github, props, floatingRef.object) !== sha) {
      fail(`Floating tag v${target.major} did not verify at ${sha}`);
    }

    await github.rest.repos.updateRelease({
      ...props,
      release_id: release.id,
      tag_name: tag,
      target_commitish: sha,
      name: tag,
      body: release.body || `Automatic release of ${sha}.`,
      draft: false,
      prerelease: false,
    });

    const completedState = await awaitReleaseState(
      github,
      props,
      (state) => state.published.some((item) => item.tag === tag && item.sha === sha),
      `Release ${tag} did not verify as published for ${sha}`,
    );
    const completed = uniqueItem(
      completedState.published.filter((item) => item.sha === sha),
      `published immutable releases for revision ${sha}`,
    );
    if (!completed || completed.tag !== tag) {
      fail(`Release ${tag} did not verify as published for ${sha}`);
    }
    await verifyCompletedRelease(github, props, completedState, completed);

    core.info(`${outcomePrefix} outcome=published version=${tag}`);
    await core.summary
      .addHeading('Semantic release publication')
      .addTable([
        [{ data: 'Revision', header: true }, sha],
        [{ data: 'Version', header: true }, tag],
        [{ data: 'Classification', header: true }, classification.outcome],
        [{ data: 'API change', header: true }, String(classification.apiChange)],
        [{ data: 'Affected actions', header: true }, classification.affectedActions.join(', ') || '(none)'],
        [{ data: 'Declarations', header: true }, classification.declarationPaths.join(', ')],
      ])
      .write();
  } catch (error) {
    core.error(`${outcomePrefix} outcome=failed message=${error.message}`);
    await core.summary
      .addHeading('Semantic release publication failed')
      .addRaw(`Revision \`${sha}\` was not completely published. ${error.message}`)
      .write();
    throw error;
  }
}

module.exports = {
  bootstrapBaseline,
  classifyChangeSet,
  publish,
  validateLocal,
  validateWorktree,
  validateRegistry,
  validateDeclaration,
  validateBaselineAuthorization,
};

if (require.main === module) {
  const [command, baseSha, headSha] = process.argv.slice(2);
  if ((command !== 'validate' && command !== 'validate-worktree') || !baseSha || (command === 'validate' && !headSha)) {
    process.stderr.write([
      'Usage:',
      '  node .github/scripts/semantic-release.js validate <base-sha> <head-sha>',
      '  node .github/scripts/semantic-release.js validate-worktree <base-sha>',
      '',
    ].join('\n'));
    process.exitCode = 2;
  } else {
    try {
      if (command === 'validate') validateLocal(baseSha, headSha);
      else validateWorktree(baseSha);
    } catch (error) {
      process.stderr.write(`Semantic release validation failed: ${error.message}\n`);
      process.exitCode = 1;
    }
  }
}
