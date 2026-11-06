import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const API_PATH = '/api/chaoxing.homework';
const FALLBACK = path.join(os.homedir(), '.chaoxing-homework', 'result.json');
const OPENCLAW = path.join(os.homedir(), '.openclaw', 'workspace', 'tools', 'chaoxing', 'result.json');

function candidates(config) {
  const list = [];
  if (config && typeof config.resultPath === 'string' && config.resultPath) list.push(config.resultPath);
  if (process.env.CX_RESULT) list.push(process.env.CX_RESULT);
  list.push(OPENCLAW, FALLBACK);
  return list.filter((v, i, a) => v && a.indexOf(v) === i);
}

function newest(config) {
  let best = null;
  for (const p of candidates(config)) {
    try {
      const st = fs.statSync(p);
      if (!st.isFile()) continue;
      if (!best || st.mtimeMs > best.mtimeMs) best = { path: p, mtimeMs: st.mtimeMs };
    } catch (_) { /* ignore missing or unreadable candidates */ }
  }
  return best;
}

function normalize(raw, source) {
  const courses = Array.isArray(raw) ? raw : (raw.courses || []);
  const items = [];
  for (const c of courses) {
    for (const it of (c.items || [])) {
      const status = String(it.status || '');
      const submitted = /待批阅|已完成|已提交|已交/.test(status) && !/未交|未完成/.test(status);
      items.push({
        course: String(c.course || ''),
        name: String(it.name || ''),
        status: status,
        submitted: submitted,
        deadline: it.deadline || null,
        deadlineFull: it.deadlineFull || null,
        deadlineSource: it.deadlineSource || null,
        remainText: it.remainText || null,
        expired: !!it.expired,
        closed: !!it.closed,
        taskUrl: it.taskUrl || null,
      });
    }
  }
  return {
    checkedAt: raw.checkedAt || null,
    semesterEnd: raw.semesterEnd || null,
    source: source,
    items: items,
  };
}

export const inject = ['connection'];

export function apply(ctx, config) {
  ctx.effect(() => ctx.connection.fetch.register({
    path: API_PATH,
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: () => {
      const found = newest(config);
      const headers = { 'cache-control': 'no-store' };
      if (!found) {
        return Promise.resolve(Response.json(
          { ok: false, error: 'NO_RESULT', message: '找不到学习通扫描结果 result.json' },
          { headers: headers }
        ));
      }
      try {
        const raw = JSON.parse(fs.readFileSync(found.path, 'utf8'));
        const data = normalize(raw, { path: found.path, mtime: new Date(found.mtimeMs).toISOString() });
        return Promise.resolve(Response.json({ ok: true, ...data }, { headers: headers }));
      } catch (e) {
        return Promise.resolve(Response.json(
          { ok: false, error: 'READ_FAILED', message: String((e && e.message) || e) },
          { headers: headers }
        ));
      }
    },
  }), 'chaoxing-homework: /api route');
}
