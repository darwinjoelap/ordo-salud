"""Fases 03–06: configuración, tasa, servicios, pacientes y motor de historia."""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.clinica import esquemas
from apps.clinica import servicios as clinica
from apps.clinica.formularios import FormularioSeccion
from apps.clinica.models import PlantillaHistoria, PlantillaSeccion, SeccionClinica
from apps.cobros.models import Servicio
from apps.core.excepciones import ErrorDeNegocio
from apps.pacientes import servicios as pacientes
from apps.pacientes.models import Paciente, Representante
from apps.tasas import servicios as tasas
from apps.tasas.models import TasaCambio

from .base import BaseTest


def png(nombre='firma.png'):
    buffer = BytesIO()
    Image.new('RGBA', (120, 60), (0, 0, 0, 0)).save(buffer, 'PNG')
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type='image/png')


class ConfiguracionTest(BaseTest):
    def test_guardar_configuracion_y_pdf_de_prueba(self):
        r = self.cliente.post('/configuracion/', {
            'tab': 'identidad', 'nombre_mostrar': 'Consultorio Pérez', 'color_primario': '#2AACA8',
            'visibilidad_historia': 'PRIVADA', 'horas_edicion_consulta': 12, 'duracion_cita_min': 20,
            'logo': png('logo.png')})
        self.assertEqual(r.status_code, 302)
        self.tenant.configuracion.refresh_from_db()
        self.assertEqual(self.tenant.configuracion.visibilidad_historia, 'PRIVADA')
        self.assertTrue(self.tenant.configuracion.logo_pdf)
        r = self.cliente.get('/configuracion/pdf-prueba/')
        self.assertEqual(r['Content-Type'], 'application/pdf')

    def test_perfil_profesional_con_firma(self):
        r = self.cliente.post('/equipo/mi-perfil-profesional/', {
            'titulo': 'Dra.', 'numero_mpps': '12345', 'numero_colegio': 'CMEL 999', 'color_agenda': '#0F6E8C',
            'firma': png(), 'sello': png('sello.png')})
        self.assertEqual(r.status_code, 302)
        from apps.equipo.models import PerfilProfesional
        perfil = PerfilProfesional.todos.get(membresia__usuario=self.titular)
        self.assertTrue(perfil.tiene_firma)
        self.assertEqual(perfil.registros_texto, 'MPPS 12345 · CMEL 999')
        self.assertEqual(self.cliente.get('/configuracion/pdf-prueba/').status_code, 200)

    def test_lugares(self):
        self.cliente.post('/configuracion/lugares/', {'nombre': 'Clínica Norte', 'orden': 0, 'activo': 'on'})
        r = self.cliente.post('/configuracion/lugares/', {'nombre': 'clínica norte', 'orden': 0, 'activo': 'on'})
        self.assertContains(r, 'Ya hay un lugar')


class TasaYServiciosTest(BaseTest):
    def test_tasa_del_tenant_gana_el_mismo_dia(self):
        hoy = timezone.localdate()
        tasas.registrar(Decimal('100'), TasaCambio.Fuente.BCV, fecha=hoy)
        self.cliente.post('/tasa/', {'valor': '101,5'})
        self.assertEqual(tasas.tasa_vigente(self.tenant).bs_por_usd, Decimal('101.5000'))
        tasas.registrar(Decimal('102'), TasaCambio.Fuente.BCV, fecha=hoy + timedelta(days=1))
        self.assertEqual(tasas.tasa_vigente(self.tenant).bs_por_usd, Decimal('102'))

    def test_leer_tasa_html_bcv(self):
        html = '<div id="dolar"><strong> 203,74080000 </strong></div>'
        self.assertEqual(tasas.leer_tasa_html(html), Decimal('203.7408'))

    def test_servicio_con_precio_en_bs(self):
        tasas.registrar(Decimal('200'), TasaCambio.Fuente.BCV)
        self.cliente.post('/cobros/servicios/', {'nombre': 'Consulta', 'precio_usd': '40', 'activo': 'on'})
        with self.en_tenant():
            self.assertEqual(Servicio.objects.get().precio_usd, Decimal('40'))
        self.assertContains(self.cliente.get('/cobros/servicios/'), 'Bs 8.000,00')


class PacientesTest(BaseTest):
    def datos(self, **extra):
        base = {'nombres': 'María', 'apellidos': 'Gómez', 'sexo': 'F', 'fecha_nacimiento': '1990-05-10',
                'tipo_documento': 'V', 'numero_documento': '12.345.678', 'telefono': '0414-123 45 67'}
        base.update(extra)
        return base

    def test_crear_y_buscar_sin_acentos(self):
        r = self.cliente.post('/pacientes/nuevo/', self.datos(alergias='Penicilina'))
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            p = Paciente.objects.get()
            self.assertEqual(p.telefono, '04141234567')
            self.assertEqual(p.antecedentes.alergias, 'Penicilina')
        self.assertContains(self.cliente.get('/pacientes/?q=maria gomez'), 'Gómez')
        self.assertContains(self.cliente.get('/pacientes/?q=12345678'), 'Gómez')
        self.assertContains(self.cliente.get(f'/pacientes/{p.pk}/'), 'Penicilina')

    def test_duplicado_por_documento_avisa_y_enlaza(self):
        self.cliente.post('/pacientes/nuevo/', self.datos())
        r = self.cliente.post('/pacientes/nuevo/', self.datos(nombres='Otra', numero_documento='V12345678'))
        self.assertContains(r, 'Abrir su ficha')
        with self.en_tenant():
            self.assertEqual(Paciente.objects.count(), 1)

    def test_menor_sin_documento_ni_representante_se_registra_con_aviso(self):
        hace_3 = (timezone.localdate() - timedelta(days=365 * 3)).isoformat()
        r = self.cliente.post('/pacientes/nuevo/', self.datos(fecha_nacimiento=hace_3, tipo_documento='V',
                                                              numero_documento='', sexo=''), follow=True)
        self.assertContains(r, 'conviene registrarlo')
        with self.en_tenant():
            p = Paciente.objects.get()
            self.assertEqual((p.tipo_documento, p.sexo), ('N', ''))
        r = self.cliente.post('/pacientes/nuevo/', self.datos(
            nombres='Luz', fecha_nacimiento=hace_3, tipo_documento='N', numero_documento='', **{
                'rep-nombre': 'Carla Gómez', 'rep-parentesco': 'MADRE', 'rep-tipo_documento': 'V',
                'rep-numero_documento': '15000111'}))
        self.assertEqual(r.status_code, 302)

    def test_hermanos_con_el_mismo_representante(self):
        with self.en_tenant():
            for nombre, nacimiento in (('Pedro', date(2022, 1, 1)), ('Pablo', date(2024, 6, 1))):
                p = Paciente(nombres=nombre, apellidos='Gil', sexo='M', fecha_nacimiento=nacimiento,
                             tipo_documento='N')
                rep = Representante(nombre='Laura Gil', numero_documento='14000222')
                pacientes.crear_paciente(paciente=p, representante=rep)
            self.assertEqual(Paciente.objects.count(), 2)

    def test_sin_documento_mismo_nombre_y_fecha_es_duplicado(self):
        with self.en_tenant():
            rep = lambda: Representante(nombre='Laura Gil', numero_documento='14000222')  # noqa: E731
            pacientes.crear_paciente(paciente=Paciente(nombres='Pedro', apellidos='Gil', sexo='M',
                                                       fecha_nacimiento=date(2022, 1, 1), tipo_documento='N'),
                                     representante=rep())
            with self.assertRaises(pacientes.PacienteDuplicado):
                pacientes.crear_paciente(paciente=Paciente(nombres='pedro', apellidos='gil', sexo='M',
                                                           fecha_nacimiento=date(2022, 1, 1), tipo_documento='N'),
                                         representante=rep())

    def test_auditoria_al_ver_la_ficha(self):
        self.cliente.post('/pacientes/nuevo/', self.datos())
        with self.en_tenant():
            from apps.core.models import Auditoria
            p = Paciente.objects.get()
            self.cliente.get(f'/pacientes/{p.pk}/')
            self.assertTrue(Auditoria.objects.filter(accion='VER', paciente_id=p.pk).exists())


class EsquemasTest(BaseTest):
    ESQUEMA = {'campos': [
        {'clave': 'peso_kg', 'tipo': 'numero', 'etiqueta': 'Peso', 'min': 1, 'max': 300, 'decimales': 1},
        {'clave': 'talla_cm', 'tipo': 'numero', 'etiqueta': 'Talla', 'decimales': 0},
        {'clave': 'imc', 'tipo': 'calculado', 'etiqueta': 'IMC', 'funcion': 'nucleo.imc'},
        {'clave': 'fuma', 'tipo': 'si_no', 'etiqueta': 'Fuma', 'requerido': True},
        {'clave': 'cuantos', 'tipo': 'numero', 'etiqueta': 'Cuántos', 'decimales': 0,
         'visible_si': {'campo': 'fuma', 'igual': True}},
        {'clave': 'dolor', 'tipo': 'escala', 'etiqueta': 'Dolor', 'min': 0, 'max': 10},
        {'clave': 'meds', 'tipo': 'tabla', 'etiqueta': 'Medicamentos',
         'subcampos': [{'clave': 'nombre', 'tipo': 'texto'}, {'clave': 'dosis', 'tipo': 'texto'}]},
    ]}

    def test_esquemas_registrados_son_validos(self):
        from apps.clinica import registro
        for codigo, s in registro.secciones().items():
            self.assertEqual(esquemas.validar_esquema(s.esquema), [], codigo)

    def test_esquema_invalido(self):
        errores = esquemas.validar_esquema({'campos': [{'clave': 'A b', 'tipo': 'raro'}]})
        self.assertTrue(errores)

    def test_validar_datos_calcula_y_descarta_ocultos(self):
        limpios, errores = esquemas.validar_datos(self.ESQUEMA['campos'], {
            'peso_kg': '70,25', 'talla_cm': '175', 'fuma': 'no', 'cuantos': '10', 'dolor': '4',
            'meds': [{'nombre': 'Losartán 50 mg', 'dosis': '1 tab'}, {'nombre': '', 'dosis': ''}]})
        self.assertEqual(errores, {})
        self.assertEqual(limpios['peso_kg'], 70.3)
        self.assertEqual(limpios['imc'], 23.0)
        self.assertNotIn('cuantos', limpios)          # oculto porque no fuma
        self.assertEqual(len(limpios['meds']), 1)

    def test_requerido_y_rangos(self):
        _, errores = esquemas.validar_datos(self.ESQUEMA['campos'], {'peso_kg': '500', 'dolor': '11'})
        self.assertIn('fuma', errores)
        self.assertIn('peso_kg', errores)
        self.assertIn('dolor', errores)

    def test_formulario_de_seccion(self):
        form = FormularioSeccion(self.ESQUEMA['campos'], {
            's-peso_kg': '80', 's-talla_cm': '180', 's-fuma': 'si', 's-cuantos': '5',
            's-meds__0__nombre': 'Aspirina', 's-meds__0__dosis': '100 mg', 's-meds__3__nombre': 'Extra'},
            prefix='s')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.datos_limpios['cuantos'], 5)
        self.assertEqual([m['nombre'] for m in form.datos_limpios['meds']], ['Aspirina', 'Extra'])
        self.assertEqual(esquemas.texto_valor(self.ESQUEMA['campos'][0], 1234.5), '1.234,5')


class PlantillasTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.plantilla = PlantillaHistoria.objects.get(es_predeterminada=True)

    def test_vista_previa_valida_sin_guardar(self):
        r = self.cliente.get(f'/plantillas/{self.plantilla.pk}/vista-previa/')
        self.assertContains(r, 'Signos vitales')
        with self.en_tenant():
            sv = SeccionClinica.objects.get(codigo='nucleo.signos_vitales')
        r = self.cliente.post(f'/plantillas/{self.plantilla.pk}/vista-previa/', {
            f's{sv.pk}-peso_kg': '60', f's{sv.pk}-talla_cm': '160'})
        self.assertContains(r, 'IMC')
        self.assertContains(r, '23,4')

    def test_reordenar_quitar_y_agregar(self):
        with self.en_tenant():
            items = list(self.plantilla.items.order_by('orden'))
            segundo = items[1]
        self.cliente.post(f'/plantillas/{self.plantilla.pk}/accion/', {'accion': 'subir', 'item': segundo.pk})
        with self.en_tenant():
            self.assertEqual(self.plantilla.items.order_by('orden').first().pk, segundo.pk)
        self.cliente.post(f'/plantillas/{self.plantilla.pk}/accion/', {'accion': 'quitar', 'item': segundo.pk})
        self.cliente.post(f'/plantillas/{self.plantilla.pk}/accion/', {'accion': 'agregar',
                                                                     'seccion': segundo.seccion_id})
        with self.en_tenant():     # vuelve a su lugar natural (orden del catálogo), no al final
            orden = list(self.plantilla.items.order_by('orden').values_list('seccion_id', flat=True))
            self.assertEqual(orden.index(segundo.seccion_id), 1)

    def test_ajustes_ocultan_y_renombran(self):
        with self.en_tenant():
            item = self.plantilla.items.get(seccion__codigo='nucleo.examen_fisico')
        self.cliente.post(f'/plantillas/{self.plantilla.pk}/secciones/{item.pk}/', {
            'visible_general': 'on', 'etiqueta_general': 'Inspección general',
            'defecto_general': 'Buenas condiciones generales'})
        with self.en_tenant():
            item.refresh_from_db()
            campos = esquemas.campos_efectivos(item.seccion.esquema, item.ajustes)
        self.assertEqual([c['clave'] for c in campos], ['general'])
        self.assertEqual(campos[0]['etiqueta'], 'Inspección general')
        self.assertEqual(campos[0]['por_defecto'], 'Buenas condiciones generales')

    def test_plantilla_propia_partiendo_de_otra(self):
        r = self.cliente.post('/plantillas/nueva/', {'nombre': 'Mi control', 'especialidad':
                              self.plantilla.especialidad_id, 'copiar_de': self.plantilla.pk})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            nueva = PlantillaHistoria.objects.get(nombre='Mi control')
            self.assertIsNotNone(nueva.profesional)
            self.assertEqual(nueva.items.count(), self.plantilla.items.count())

    def test_seccion_de_especialidad_no_habilitada_no_se_agrega(self):
        with self.en_tenant():
            from apps.plataforma.models import Especialidad
            otra = SeccionClinica.objects.create(codigo='x.prueba', nombre='Prueba', tipo='MODULO',
                                                 especialidad=Especialidad.objects.get(codigo='cardiologia'),
                                                 esquema={'campos': []})
            with self.assertRaises(ErrorDeNegocio):
                clinica.agregar_seccion(self.plantilla, otra)


class SeccionesPersonalizadasTest(BaseTest):
    def formset(self, campos):
        datos = {'nombre': 'Pie diabético', 'ambito': 'CONSULTA', 'campos-TOTAL_FORMS': len(campos),
                 'campos-INITIAL_FORMS': 0, 'campos-MIN_NUM_FORMS': 1, 'campos-MAX_NUM_FORMS': 1000}
        for i, c in enumerate(campos):
            for k, v in c.items():
                datos[f'campos-{i}-{k}'] = v
            datos[f'campos-{i}-orden'] = i
        return datos

    def test_crear_editar_y_versionar(self):
        r = self.cliente.post('/secciones/nueva/', self.formset([
            {'etiqueta': 'Monofilamento', 'tipo': 'opcion', 'opciones': 'Normal\nAlterado', 'ancho': 6},
            {'etiqueta': 'Pulsos pedios', 'tipo': 'si_no', 'ancho': 6, 'requerido': 'on'},
        ]))
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            s = SeccionClinica.objects.get(tenant=self.tenant)
            self.assertEqual(s.codigo, 'per.pie_diabetico')
            self.assertEqual([c['clave'] for c in s.campos], ['monofilamento', 'pulsos_pedios'])
        datos = self.formset([
            {'clave': 'monofilamento', 'etiqueta': 'Monofilamento 10 g', 'tipo': 'opcion',
             'opciones': 'Normal\nAlterado', 'ancho': 6},
            {'etiqueta': 'Úlceras', 'tipo': 'texto_largo', 'ancho': 12},
        ])
        self.cliente.post(f'/secciones/{s.pk}/editar/', datos)
        with self.en_tenant():
            s.refresh_from_db()
            self.assertEqual(s.version, 2)
            self.assertEqual([c['clave'] for c in s.campos], ['monofilamento', 'ulceras'])
            self.assertEqual(s.esquema_version(1)['campos'][1]['clave'], 'pulsos_pedios')

    def test_seccion_personalizada_en_plantilla_y_aislada(self):
        self.cliente.post('/secciones/nueva/', self.formset([{'etiqueta': 'Escala de dolor', 'tipo': 'escala',
                                                              'minimo': 0, 'maximo': 10, 'ancho': 6}]))
        with self.en_tenant():
            s = SeccionClinica.objects.get(tenant=self.tenant)
            p = PlantillaHistoria.objects.get(es_predeterminada=True)
            clinica.agregar_seccion(p, s)
            self.assertTrue(PlantillaSeccion.objects.filter(plantilla=p, seccion=s).exists())
        from .base import crear_consultorio
        otro, _ = crear_consultorio('Otro', 'otro', usuario='otro')
        with self.en_tenant(otro):
            self.assertFalse(SeccionClinica.objects.visibles().filter(pk=s.pk).exists())


class ArmarHistoriaTest(BaseTest):
    """Plantillas con casillas: catálogo agrupado, marcar/desmarcar y «hacer mi copia»."""

    def test_marcar_desmarcar_y_copia(self):
        from apps.clinica.models import PlantillaHistoria
        with self.en_tenant():
            p = PlantillaHistoria.objects.filter(activa=True).first()
            examen = p.items.get(seccion__codigo='nucleo.examen_fisico')
        r = self.cliente.get(f'/plantillas/{p.pk}/')
        self.assertContains(r, 'Secciones disponibles')
        self.assertContains(r, 'role="switch"')
        self.cliente.post(f'/plantillas/{p.pk}/accion/', {'accion': 'quitar', 'item': examen.pk})
        with self.en_tenant():
            self.assertFalse(p.items.filter(seccion__codigo='nucleo.examen_fisico').exists())
        r = self.cliente.post(f'/plantillas/{p.pk}/copiar/')
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            copia = PlantillaHistoria.objects.get(nombre__endswith='(mía)')
            self.assertIsNotNone(copia.profesional_id)
            self.assertEqual(copia.items.count(), p.items.count())

