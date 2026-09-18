// Run: node scripts/test-tv.cjs. No database or extra dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('../frontend/node_modules/typescript');
const vm = require('node:vm');
const output = ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname, '../frontend/src/lib/tv.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const exportsObject = {};
const displayExports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname, '../frontend/src/lib/public-display.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { exports: displayExports });
vm.runInNewContext(output, { exports: exportsObject, URLSearchParams, require: name => {
  assert.equal(name, './public-display');
  return displayExports;
} });
const { readTvSettings, tvQuery, paginateTv, nextTvGroup } = exportsObject;
const plain = value => JSON.parse(JSON.stringify(value));
const defaults = { ...displayExports.PUBLIC_DISPLAY_DEFAULTS, tv_stage:'final', tv_interval_seconds:37, tv_teams:true };
assert.deepEqual(plain(readTvSettings(new URLSearchParams(), defaults)), { stage:'final', interval:37, teams:true, groups:null });
assert.deepEqual(plain(readTvSettings(new URLSearchParams('stage=qualification&interval=9'), defaults)), { stage:'qualification', interval:9, groups:null });
assert.equal(!!readTvSettings(new URLSearchParams('teams=0'), defaults).teams, false);
assert.equal(readTvSettings(new URLSearchParams('stage=final&teams=1&group=boys'), defaults).teams, true);
assert.deepEqual(plain(readTvSettings(new URLSearchParams('group=boys'), defaults).groups), ['boys']);
assert.equal(!!readTvSettings(new URLSearchParams(tvQuery({ stage:'final', interval:37, teams:false, groups:null }, true)), defaults).teams, false);
assert.deepEqual(plain(readTvSettings(new URLSearchParams('stage=wrong&interval=5.5'))), { stage:'qualification', interval:15, groups:null });
for (const interval of ['', 'NaN', '0', '121', '-5']) assert.equal(readTvSettings(new URLSearchParams({ interval })).interval, 15);
for (const interval of [5,10,15,120]) assert.equal(readTvSettings(new URLSearchParams({ interval:String(interval) })).interval, interval);
for (const groups of [null, [], ['М 10–12', 'girls', 'Имя с пробелом']]) {
  const settings = { stage:'final', interval:10, groups };
  const restored = plain(readTvSettings(new URLSearchParams(tvQuery(settings, true))));
  assert.deepEqual(restored, settings);
  assert.equal(new URLSearchParams(tvQuery(settings,true)).get('autoplay'), '1');
  assert.equal(new URLSearchParams(tvQuery(settings,false)).has('autoplay'), false);
}
assert.deepEqual(plain(paginateTv(0)), []);
assert.deepEqual(plain(paginateTv(20)), [{left:[0,20]}]);
assert.deepEqual(plain(paginateTv(21)), [{left:[0,20],right:[20,21]}]);
assert.deepEqual(plain(paginateTv(40)), [{left:[0,20],right:[20,40]}]);
assert.deepEqual(plain(paginateTv(41)), [{left:[0,20],right:[20,40]},{left:[40,41],right:[41,41]}]);
for (let count=1;count<=500;count++) {
  const pages=paginateTv(count);
  const indexes=pages.flatMap(page=>[page.left,page.right].filter(Boolean).flatMap(([a,b])=>Array.from({length:b-a},(_,i)=>a+i)));
  assert.deepEqual(plain(indexes),Array.from({length:count},(_,i)=>i));
  for(const page of pages) for(const [a,b] of [page.left,page.right].filter(Boolean)) assert.ok(b-a<=20);
  if (count>20) assert.ok(pages.every(page=>page.right));
}
const groups=[{slug:'a'},{slug:'b'},{slug:'c'}];
assert.equal(nextTvGroup(groups,'a').slug,'b');
assert.equal(nextTvGroup(groups,'c').slug,'a');
assert.equal(nextTvGroup(groups,'removed').slug,'a');
assert.equal(nextTvGroup([], 'a'),undefined);
assert.equal(nextTvGroup([groups[0]],'a').slug,'a');
console.log('TV: URL validation, 20-row columns, 500 pagination scenarios, order, empty columns and group wrap passed.');

assert.equal(readTvSettings(new URLSearchParams(tvQuery({stage:"final", interval:5, groups:[], teams:true}, true))).teams, true);
assert.equal(readTvSettings(new URLSearchParams("teams=0")).teams, undefined);

for (const capacity of [1, 15, 30]) for (const columns of [1, 2]) for (const count of [0, 1, 29, 30, 31, 60, 130]) {
  const pages=paginateTv(count,capacity,columns);
  const ranges=pages.flatMap(page=>[page.left,page.right].filter(Boolean));
  assert.deepEqual(plain(ranges.flatMap(([a,b])=>Array.from({length:b-a},(_,i)=>a+i))),Array.from({length:count},(_,i)=>i));
  assert.ok(ranges.every(([a,b])=>b-a<=capacity));
  if(columns===1) assert.ok(pages.every(page=>!page.right));
}
console.log('TV: adaptive capacities 1/15/30 and single/double columns preserve every participant.');
