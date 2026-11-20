const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

function pantallaPwa(almacen, cantidadDictados = null) {
  const eventos = {}, worker = {}, modal = {};
  const estados = ['borrador', 'outbox', 'dictado'].map((estado) => ({dataset: {estado}, hidden: true}));
  let cierres = 0, aperturas = 0, cerrarAviso, recargas = 0;
  const aviso = {
    hidden: true,
    querySelectorAll: () => estados,
    querySelector: () => ({addEventListener(_, fn) { cerrarAviso = fn; }}),
  };
  const indexedDB = {
    databases: async () => cantidadDictados === null ? [] : [{name: 'ordo-dictado'}],
    open(nombre) {
      assert.equal(nombre, 'ordo-dictado');
      aperturas++;
      const apertura = {result: {
        objectStoreNames: {contains: (nombre) => nombre === 'pendientes'},
        transaction(almacen, modo) {
          assert.equal(almacen, 'pendientes');
          assert.equal(modo, 'readonly');
          return {objectStore: () => ({count() {
            const lectura = {result: cantidadDictados};
            queueMicrotask(() => lectura.onsuccess());
            return lectura;
          }})};
        },
        close() { cierres++; },
      }};
      queueMicrotask(() => apertura.onsuccess());
      return apertura;
    },
    deleteDatabase() { assert.fail('El aviso no debe borrar bases'); },
  };
  const dialogo = {
    showModal() { this.open = true; },
    addEventListener(evento, fn) { modal[evento] = fn; },
    querySelector() { return {addEventListener(evento, fn) { modal[evento] = fn; }}; },
  };
  const navigator = {
    userAgent: '', onLine: false,
    serviceWorker: {addEventListener: (evento, fn) => { worker[evento] = fn; }},
  };
  vm.runInNewContext(fs.readFileSync('static/js/pwa.js', 'utf8'), {
    navigator, location: {reload() { recargas++; }},
    window: {
      navigator, indexedDB, matchMedia: () => ({matches: false}),
      caches: {keys() { assert.fail('Una caché hist?rica no indica trabajo pendiente'); }},
      addEventListener: (evento, fn) => { eventos[evento] = fn; },
    },
    document: {
      addEventListener() {},
      getElementById: (id) => ({'os-transicion-pwa': aviso, 'os-pagina-restaurada': dialogo}[id]),
    },
    localStorage: {
      get length() { return almacen.size; },
      key: (i) => [...almacen.keys()][i],
      getItem: (clave) => almacen.get(clave),
      removeItem() { assert.fail('Cerrar el aviso no debe borrar datos'); },
      clear() { assert.fail('El aviso no debe limpiar el almacenamiento'); },
    },
  });
  return {eventos, worker, aviso, estados, dialogo, modal, cerrarAviso, recargas: () => recargas,
    aperturas: () => aperturas, cierres: () => cierres};
}

test('aviso oculto en el HTML y con solo marcas, cola vacía o base de dictado vacía', async () => {
  const plantilla = fs.readFileSync('templates/base.html', 'utf8');
  assert.match(plantilla, /<section[^>]*id="os-transicion-pwa"[^>]*\bhidden\b/);
  const almacen = new Map([
    ['ofl:ordo-salud:clinica:1:precarga', '{}'],
    ['ofl:omnis:clinica:1:otro', 'marca'],
    ['ofl:omnis:clinica:1:outbox', '[null]'],
    ['ofl:ordo-salud:clinica:1:outbox', '[]'],
    ['ofl:ordo-salud:clinica:1:draft:/consulta/#form', '{"campos":[]}'],
  ]);
  const original = [...almacen];
  const sinBase = pantallaPwa(almacen);
  await sinBase.worker.controllerchange();
  assert.equal(sinBase.aviso.hidden, true);
  assert.equal(sinBase.aperturas(), 0);
  const baseVacia = pantallaPwa(almacen, 0);
  await baseVacia.worker.controllerchange();
  assert.equal(baseVacia.aviso.hidden, true);
  assert.equal(baseVacia.aperturas(), baseVacia.cierres());
  assert.deepEqual([...almacen], original);
});

for (const [estado, entrada, dictados] of [
  ['borrador', ['ofl:ordo-salud:clinica:1:draft:/consulta/#form', '{"campos":[["nota","Sintética"]]}']],
  ['outbox', ['ofl:omnis:clinica:1:outbox', '[{"id":"sintetico","estado":"pendiente"}]']],
  ['dictado', null, 1],
]) {
  test(`aviso muestra ${estado} y permite cerrarlo sin modificar almacenamiento`, async () => {
    const almacen = new Map(entrada ? [entrada] : []);
    const original = [...almacen];
    const pantalla = pantallaPwa(almacen, dictados);
    await pantalla.worker.controllerchange();
    assert.equal(pantalla.aviso.hidden, false);
    assert.deepEqual(pantalla.estados.filter((el) => !el.hidden).map((el) => el.dataset.estado), [estado]);
    pantalla.cerrarAviso();
    assert.equal(pantalla.aviso.hidden, true);
    await pantalla.eventos.storage();
    await pantalla.worker.controllerchange();
    assert.equal(pantalla.aviso.hidden, true);
    assert.deepEqual([...almacen], original);
    assert.equal(pantalla.aperturas(), pantalla.cierres());
  });
}

test('restaurar una pestaña desde el historial conserva el bloqueo de sesión', () => {
  const pantalla = pantallaPwa(new Map());
  pantalla.eventos.pageshow({persisted: true});
  assert.equal(pantalla.dialogo.open, true);
  assert.equal(pantalla.recargas(), 0);
  let cancelado = false;
  pantalla.modal.cancel({preventDefault() { cancelado = true; }});
  assert.equal(cancelado, true);
  pantalla.modal.click();
  assert.equal(pantalla.recargas(), 1);
});

function pantalla(agente, responder) {
  const acciones = ['validar', 'business', 'web', 'copiar'];
  const botones = acciones.map((accion) => ({
    dataset: {whatsapp: accion}, hidden: true, addEventListener(_, clic) { this.clic = clic; },
  }));
  const navegaciones = [], copias = [], llamadas = [];
  const estado = {};
  const formulario = {
    action: 'https://ordo.example/agenda/contacto/',
    querySelectorAll: () => botones, querySelector: () => estado, addEventListener() {},
  };
  const codigo = fs.readFileSync('static/js/whatsapp.js', 'utf8');
  vm.runInNewContext(codigo, {
    document: {querySelectorAll: () => [formulario]},
    navigator: {userAgent: agente, clipboard: {writeText: async (texto) => copias.push(texto)}},
    crypto: {getRandomValues: (bytes) => bytes.fill(17)}, Uint8Array,
    window: {location: {assign: (url) => navegaciones.push(url)}},
    FormData: class extends Map { constructor() { super(); } },
    fetch: async (_, opciones) => {
      llamadas.push(opciones);
      return responder(opciones.body.get('accion'));
    },
  });
  return {botones, navegaciones, copias, llamadas, estado, clic: (accion) => botones[acciones.indexOf(accion)].clic()};
}

test('Business exige nueva validación y los fallos impiden apertura y copia', async () => {
  for (const status of [403, 409, 500, null]) {
    const p = pantalla('Android', (accion) => {
      if (accion === 'validar') return new Response(null, {status: 204});
      if (!status) throw new Error('sin red');
      return Response.json({destino: 'https://wa.me/584140000000', mensaje: 'sintético'}, {status});
    });
    assert.equal(p.botones[1].hidden, true);
    await p.clic('validar');
    assert.equal(p.botones[1].hidden, false);
    await p.clic('business');
    assert.equal(p.botones[1].hidden, true);
    await p.clic('web');
    await p.clic('copiar');
    assert.deepEqual(p.navegaciones, []);
    assert.deepEqual(p.copias, []);
    assert.match(p.estado.textContent, /reintenta/);
    assert.ok(p.llamadas.every((opciones) => opciones.cache === 'no-store'));
  }
});

test('un doble clic envía un POST y el reintento usa la misma clave', async () => {
  let resolver;
  const p = pantalla('Android', () => new Promise((ok) => { resolver = ok; }));
  const pendiente = p.clic('web');
  await p.clic('web');
  assert.equal(p.llamadas.length, 1);
  assert.deepEqual(p.navegaciones, []);
  resolver(Response.json({}, {status: 500}));
  await pendiente;
  const reintento = p.clic('web');
  assert.equal(p.llamadas[0].body.get('clave_intento'), p.llamadas[1].body.get('clave_intento'));
  resolver(Response.json({destino: 'https://wa.me/584140000000'}));
  await reintento;
  assert.deepEqual(p.navegaciones, ['https://wa.me/584140000000']);
});

test('apertura validada en Android y alternativa HTTPS y copia en iOS y escritorio', async () => {
  for (const agente of ['Android', 'iPhone', 'Windows']) {
    const p = pantalla(agente, (accion) => {
      if (accion === 'validar') return new Response(null, {status: 204});
      if (accion === 'copiar') return Response.json({mensaje: 'Mensaje sintético'});
      return Response.json({destino: accion === 'business'
        ? 'intent://send/?phone=584140000000#Intent;package=com.whatsapp.w4b;end'
        : 'https://wa.me/584140000000'});
    });
    if (agente === 'Android') {
      await p.clic('validar');
      await p.clic('business');
      assert.match(p.navegaciones[0], /^intent:/);
    } else {
      assert.equal(p.botones[0].hidden, true);
    }
    await p.clic('web');
    assert.ok(p.navegaciones.at(-1).startsWith('https://wa.me/'));
    await p.clic('copiar');
    assert.deepEqual(p.copias, ['Mensaje sintético']);
  }
});

test('SW conserva aisladas las cachés anteriores al cambiar o perder sesión', async () => {
  const python = fs.readFileSync('apps/core/pwa.py', 'utf8');
  const codigo = python.split('SW_JS = r"""')[1].split('"""')[0]
    .replaceAll('__VERSION__', 'test').replace('__PRECARGA__', '["/static/publico.css", "/static/sensible.css"]');
  const origen = 'https://ordo.example';
  const eventos = {};
  const almacen = new Map([
    ['ordo-paginas-v1', new Map([[origen + '/agenda/', new Response('Paciente anterior')]])],
    ['omnis-paginas-v1', new Map([[origen + '/agenda/', new Response('Paciente anterior')]])],
    ['ordo-static-anterior', new Map()],
    ['otra-app', new Map()],
  ]);
  let usuario = 'Usuario A', sinRed = false, errorEnvio;
  let borrada = false;
  const peticiones = [];
  vm.runInNewContext(codigo, {
    URL, Response,
    self: {location: {origin: origen}, addEventListener: (nombre, fn) => { eventos[nombre] = fn; },
           skipWaiting() {}, clients: {claim() {}}, indexedDB: {deleteDatabase() { borrada = true; }}},
    caches: {
      keys: async () => [...almacen.keys()], delete: async (nombre) => almacen.delete(nombre),
      open: async (nombre) => {
        if (!almacen.has(nombre)) almacen.set(nombre, new Map());
        return {match: async (url) => almacen.get(nombre).get(url)?.clone(),
                put: async (url, resp) => almacen.get(nombre).set(url, resp)};
      },
    },
    fetch: async (solicitud, opciones) => {
      peticiones.push(opciones);
      if (typeof solicitud === 'string') {
        return solicitud.endsWith('publico.css')
          ? new Response('body {}', {headers: {'Content-Type': 'text/css', 'Cache-Control': 'max-age=60, public'}})
          : new Response('Dato personal sintético', {headers: {'Content-Type': 'text/html', 'Cache-Control': 'private'}});
      }
      if (solicitud.method === 'POST') {
        if (errorEnvio instanceof Error) throw errorEnvio;
        return new Response('Fallo sintético', {status: 500});
      }
      if (sinRed) throw new Error('sin red');
      return usuario ? new Response(usuario) : new Response(null, {status: 302, headers: {Location: '/cuenta/entrar/'}});
    },
  });
  function ejecutar(evento, datos = {}) {
    let resultado;
    eventos[evento]({...datos, waitUntil: (promesa) => { resultado = promesa; },
                     respondWith: (promesa) => { resultado = promesa; }});
    return resultado;
  }
  function navegar(ruta) {
    return ejecutar('fetch', {request: {url: origen + ruta, method: 'GET', mode: 'navigate'}});
  }
  await ejecutar('install');
  await ejecutar('activate');
  assert.equal(borrada, false);
  assert.deepEqual([...almacen.keys()], ['ordo-paginas-v1', 'omnis-paginas-v1', 'ordo-static-anterior',
                                        'otra-app', 'ordo-static-test']);
  assert.deepEqual([...almacen.get('ordo-static-test').keys()], [origen + '/static/publico.css']);
  assert.ok(peticiones.slice(0, 2).every((opciones) => opciones.credentials === 'omit'));
  assert.equal(await (await navegar('/agenda/')).text(), 'Usuario A');
  usuario = null;
  assert.equal((await navegar('/agenda/')).status, 302);
  usuario = 'Usuario B';
  assert.equal(await (await navegar('/agenda/')).text(), 'Usuario B');
  const solicitud = {request: {url: origen + '/consultas/8/editar/', method: 'POST', mode: 'same-origin'}};
  assert.equal((await ejecutar('fetch', solicitud)).status, 500);
  for (const mensaje of ['sin red', 'timeout']) {
    errorEnvio = new Error(mensaje);
    await assert.rejects(ejecutar('fetch', solicitud), errorEnvio);
  }
  sinRed = true;
  for (const ruta of ['/agenda/', '/pacientes/4/', '/consultas/8/editar/']) {
    const r = await navegar(ruta);
    assert.equal(r.status, 503);
    assert.doesNotMatch(await r.text(), /Paciente anterior|Usuario [AB]/);
  }
  assert.ok(peticiones.slice(2).every((opciones) => opciones.cache === 'no-store'));
  assert.deepEqual([...almacen.get('ordo-static-test').keys()], [origen + '/static/publico.css']);
});
