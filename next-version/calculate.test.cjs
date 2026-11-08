const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');
const { calculateVersion, nextVersion, run } = require('./calculate.cjs');

function fixture(t, options = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'next-version test-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const env = {
    ...process.env,
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_CONFIG_GLOBAL: '/dev/null',
    GIT_AUTHOR_NAME: 'Version test',
    GIT_AUTHOR_EMAIL: 'version@example.invalid',
    GIT_COMMITTER_NAME: 'Version test',
    GIT_COMMITTER_EMAIL: 'version@example.invalid',
  };
  const git = (...args) => execFileSync('git', args, {
    cwd: dir, env, encoding: 'utf8', stdio: 'pipe',
  }).trim();
  git('init', '--quiet');
  let sequence = 0;
  const commit = () => {
    env.GIT_AUTHOR_DATE = env.GIT_COMMITTER_DATE = new Date(1600000000000 + sequence++ * 1000).toISOString();
    git('commit', '--quiet', '--allow-empty', '-m', 'Fixture commit');
    return git('rev-parse', 'HEAD');
  };
  const prefix = options.prefix ?? 'Play version';
  const tag = (code, name, ref = 'HEAD') => git('tag', '-a', code, '-m', `${prefix} ${name}`, ref);
  const baselineCode = options.baselineCode ?? '411';
  const latestCode = options.latestCode ?? '426';
  const baselineTag = options.baselineTag ?? 'play-production';
  const baselineCommit = commit();
  if (options.history !== false) tag(baselineCode, options.baselineName ?? '2.2.16');
  if (options.marker !== false) git('tag', baselineTag);
  if (options.history !== false && latestCode !== baselineCode) {
    commit();
    tag(latestCode, options.latestName ?? '2.3.9');
  }
  const sourceSha = commit();
  const inputs = { baselineTag, fallbackTag: baselineCode, annotationPrefix: prefix, cwd: dir };
  const calculate = (overrides = {}) => {
    const refs = git('for-each-ref', '--format=%(refname) %(objectname)');
    const status = git('status', '--porcelain');
    try {
      return nextVersion({ ...inputs, ...overrides });
    } finally {
      assert.equal(git('for-each-ref', '--format=%(refname) %(objectname)'), refs, 'calculation must not mutate refs');
      assert.equal(git('status', '--porcelain'), status, 'calculation must not mutate the checkout');
    }
  };
  return { dir, git, commit, tag, calculate, inputs, baselineCode, latestCode, baselineCommit, sourceSha };
}

for (const [baselineName, latestName, expected] of [
  ['2.2.16', '2.2.16', '2.3.0'],
  ['2.3.1', '2.3.1', '2.4.0'],
  ['2.2.16', '2.3.9', '2.3.10'],
  ['2.9.1', '2.9.99', '2.10.0'],
  ['2.9.1', '2.10.9', '2.10.10'],
  ['3.0.0', '2.99.9', '3.1.0'],
]) {
  test(`arithmetic: baseline ${baselineName}, latest ${latestName} gives ${expected}`, () => {
    assert.deepEqual(calculateVersion({ baselineName, latestName, latestCode: '426' }), {
      name: expected, code: '427',
    });
  });
}

for (const [baselineName, latestName] of [['2.3.1', '2.5.0'], ['2.8.1', '2.10.0'], ['2.9.1', '3.0.0']]) {
  test(`arithmetic: rejects latest ${latestName} ahead of baseline ${baselineName}'s target`, () => {
    assert.throws(() => calculateVersion({ baselineName, latestName, latestCode: '426' }), /ahead of target/);
  });
}

test('calculates the next candidate from actual annotated Git tags without writing', t => {
  const f = fixture(t);
  assert.deepEqual(f.calculate({ sourceSha: f.sourceSha }), { name: '2.3.10', code: '427' });
});

test('uses numeric version order rather than lexical or creation order and ignores other tag names', t => {
  const f = fixture(t, { baselineCode: '9', latestCode: '100' });
  f.commit();
  f.tag('10', '2.3.2');
  for (const code of ['01000', '0', 'v9999', '10000-build']) f.git('tag', code);
  assert.deepEqual(f.calculate(), { name: '2.3.10', code: '101' });
  assert.deepEqual(f.calculate({ minimumCode: '200' }), { name: '2.3.10', code: '201' });
});

test('bootstraps empty numeric history from values without creating tags or editing caller files', t => {
  const f = fixture(t, { history: false, marker: false });
  for (const code of ['0', '02', 'v9999']) f.git('tag', code);
  const pubspec = 'name: caller\nversion: 0.0.0+2\n';
  writeFileSync(join(f.dir, 'pubspec.yaml'), pubspec);
  const inputs = { fallbackTag: '', fallbackVersion: '0.0.0', minimumCode: '2', sourceSha: f.sourceSha };
  assert.deepEqual(f.calculate(inputs), { name: '0.1.0', code: '3' });
  assert.equal(readFileSync(join(f.dir, 'pubspec.yaml'), 'utf8'), pubspec);
  assert.deepEqual(f.calculate({ ...inputs, minimumCode: '0' }), { name: '0.1.0', code: '1' });
});

for (const inputs of [{}, { fallbackVersion: '0.0.0' }, { minimumCode: '2' }]) {
  test(`empty numeric history requires both explicit value inputs: ${JSON.stringify(inputs)}`, t => {
    const f = fixture(t, { history: false, marker: false });
    assert.throws(() => f.calculate({ fallbackTag: '', ...inputs }), /No positive-integer numeric version tag/);
  });
}

for (const [minimumCode, code] of [['0', '427'], ['2', '427'], ['426', '427'], ['500', '501'], ['9007199254740993', '9007199254740994']]) {
  test(`minimum code ${minimumCode} changes only allocation, not semantic selection`, t => {
    const f = fixture(t);
    assert.deepEqual(f.calculate({ minimumCode }), { name: '2.3.10', code });
  });
}

test('code allocation remains exact for numeric history above the safe Number range', t => {
  const f = fixture(t, { latestCode: '9007199254740993' });
  assert.deepEqual(f.calculate({ minimumCode: '500' }), { name: '2.3.10', code: '9007199254740994' });
});

test('an absent marker without a fallback tag can use a value baseline with existing history', t => {
  const f = fixture(t, { marker: false });
  const inputs = { fallbackTag: '', fallbackVersion: '2.2.16' };
  assert.deepEqual(f.calculate(inputs), { name: '2.3.10', code: '427' });
  assert.deepEqual(f.calculate({ ...inputs, minimumCode: '500' }), { name: '2.3.10', code: '501' });
  assert.deepEqual(f.calculate({ ...inputs, fallbackVersion: '3.0.0' }), { name: '3.1.0', code: '427' });
});

test('the actual production baseline takes precedence over both supplied fallbacks', t => {
  const f = fixture(t);
  assert.deepEqual(f.calculate({ fallbackTag: f.latestCode, fallbackVersion: '9.0.0', minimumCode: '500' }), {
    name: '2.3.10', code: '501',
  });
});

test('a supplied fallback tag takes precedence over the fallback value', t => {
  const f = fixture(t, { marker: false });
  assert.deepEqual(f.calculate({ fallbackVersion: '9.0.0' }), { name: '2.3.10', code: '427' });
});

test('project marker, initial code, and annotation prefix are caller-owned and literal', t => {
  const f = fixture(t, {
    baselineCode: '7', latestCode: '8', baselineTag: 'store-live', prefix: 'Version [candidate].*',
    baselineName: '7.4.2', latestName: '7.5.0',
  });
  assert.deepEqual(f.calculate(), { name: '7.5.1', code: '9' });
});

test('a new minor starts at zero with the latest tag also serving as the baseline', t => {
  const f = fixture(t, { latestCode: '411' });
  assert.deepEqual(f.calculate(), { name: '2.3.0', code: '412' });
});

test('an absent marker uses the supplied initial numeric tag', t => {
  const f = fixture(t, { marker: false });
  assert.deepEqual(f.calculate(), { name: '2.3.10', code: '427' });
});

test('an absent marker without a fallback fails instead of initializing history', t => {
  const f = fixture(t, { marker: false });
  assert.throws(() => f.calculate({ fallbackTag: '' }), /missing and no fallback-tag/);
});

test('an unused fallback need not exist when the production marker exists', t => {
  const f = fixture(t);
  assert.deepEqual(f.calculate({ fallbackTag: '999' }), { name: '2.3.10', code: '427' });
});

test('missing fallback tag fails when it is required', t => {
  const f = fixture(t, { marker: false });
  assert.throws(() => f.calculate({ fallbackTag: '999', fallbackVersion: '0.0.0', minimumCode: '2' }), /Git rev-parse failed/);
});

test('missing numeric history fails rather than generating the first code', t => {
  const f = fixture(t);
  f.git('tag', '-d', f.baselineCode, f.latestCode);
  assert.throws(() => f.calculate(), /No positive-integer numeric version tag/);
});

test('an existing marker without a numeric tag does not fall back', t => {
  const f = fixture(t);
  f.git('tag', '-f', f.inputs.baselineTag, f.sourceSha);
  assert.throws(() => f.calculate({ fallbackVersion: '0.0.0', minimumCode: '2' }), /expected one numeric tag/);
});

for (const marker of [true, false]) {
  test(`multiple numeric tags at the ${marker ? 'production' : 'fallback'} baseline are ambiguous`, t => {
    const f = fixture(t, { marker });
    f.tag('410', '2.2.15', f.baselineCommit);
    assert.throws(() => f.calculate({ fallbackVersion: '0.0.0', minimumCode: '2' }), /expected one numeric tag/);
  });
}

test('value inputs do not conceal an existing production marker with empty numeric history', t => {
  const f = fixture(t, { history: false });
  assert.throws(() => f.calculate({ fallbackTag: '', fallbackVersion: '0.0.0', minimumCode: '2' }), /expected one numeric tag/);
});

test('an unreadable existing marker target does not trigger fallback', t => {
  const f = fixture(t);
  f.git('tag', '-f', f.inputs.baselineTag, 'HEAD^{tree}');
  assert.throws(() => f.calculate({ fallbackVersion: '0.0.0', minimumCode: '2' }), /Git rev-parse failed/);
});

for (const [label, code, message, lightweight, marker = true] of [
  ['latest wrong prefix', '426', 'Other version 2.3.9', false],
  ['latest partial version', '426', 'Play version 2.3', false],
  ['latest prerelease', '426', 'Play version 2.3.9-rc.1', false],
  ['latest lightweight tag', '426', '', true],
  ['baseline wrong prefix', '411', 'Other version 2.2.16', false],
  ['baseline lightweight tag', '411', '', true],
  ['fallback wrong prefix', '411', 'Other version 2.2.16', false, false],
  ['fallback lightweight tag', '411', '', true, false],
]) {
  test(`rejects an unreadable used annotation: ${label}`, t => {
    const f = fixture(t, { marker });
    const ref = f.git('rev-parse', `${code}^{commit}`);
    f.git('tag', '-d', code);
    if (lightweight) f.git('tag', code, ref);
    else f.git('tag', '-a', code, '-m', message, ref);
    assert.throws(() => f.calculate({ fallbackVersion: '0.0.0', minimumCode: '500' }), new RegExp(`Unreadable version annotation for ${code}`));
  });
}

test('irrelevant malformed annotations and historical lightweight tags do not block', t => {
  const f = fixture(t);
  f.commit();
  f.git('tag', '-a', '425', '-m', 'Unreadable old candidate');
  f.git('tag', '410');
  assert.deepEqual(f.calculate(), { name: '2.3.10', code: '427' });
});

test('latest candidate ahead of the production target fails without scanning for an older replacement', t => {
  const f = fixture(t, { latestName: '2.5.0', baselineName: '2.3.1' });
  f.commit();
  f.tag('425', '2.4.7');
  assert.throws(() => f.calculate(), /2\.5 is ahead of target 2\.4/);
});

for (const latestName of ['2.5.0', '3.0.0']) {
  test(`a value baseline and high code floor cannot hide an ahead-of-target candidate ${latestName}`, t => {
    const f = fixture(t, { marker: false, latestName });
    f.commit();
    f.tag('425', '2.3.8');
    assert.throws(() => f.calculate({ fallbackTag: '', fallbackVersion: '2.2.16', minimumCode: '500' }), /ahead of target/);
  });
}

test('a tagged source is rejected for release but remains eligible for a forecast', t => {
  const f = fixture(t);
  const taggedSource = f.git('rev-parse', `${f.latestCode}^{commit}`);
  assert.throws(() => f.calculate({ sourceSha: taggedSource }), /Source already has a numeric tag/);
  assert.deepEqual(f.calculate(), { name: '2.3.10', code: '427' });
});

test('the source guard includes old numeric tags rather than only the latest code', t => {
  const f = fixture(t);
  assert.throws(() => f.calculate({ sourceSha: f.baselineCommit }), /Source already has a numeric tag/);
});

test('invalid source commits fail instead of silently disabling the guard', t => {
  const f = fixture(t);
  assert.throws(() => f.calculate({ sourceSha: 'not-an-existing-commit' }), /Git rev-parse failed/);
});

test('value fallback and code floor preserve the latest and older tagged-source guards', t => {
  const f = fixture(t, { marker: false });
  const inputs = { fallbackTag: '', fallbackVersion: '2.2.16', minimumCode: '500' };
  for (const sourceSha of [f.baselineCommit, f.git('rev-parse', `${f.latestCode}^{commit}`)]) {
    assert.throws(() => f.calculate({ ...inputs, sourceSha }), /Source already has a numeric tag/);
  }
  assert.deepEqual(f.calculate(inputs), { name: '2.3.10', code: '501' });
});

test('an invalid source still fails during value-only bootstrap', t => {
  const f = fixture(t, { history: false, marker: false });
  assert.throws(() => f.calculate({
    fallbackTag: '', fallbackVersion: '0.0.0', minimumCode: '2', sourceSha: 'not-an-existing-commit',
  }), /Git rev-parse failed/);
});

test('a pre-upload retry can recalculate after another candidate is recorded', t => {
  const f = fixture(t);
  assert.deepEqual(f.calculate({ sourceSha: f.sourceSha }), { name: '2.3.10', code: '427' });
  f.commit();
  f.tag('427', '2.3.10');
  assert.deepEqual(f.calculate({ sourceSha: f.sourceSha }), { name: '2.3.11', code: '428' });
});

for (const [inputs, error] of [
  [{ baselineTag: '' }, /baseline-tag.*required/],
  [{ baselineTag: 'bad*tag' }, /Git check-ref-format failed/],
  [{ annotationPrefix: '' }, /annotation-prefix/],
  [{ annotationPrefix: 'Version ' }, /annotation-prefix/],
  [{ annotationPrefix: 'Version\nName' }, /annotation-prefix/],
  [{ fallbackTag: 'v1' }, /fallback-tag.*positive integer/],
  ...['0.0', 'v0.0.0', '0.0.0-rc.1', '-1.0.0', '0.0.0\n', ' 0.0.0', ' '].map(fallbackVersion => [
    { fallbackVersion }, /fallback-version.*X\.Y\.Z/,
  ]),
  ...['-1', '02', '2.0', '1e3', '2\n', ' 2', ' '].map(minimumCode => [
    { minimumCode }, /minimum-code.*nonnegative integer/,
  ]),
]) {
  test(`validates explicit action inputs: ${JSON.stringify(inputs)}`, t => {
    const f = fixture(t);
    assert.throws(() => f.calculate(inputs), error);
  });
}

function actionEnv(f, actionPath = __dirname) {
  return {
    GITHUB_WORKSPACE: f.dir,
    NEXT_VERSION_ACTION_PATH: actionPath,
    NEXT_VERSION_BASELINE_TAG: f.inputs.baselineTag,
    NEXT_VERSION_FALLBACK_TAG: f.inputs.fallbackTag,
    NEXT_VERSION_FALLBACK_VERSION: f.inputs.fallbackVersion || '',
    NEXT_VERSION_MINIMUM_CODE: f.inputs.minimumCode || '',
    NEXT_VERSION_ANNOTATION_PREFIX: f.inputs.annotationPrefix,
    NEXT_VERSION_SOURCE_SHA: f.sourceSha,
  };
}

test('publishes name and code as strings only after successful calculation', t => {
  const f = fixture(t);
  const outputs = {};
  run({ core: { setOutput: (name, value) => { outputs[name] = value; } }, env: actionEnv(f) });
  assert.deepEqual(outputs, { name: '2.3.10', code: '427' });
});

test('publishes value-only bootstrap outputs as strings', t => {
  const f = fixture(t, { history: false, marker: false });
  Object.assign(f.inputs, { fallbackTag: '', fallbackVersion: '0.0.0', minimumCode: '2' });
  const outputs = {};
  run({ core: { setOutput: (name, value) => { outputs[name] = value; } }, env: actionEnv(f) });
  assert.deepEqual(outputs, { name: '0.1.0', code: '3' });
});

test('an incomplete empty-history opt-in publishes neither output', t => {
  const f = fixture(t, { history: false, marker: false });
  Object.assign(f.inputs, { fallbackTag: '', fallbackVersion: '0.0.0' });
  const outputs = [];
  assert.throws(() => run({
    core: { setOutput: (...args) => outputs.push(args) }, env: actionEnv(f),
  }), /No positive-integer numeric version tag/);
  assert.deepEqual(outputs, []);
});

for (const [inputs, error] of [
  [{ fallbackVersion: 'bad' }, /fallback-version/],
  [{ minimumCode: '-1' }, /minimum-code/],
  [{ fallbackTag: '999', fallbackVersion: '0.0.0', minimumCode: '2' }, /Git rev-parse failed/],
]) {
  test(`invalid value or tag baseline publishes neither output: ${JSON.stringify(inputs)}`, t => {
    const f = fixture(t, { marker: false });
    Object.assign(f.inputs, inputs);
    const outputs = [];
    assert.throws(() => run({
      core: { setOutput: (...args) => outputs.push(args) }, env: actionEnv(f),
    }), error);
    assert.deepEqual(outputs, []);
  });
}

test('failed calculation does not publish partial outputs', t => {
  const f = fixture(t, { latestName: '2.5.0' });
  const outputs = [];
  assert.throws(() => run({
    core: { setOutput: (...args) => outputs.push(args) }, env: actionEnv(f),
  }), /ahead of target/);
  assert.deepEqual(outputs, []);
});

test('requires an explicit caller workspace rather than using the action directory', () => {
  assert.throws(() => run({ core: {}, env: {} }), /GITHUB_WORKSPACE/);
});

for (const [label, options, overrides, expected] of [
  ['tag-backed defaults', {}, {}, { name: '2.3.10', code: '427' }],
  ['value-only bootstrap', { history: false, marker: false }, { fallbackTag: '', fallbackVersion: '0.0.0', minimumCode: '2' }, { name: '0.1.0', code: '3' }],
  ['existing history with a code floor', { marker: false }, { fallbackTag: '', fallbackVersion: '2.2.16', minimumCode: '500' }, { name: '2.3.10', code: '501' }],
]) {
  test(`executes the relocated composite wrapper and input bindings: ${label}`, t => {
    const f = fixture(t, options);
    Object.assign(f.inputs, overrides);
    const actionDir = mkdtempSync(join(tmpdir(), 'relocated next-version-'));
    t.after(() => rmSync(actionDir, { recursive: true, force: true }));
    cpSync(__dirname, actionDir, { recursive: true });
    // A relative require in the caller must not replace the action's own module.
    writeFileSync(join(f.dir, 'calculate.cjs'), 'throw new Error("wrong module location");\n');
    const metadata = readFileSync(join(actionDir, 'action.yml'), 'utf8');
    const body = metadata.split('        script: |\n')[1];
    assert.ok(body, 'composite wrapper must have its executable script');
    const script = body.trimEnd().split('\n').map(line => line.slice(10)).join('\n');
    const inputs = {
      'baseline-tag': f.inputs.baselineTag,
      'fallback-tag': f.inputs.fallbackTag,
      'fallback-version': f.inputs.fallbackVersion || '',
      'minimum-code': f.inputs.minimumCode || '',
      'annotation-prefix': f.inputs.annotationPrefix,
      'source-sha': f.sourceSha,
    };
    const env = { GITHUB_WORKSPACE: f.dir };
    for (const [, key, expression] of metadata.matchAll(/^        (NEXT_VERSION_\w+): \$\{\{ (.+) \}\}$/gm)) {
      env[key] = expression === 'github.action_path' ? actionDir : inputs[expression.slice('inputs.'.length)];
    }
    const outputs = {};
    runInNewContext(script, {
      require,
      core: { setOutput: (name, value) => { outputs[name] = value; } },
      process: { env },
    });
    assert.deepEqual(outputs, expected);
  });
}
