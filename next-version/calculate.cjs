const { execFileSync } = require('node:child_process');

const numeric = /^[1-9][0-9]*$/;
const nonnegative = /^(0|[1-9][0-9]*)$/;
const version = /^\d+\.\d+\.\d+$/;

function calculateVersion({ baselineName, latestName, latestCode = '0', minimumCode = '0' }) {
  const [major, minor] = baselineName.split('.').map(Number);
  const [latestMajor, latestMinor, latestPatch] = latestName ? latestName.split('.').map(Number) : [];
  const nextMinor = minor + 1;
  if (latestMajor > major || (latestMajor === major && latestMinor > nextMinor)) {
    throw new Error(`Latest candidate series ${latestMajor}.${latestMinor} is ahead of target ${major}.${nextMinor}; release owner must resolve manually`);
  }
  const patch = latestMajor === major && latestMinor === nextMinor ? latestPatch + 1 : 0;
  const highestCode = BigInt(latestCode);
  const minimum = BigInt(minimumCode);
  return { name: `${major}.${nextMinor}.${patch}`, code: String((highestCode > minimum ? highestCode : minimum) + 1n) };
}

function nextVersion({ baselineTag, fallbackTag = '', fallbackVersion = '', minimumCode = '', annotationPrefix, sourceSha = '', cwd }) {
  if (typeof baselineTag !== 'string' || !baselineTag.trim()) {
    throw new Error('Input "baseline-tag" is required');
  }
  if (typeof annotationPrefix !== 'string' || !annotationPrefix.trim()
      || annotationPrefix !== annotationPrefix.trim() || /[\r\n\t]/.test(annotationPrefix)) {
    throw new Error('Input "annotation-prefix" must be a nonempty single-line prefix without surrounding whitespace');
  }
  baselineTag = baselineTag.trim();
  fallbackTag = fallbackTag.trim();
  sourceSha = sourceSha.trim();
  if (fallbackTag && !numeric.test(fallbackTag)) {
    throw new Error('Input "fallback-tag" must be a positive integer tag name');
  }
  if (fallbackVersion !== '' && (typeof fallbackVersion !== 'string'
      || fallbackVersion !== fallbackVersion.trim() || !version.test(fallbackVersion))) {
    throw new Error('Input "fallback-version" must be a numeric X.Y.Z version value');
  }
  if (minimumCode !== '' && (typeof minimumCode !== 'string'
      || minimumCode !== minimumCode.trim() || !nonnegative.test(minimumCode))) {
    throw new Error('Input "minimum-code" must be a nonnegative integer without leading zeroes');
  }
  const git = (...args) => {
    try {
      return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: 'pipe' }).trim();
    } catch (error) {
      const detail = error.stderr?.toString().trim() || error.message;
      throw new Error(`Git ${args[0]} failed: ${detail}`);
    }
  };
  git('check-ref-format', `refs/tags/${baselineTag}`);
  const latestCode = git('tag', '--list', '--sort=-version:refname')
    .split('\n').find(code => numeric.test(code));
  if (!latestCode && (!fallbackVersion || !minimumCode)) {
    throw new Error('No positive-integer numeric version tag found; empty history requires fallback-version and minimum-code');
  }

  const codesAt = ref => git('tag', '--points-at', ref).split('\n').filter(code => numeric.test(code));
  if (sourceSha) {
    const source = git('rev-parse', '--verify', '--end-of-options', `${sourceSha}^{commit}`);
    if (codesAt(source).length) {
      throw new Error('Source already has a numeric tag; recover the original candidate manually without rebuilding or uploading');
    }
  }
  const versionName = code => {
    const [type, subject = ''] = git('for-each-ref',
      '--format=%(objecttype)%09%(contents:subject)', `refs/tags/${code}`).split('\t');
    const prefix = `${annotationPrefix} `;
    const name = subject.startsWith(prefix) ? subject.slice(prefix.length) : '';
    if (type !== 'tag' || !version.test(name)) {
      throw new Error(`Unreadable version annotation for ${code}; expected ${prefix}X.Y.Z`);
    }
    return name;
  };
  const baseline = git('tag', '--list', '--', baselineTag) ? baselineTag : fallbackTag;
  let baselineName = fallbackVersion;
  if (baseline) {
    const baselineCommit = git('rev-parse', '--verify', '--end-of-options', `refs/tags/${baseline}^{commit}`);
    const baselineCodes = codesAt(baselineCommit);
    if (baselineCodes.length !== 1) throw new Error('Cannot read the production baseline version: expected one numeric tag');
    baselineName = versionName(baselineCodes[0]);
  } else if (!baselineName) {
    throw new Error(`Baseline tag ${baselineTag} is missing and no fallback-tag or fallback-version was supplied`);
  }
  return calculateVersion({
    baselineName,
    latestName: latestCode ? versionName(latestCode) : undefined,
    latestCode,
    minimumCode: minimumCode || '0',
  });
}

function run({ core, env }) {
  if (!env.GITHUB_WORKSPACE) throw new Error('GITHUB_WORKSPACE must identify the caller checkout');
  const result = nextVersion({
    baselineTag: env.NEXT_VERSION_BASELINE_TAG,
    fallbackTag: env.NEXT_VERSION_FALLBACK_TAG || '',
    fallbackVersion: env.NEXT_VERSION_FALLBACK_VERSION || '',
    minimumCode: env.NEXT_VERSION_MINIMUM_CODE || '',
    annotationPrefix: env.NEXT_VERSION_ANNOTATION_PREFIX,
    sourceSha: env.NEXT_VERSION_SOURCE_SHA || '',
    cwd: env.GITHUB_WORKSPACE,
  });
  core.setOutput('name', result.name);
  core.setOutput('code', result.code);
}

module.exports = { calculateVersion, nextVersion, run };
