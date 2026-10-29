const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup(api) {
  const elements = new Map();
  function node(tag, text, className = '') {
    const classes = new Set(className.split(' '));
    return {
      textContent: text, children: [], attributes: {}, value: '',
      classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c)},
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      get lastElementChild() { return this.children.at(-1); },
      setAttribute(key, value) { this.attributes[key] = value; },
      addEventListener(type, handler) { this[type] = handler; },
      focus() {}, scrollIntoView() {},
    };
  }
  const $ = id => {
    if (!elements.has(id)) elements.set(id, node('div'));
    return elements.get(id);
  };
  let timer, cleared = false;
  const context = vm.createContext({
    $, node, api, AbortController, Date, notify() {},
    setInterval(callback) {timer = callback; return 1;},
    clearInterval() {cleared = true;},
    document: {querySelectorAll: () => []},
    startNewDocument: () => true, startNewIncident: () => true,
    markDirty() {}, incidentDirty: false,
  });
  const source = fs.readFileSync(path.join(__dirname, '../src/support_ai/web/app.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function addMessage('), source.indexOf("$('chat-return').addEventListener")), context);
  return {context, $, tick: () => timer(), cleared: () => cleared};
}

test('shows processing while waiting and clears it on success', async () => {
  let resolve;
  const ui = setup(() => new Promise(r => {resolve = r;}));
  const request = ui.context.ask('Error de pagos');
  const message = ui.$('messages').lastElementChild;
  assert.equal(message.attributes['aria-busy'], 'true');
  assert.equal(ui.$('send').disabled, true);
  ui.tick();
  assert.match(message.lastElementChild.textContent, /Sigo procesando/);
  resolve({answer: 'Respuesta verificada', abstained: false, sources: []});
  await request;
  assert.equal(message.lastElementChild.textContent, 'Respuesta verificada');
  assert.equal(message.attributes['aria-busy'], 'false');
  assert.equal(ui.$('send').disabled, false);
  assert.ok(ui.cleared());
});

test('missing information offers both forms and preserves the question', async () => {
  const question = 'Falla el servicio de pagos';
  const ui = setup(async () => ({answer: 'No hay información', abstained: true, sources: []}));
  await ui.context.ask(question);
  const actions = ui.$('messages').lastElementChild.lastElementChild.children;
  assert.deepEqual(actions.map(action => action.textContent), ['Documentar conocimiento', 'Registrar un error']);
  actions[0].click();
  assert.ok(ui.$('notes').value.includes(question));
  actions[1].click();
  assert.equal(ui.$('incident-symptoms').value, question);
});

test('errors stop the processing indicator and allow another question', async () => {
  const ui = setup(async () => {throw new Error('Ollama no respondió');});
  await ui.context.ask('Error de pagos');
  const message = ui.$('messages').lastElementChild;
  assert.equal(message.lastElementChild.textContent, 'Ollama no respondió');
  assert.equal(message.classList.contains('loading'), false);
  assert.equal(ui.$('send').disabled, false);
  assert.ok(ui.cleared());
});

test('cancelled document creation does not overwrite existing notes', async () => {
  const ui = setup(async () => ({answer: 'Sin fuentes', abstained: true, sources: []}));
  ui.context.startNewDocument = () => false;
  ui.$('notes').value = 'Mis notas anteriores';
  await ui.context.ask('Nueva consulta');
  ui.$('messages').lastElementChild.lastElementChild.children[0].click();
  assert.equal(ui.$('notes').value, 'Mis notas anteriores');
});
