"""Fase 13.4–13.7: paneles, curvas, vacunas, pesquisas, constancias, reporte pediátrico y glosario de medicamentos."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.clinica import registro
from apps.clinica.models import Medicamento, PlantillaHistoria, SeccionClinica
from apps.documentos import servicios as dsrv
from apps.documentos.registro import documento
from apps.especialidades.pediatria import curvas, vacunas
from apps.especialidades.pediatria.models import MedicionCrecimiento, Pesquisa, Vacuna, VacunaAplicada
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class ModuloPediatriaTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Pediatra', 'pediatra', especialidad='pediatria')
        self.cliente = self.entrar(self.tenant, 'titular')
        self.nacimiento = timezone.localdate() - timedelta(days=400)          # ≈ 13 meses
        with self.en_tenant():
            self.nino = Paciente.objects.create(nombres='Lucía', apellidos='Mora', sexo='F',
                                                fecha_nacimiento=self.nacimiento)
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}

    def consulta_con_medidas(self, peso='9,2', talla='75', pc='45'):
        r = self.cliente.post(f'/pacientes/{self.nino.pk}/consultas/nueva/', {'tipo': 'PRIMERA'})
        self.assertEqual(r.status_code, 302)
        from apps.clinica.models import Consulta
        with self.en_tenant():
            c = Consulta.objects.latest('id')
        a = self.s['ped.antropometria']
        self.cliente.post(f'/consultas/{c.pk}/editar/', {f's{a}-peso_kg': peso, f's{a}-talla_cm': talla,
                                                         f's{a}-pc_cm': pc,
                                                         f's{self.s["nucleo.motivo"]}-motivo': 'Control'})
        return c

    # ---- módulos y rutas ----
    def test_rutas_del_modulo_se_cargan_solas(self):
        self.assertEqual(reverse('pediatria:vacunas', args=[1]), '/esp/pediatria/pacientes/1/vacunas/')
        esp = registro.especialidad('pediatria')
        self.assertEqual([p.codigo for p in esp.paneles], ['ped_crecimiento', 'ped_vacunas'])
        self.assertEqual([r.codigo for r in esp.reportes], ['ped_reporte'])

    def test_ficha_del_paciente_muestra_paneles_y_ficha_pediatrica(self):
        self.consulta_con_medidas()
        r = self.cliente.get(f'/pacientes/{self.nino.pk}/')
        self.assertContains(r, 'os-curva')                       # SVG de crecimiento
        self.assertContains(r, 'Vacunas')
        self.assertContains(r, reverse('clinica:ficha_especialidad', args=[self.nino.pk, 'pediatria']))

    # ---- curvas ----
    def test_curvas_svg_y_pdf(self):
        self.consulta_con_medidas()
        with self.en_tenant():
            meds = list(MedicionCrecimiento.objects.filter(paciente=self.nino))
            pts = curvas.puntos_del_paciente(self.nino, 'peso', meds, {'peso_nacer_g': 3100})
            self.assertEqual(len(pts), 2)
            g = curvas.geometria('peso', 'F', pts)
            self.assertEqual(set(g['lineas']), {3, 15, 50, 85, 97})
            svg = curvas.svg(g)
            self.assertIn('<svg', svg)
            self.assertIn('P97', svg)
            self.assertEqual(svg.count('<circle'), 2)
            self.assertIsNotNone(curvas.dibujo_pdf(g))
            self.assertIsNone(curvas.geometria('peso', '', pts))          # sin sexo no hay curva
            self.assertEqual(curvas.svg(None), '')

    def test_curva_escolar_no_arranca_en_el_nacimiento(self):
        g = curvas.geometria('talla', 'M', [(100.0, 112.0, None, 'x'), (130.0, 128.0, None, 'y')])
        self.assertGreater(g['marcas_x'][0][1].count('a'), 0)
        self.assertNotEqual(g['marcas_x'][0][1], '0a')

    # ---- vacunas y pesquisas ----
    def test_esquema_estados_y_anual(self):
        with self.en_tenant():
            filas = {f['vacuna'].pk: f for f in vacunas.esquema(self.nino)}
            self.assertTrue(any(f['estado'] == 'pendiente' for f in filas.values()))
            self.assertTrue(any(f['estado'] == 'futura' for f in filas.values()))
            gripe = Vacuna.objects.visibles().filter(anual=True).first()
            unica = Vacuna.objects.visibles().filter(anual=False, edad_meses=0).first()
        url = f'/esp/pediatria/pacientes/{self.nino.pk}/vacunas/registrar/'
        for _ in range(2):
            self.cliente.post(url, {'vacuna': gripe.pk, 'fecha': str(timezone.localdate())})
            self.cliente.post(url, {'vacuna': unica.pk, 'lote': 'L1'})
        with self.en_tenant():
            self.assertEqual(VacunaAplicada.objects.filter(vacuna=gripe).count(), 2)     # anual: una por año
            self.assertEqual(VacunaAplicada.objects.filter(vacuna=unica).count(), 1)     # única: no duplica
        r = self.cliente.get(f'/esp/pediatria/pacientes/{self.nino.pk}/vacunas/')
        self.assertContains(r, 'Aplicada')
        # antes del nacimiento: rechazada
        self.cliente.post(url, {'vacuna': unica.pk, 'fecha': str(self.nacimiento - timedelta(days=3))})
        with self.en_tenant():
            self.assertNotEqual(VacunaAplicada.objects.get(vacuna=unica).fecha, self.nacimiento - timedelta(days=3))

    def test_catalogo_propio_aislado_entre_consultorios(self):
        with self.en_tenant():
            propia = Vacuna.objects.create(tenant=self.tenant, nombre='Dengue', dosis=1, edad_meses=108)
        otro, _ = crear_consultorio('Otro', 'otro', especialidad='pediatria', usuario='otro')
        with self.en_tenant(otro):
            self.assertFalse(Vacuna.objects.visibles().filter(pk=propia.pk).exists())
            p = Paciente.objects.create(nombres='X', apellidos='Y', sexo='M', fecha_nacimiento=self.nacimiento)
            from apps.core.excepciones import ErrorDeNegocio
            with self.assertRaises(ErrorDeNegocio):
                vacunas.registrar_vacuna(p, propia)

    def test_pesquisa_unica_por_paciente(self):
        with self.en_tenant():
            pq = Pesquisa.objects.visibles().first()
        url = f'/esp/pediatria/pacientes/{self.nino.pk}/pesquisas/registrar/'
        self.cliente.post(url, {'pesquisa': pq.pk, 'resultado': 'Normal'})
        self.cliente.post(url, {'pesquisa': pq.pk, 'resultado': 'Repetir'})
        with self.en_tenant():
            filas = [f for f in vacunas.pesquisas(self.nino) if f['realizada']]
            self.assertEqual(len(filas), 1)
            self.assertEqual(filas[0]['realizada'].resultado, 'Repetir')

    # ---- constancias ----
    def test_constancias_pediatricas_generan_pdf(self):
        self.consulta_con_medidas()
        with self.en_tenant():
            perfil = self.titular.membresias.get().perfil_activo
            for codigo in ('ped_nino_sano', 'ped_lactancia', 'ped_lactancia_trabajo', 'ped_vacunas', 'ped_curvas'):
                d = documento(codigo)
                self.assertIsNotNone(d, codigo)
                datos = {}
                if d.formulario:
                    inicial = d.inicial(self.nino, None) if d.inicial else {}
                    vacio = d.formulario(initial=inicial)
                    post = {}
                    for nombre, campo in vacio.fields.items():
                        valor = vacio[nombre].value()
                        post[nombre] = valor if valor not in (None, '', []) else ('Texto' if campo.required else '')
                    form = d.formulario(post)
                    self.assertTrue(form.is_valid(), (codigo, form.errors))
                    datos = form.datos()
                doc = dsrv.emitir(codigo, paciente=self.nino, profesional=perfil, datos=datos)
                self.assertTrue(dsrv.pdf(doc, con_firma=False).startswith(b'%PDF'), codigo)
        r = self.cliente.get(reverse('documentos:emitir', args=['ped_nino_sano']) + f'?paciente={self.nino.pk}')
        self.assertContains(r, 'Diagnóstico nutricional')

    # ---- reporte ----
    def test_reporte_pediatrico_y_excel(self):
        self.consulta_con_medidas()
        r = self.cliente.get('/esp/pediatria/reportes/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['consultas'], 1)
        self.assertEqual(r.context['con_medicion'], 1)
        x = self.cliente.get('/esp/pediatria/reportes/?formato=excel')
        self.assertEqual(x['Content-Type'].split(';')[0],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertContains(self.cliente.get('/reportes/'), '/esp/pediatria/reportes/')  # pestaña Pediatría
        pdf = self.cliente.get('/esp/pediatria/reportes/?formato=pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    # ---- plantillas de módulo ----
    def test_actualizar_plantillas_respeta_la_elegida_por_el_medico(self):
        from apps.clinica.servicios import actualizar_plantillas_de_modulos
        with self.en_tenant():
            control = PlantillaHistoria.objects.get(nombre='Control de niño sano')
            control.es_predeterminada = True
            control.save()
            PlantillaHistoria.objects.exclude(pk=control.pk).update(es_predeterminada=False)
        actualizar_plantillas_de_modulos()
        with self.en_tenant():
            self.assertEqual(PlantillaHistoria.objects.filter(activa=True, es_predeterminada=True).count(), 1)


class GlosarioTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Ana', apellidos='Sol', sexo='F',
                                             fecha_nacimiento=timezone.localdate() - timedelta(days=900))

    def test_crear_editar_calcular(self):
        r = self.cliente.post('/medicamentos/nuevo/', {
            'nombre': 'Acetaminofén', 'presentacion': 'jarabe 160 mg/5 mL', 'modo': 'PESO', 'unidad_kg': 'mg',
            'dosis_kg_min': '10', 'dosis_kg_max': '15', 'concentracion_mg': '160', 'volumen_ml': '5',
            'unidad_resultado': 'mL', 'dosis_max': '1000', 'frecuencia_horas': '6', 'activo': 'on'})
        self.assertEqual(r.status_code, 302, getattr(r, 'context', {}) and r.context['form'].errors)
        with self.en_tenant():
            m = Medicamento.objects.get()
            self.assertIsNone(m.profesional)
        self.assertContains(self.cliente.get('/medicamentos/'), 'Acetaminofén')
        self.assertContains(self.cliente.get(f'/medicamentos/{m.pk}/'), 'Prueba del cálculo')
        j = self.cliente.get(f'/medicamentos/{m.pk}/calcular/?peso=12,8&edad_meses=30').json()
        self.assertEqual(j['dosis_mg'], '160 mg')                      # 12,5 mg/kg × 12,8 kg
        self.assertEqual(j['dosis'], '5 mL')
        self.assertEqual(j['frecuencia'], 'cada 6 horas')
        # la consulta muestra la barra del glosario en el récipe
        r = self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {'tipo': 'PRIMERA'})
        self.assertContains(self.cliente.get(r['Location']), 'data-glosario')
        self.cliente.post(f'/medicamentos/{m.pk}/activar/')
        self.assertEqual(self.cliente.get(f'/medicamentos/{m.pk}/calcular/').status_code, 404)

    def test_por_edad_y_validaciones(self):
        r = self.cliente.post('/medicamentos/nuevo/', {'nombre': 'SRO', 'modo': 'EDAD', 'unidad_kg': 'mg',
                                                       'rangos': 'xx', 'activo': 'on'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('rangos', r.context['form'].errors)
        r = self.cliente.post('/medicamentos/nuevo/', {'nombre': 'SRO', 'modo': 'EDAD', 'unidad_kg': 'mg',
                                                       'rangos': '0-23: ½ sobre\n24-: 1 sobre', 'solo_mio': 'on',
                                                       'activo': 'on'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            m = Medicamento.objects.get()
            self.assertEqual(m.rangos_edad[1], {'min': 24, 'max': None, 'dosis': '1 sobre'})
            self.assertIsNotNone(m.profesional)
        self.assertEqual(self.cliente.get(f'/medicamentos/{m.pk}/calcular/?edad_meses=30').json()['dosis'], '1 sobre')

    def test_medicamento_propio_no_lo_ve_otro_medico(self):
        with self.en_tenant():
            m = Medicamento.objects.create(nombre='Privado', modo='FIJA', dosis_fija='1 tab',
                                           profesional=self.titular.membresias.get().perfil_activo)
        otro, _ = crear_consultorio('Otro', 'otro2', usuario='otro2')
        c = self.entrar(otro, 'otro2')
        self.assertEqual(c.get(f'/medicamentos/{m.pk}/').status_code, 404)
