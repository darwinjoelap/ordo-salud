"""Fase 13.2: módulo de pediatría (plantillas, ficha pediátrica, antropometría con percentiles OMS)."""
from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.clinica.consultas import datos_guardados
from apps.clinica.models import (
    Consulta,
    PlantillaHistoria,
    PlantillaSeccion,
    RegistroSeccionPaciente,
    SeccionClinica,
    SignosVitales,
)
from apps.clinica.servicios import sincronizar_catalogo
from apps.especialidades.pediatria import oms
from apps.especialidades.pediatria.models import MedicionCrecimiento, VacunaAplicada
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class PediatriaTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Pediatra', 'pediatra', especialidad='pediatria')
        self.cliente = self.entrar(self.tenant, 'titular')
        self.nacimiento = timezone.localdate() - timedelta(days=730)          # ≈ 24 meses
        with self.en_tenant():
            self.nino = Paciente.objects.create(nombres='Mateo', apellidos='Rondón', sexo='M',
                                                fecha_nacimiento=self.nacimiento)
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}

    def abrir(self, paciente=None, plantilla=None):
        datos = {'tipo': 'PRIMERA'}
        if plantilla:
            with self.en_tenant():
                datos['plantilla'] = PlantillaHistoria.objects.get(nombre=plantilla).pk
        r = self.iniciar_independiente(paciente or self.nino, datos)
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            return Consulta.objects.latest('id')

    def campo(self, codigo, clave):
        return f's{self.s[codigo]}-{clave}'

    def test_plantillas_pediatricas_y_predeterminada(self):
        with self.en_tenant():
            nombres = set(PlantillaHistoria.objects.filter(activa=True).values_list('nombre', flat=True))
            self.assertEqual(nombres, {'Consulta pediátrica', 'Primera consulta con ficha completa',
                                       'Control de niño sano'})
        c = self.abrir()
        codigos = [i['codigo'] for i in c.estructura]
        self.assertEqual(codigos[:4], ['ped.tipo', 'ped.antropometria', 'nucleo.signos_vitales', 'nucleo.motivo'])
        self.assertIn('ped.perinatales', codigos)             # historia completa en una pantalla (2026-10-22)
        self.assertEqual(codigos[-2:], ['ped.habitos', 'ped.vacunas_pendientes'])
        signos = next(i for i in c.estructura if i['codigo'] == 'nucleo.signos_vitales')
        self.assertNotIn('peso_kg', [x['clave'] for x in signos['campos']])     # el peso va en antropometría

    def test_texto_libre_de_patologicos_y_vacunas_pendientes(self):
        otros = self.campo('ped.patologicos', 'otros')
        vacunas = self.campo('ped.vacunas_pendientes', 'notas')
        consulta = self.abrir()
        editar = f'/consultas/{consulta.pk}/editar/'
        formulario = self.cliente.get(editar)
        for campo in (otros, vacunas):
            self.assertContains(formulario, f'name="{campo}"')
        nota = 'Pendiente verificar el carné.\nConsultar fecha en el próximo control.'
        respuesta = self.cliente.post(editar, {otros: 'Antecedente descrito por la familia.', vacunas: nota})
        self.assertEqual(respuesta.status_code, 302)
        self.assertContains(self.cliente.get(f'/consultas/{consulta.pk}/'), 'Pendiente verificar el carné.')
        siguiente = self.abrir()
        with self.en_tenant():
            datos = datos_guardados(siguiente)
            self.assertEqual(datos[self.s['ped.patologicos']]['otros'], 'Antecedente descrito por la familia.')
            self.assertNotIn(self.s['ped.vacunas_pendientes'], datos)
            self.assertEqual(datos_guardados(consulta)[self.s['ped.vacunas_pendientes']]['notas'], nota)
            self.assertFalse(VacunaAplicada.objects.filter(paciente=self.nino).exists())

    def test_borrador_con_esquema_anterior_conserva_otros_en_la_ficha(self):
        with self.en_tenant():
            seccion = SeccionClinica.objects.get(codigo='ped.patologicos')
            esquema_v1 = {'campos': [c for c in seccion.campos if c['clave'] != 'otros']}
            SeccionClinica.objects.filter(pk=seccion.pk).update(version=1, esquema=esquema_v1)
        anterior = self.abrir()
        sincronizar_catalogo(verbosidad=0)
        actual = self.abrir()
        datos = {self.campo('ped.patologicos', 'traumatismos'): 'si'}
        self.cliente.post(f'/consultas/{actual.pk}/editar/', {**datos, self.campo('ped.patologicos', 'otros'): 'Nota nueva'})
        self.cliente.post(f'/consultas/{anterior.pk}/editar/', {
            **datos, self.campo('ped.patologicos', 'traumatismos_detalle'): 'Detalle anterior corregido',
        })
        with self.en_tenant():
            ficha = RegistroSeccionPaciente.objects.get(paciente=self.nino, seccion=seccion, vigente=True)
            self.assertEqual(ficha.version_seccion, 2)
            self.assertEqual(ficha.datos['otros'], 'Nota nueva')
            self.assertEqual(ficha.datos['traumatismos_detalle'], 'Detalle anterior corregido')
            self.assertNotIn('otros', anterior.registros.get(seccion=seccion).datos)
            self.assertEqual(seccion.versiones.get(version=1).esquema, esquema_v1)

    def test_inicio_desde_formulario_anterior_conserva_otros_si_no_envia_el_campo(self):
        otros = self.campo('ped.patologicos', 'otros')
        traumatismos = self.campo('ped.patologicos', 'traumatismos')
        consulta = self.abrir()
        self.cliente.post(f'/consultas/{consulta.pk}/editar/', {otros: 'Nota de ficha', traumatismos: 'si'})
        self.iniciar_independiente(self.nino, {'completa': '1', 'accion': 'guardar'})
        with self.en_tenant():
            ficha = RegistroSeccionPaciente.objects.get(paciente=self.nino, seccion_id=self.s['ped.patologicos'],
                                                        vigente=True)
            self.assertEqual(ficha.datos, {'traumatismos': True, 'otros': 'Nota de ficha'})
        r = self.iniciar_independiente(self.nino, {'completa': '1', 'accion': 'guardar', traumatismos: 'no'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            ficha = RegistroSeccionPaciente.objects.get(paciente=self.nino, seccion_id=self.s['ped.patologicos'],
                                                        vigente=True)
            self.assertEqual(ficha.datos, {'traumatismos': False, 'otros': 'Nota de ficha'})
            actual = Consulta.objects.latest('id')
        self.cliente.post(f'/consultas/{actual.pk}/editar/', {otros: '', traumatismos: 'no'})
        ficha.refresh_from_db()
        self.assertFalse(ficha.vigente)
        with self.en_tenant():
            self.assertEqual(RegistroSeccionPaciente.objects.get(
                paciente=self.nino, seccion_id=self.s['ped.patologicos'], vigente=True,
            ).datos, {'traumatismos': False})

    def test_migracion_agrega_vacunas_pendientes_a_plantilla_personalizada_sin_reordenar(self):
        nombre = '0004_vacunas_pendientes'
        migracion = import_module(f'apps.especialidades.pediatria.migrations.{nombre}')
        historicos = MigrationExecutor(connection).loader.project_state([('esp_pediatria', nombre)]).apps
        with self.en_tenant():
            especialidad = PlantillaHistoria.objects.first().especialidad
            plantilla = PlantillaHistoria.objects.create(nombre='Consulta propia', especialidad=especialidad)
            seccion = SeccionClinica.objects.get(codigo='ped.patologicos')
            item = PlantillaSeccion.objects.create(plantilla=plantilla, seccion=seccion, orden=70, colapsada=True)
            for _ in range(2):
                migracion.agregar_seccion(historicos, SimpleNamespace(connection=connection))
            item.refresh_from_db()
            self.assertEqual((item.orden, item.colapsada), (70, True))
            nueva = plantilla.items.get(seccion__codigo='ped.vacunas_pendientes')
            self.assertEqual((nueva.orden, nueva.obligatoria, nueva.tenant_id), (80, False, self.tenant.pk))
            self.assertEqual(plantilla.items.count(), 2)

    def test_antropometria_calcula_percentiles_y_guarda_medicion(self):
        c = self.abrir(plantilla='Primera consulta con ficha completa')
        r = self.cliente.post(f'/consultas/{c.pk}/editar/', {
            self.campo('nucleo.motivo', 'motivo'): 'Control',
            self.campo('nucleo.signos_vitales', 'fc'): '110',
            self.campo('ped.antropometria', 'peso_kg'): '10,0',
            self.campo('ped.antropometria', 'talla_cm'): '82',
            self.campo('ped.antropometria', 'pc_cm'): '47,5',
            self.campo('ped.perinatales', 'peso_nacer_g'): '3200',
            self.campo('ped.familiares', 'antecedentes'): ['ASMA_ATOPIA', 'DIABETES'],
        })
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            datos = datos_guardados(Consulta.objects.get(pk=c.pk))[self.s['ped.antropometria']]
            m = MedicionCrecimiento.objects.get(consulta=c)
            esperado = oms.percentil(oms.zscore('peso', 'M', oms.edad_en_meses(self.nacimiento, m.fecha), 10.0))
            self.assertAlmostEqual(datos['percentil_peso'], esperado, delta=0.06)
            self.assertEqual(m.estado_nutricional, 'Desnutrición (p3–p10)')
            self.assertEqual(datos['estado_nutricional'], 'Desnutrición (p3–p10)')
            self.assertIsNotNone(m.p_pc)
            self.assertEqual(m.peso_kg, Decimal('10.000'))
            signos = SignosVitales.objects.get(consulta=c)
            self.assertEqual((signos.fc, signos.peso_kg), (110, Decimal('10.00')))      # FC del núcleo + peso
            ficha = RegistroSeccionPaciente.objects.get(paciente=self.nino, seccion_id=self.s['ped.familiares'])
            self.assertEqual(sorted(ficha.datos['antecedentes']), ['ASMA_ATOPIA', 'DIABETES'])
        # la ficha pasa llena a la consulta siguiente
        c2 = self.abrir(plantilla='Primera consulta con ficha completa')
        with self.en_tenant():
            self.assertEqual(datos_guardados(c2)[self.s['ped.perinatales']]['peso_nacer_g'], 3200)

    def test_sin_sexo_no_hay_percentiles(self):
        with self.en_tenant():
            sin_sexo = Paciente.objects.create(nombres='Luz', apellidos='Mar', sexo='',
                                               fecha_nacimiento=date(2025, 1, 1))
        c = self.abrir(sin_sexo)
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('nucleo.motivo', 'motivo'): 'Control',
                                                         self.campo('ped.antropometria', 'peso_kg'): '8'})
        with self.en_tenant():
            m = MedicionCrecimiento.objects.get(consulta=c)
            self.assertIsNone(m.p_peso)
            self.assertEqual(m.estado_nutricional, '')
            self.assertNotIn('percentil_peso', datos_guardados(c)[self.s['ped.antropometria']])

    def test_vaciar_antropometria_borra_la_medicion(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('nucleo.motivo', 'motivo'): 'x',
                                                         self.campo('ped.antropometria', 'peso_kg'): '11'})
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('nucleo.motivo', 'motivo'): 'x'})
        with self.en_tenant():
            self.assertFalse(MedicionCrecimiento.objects.exists())

    def test_aislamiento_de_mediciones(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('nucleo.motivo', 'motivo'): 'x',
                                                         self.campo('ped.antropometria', 'peso_kg'): '11'})
        otro, _ = crear_consultorio('Otro', 'otro-ped', especialidad='pediatria', usuario='otro')
        with self.en_tenant(otro):
            self.assertFalse(MedicionCrecimiento.objects.exists())

    def test_ficha_pediatrica_fuera_de_la_consulta(self):
        url = f'/pacientes/{self.nino.pk}/ficha/pediatria/'
        r = self.cliente.get(url)
        self.assertContains(r, 'Antecedentes prenatales')
        r = self.cliente.post(url, {f's{self.s["ped.perinatales"]}-semanas_gestacion': '38',
                                    f's{self.s["ped.perinatales"]}-via_parto': 'CESAREA',
                                    f's{self.s["ped.perinatales"]}-indicacion_cesarea': 'Podálico'})
        self.assertRedirects(r, f'/pacientes/{self.nino.pk}/', fetch_redirect_response=False)
        r = self.cliente.get(f'/pacientes/{self.nino.pk}/')
        self.assertContains(r, 'Ficha de pediatría')
        self.assertContains(r, 'Podálico')
        c = self.abrir(plantilla='Primera consulta con ficha completa')       # y aparece en la consulta
        with self.en_tenant():
            self.assertEqual(datos_guardados(c)[self.s['ped.perinatales']]['semanas_gestacion'], 38)
