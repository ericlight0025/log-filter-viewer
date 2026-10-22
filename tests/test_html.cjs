// 以最小 DOM 替身執行 HTML 的原始 JavaScript，無須安裝前端測試框架。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = []; this.events = {}; this.style = {}; this.value = '';
    this.checked = false; this.disabled = false; this.className = '';
    this.classList = {add() {}, remove() {}};
  }
  set innerHTML(value) { this.html = value; this.children = []; }
  get innerHTML() { return this.html || ''; }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  addEventListener(type, handler) { this.events[type] = handler; }
  querySelectorAll(selector) {
    const name = selector.slice(1);
    return this.children.flatMap(child => [
      ...(child.className.split(' ').includes(name) ? [child] : []), ...child.querySelectorAll(selector)
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  focus() {}
  click() {}
}

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'standalone_html', 'index.html'), 'utf8');
const elements = new Map();
const document = {
  body: new Element(), createElement: () => new Element(),
  getElementById(id) { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); }
};
class FileReader { readAsText(file) { this.onload({target: {result: file.text}}); } }
const context = {
  document, FileReader, console, assert, Float64Array, Date, Set, Blob, URL, setTimeout,
  alert: message => { throw new Error(message); }, localStorage: {getItem() { return null; }, setItem() {}}
};
vm.createContext(context);
vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const run = source => vm.runInContext(source, context);
const plain = value => JSON.parse(JSON.stringify(value));

run(`matchModeSel.value = 'or'; contextSel.value = '0';
     keywordsContainer.querySelector('.search-input').value = 'ERROR';
     loadFile({name: 'unordered.log', text: '2026-09-24 10:00:00 ERROR A\\n2026-09-24 09:00:00 ERROR B'});`);
assert.equal(run('startTimeInput.value'), '2026-09-24T09:00:00');
assert.equal(run('endTimeInput.value'), '2026-09-24T10:00:01');
assert.deepEqual(plain(run("findMatches(['ERROR'], 'or', true, startTimeInput.value, endTimeInput.value)")), [0, 1]);
console.log('PASS: 亂序時間範圍與命中');

run(`logLines = ['ERROR timeout', 'ERROR', 'INFO timeout'];
     lineTimestamps = new Float64Array(3);`);
assert.deepEqual(plain(run("findMatches(['error', 'timeout'], 'and', false, '', '')")), [0]);
assert.deepEqual(plain(run("findMatches(['error', 'timeout'], 'or', false, '', '')")), [0, 1, 2]);
assert.deepEqual(plain(run('mergeRanges([[3, 5], [1, 3], [6, 7], [10, 10]])')), [[1, 7], [10, 10]]);
run("renderResults([[0, 2]], new Set([0, 1]), ['ERROR']);");
const rowNumbers = [...run('logContainer.innerHTML').matchAll(/class="line-no">(\d+)/g)].map(match => Number(match[1]));
assert.deepEqual(rowNumbers, [1, 2, 3]);
const escaped = run(`safeHighlight('<script>ERROR & "x"</script>', /(ERROR)/gi, [{raw: 'ERROR', colorIdx: 0}])`);
assert.ok(escaped.includes('&lt;script&gt;') && escaped.includes('&amp;') && !escaped.includes('<script>'));
console.log('PASS: AND/OR、區間合併、行號與安全高亮');

run(`logLines = Array.from({length: 1000000}, (_, i) => i % 101 === 50 ? 'ERROR' : 'INFO');
     lineTimestamps = new Float64Array(logLines.length);
     enableTimeFilter.checked = false; contextSel.value = '50';
     const realRenderResults = renderResults;
     let renderedRows = 0;
     renderResults = ranges => { renderedRows = ranges.reduce((n, [a, b]) => n + b - a + 1, 0); };
     searchLog();`);
assert.equal(run('renderedRows'), 0);
assert.equal(run('currentMergedRanges.length'), 0);
assert.equal(run('copyBtn.disabled'), true);
assert.ok(run('placeholder.innerHTML').includes('1,000,000'));
// 正好 50,000 行可展示，50,001 行則必須阻擋。
run("logLines = Array(50000).fill('ERROR'); contextSel.value = '0'; searchLog();");
assert.equal(run('renderedRows'), 50000);
run("logLines.push('ERROR'); renderedRows = 0; searchLog();");
assert.equal(run('renderedRows'), 0);
run('renderResults = realRenderResults;');
console.log('PASS: 百萬行上下文保護與 50,000 行邊界');

const canonical = {
  schemaVersion: 1, keywords: ['ERROR', 'timeout'], matchMode: 'and', contextLines: 0,
  enableTimeFilter: true, startTime: '2026-09-24T09:30:00', endTime: '2026-09-24T10:00:00'
};
run(`applyPreset(${JSON.stringify(canonical)});`);
assert.deepEqual(plain(run('getPreset()')), canonical);
run(`loadFile({name: 'other.log', text: '2026-09-25 12:00:00 ERROR timeout'});`);
assert.deepEqual(plain(run('getPreset()')), canonical, '載入檔案不可覆蓋明確匯入的時間');
run(`applyPreset({keywords: ['WARN'], match_mode: '符合全部 (AND)', context_lines: 20, enable_time: false});`);
assert.equal(run('getPreset().matchMode'), 'and');
assert.equal(run('getPreset().contextLines'), 20);
assert.equal(run('startTimeInput.value'), '');
assert.equal(run('endTimeInput.value'), '');
run(`applyPreset({keywords: [], contextLines: '0'});`);
assert.equal(run('getPreset().contextLines'), 0);
assert.equal(run("keywordsContainer.querySelectorAll('.search-input').length"), 1);
console.log('PASS: 設定往返、舊版相容、零上下文與空時間');

const invalid = [null, [], {keywords: [1]}, {keywords: null}, {matchMode: []}, {contextLines: true},
  {contextLines: null}, {enableTimeFilter: 'false'}, {startTime: '2026-02-30T00:00:00'},
  {startTime: '2026-09-25T00:00:00', endTime: '2026-09-24T00:00:00'}, {schemaVersion: 2}];
const before = plain(run('getPreset()'));
for (const data of invalid) {
  assert.throws(() => run(`applyPreset(${JSON.stringify(data)});`));
  assert.deepEqual(plain(run('getPreset()')), before, '錯誤設定不可部分改寫查詢');
}
run(`applyPreset(${JSON.stringify(canonical)});
     startTimeInput.value = '2026-09-25T00:00:00'; searchLog();`);
assert.equal(run('copyBtn.disabled'), true);
assert.equal(run('currentMergedRanges.length'), 0);
assert.ok(run('placeholder.textContent').includes('開始時間不可晚於結束時間'));
console.log('PASS: 無效設定不改寫條件，反向時間不保留舊結果');
