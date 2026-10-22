'use strict';

const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const { test } = require('node:test');
const { publishPatch, publishMajor } = require('./semantic-release');

const BASE = 'a'.repeat(40);
const HEAD = 'b'.repeat(40);
const OTHER = 'c'.repeat(40);
const BASE_TAG = 'v1.0.12';
const NEXT_TAG = 'v1.0.13';
const SCOPE_PATH = '.github/semantic-release/actions.json';
const SCOPE = JSON.stringify({ schema: 2, actionDirectories: ['example'], sharedPaths: [] });

function apiError(status) {
  return Object.assign(new Error(`HTTP ${status}`), {
    status, response: { headers: { 'x-github-request-id': `error-${status}` } },
  });
}

// Everything reachable from the public publishers is in memory. Unknown Git
// commands fail rather than falling through to the real repository or network.
function fixture(t) {
  const h = {
    refs: new Map([[BASE_TAG, BASE], ['v1', BASE]]),
    releases: new Map(), master: HEAD, round: 0, nextId: 1,
    writes: [], pages: [], direct: [], delays: [], logs: [], contents: new Map(),
    refView: (items) => items,
    listView: (items) => items,
    directView: (item) => item,
  };
  h.addRelease = (tag, sha, draft = false) => {
    h.refs.set(tag, sha);
    const release = { id: h.nextId++, tag_name: tag, draft, prerelease: false, body: 'fixture' };
    h.releases.set(tag, release);
    return release;
  };
  h.addRelease(BASE_TAG, BASE);
  t.mock.method(console, 'info', (message) => h.logs.push(message));
  t.mock.method(global, 'setTimeout', (resolve, delay) => {
    h.delays.push(delay);
    resolve();
  });
  t.mock.method(childProcess, 'execFileSync', (command, args) => {
    assert.equal(command, 'git');
    h.writes.push({ method: 'git', args: [...args] });
    if (args[0] === 'fetch') {
      assert.deepEqual(args.slice(0, 3), ['fetch', '--no-tags', 'origin']);
      assert.match(args[3], /^refs\/tags\/v\d+\.\d+\.\d+:refs\/release-target\/v\d+\.\d+\.\d+$/);
      assert.equal(args.length, 4);
    } else {
      assert.equal(args[0], 'push', 'unmocked Git command');
      assert.equal(args[1], '--porcelain');
      const lease = /^--force-with-lease=refs\/tags\/(v\d+):([a-f0-9]{40})$/.exec(args[2]);
      assert.ok(lease, 'floating moves must use an exact lease');
      assert.equal(h.refs.get(lease[1]), lease[2]);
      assert.equal(args[3], 'origin');
      const target = /^([a-f0-9]{40}):refs\/tags\/(v\d+)$/.exec(args[4]);
      assert.ok(target);
      assert.equal(target[2], lease[1]);
      assert.equal(args.length, 5);
      if (h.rejectLease) throw new Error('simulated concurrent update');
      h.refs.set(target[2], target[1]);
    }
    return '';
  });

  // Model the paginated endpoint itself: it returns only this page and a next
  // Link. The paginate adapter follows that Link and applies Octokit's mapper.
  function page(kind, params, items) {
    h.pages.push({ kind, round: h.round, ...params });
    assert.equal(params.owner, 'fixture');
    assert.equal(params.repo, 'commons');
    const start = (params.page - 1) * params.per_page;
    const headers = { 'x-github-request-id': `${kind}-${h.round}-${params.page}` };
    if (start + params.per_page < items.length) {
      headers.link = `<https://fixture.invalid/${kind}?page=${params.page + 1}>; rel="next"`;
    }
    return { data: items.slice(start, start + params.per_page), headers };
  }
  const git = {
    listMatchingRefs: async (params) => {
      if (params.page === 1) h.round += 1;
      assert.equal(params.ref, 'tags/v');
      const items = [...h.refs].map(([tag, sha]) => ({ ref: `refs/tags/${tag}`, object: { type: 'commit', sha } }));
      return page('refs', params, h.refView(items, h));
    },
    getRef: async ({ ref }) => {
      const sha = ref === 'heads/master' ? h.master : h.refs.get(ref.replace(/^tags\//, ''));
      if (!sha) throw apiError(404);
      return { data: { object: { type: 'commit', sha } } };
    },
    createRef: async (params) => {
      h.writes.push({ method: 'createRef', ...params });
      const tag = params.ref.replace(/^refs\/tags\//, '');
      if (h.refConflict) h.refs.set(tag, OTHER);
      if (h.refs.has(tag)) throw apiError(422);
      h.refs.set(tag, params.sha);
      return { data: {} };
    },
    getCommit: async ({ commit_sha }) => ({ data: { tree: { sha: commit_sha } } }),
    getTree: async ({ tree_sha }) => ({ data: { truncated: false, tree: [
      { path: SCOPE_PATH, type: 'blob', mode: '100644', sha: 'scope-blob' },
      { path: 'example/action.yml', type: 'blob', mode: '100644', sha: h.contents.get(tree_sha) || tree_sha },
    ] } }),
    getBlob: async ({ file_sha }) => {
      assert.equal(file_sha, 'scope-blob');
      return { data: { encoding: 'base64', content: Buffer.from(SCOPE).toString('base64') } };
    },
  };
  const repos = {
    listReleases: async (params) => page('releases', params, h.listView(structuredClone([...h.releases.values()]), h)),
    getReleaseByTag: async ({ tag }) => {
      h.direct.push({ tag, round: h.round });
      const release = h.directView(structuredClone(h.releases.get(tag)), tag, h);
      if (!release) throw apiError(404);
      return { data: release, headers: { 'x-github-request-id': `direct-${tag}-${h.round}` } };
    },
    createRelease: async (params) => {
      h.writes.push({ method: 'createRelease', ...params });
      assert.equal(params.draft, true);
      assert.equal(params.prerelease, false);
      assert.equal(h.refs.get(params.tag_name), params.target_commitish);
      assert.ok(!h.releases.has(params.tag_name));
      const release = { ...params, id: h.nextId++ };
      h.releases.set(params.tag_name, release);
      h.createdAt = h.round;
      if (h.create422) throw apiError(422);
      return { data: structuredClone(release) };
    },
    updateRelease: async (params) => {
      h.writes.push({ method: 'updateRelease', ...params });
      const release = h.releases.get(params.tag_name);
      assert.equal(params.release_id, release.id);
      assert.equal(params.draft, false);
      assert.equal(params.prerelease, false);
      const major = params.tag_name.split('.')[0];
      assert.equal(h.refs.get(major), params.target_commitish, 'floating ref must move before publication');
      if (params.tag_name.endsWith('.0.0')) assert.equal(h.refs.get(`${major}.0`), params.target_commitish);
      Object.assign(release, params);
      h.publishedAt = h.round;
      return { data: structuredClone(release) };
    },
  };
  const github = {
    rest: { git, repos },
    paginate: async (method, params, map) => {
      assert.equal(params.page, 1, 'every paginated read must explicitly start at page 1');
      const result = [];
      let nextPage = params.page;
      while (nextPage) {
        const response = await method({ ...params, page: nextPage });
        result.push(...map(response));
        const next = /[?&]page=(\d+)>; rel="next"/.exec(response.headers.link || '');
        nextPage = next ? Number(next[1]) : null;
      }
      return result;
    },
  };
  const summary = {
    addHeading: () => summary, addRaw: () => summary, addTable: () => summary, write: async () => {},
  };
  const context = { repo: { owner: 'fixture', repo: 'commons' }, sha: HEAD, ref: 'refs/heads/master', eventName: 'push' };
  const args = { github, context, core: { info: (message) => h.logs.push(message), summary } };
  h.patch = () => publishPatch(args);
  h.major = () => publishMajor(args);
  h.context = context;
  h.authorizeMajor = () => {
    context.eventName = 'workflow_dispatch';
    const previous = [process.env.RELEASE_TARGET_SHA, process.env.RELEASE_CONFIRMATION];
    process.env.RELEASE_TARGET_SHA = context.sha;
    process.env.RELEASE_CONFIRMATION = `PUBLISH NEXT MAJOR AT ${context.sha}`;
    t.after(() => {
      for (const [index, key] of ['RELEASE_TARGET_SHA', 'RELEASE_CONFIRMATION'].entries()) {
        if (previous[index] === undefined) delete process.env[key];
        else process.env[key] = previous[index];
      }
    });
  };
  h.calls = (method) => h.writes.filter((call) => call.method === method);
  return h;
}

function completed(h, tag = NEXT_TAG, sha = HEAD) {
  assert.equal(h.refs.get(tag), sha);
  assert.equal(h.refs.get(tag.split('.')[0]), sha);
  assert.equal(h.releases.get(tag).draft, false);
  assert.equal(h.calls('updateRelease').length, 1);
}

test('empty release list settles before any mutation, with bounded alternate reads', async (t) => {
  const h = fixture(t);
  h.listView = (items) => {
    if (h.round <= 2) {
      assert.deepEqual(h.writes, []);
      return [];
    }
    return items;
  };
  h.directView = (item) => h.round <= 2 ? undefined : item;
  await h.patch();
  completed(h);
  assert.deepEqual(h.delays, [1000, 2000]);
  assert.deepEqual(h.pages.filter((p) => p.kind === 'releases').slice(0, 3).map((p) => p.per_page), [100, 30, 100]);
  assert.match(h.logs.join('\n'), /request_ids=refs-1-1,releases-1-1,error-404/);
});

test('an omitted newer release is found by tag and selects the correct next semver', async (t) => {
  const h = fixture(t);
  h.addRelease('v1.0.13', OTHER);
  h.refs.set('v1', OTHER);
  h.listView = (items) => {
    if (h.round <= 6) assert.deepEqual(h.writes, []);
    return items.filter((item) => item.tag_name !== 'v1.0.13');
  };
  await h.patch();
  completed(h, 'v1.0.14');
  assert.ok(h.direct.some(({ tag }) => tag === 'v1.0.13'));
  assert.deepEqual(h.calls('createRef').map(({ ref }) => ref), ['refs/tags/v1.0.14']);
});

test('persistent missing baseline fails closed after six reads without writes', async (t) => {
  const h = fixture(t);
  h.listView = () => [];
  h.directView = () => undefined;
  await assert.rejects(h.patch(), /No published stable semantic release exists; attempt=6\/6.*missing=v1.0.12/);
  assert.equal(h.round, 6);
  assert.deepEqual(h.delays, [1000, 2000, 2000, 2000, 2000]);
  assert.deepEqual(h.writes, []);
});

for (const create422 of [false, true]) {
  test(`delayed draft visibility after ${create422 ? '422' : 'success'} never replays creation`, async (t) => {
    const h = fixture(t);
    h.create422 = create422;
    const hidden = () => h.createdAt !== undefined && h.round <= h.createdAt + 2;
    h.listView = (items) => items.filter((item) => item.tag_name !== NEXT_TAG || !hidden());
    h.directView = (item, tag) => tag === NEXT_TAG && hidden() ? undefined : item;
    await h.patch();
    completed(h);
    assert.equal(h.calls('createRelease').length, 1);
    assert.equal(h.calls('createRef').length, 1);
    assert.deepEqual(h.delays, [1000, 2000]);
  });
}

test('publication visibility retries reads, not the update or leased floating move', async (t) => {
  const h = fixture(t);
  const lag = (item) => item && item.tag_name === NEXT_TAG && h.publishedAt !== undefined && h.round <= h.publishedAt + 2
    ? { ...item, draft: true } : item;
  h.listView = (items) => items.map(lag);
  h.directView = lag;
  await h.patch();
  completed(h);
  assert.equal(h.calls('createRelease').length, 1);
  assert.equal(h.calls('git').length, 2);
  assert.deepEqual(h.delays, [1000, 2000]);
});

test('persistent publication invisibility fails without replaying a successful update', async (t) => {
  const h = fixture(t);
  const lag = (item) => item && item.tag_name === NEXT_TAG ? { ...item, draft: true } : item;
  h.listView = (items) => items.map(lag);
  h.directView = lag;
  await assert.rejects(h.patch(), /v1.0.13 is not published.*attempt=6\/6/);
  assert.equal(h.calls('createRelease').length, 1);
  assert.equal(h.calls('updateRelease').length, 1);
  assert.equal(h.calls('git').length, 2);
  assert.equal(h.releases.get(NEXT_TAG).draft, false, 'successful write remains published despite lagging reads');
  assert.deepEqual(h.delays, [1000, 2000, 2000, 2000, 2000]);
});

test('unreadable draft exhausts the window without replay or publication', async (t) => {
  const h = fixture(t);
  h.listView = (items) => items.filter((item) => item.tag_name !== NEXT_TAG);
  h.directView = (item, tag) => tag === NEXT_TAG ? undefined : item;
  await assert.rejects(h.patch(), /Release v1.0.13 is not readable; attempt=6\/6/);
  assert.equal(h.calls('createRelease').length, 1);
  assert.equal(h.calls('updateRelease').length, 0);
  assert.equal(h.calls('git').length, 0);
});

for (const perPage of [100, 30]) {
  test(`full pagination at page size ${perPage} starts at page 1 and reaches the highest semver`, async (t) => {
    const h = fixture(t);
    for (let patch = 13; patch <= 116; patch += 1) h.addRelease(`v1.0.${patch}`, BASE);
    // The highest version is on the last page, not the first result/page.
    if (perPage === 30) {
      h.listView = (items) => h.round === 1 ? [] : items;
      h.directView = (item) => h.round === 1 ? undefined : item;
    }
    await h.patch();
    completed(h, 'v1.0.117');
    const round = perPage === 100 ? 1 : 2;
    for (const kind of ['refs', 'releases']) {
      const pages = h.pages.filter((p) => p.kind === kind && p.round === round);
      const size = kind === 'refs' ? 100 : perPage;
      assert.deepEqual(pages.map((p) => p.page), size === 100 ? [1, 2] : [1, 2, 3, 4]);
      assert.equal(pages[0].per_page, size);
    }
    assert.equal(h.direct.some((call) => call.tag === 'v1.0.116' && call.round >= round), false,
      'highest release must come from pagination, not a direct lookup fallback');
  });
}

for (const status of [401, 403]) {
  for (const endpoint of ['list', 'direct']) {
    test(`${endpoint} HTTP ${status} fails immediately, not as missing state`, async (t) => {
      const h = fixture(t);
      h.listView = endpoint === 'list' ? () => { throw apiError(status); } : () => [];
      if (endpoint === 'direct') h.directView = () => { throw apiError(status); };
      await assert.rejects(h.patch(), new RegExp(`HTTP ${status}; release read attempt=1/6.*error-${status}`));
      assert.equal(h.round, 1);
      assert.deepEqual(h.delays, []);
      assert.deepEqual(h.writes, []);
    });
  }
}

for (const conflict of ['duplicate', 'prerelease', 'lookup tag', 'lookup ID']) {
  test(`${conflict} identity conflict is not retried or mutated`, async (t) => {
    const h = fixture(t);
    if (conflict === 'duplicate') h.listView = (items) => [...items, items[0]];
    if (conflict === 'prerelease') h.releases.get(BASE_TAG).prerelease = true;
    if (conflict === 'lookup tag') {
      h.listView = () => [];
      h.directView = (item) => ({ ...item, tag_name: NEXT_TAG });
    }
    if (conflict === 'lookup ID') {
      h.releases.get(BASE_TAG).draft = true;
      h.directView = (item) => ({ ...item, id: 999, draft: false });
    }
    await assert.rejects(h.patch(), /Multiple releases|prerelease|Release lookup|Conflicting release IDs/);
    assert.equal(h.round, 1);
    assert.deepEqual(h.delays, []);
    assert.deepEqual(h.writes, []);
  });
}

test('a created draft with a conflicting observed ID cannot move refs or publish', async (t) => {
  const h = fixture(t);
  h.listView = (items) => items.map((item) => item.tag_name === NEXT_TAG ? { ...item, id: 999 } : item);
  h.directView = (item, tag) => tag === NEXT_TAG && item ? { ...item, id: 999 } : item;
  await assert.rejects(h.patch(), /Conflicting release IDs for v1.0.13/);
  assert.equal(h.calls('createRelease').length, 1);
  assert.equal(h.calls('updateRelease').length, 0);
  assert.equal(h.calls('git').length, 0);
});

test('a previously observed published release disappearing cannot authorize a new baseline', async (t) => {
  const h = fixture(t);
  h.refs.set(NEXT_TAG, OTHER); // Keep the initial read unsettled for the whole window.
  h.listView = (items) => h.round === 1 ? items : [];
  h.directView = (item) => h.round === 1 ? item : undefined;
  await assert.rejects(h.patch(), /Previously published releases are no longer visible: v1.0.12; attempt=6\/6/);
  assert.deepEqual(h.writes, []);
});

test('persistent orphaned release cannot establish a baseline', async (t) => {
  const h = fixture(t);
  h.refs.delete(BASE_TAG);
  await assert.rejects(h.patch(), /Releases have no immutable tag: v1.0.12; attempt=6\/6/);
  assert.deepEqual(h.writes, []);
});

for (const changed of ['sha', 'id']) {
  test(`published ${changed} changing within a read window fails immediately`, async (t) => {
    const h = fixture(t);
    h.refs.set(NEXT_TAG, OTHER);
    if (changed === 'sha') h.refView = (items) => items.map((item) => h.round > 1 && item.ref === `refs/tags/${BASE_TAG}`
      ? { ...item, object: { type: 'commit', sha: OTHER } } : item);
    else h.listView = (items) => items.map((item) => h.round > 1 ? { ...item, id: 999 } : item);
    await assert.rejects(h.patch(), /Published identity changed for v1.0.12/);
    assert.equal(h.round, 2);
    assert.deepEqual(h.writes, []);
  });
}

test('stale push cannot start a fresh release', async (t) => {
  const h = fixture(t);
  h.master = OTHER;
  await assert.rejects(h.patch(), /Stale target/);
  assert.deepEqual(h.writes, []);
});

test('an exact draft partial can finish at a superseded push without recreating resources', async (t) => {
  const h = fixture(t);
  h.master = OTHER;
  h.addRelease(NEXT_TAG, HEAD, true);
  await h.patch();
  completed(h);
  assert.equal(h.calls('createRef').length, 0);
  assert.equal(h.calls('createRelease').length, 0);
  assert.ok(h.logs.some((line) => line.includes('resuming-superseded-partial')));
});

for (const invalid of ['multiple', 'not next patch', 'no scoped change', 'floating before draft', 'unknown floating']) {
  test(`invalid partial: ${invalid} fails without writes`, async (t) => {
    const h = fixture(t);
    h.refs.set(NEXT_TAG, HEAD);
    if (invalid === 'multiple') h.refs.set('v1.0.14', OTHER);
    if (invalid === 'not next patch') { h.refs.delete(NEXT_TAG); h.refs.set('v2.0.0', HEAD); }
    if (invalid === 'no scoped change') h.contents.set(HEAD, BASE);
    if (invalid === 'floating before draft') h.refs.set('v1', HEAD);
    if (invalid === 'unknown floating') h.refs.set('v1', OTHER);
    await assert.rejects(h.patch(), /Multiple incomplete|not the next patch|no scoped change|moved before draft|unknown partial state/);
    assert.deepEqual(h.writes, []);
  });
}

test('immutable create conflict fails closed rather than replacing a tag', async (t) => {
  const h = fixture(t);
  h.refConflict = true;
  await assert.rejects(h.patch(), /already exists at another revision/);
  assert.equal(h.calls('createRef').length, 1);
  assert.equal(h.calls('createRelease').length, 0);
});

test('leased floating move conflict stops before publishing the draft', async (t) => {
  const h = fixture(t);
  h.rejectLease = true;
  await assert.rejects(h.patch(), /Concurrent update prevented the leased move/);
  assert.equal(h.calls('createRelease').length, 1);
  assert.equal(h.calls('updateRelease').length, 0);
  assert.equal(h.refs.get('v1'), BASE);
});

test('unchanged exposed content is a no-op', async (t) => {
  const h = fixture(t);
  h.contents.set(HEAD, BASE);
  await h.patch();
  assert.deepEqual(h.writes, []);
  assert.ok(h.logs.some((line) => line.includes('outcome=no-action-change')));
});

test('already published retry only verifies existing state', async (t) => {
  const h = fixture(t);
  h.context.sha = BASE;
  await h.patch();
  assert.deepEqual(h.writes, []);
  assert.ok(h.logs.some((line) => line.includes('outcome=already-published')));
});

for (const invalid of ['confirmation', 'event', 'stale', 'patch partial', 'reordered major']) {
  test(`manual major rejects ${invalid} without writes`, async (t) => {
    const h = fixture(t);
    h.authorizeMajor();
    if (invalid === 'confirmation') process.env.RELEASE_CONFIRMATION = 'PUBLISH NEXT MAJOR';
    if (invalid === 'event') h.context.eventName = 'push';
    if (invalid === 'stale') h.master = OTHER;
    if (invalid === 'patch partial') h.refs.set(NEXT_TAG, HEAD);
    if (invalid === 'reordered major') h.addRelease('v2.0.0', HEAD, true); // Fixed tag is missing.
    await assert.rejects(h.major(), /confirmation|requires workflow_dispatch|Stale manual target|not authorized target|resources before its fixed tag/);
    assert.deepEqual(h.writes, []);
  });
}

test('authorized manual major creates fixed and floating refs without moving the prior major', async (t) => {
  const h = fixture(t);
  h.authorizeMajor();
  await h.major();
  completed(h, 'v2.0.0');
  assert.equal(h.refs.get('v2.0'), HEAD);
  assert.equal(h.refs.get('v1'), BASE);
  assert.deepEqual(h.calls('createRef').map(({ ref }) => ref), ['refs/tags/v2.0.0', 'refs/tags/v2.0', 'refs/tags/v2']);
  assert.deepEqual(h.calls('git'), []);
});

test('authorized stale major resumes only its exact ordered partial', async (t) => {
  const h = fixture(t);
  h.authorizeMajor();
  h.master = OTHER;
  h.refs.set('v2.0.0', HEAD);
  await h.major();
  completed(h, 'v2.0.0');
  assert.equal(h.refs.get('v2.0'), HEAD);
  assert.deepEqual(h.calls('createRef').map(({ ref }) => ref), ['refs/tags/v2.0', 'refs/tags/v2']);
  assert.equal(h.refs.get('v1'), BASE);
});
