const { execFileSync } = require('node:child_process');

const numeric = /^[1-9][0-9]*$/;
const version = /^\d+\.\d+\.\d+$/;

function calculateVersion({ baselineName, latestName, latestCode }) {
  const [major, minor] = baselineName.split('.').map(Number);
  const [latestMajor, latestMinor, latestPatch] = latestName.split('.').map(Number);
  const nextMinor = minor + 1;
  if (latestMajor > major || (latestMajor === major && latestMinor > nextMinor)) {
    throw new Error(`Latest candidate series ${latestMajor}.${latestMinor} is ahead of target ${major}.${nextMinor}; release owner must resolve manually`);
  }
  const patch = latestMajor === major && latestMinor === nextMinor ? latestPatch + 1 : 0;
  return { name: `${major}.${nextMinor}.${patch}`, code: String(Number(latestCode) + 1) };
}

function nextVersion({ baselineTag, fallbackTag = '', annotationPrefix, sourceSha = '', cwd }) {
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
  if (!latestCode) throw new Error('No positive-integer numeric version tag found');

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
  if (!baseline) throw new Error(`Baseline tag ${baselineTag} is missing and no fallback-tag was supplied`);
  const baselineCommit = git('rev-parse', '--verify', '--end-of-options', `refs/tags/${baseline}^{commit}`);
  const baselineCodes = codesAt(baselineCommit);
  if (baselineCodes.length !== 1) throw new Error('Cannot read the production baseline version: expected one numeric tag');
  return calculateVersion({
    baselineName: versionName(baselineCodes[0]),
    latestName: versionName(latestCode),
    latestCode,
  });
}

function run({ core, env }) {
  if (!env.GITHUB_WORKSPACE) throw new Error('GITHUB_WORKSPACE must identify the caller checkout');
  const result = nextVersion({
    baselineTag: env.NEXT_VERSION_BASELINE_TAG,
    fallbackTag: env.NEXT_VERSION_FALLBACK_TAG || '',
    annotationPrefix: env.NEXT_VERSION_ANNOTATION_PREFIX,
    sourceSha: env.NEXT_VERSION_SOURCE_SHA || '',
    cwd: env.GITHUB_WORKSPACE,
  });
  core.setOutput('name', result.name);
  core.setOutput('code', result.code);
}

module.exports = { calculateVersion, nextVersion, run };
