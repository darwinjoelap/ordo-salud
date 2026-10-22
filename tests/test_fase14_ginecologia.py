"""Fase 14: ginecología y obstetricia (perfil desde Ginea): ficha, control prenatal, paneles, documentos, reporte."""
from datetime import date, timedelta

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.clinica.models import Consulta, PlantillaHistoria, RegistroSeccionPaciente, SeccionClinica
from apps.documentos import servicios as dsrv
from apps.documentos.registro import documento
from apps.especialidades.ginecologia import obstetricia as ob
from apps.especialidades.ginecologia.models import ControlPrenatal
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class ObstetriciaTest(SimpleTestCase):
    def test_eg_y_fpp_por_fur(self):
        fur = date(2026, 3, 1)
        dias, metodo = ob.eg_dias({'fur': fur.isoformat()}, date(2026, 6, 1))
        self.assertEqual((dias, metodo), (92, 'FUR'))
        self.assertEqual(ob.texto_eg(dias), '13 sem 1 d')
        self.assertEqual(ob.fpp({'fur': '2026-03-01'}), date(2026, 12, 6))          # Naegele: FUR + 280 días
        self.assertEqual(ob.trimestre(dias), 1)

    def test_la_ecografia_manda_sobre_la_fur(self):
        datos = {'fur': '2026-03-01', 'eco_fecha': '2026-04-20', 'eco_semanas': 8, 'eco_dias': 2}
        dias, metodo = ob.eg_dias(datos, date(2026, 4, 20))
        self.assertEqual((dias, metodo), (58, 'ECO'))
        self.assertEqual(ob.fpp(datos), date(2026, 4, 20) + timedelta(days=280 - 58))

    def test_sin_datos_o_fuera_de_rango(self):
        self.assertEqual(ob.eg_dias({}, date.today()), (None, ''))
        self.assertEqual(ob.eg_dias({'fur': '2020-01-01'}, date(2026, 1, 1)), (None, ''))   # > 42 semanas

    def test_formula_obstetrica(self):
        self.assertEqual(ob.formula({'gestas': 3, 'partos': 1, 'cesareas': 1, 'abortos': 1}), 'G3 P1 C1 A1')
        self.assertEqual(ob.formula({'gestas': 2, 'ectopicos': 1}), 'G2 P0 C0 A0 E1')
        self.assertTrue(ob.formula_incongruente({'gestas': 1, 'partos': 1, 'abortos': 1}))
        self.assertEqual(ob.formula({}), '')


class GinecologiaTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Gineco', 'gineco', especialidad='ginecologia')
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='María', apellidos='Pérez', sexo='F',
                                             fecha_nacimiento=date(1994, 5, 10))
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}

    def campo(self, codigo, clave):
        return f's{self.s[codigo]}-{clave}'

    def abrir(self, plantilla=None):
        datos = {'tipo': 'PRIMERA'}
        if plantilla:
            with self.en_tenant():
                datos['plantilla'] = PlantillaHistoria.objects.get(nombre=plantilla).pk
        r = self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', datos)
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            return Consulta.objects.latest('id')

    def test_plantillas_igual_que_ginea(self):
        with self.en_tenant():
            nombres = set(PlantillaHistoria.objects.filter(activa=True).values_list('nombre', flat=True))
            self.assertEqual(nombres, {'Consulta ginecológica', 'Control prenatal',
                                       'Primera consulta con ficha completa'})
        c = self.abrir()
        codigos = [i['codigo'] for i in c.estructura]
        self.assertEqual(codigos[:5], ['go.tipo', 'nucleo.signos_vitales', 'nucleo.motivo', 'go.habitos',
                                       'go.familiares'])
        self.assertEqual(codigos[-2:], ['go.notas', 'go.prenatal'])
        self.assertNotIn('go.actualizar', codigos)               # ya no hace falta: la ficha está en la pantalla
        self.assertIn('go.gineco', codigos)                      # historia completa en una pantalla (2026-10-22)

    def test_control_prenatal_calcula_y_sigue_el_embarazo(self):
        fur = timezone.localdate() - timedelta(days=150)
        c = self.abrir('Control prenatal')
        r = self.cliente.post(f'/consultas/{c.pk}/editar/', {
            self.campo('go.tipo', 'tipo'): 'PRENATAL',
            self.campo('go.prenatal', 'fur'): fur.isoformat(),
            self.campo('go.prenatal', 'altura_uterina'): '20',
            self.campo('go.prenatal', 'fcf'): '145',
            self.campo('nucleo.signos_vitales', 'pa_sistolica'): '145',
            self.campo('nucleo.signos_vitales', 'pa_diastolica'): '95',
            self.campo('nucleo.motivo', 'motivo'): 'Control prenatal'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            control = ControlPrenatal.objects.get(consulta=c)
            self.assertEqual((control.eg_dias, control.metodo_eg), (150, 'FUR'))
            self.assertEqual(control.fpp, fur + timedelta(days=280))
            ficha = RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.gineco'], vigente=True)
            self.assertEqual(ficha.datos['fur'], fur.isoformat())           # la FUR pasa a la ficha
        detalle = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(detalle, 'Embarazo en curso')
        self.assertContains(detalle, '21 sem 3 d')
        self.assertContains(detalle, 'Tensión arterial ≥ 140/90')
        # la consulta siguiente abre con la FUR del embarazo en curso
        c2 = self.abrir('Control prenatal')
        form = self.cliente.get(f'/consultas/{c2.pk}/editar/')
        self.assertContains(form, f'value="{fur.isoformat()}"')

    def test_consulta_no_prenatal_no_crea_control(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('go.tipo', 'tipo'): 'GINECOLOGICA',
                                                         self.campo('nucleo.motivo', 'motivo'): 'Flujo'})
        with self.en_tenant():
            self.assertFalse(ControlPrenatal.objects.exists())

    def test_actualizar_ficha_desde_la_consulta(self):
        c = self.abrir()
        hoy = timezone.localdate().isoformat()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {
            self.campo('go.gineco', 'citologia_fecha'): hoy,             # la ficha está dentro de la consulta
            self.campo('go.gineco', 'citologia_resultado'): 'NILM',
            self.campo('nucleo.motivo', 'motivo'): 'Citología'})
        with self.en_tenant():
            cito = RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.gineco'],
                                                       vigente=True)
            self.assertEqual((cito.datos['citologia_fecha'], cito.datos['citologia_resultado']), (hoy, 'NILM'))
        detalle = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(detalle, 'Resumen ginecológico')
        self.assertNotContains(detalle, 'Toca citología')

    def test_resumen_avisa_citologia_y_formula(self):
        url = reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia'])
        r = self.cliente.post(url, {self.campo('go.gineco', 'gestas'): '2', self.campo('go.gineco', 'partos'): '1',
                                    self.campo('go.gineco', 'cesareas'): '1', self.campo('go.gineco', 'abortos'): '1'})
        self.assertIn(r.status_code, (200, 302))
        detalle = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(detalle, 'G2 P1 C1 A1')
        self.assertContains(detalle, 'Toca citología')
        self.assertContains(detalle, 'supera las gestas')

    def test_documentos_y_carnet_desde_la_ficha(self):
        fur = timezone.localdate() - timedelta(days=100)
        c = self.abrir('Control prenatal')
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('go.tipo', 'tipo'): 'PRENATAL',
                                                         self.campo('go.prenatal', 'fur'): fur.isoformat()})
        with self.en_tenant():
            perfil = self.titular.membresias.get().perfil_activo
            d = documento('go_embarazo')
            ini = d.inicial(self.p, None)
            self.assertEqual(ini['edad_gestacional'], '14 semanas 2 días')
            form = d.formulario({**{k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in ini.items()}})
            self.assertTrue(form.is_valid(), form.errors)
            doc = dsrv.emitir('go_embarazo', paciente=self.p, profesional=perfil, datos=form.datos())
            self.assertTrue(dsrv.pdf(doc, con_firma=False).startswith(b'%PDF'))
        r = self.cliente.get(reverse('documentos:emitir', args=['go_carnet']) + f'?paciente={self.p.pk}')
        self.assertEqual(r.status_code, 302)                       # sin formulario: se emite y abre el PDF
        pdf = self.cliente.get(r['Location'])
        self.assertEqual(pdf.status_code, 200)

    def test_reporte_y_excel(self):
        c = self.abrir('Control prenatal')
        self.cliente.post(f'/consultas/{c.pk}/editar/', {
            self.campo('go.tipo', 'tipo'): 'PRENATAL',
            self.campo('go.prenatal', 'fur'): (timezone.localdate() - timedelta(days=270)).isoformat()})
        r = self.cliente.get('/esp/ginecologia/reportes/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.context['prenatales'], r.context['en_curso']), (1, 1))
        self.assertEqual(len(r.context['proximos']), 1)            # FPP en 10 días
        x = self.cliente.get('/esp/ginecologia/reportes/?formato=excel')
        self.assertEqual(x['Content-Type'].split(';')[0],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        general = self.cliente.get('/reportes/')
        self.assertContains(general, 'Ginecología')                  # pestaña de la especialidad
        self.assertFalse(general.context['mostrar_sexo'])            # en GO el reporte por sexo no tiene sentido
        self.assertContains(r, 'Enfermedades e infecciones')
        self.assertContains(r, 'Vacuna contra el VPH')
        self.assertTrue(r.context['prenatales_mes'])                 # controles prenatales por mes
        pdf = self.cliente.get('/esp/ginecologia/reportes/?formato=pdf')
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_filtro_por_diagnostico(self):
        from apps.clinica.models import DiagnosticoConsulta
        c1, c2 = self.abrir(), self.abrir()
        with self.en_tenant():
            DiagnosticoConsulta.objects.create(consulta=c1, paciente=self.p, codigo='N76.0', descripcion='Vaginitis aguda')
            DiagnosticoConsulta.objects.create(consulta=c2, paciente=self.p, codigo='', descripcion='Control sano')
        r = self.cliente.get('/reportes/')
        self.assertEqual(r.context['consultas'], 2)
        self.assertEqual({b['filtro'] for b in r.context['morbilidad']}, {'N76.0', 'Control sano'})
        self.assertContains(r, 'diagnostico=N76.0')                   # cada enfermedad filtra al tocarla
        self.assertNotContains(r, 'CIE-10')
        for consulta in ('n76.0', 'vagini'):                          # código exacto o parte del nombre
            r = self.cliente.get(f'/reportes/?diagnostico={consulta}')
            self.assertEqual(r.context['consultas'], 1)
            self.assertContains(r, 'Quitar filtro')
        go = self.cliente.get('/esp/ginecologia/reportes/?diagnostico=sano')
        self.assertEqual(go.context['consultas'], 1)
        self.assertIn('diagnostico=sano', go.context['pestanas'][0]['url'])   # se conserva al cambiar de pestaña

    def test_paciente_nueva_sale_femenina_y_editar_funciona(self):
        r = self.cliente.get('/pacientes/nuevo/')
        self.assertContains(r, 'value="F" selected')
        self.assertEqual(self.cliente.get(f'/pacientes/{self.p.pk}/editar/').status_code, 200)

    def test_ficha_y_consulta_tal_cual_ginea(self):
        r = self.cliente.get(reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia']))
        for etiqueta in ('Antecedentes personales', 'Antecedentes familiares', 'Historia gineco-obstétrica',
                         'Planificación familiar', 'Observaciones generales', 'Inicio vida sexual (edad)',
                         'Número de parejas sexuales', 'Características del sangrado menstrual', 'Dispareunia',
                         'Última citología (tiempo aproximado)', 'Tipo de DIU', 'Alcoholismo'):
            self.assertContains(r, etiqueta)
        c = self.abrir()
        form = self.cliente.get(f'/consultas/{c.pk}/editar/')
        for etiqueta in ('Motivo / notas adicionales', 'Síntomas actuales', 'Tratamiento', 'Próxima cita',
                         'Exámenes solicitados', 'Tensión arterial (sistólica)'):
            self.assertContains(form, etiqueta)
        self.assertNotContains(form, 'Frec. respiratoria')

    def test_refrescar_plantillas(self):
        from io import StringIO

        from django.core.management import call_command
        with self.en_tenant():
            plantilla = PlantillaHistoria.objects.get(nombre='Consulta ginecológica')
            plantilla.items.all().delete()
        call_command('refrescar_plantillas', 'ginecologia', '--consultorio', 'gineco', stdout=StringIO())
        with self.en_tenant():
            self.assertEqual(plantilla.items.count(), 16)                  # 11 de la consulta + 5 de la ficha



class HistoriaCompletaYHisterectomiaTest(BaseTest):
    """2026-10-22: la ficha va dentro de la consulta; con histerectomía el ciclo «no aplica» (sin borrar datos)."""
    setUp, campo, abrir = GinecologiaTest.setUp, GinecologiaTest.campo, GinecologiaTest.abrir

    def ficha(self, **datos):
        url = reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia'])
        self.cliente.post(url, {self.campo('go.gineco', k): v for k, v in datos.items()})
        with self.en_tenant():
            return RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.gineco'],
                                                       vigente=True).datos

    def test_ciclo_no_aplica_con_histerectomia_y_conserva_la_fur(self):
        datos = self.ficha(fur='2024-05-01', ciclo_dias='28', histerectomia='si', histerectomia_tipo='TOTAL')
        self.assertEqual((datos['fur'], datos['histerectomia_tipo']), ('2024-05-01', 'TOTAL'))   # no se borra
        r = self.cliente.get(reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia']))
        self.assertContains(r, 'data-no-aplica-si')
        detalle = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(detalle, 'Histerectomía total')
        self.assertNotContains(detalle, 'FUR 01/05/2024')                     # el ciclo no aplica
        self.assertNotContains(detalle, 'Toca citología')

    def test_histerectomia_subtotal_sigue_pidiendo_citologia(self):
        self.ficha(histerectomia='si', histerectomia_tipo='SUBTOTAL')
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/'), 'Toca citología')

    def test_consulta_sin_campos_de_ficha_no_borra_la_ficha(self):
        self.ficha(gestas='2', partos='2')
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {self.campo('nucleo.motivo', 'motivo'): 'Control'})
        with self.en_tenant():
            datos = RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.gineco'],
                                                        vigente=True).datos
        self.assertEqual(datos['gestas'], 2)
