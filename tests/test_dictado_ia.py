"""Dictado de toda la consulta con IA (ADR-045): permisos, minutos del plan, esquema, validación y llenado."""
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from apps.clinica.models import Consulta, PlantillaHistoria
from apps.configuracion.models import ConfiguracionTenant
from apps.dictado import audio as conversor
from apps.dictado import proveedores, servicios
from apps.dictado.models import SesionDictado
from apps.pacientes.models import Paciente
from apps.plataforma.models import Plan

from .base import BaseTest, crear_consultorio

ENTRADA = {'secciones': {
    'nucleo.signos_vitales': {'fc': 103, 'spo2': 97, 'pa_sistolica': 105, 'pa_diastolica': 60, 'peso_kg': 21.1,
                              'talla_cm': 121},
    'cp.ekg': {'ritmo': 'RS', 'fc': 94, 'pr': 0.12, 'qt': 0.34, 'trazo': 'HVD'},
    'cp.eco': {'tia': 'DEFECTO', 'cia_tipo': 'OS', 'qpqs': 2.5, 'situs': 'NO_EXISTE', 'fevi': '74 %',
               'pulm_z': -50},
    'nucleo.diagnosticos': {'diagnosticos': [{'codigo': 'Q21.1', 'descripcion': 'CIA ostium secundum'}]},
    'nucleo.plan': {'plan': 'Se inicia tratamiento. Se revalorará en 4 meses.'}},
    'no_ubicado': 'La mamá trae un Holter de otra institución.'}


def audio():
    return SimpleUploadedFile('dictado.webm', b'\x1aE\xdf\xa3audio-falso', content_type='audio/webm')


@override_settings(DICTADO_SINCRONO=True)
class DictadoTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Cardio', 'cardio2', especialidad='cardiologia_pediatrica')
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Ana', apellidos='Ruiz', sexo='F')
            self.plantilla = PlantillaHistoria.objects.get(nombre='Consulta de cardiología pediátrica')

    def activar(self, minutos=0, **plan):
        ConfiguracionTenant.objects.filter(tenant=self.tenant).update(dictado_activo=True)
        plan = Plan.objects.create(nombre='Con dictado', incluye_dictado=True, minutos_dictado_mes=minutos, **plan)
        self.tenant.plan = plan
        self.tenant.save(update_fields=['plan'])

    def subir(self, segundos=120, **extra):
        return self.cliente.post('/dictado/', {'audio': audio(), 'segundos': segundos, 'consentimiento': '1',
                                                'paciente': self.p.pk, 'plantilla': self.plantilla.pk, **extra})

    def test_inactivo_o_sin_consentimiento_no_dicta(self):
        self.assertEqual(self.subir().status_code, 403)
        self.assertNotContains(self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/'), 'Dictar consulta')
        self.activar()
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/'), 'Dictar consulta')
        r = self.cliente.post('/dictado/', {'audio': audio(), 'segundos': 10, 'paciente': self.p.pk,
                                            'plantilla': self.plantilla.pk})
        self.assertEqual(r.status_code, 400)

    def test_minutos_del_plan_sin_excedente_bloquea(self):
        self.activar(minutos=3, precio_minuto_extra_usd=0)
        with mock.patch('apps.dictado.proveedores.en_prueba', return_value=True), \
             mock.patch('apps.dictado.audio._ffmpeg', return_value=None):
            self.assertEqual(self.subir(segundos=150).status_code, 200)
            self.assertEqual(self.subir(segundos=60).status_code, 403)          # 2.5 + 1 > 3

    def test_excedente_se_cobra_hasta_el_tope(self):
        from apps.dictado import servicios
        self.activar(minutos=3, tope_minutos_extra=2)                         # US$0.04 el minuto extra
        with mock.patch('apps.dictado.proveedores.en_prueba', return_value=True), \
             mock.patch('apps.dictado.audio._ffmpeg', return_value=None):
            self.assertEqual(self.subir(segundos=150).status_code, 200)
            self.assertEqual(self.subir(segundos=60).status_code, 200)          # 3.5 min: excedente
            u = servicios.uso(self.tenant)
            self.assertEqual((u['extra'], str(u['monto_extra']), u['en_excedente']), (1, '0.04', True))
            self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/'), 'excedente: 1 min')
            self.assertEqual(self.subir(segundos=120).status_code, 403)         # 5.5 > 3 + 2 de tope

    def test_esquema_y_llenado_validado(self):
        self.activar()
        resultado = proveedores.Resultado('texto dictado', json.loads(json.dumps(ENTRADA)), 9000, 1500,
                                          'gemini-3.8-flash', 'gemini-3.8-flash')
        with mock.patch('apps.dictado.proveedores.procesar_audio', return_value=resultado) as procesar:
            r = self.subir()
        self.assertEqual(r.json()['estado'], 'LISTO')
        sistema, herramienta = procesar.call_args[0][3], procesar.call_args[0][4]
        self.assertNotIn('Ana', sistema)                                       # sin nombre del paciente
        eco = herramienta['input_schema']['properties']['secciones']['properties']['cp.eco']['properties']
        self.assertIn('OS', eco['cia_tipo']['enum'])
        self.assertNotIn('texto_informe', eco)                                  # los calculados no se piden
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        campos = {(c['prefijo'], c['clave']): c['valor'] for c in j['resultado']['campos']}
        self.assertIn(94, campos.values())
        self.assertEqual(j['resultado']['tablas'][0]['filas'][0]['codigo'], 'Q21.1')
        self.assertIn('Holter', j['no_ubicado'])
        self.assertIn('NO_EXISTE', j['no_ubicado'])                            # opción inválida → a revisar
        self.assertIn('-50', j['no_ubicado'])                                  # fuera de rango → a revisar
        with self.en_tenant():
            s = SesionDictado.objects.get()
        self.assertEqual((s.tokens_entrada, s.modelo_ia), (9000, 'gemini-3.8-flash'))
        # al guardar la consulta, la sesión queda vinculada
        self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {
            'completa': '1', 'tipo': 'PRIMERA', 'plantilla': self.plantilla.pk, 'accion': 'guardar',
            'dictado': s.pk})
        with self.en_tenant():
            self.assertEqual(SesionDictado.objects.get().consulta, Consulta.objects.latest('id'))

    def test_error_del_proveedor_no_cuelga(self):
        self.activar()
        from apps.dictado.proveedores import ErrorProveedor
        with mock.patch('apps.dictado.proveedores.procesar_audio', side_effect=ErrorProveedor('sin saldo')):
            r = self.subir()
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        self.assertEqual((j['estado'], j['error']), ('ERROR', 'sin saldo'))
        self.assertEqual(servicios.minutos_usados(self.tenant), 0)              # un error no consume minutos

    def test_modo_prueba_sin_claves(self):
        self.activar()
        with self.settings(GEMINI_API_KEY=''):
            r = self.subir()
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        self.assertTrue(j['prueba'])
        self.assertIn('Modo de prueba', j['no_ubicado'])

    def test_procesar_fuera_del_request_sin_tenant_activo(self):
        """En producción corre en un hilo sin consultorio activo: debe encontrar la sesión igual."""
        self.activar()
        with self.en_tenant():
            s = SesionDictado.objects.create(paciente=self.p, profesional=self.titular.membresias.first().perfil,
                                             plantilla=self.plantilla, segundos=30, consentimiento=True)
            from apps.clinica.consultas import congelar_estructura
            estructura = congelar_estructura(self.plantilla)
        with self.settings(GEMINI_API_KEY=''):
            servicios.procesar(s.pk, b'audio', 'a.webm', 'audio/webm', estructura, 'cardiologia_pediatrica', 'Cardio')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'LISTO')


    def test_grabacion_del_telefono_se_convierte_y_mide(self):
        """«Si se va la luz»: la doctora graba con el teléfono (.m4a) y lo sube después; se cobra la duración real."""
        import os
        import subprocess
        import tempfile
        ffmpeg = conversor._ffmpeg()
        if not ffmpeg:
            self.skipTest('sin ffmpeg')
        # Carpeta temporal (no NamedTemporaryFile): en Windows un archivo abierto no lo puede escribir ffmpeg.
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'nota.m4a')
            subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=75', '-c:a', 'aac',
                            ruta], capture_output=True, check=True)
            with open(ruta, 'rb') as leido:
                datos = leido.read()
        mp3, tipo, segundos = conversor.convertir(datos, 'nota de voz.m4a', 'audio/x-m4a')
        self.assertEqual((tipo, segundos), ('audio/mp3', 75))
        self.assertLess(len(mp3), len(datos))
        self.activar()
        with self.settings(GEMINI_API_KEY=''):
            r = self.cliente.post('/dictado/', {
                'audio': SimpleUploadedFile('nota de voz.m4a', datos, content_type='audio/x-m4a'), 'segundos': 0,
                'origen': 'archivo', 'consentimiento': '1', 'paciente': self.p.pk, 'plantilla': self.plantilla.pk})
        with self.en_tenant():
            s = SesionDictado.objects.get(pk=r.json()['id'])
        self.assertEqual((s.origen, s.segundos), ('ARCHIVO', 75))           # el navegador no la supo: la mide ffmpeg
        self.assertEqual(self.cliente.post('/dictado/', {
            'audio': SimpleUploadedFile('foto.jpg', b'x', content_type='image/jpeg'), 'consentimiento': '1',
            'paciente': self.p.pk, 'plantilla': self.plantilla.pk}).status_code, 400)


class GeminiTest(SimpleTestCase):
    """Dictado en dos pasos (ADR-052): transcribir el audio y después ordenar el texto (sin salir a internet)."""

    def respuesta(self, datos, estado=200, texto=''):
        r = mock.Mock(status_code=estado, text=texto or json.dumps(datos))
        r.json.return_value = datos
        return r

    def con_texto(self, texto, **uso):
        return self.respuesta({'candidates': [{'content': {'parts': [{'text': 'pensando', 'thought': True},
                                                                       {'text': texto}]}}],
                               'usageMetadata': uso})

    def transcrito(self, texto='EKG frecuencia 94'):
        return self.con_texto(texto, promptTokenCount=2000, candidatesTokenCount=100,
                              promptTokensDetails=[{'modality': 'AUDIO', 'tokenCount': 1920}])

    def ordenado(self, secciones=None):
        datos = [{'campo': f'{codigo}.{clave}', 'valor': str(valor)}
                 for codigo, campos in (secciones or {}).items() for clave, valor in campos.items()]
        return self.con_texto(json.dumps({'datos': datos, 'no_ubicado': ''}),
                              promptTokenCount=800, candidatesTokenCount=300, thoughtsTokenCount=200)

    @override_settings(GEMINI_API_KEY='clave', DICTADO_MODELO_GEMINI='gemini-3.8-flash', DICTADO_PROVEEDOR='gemini',
                       DICTADO_RAZONAMIENTO='low')
    def test_transcribe_sin_datos_del_paciente_y_ordena_el_texto(self):
        herramienta = servicios.herramienta([{'seccion_id': 7, 'codigo': 'cp.ekg', 'nombre': 'EKG', 'campos': [
            {'clave': 'fc', 'tipo': 'numero', 'etiqueta': 'FC', 'unidad': 'lpm'}]}])
        with mock.patch('apps.dictado.proveedores.requests.post',
                        side_effect=[self.transcrito(), self.ordenado({'cp.ekg': {'fc': 94}})]) as post:
            r = proveedores.procesar_audio(b'mp3', 'audio/mp3', 'TAPSE', 'sistema con paciente masculino', herramienta)
        paso1, paso2 = (json.loads(c.kwargs['data']) for c in post.call_args_list)
        self.assertIn('gemini-3.8-flash:generateContent', post.call_args.args[0])
        self.assertFalse(paso1['store'] or paso2['store'])                   # Google no guarda la conversación
        # paso 1: audio y nada del paciente ni del formulario
        self.assertEqual(paso1['contents'][0]['parts'][0]['inline_data']['mime_type'], 'audio/mp3')
        self.assertNotIn('masculino', json.dumps(paso1))
        self.assertNotIn('response_json_schema', paso1['generation_config'])
        # paso 2: el texto transcrito (no el audio) con el esquema y razonamiento bajo
        self.assertIn('EKG frecuencia 94', paso2['contents'][0]['parts'][0]['text'])
        self.assertNotIn('inline_data', json.dumps(paso2))
        self.assertEqual(paso2['generation_config']['thinking_config'], {'thinking_level': 'low'})
        # lista plana de {campo, valor} con catálogo (no el formulario anidado)
        self.assertEqual(paso2['generation_config']['response_json_schema']['properties']['datos']['items']
                         ['properties']['campo']['enum'], ['cp.ekg.fc'])
        self.assertIn('cp.ekg.fc (número): FC', paso2['system_instruction']['parts'][0]['text'])
        self.assertEqual(r.entrada['secciones']['cp.ekg']['fc'], '94')
        self.assertEqual((r.transcripcion, r.tokens_entrada, r.tokens_salida, r.segundos_audio),
                         ('EKG frecuencia 94', 2800, 600, 60))

    def test_la_lista_se_reparte_en_las_secciones(self):
        estructura = [{'seccion_id': 3, 'codigo': 'cp.antecedentes', 'nombre': 'Antecedentes', 'campos': [
            {'clave': 'edad_madre', 'tipo': 'numero', 'etiqueta': 'Edad de la madre', 'min': 10, 'max': 60},
            {'clave': 'via_parto', 'tipo': 'opcion', 'etiqueta': 'Vía', 'opciones': [['EUTOCICO', 'Parto eutócico'],
                                                                                    ['CESAREA', 'Cesárea']]},
            {'clave': 'asma', 'tipo': 'si_no', 'etiqueta': 'Asma'},
            {'clave': 'alergias', 'tipo': 'texto', 'etiqueta': 'Alergias'}]},
            {'seccion_id': 9, 'codigo': 'nucleo.diagnosticos', 'nombre': 'Diagnósticos', 'campos': [
                {'clave': 'diagnosticos', 'tipo': 'tabla', 'etiqueta': 'Diagnósticos', 'subcampos': [
                    {'clave': 'codigo', 'etiqueta': 'Código'}, {'clave': 'descripcion', 'etiqueta': 'Descripción'}]}]}]
        _, _, tipos = proveedores.catalogo(servicios.herramienta(estructura))
        datos = [{'campo': 'cp.antecedentes.edad_madre', 'valor': '23'},
                 {'campo': 'cp.antecedentes.via_parto', 'valor': 'EUTOCICO'},
                 {'campo': 'cp.antecedentes.asma', 'valor': 'si'},
                 {'campo': 'cp.antecedentes.alergias', 'valor': 'Acetaminofén.'},
                 {'campo': 'cp.antecedentes.alergias', 'valor': 'Penicilina.'},
                 {'campo': 'nucleo.diagnosticos.diagnosticos', 'valor': 'Taquicardia supraventricular'},
                 {'campo': 'cp.inventado.x', 'valor': '1'}]
        secciones = proveedores.a_secciones(datos, tipos)
        resultado, avisos = servicios.validar({'secciones': secciones}, estructura)
        valores = {c['clave']: c['valor'] for c in resultado['campos']}
        self.assertEqual(valores, {'edad_madre': 23, 'via_parto': 'EUTOCICO', 'asma': True,
                                   'alergias': 'Acetaminofén. Penicilina.'})
        self.assertEqual(resultado['tablas'][0]['filas'], [{'descripcion': 'Taquicardia supraventricular'}])
        self.assertEqual(avisos, [])

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_sin_voz_no_ordena_ni_inventa(self):
        with mock.patch('apps.dictado.proveedores.requests.post', side_effect=[self.transcrito('[SIN VOZ]')]) as post, \
             self.assertRaisesMessage(proveedores.ErrorProveedor, 'No se entendió voz'):
            proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', servicios.herramienta([]))
        self.assertEqual(post.call_count, 1)                                  # el paso 2 no se llama

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_si_no_admite_json_schema_usa_el_esquema_openapi(self):
        malo = self.respuesta({}, 400, 'Unknown name "response_json_schema": schema not supported')
        with mock.patch('apps.dictado.proveedores.requests.post',
                        side_effect=[self.transcrito(), malo, self.ordenado()]) as post:
            proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', servicios.herramienta([]))
        ultimo = json.loads(post.call_args.kwargs['data'])['generation_config']
        self.assertIn('response_schema', ultimo)
        self.assertNotIn('additionalProperties', json.dumps(ultimo))

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_reintenta_si_no_responde(self):
        import requests
        with mock.patch('apps.dictado.proveedores.requests.post',
                        side_effect=[requests.ReadTimeout('lento'), self.transcrito(), self.ordenado()]) as post, \
             mock.patch('apps.dictado.proveedores.time.sleep'):
            r = proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', servicios.herramienta([]))
        self.assertEqual((post.call_count, r.transcripcion), (3, 'EKG frecuencia 94'))
        self.assertEqual(post.call_args.kwargs['timeout'], proveedores.TIMEOUT_GEMINI)

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_dos_veces_sin_respuesta_avisa_que_se_puede_reenviar(self):
        import requests
        with mock.patch('apps.dictado.proveedores.requests.post', side_effect=requests.ReadTimeout('lento')), \
             mock.patch('apps.dictado.proveedores.time.sleep'), \
             self.assertRaisesMessage(proveedores.ErrorProveedor, 'Enviar ahora'):
            proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', servicios.herramienta([]))

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_modelo_sin_razonamiento_configurable_se_llama_sin_el(self):
        malo = self.respuesta({}, 400, 'Invalid JSON payload: unknown field thinking_level')
        with mock.patch('apps.dictado.proveedores.requests.post', side_effect=[malo, self.transcrito(), self.ordenado()]) \
                as post:
            proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', servicios.herramienta([]))
        self.assertNotIn('thinking_config', json.loads(post.call_args_list[1].kwargs['data'])['generation_config'])

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_audio_grande_va_por_files_api_y_se_borra(self):
        inicio = mock.Mock(status_code=200, headers={'x-goog-upload-url': 'https://subida'})
        subida = self.respuesta({'file': {'name': 'files/abc', 'uri': 'https://archivo', 'state': 'ACTIVE'}})
        with mock.patch('apps.dictado.proveedores.requests.post',
                        side_effect=[inicio, subida, self.transcrito(), self.ordenado()]) as post, \
             mock.patch('apps.dictado.proveedores.requests.delete') as borrar:
            proveedores.procesar_audio(b'0' * (proveedores.MAX_INLINE + 1), 'audio/mp3', '', 's', servicios.herramienta([]))
        cuerpo = json.loads(post.call_args_list[2].kwargs['data'])
        self.assertEqual(cuerpo['contents'][0]['parts'][0]['file_data']['file_uri'], 'https://archivo')
        self.assertIn('files/abc', borrar.call_args.args[0])                  # no queda en Google


@override_settings(DICTADO_SINCRONO=True)
class SilencioEnSesionTest(BaseTest):
    def test_grabacion_en_silencio_no_llega_a_la_ia_ni_se_cobra(self):
        if not conversor._ffmpeg():
            self.skipTest('sin ffmpeg')
        tenant, _ = crear_consultorio('Cardio', 'cardio3', especialidad='cardiologia_pediatrica')
        cliente = self.entrar(tenant, 'titular')
        ConfiguracionTenant.objects.filter(tenant=tenant).update(dictado_activo=True)
        with self.en_tenant(tenant):
            p = Paciente.objects.create(nombres='Ana', apellidos='Ruiz', sexo='F')
            plantilla = PlantillaHistoria.objects.get(nombre='Consulta de cardiología pediátrica')
        mudo = SilencioTest().generar('anullsrc=r=48000:cl=mono:d=4')
        with mock.patch('apps.dictado.proveedores.procesar_audio') as ia:
            r = cliente.post('/dictado/', {'audio': SimpleUploadedFile('g.webm', mudo, content_type='audio/webm'),
                                           'segundos': 4, 'consentimiento': '1', 'paciente': p.pk,
                                           'plantilla': plantilla.pk})
        ia.assert_not_called()
        with self.en_tenant(tenant):
            s = SesionDictado.objects.get(pk=r.json()['id'])
        self.assertEqual((s.estado, s.segundos), ('ERROR', 0))
        self.assertIn('No se escuchó voz', s.error)


class SilencioTest(SimpleTestCase):
    """Una grabación sin voz (micrófono equivocado) se rechaza antes de llamar a la IA."""

    def generar(self, filtro):
        import os
        import subprocess
        import tempfile
        ffmpeg = conversor._ffmpeg()
        if not ffmpeg:
            self.skipTest('sin ffmpeg')
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'g.webm')
            subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', filtro, '-c:a', 'libopus', ruta],
                           capture_output=True, check=True)
            with open(ruta, 'rb') as f:
                return f.read()

    def test_mide_el_volumen(self):
        _, _, segundos, pico = conversor.convertir_y_medir(self.generar('anullsrc=r=48000:cl=mono:d=5'), 'g.webm')
        self.assertTrue(conversor.es_silencio(pico))
        _, _, _, pico = conversor.convertir_y_medir(self.generar('sine=frequency=300:duration=5'), 'g.webm')
        self.assertFalse(conversor.es_silencio(pico))
        self.assertFalse(conversor.es_silencio(None))                         # sin ffmpeg no se bloquea
