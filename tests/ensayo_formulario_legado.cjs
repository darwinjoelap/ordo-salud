// Ensayo explícito: git show REV:static/js/offline.js | node tests/ensayo_formulario_legado.cjs MARCA
// Solo se ejecuta el manejador histórico en memoria. La red, los temporizadores y el envío nativo son dobles.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const marca = process.argv[2];
assert.ok(['omnis', 'ordo-salud'].includes(marca));
const fuente = fs.readFileSync(0, 'utf8');
const arranque = "if (document.readyState === 'loading')";
assert.ok(fuente.includes(arranque));
const codigo = fuente.replace(arranque, 'window.enviarFormulario = alEnviar; ' + arranque);

function pestana(almacen, responder) {
  const nativos = [];
  const cola = () => JSON.parse(almacen.get('ofl:' + marca + ':local:1:outbox') || '[]');
  const window = {OFFLINE_CFG: {tenant: 'local', user: 1}};
  const document = {
    cookie: '', readyState: 'loading', addEventListener() {}, createElement: () => ({}),
  };
  const formulario = {
    tagName: 'FORM', dataset: {offlineTitulo: 'Prueba'}, action: '/formulario-sintetico/',
    elements: [{name: 'campo', value: 'original'}],
    getAttribute: nombre => nombre === 'method' ? 'POST' : '',
    closest: selector => selector === '.modal' ? {} : null,
    querySelector: () => null, querySelectorAll: () => [], insertBefore() {},
    appendChild(el) { this.elements.push(el); },
  };
  class Datos extends URLSearchParams {
    constructor(form) { super(form?.elements.map(el => [el.name, el.value])); }
  }
  class Formulario {
    submit() {
      nativos.push({pendientes: cola().length, campos: Object.fromEntries(this.elements.map(e => [e.name, e.value]))});
    }
  }
  vm.runInNewContext(codigo, {
    window, document, navigator: {onLine: true}, location: {pathname: '/ensayo/', search: ''},
    setTimeout() {}, clearTimeout() {}, fetch: responder, FormData: Datos, HTMLFormElement: Formulario,
    localStorage: {
      getItem: k => almacen.get(k) ?? null, setItem: (k, v) => almacen.set(k, v),
      removeItem: k => almacen.delete(k),
    },
  });
  return {cola, nativos, enviar() { window.enviarFormulario({target: formulario, preventDefault() {}}); }};
}

const esperar = () => new Promise(resolve => setImmediate(resolve));
const respuesta = status => ({status, ok: status === 200, headers: {get: () => 'text/html'}});

test('dos pestañas conservan sus formularios tras el rechazo de f28', async () => {
  const almacen = new Map();
  const responder = async (_url, peticion) => {
    assert.equal(peticion.headers['X-Offline-Form'], '1');
    return respuesta(403);
  };
  const a = pestana(almacen, responder);
  const b = pestana(almacen, responder);
  a.enviar();
  b.enviar();
  await esperar();
  assert.equal(a.cola().length, 2);
  assert.ok(a.cola().every(item => item.estado === 'error' && new Map(item.entries).get('campo') === 'original'));
  assert.equal(a.nativos.length + b.nativos.length, 0);
});

test('un resultado de red desconocido mantiene el original pendiente', async () => {
  const tab = pestana(new Map(), async () => { throw new Error('Red simulada'); });
  tab.enviar();
  await esperar();
  assert.equal(tab.cola()[0].estado, 'pendiente');
  assert.equal(new Map(tab.cola()[0].entries).get('campo'), 'original');
  assert.equal(tab.nativos.length, 0);
});

test('en un modal el cliente retira el único elemento antes de la navegación nativa', async () => {
  const almacen = new Map();
  const tab = pestana(almacen, async () => respuesta(200));
  tab.enviar();
  const clave = tab.cola()[0].id;
  await esperar();
  assert.deepEqual(tab.nativos, [{pendientes: 0, campos: {campo: 'original', _idem_key: clave}}]);
  assert.equal(almacen.size, 1);
  assert.deepEqual(tab.cola(), []);
});
