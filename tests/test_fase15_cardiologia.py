"""Fase 15: cardiología pediátrica (modelo de la Dra. Sierra): prosa, cálculos, informe, notas de evolución, reporte."""
from datetime import date

from django.test import SimpleTestCase

from apps.clinica.models import Consulta, NotaEvolucion, PlantillaHistoria, SeccionClinica
from apps.especialidades.cardiologia_pediatrica import informe
from apps.pacientes.models import Paciente, Representante

from .base import BaseTest, crear_consultorio

# Caso del «MODELO_HISTORIA.doc» (escolar de 9 años con CIA ostium secundum)
ANTECEDENTES = {'edad_madre': 17, 'gestas': 1, 'embarazo': 'SIMPLE', 'termino': 'TERMINO', 'semanas': 38, 'dias': 4,
                'complicaciones': 'ITU primer trimestre', 'via_parto': 'EUTOCICO',
                'via_detalle': 'practican maniobra de Kristeller', 'respiro_lloro': True, 'pan': 2640, 'tan': 48,
                'egreso': 'Egresó con la madre a las 24 horas', 'inmunizaciones': 'INCOMPLETO',
                'inmunizaciones_documentado': True}
ECO = {'situs': 'SOLITUS', 'apex': 'LEVO', 'rvs': 'NORMALES', 'vci': 6.8, 'vci_colapso': 'MAYOR', 'rvp': 'NORMALES',
       'tia': 'DEFECTO', 'cia_tipo': 'OS', 'cia_mm1': 10.6, 'cia_mm2': 10.1, 'cia_shunt': 'ID', 'qpqs': 2.5,
       'ad_vol': 18.9, 'ai_vol': 13.7, 'conexion_av': 'CONCORDANTE', 'tiv': 'INTACTO', 'tapse': 17.7,
       'ddvi': 25.8, 'dsvi': 15.1, 'ductus': 'NO', 'derrame': 'NO', 'trombos': False, 'vegetaciones': False}


class ProsaTest(SimpleTestCase):
    def test_antecedentes_como_los_redacta_la_doctora(self):
        texto = informe.antecedentes(ANTECEDENTES)
        self.assertTrue(texto.startswith('Producto de madre de 17 años, IG. Embarazo simple a término 38 + 4 semanas.'))
        self.assertIn('PAN: 2.640 grs, TAN: 48 cms.', texto)
        self.assertIn('Niega alergias, asma bronquial, eruptivas, ingreso hospitalario e I/Qx.', texto)
        self.assertTrue(texto.endswith('Esquema de inmunizaciones incompleto, documentado.'))
        self.assertIn('VG, I Mortinato', informe.antecedentes({'edad_madre': 43, 'gestas': 5,
                                                              'gestas_detalle': 'I Mortinato'}))

    def test_ekg_en_una_linea_con_qtc_bazett(self):
        ekg = {'ritmo': 'RS', 'fc': 88, 'pr': 0.16, 'qrs': 0.08, 'qt': 0.36, 'eje_p': 30, 'eje_qrs': 80,
               'trazo': 'HVD, variabilidad sinusal respiratoria'}
        self.assertEqual(informe.qtc(ekg), 0.44)
        self.assertEqual(informe.ekg_linea(ekg),
                         'RS/88/0.16/0.08/0.36/0.44/30°/80°. Trazo: HVD, variabilidad sinusal respiratoria.')

    def test_calculos_de_camaras(self):
        self.assertEqual(informe.fevi({'ddvi': 25.8, 'dsvi': 15.1}), 74)          # su informe: FEVI 74 %
        self.assertEqual(informe.caf({'vd_area_d': 12.8, 'vd_area_s': 6.5}), 49.2)  # su informe: CAF 49.2
        self.assertEqual(informe.gradiente(2.51), 25.2)
        self.assertEqual(informe.gradiente(3.08, 38.2), 38.2)                       # el medido manda

    def test_eco_en_prosa_y_hallazgos(self):
        texto = informe.eco(ECO, 0.85)
        self.assertTrue(texto.startswith('Situs solitus, ápex en levocardia.'))
        self.assertIn('defecto ostium secundum: 10.6 mm x 10.1 mm', texto)
        self.assertIn('QpQs: 2.5:1.', texto)
        self.assertIn('vol índex: 22.2 ml/m2SC', texto)                            # 18.9 / 0.85
        self.assertIn('FEVI: 74 %', texto)
        self.assertTrue(texto.endswith('No se observa derrame pericárdico, trombos ni vegetaciones.'))
        self.assertIn('CIA ostium secundum · Qp:Qs 2.5:1', informe.hallazgos(ECO))

    def test_edad_del_encabezado(self):
        self.assertEqual(informe.edad_informe(date(2023, 10, 10), date(2026, 10, 7)), '2 AÑOS + 11 MESES')
        self.assertEqual(informe.edad_informe(date(2017, 1, 5), date(2026, 8, 28)), '9 AÑOS')


class CardiologiaTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Cardio', 'cardio', especialidad='cardiologia_pediatrica')
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Samantha', apellidos='González', sexo='F',
                                             fecha_nacimiento=date(2023, 10, 10), ciudad='Pueblo Llano')
            Representante.objects.create(paciente=self.p, nombre='Rosa Villamizar', parentesco='MADRE',
                                         tipo_documento='V', numero_documento='15111222')
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}

    def campo(self, codigo, clave):
        return f's{self.s[codigo]}-{clave}'

    def test_plantillas_en_el_orden_del_informe(self):
        with self.en_tenant():
            nombres = set(PlantillaHistoria.objects.filter(activa=True).values_list('nombre', flat=True))
        self.assertIn('Consulta de cardiología pediátrica', nombres)
        r = self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {'tipo': 'PRIMERA'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            c = Consulta.objects.latest('id')
        codigos = [i['codigo'] for i in c.estructura]
        self.assertEqual(codigos[:5], ['nucleo.motivo', 'nucleo.signos_vitales', 'nucleo.examen_fisico', 'cp.ekg',
                                       'cp.eco'])

    def test_consulta_completa_informe_notas_panel_y_reporte(self):
        self.cliente.post(f'/pacientes/{self.p.pk}/ficha/cardiologia_pediatrica/',
                          {self.campo('cp.antecedentes', k): v for k, v in
                           {**ANTECEDENTES, 'respiro_lloro': 'si', 'inmunizaciones_documentado': 'si'}.items()})
        datos = {'completa': '1', 'tipo': 'PRIMERA', 'accion': 'guardar',
                 self.campo('nucleo.motivo', 'enfermedad_actual'): 'Dolor precordial de 3 meses.',
                 self.campo('nucleo.signos_vitales', 'peso_kg'): '21,1',
                 self.campo('nucleo.signos_vitales', 'talla_cm'): '121',
                 self.campo('nucleo.signos_vitales', 'fc'): '103',
                 self.campo('cp.ekg', 'ritmo'): 'RS', self.campo('cp.ekg', 'fc'): '94',
                 self.campo('cp.ekg', 'qt'): '0.34',
                 self.campo('nucleo.plan', 'plan'): 'CIA OS con repercusión. Se revalorará en 4 meses.'}
        datos.update({self.campo('cp.eco', k): v for k, v in ECO.items() if not isinstance(v, bool)})
        with self.en_tenant():
            datos['plantilla'] = PlantillaHistoria.objects.get(nombre='Consulta de cardiología pediátrica').pk
        r = self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', datos)
        self.assertEqual(r.status_code, 302, getattr(r, 'context', None) and r.context.get('formularios'))
        with self.en_tenant():
            c = Consulta.objects.latest('id')
            ekg = c.registros.get(seccion__codigo='cp.ekg').datos
            eco = c.registros.get(seccion__codigo='cp.eco').datos
        self.assertEqual(ekg['qtc'], 0.43)
        self.assertEqual(eco['fevi_teichholz'], 74)
        # nota de evolución en la consulta (aunque esté cerrada)
        self.cliente.post(f'/consultas/{c.pk}/evolucion/', {'fecha': '2026-10-05',
                                                             'texto': 'Se entrega Holter con resultado normal.'})
        with self.en_tenant():
            self.assertEqual(NotaEvolucion.objects.filter(consulta=c).count(), 1)
        # informe médico con su formato
        r = self.cliente.post(f'/documentos/emitir/cp_informe/?consulta={c.pk}',
                              {'consulta': c.pk, 'incluir_imagenes': 'on', 'incluir_notas': 'on'})
        self.assertEqual(r.status_code, 302)
        from apps.documentos.models import DocumentoEmitido
        from apps.especialidades.cardiologia_pediatrica.documentos import datos_informe
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='cp_informe')
            d = datos_informe(c)
        self.assertTrue(self.cliente.get(f'/documentos/{doc.pk}/pdf/').content.startswith(b'%PDF'))
        self.assertTrue(d['antecedentes'].startswith('Producto de madre de 17 años'), d['antecedentes'])
        self.assertIn('SC: 0.84 m2SC', d['examen_linea'])
        self.assertIn('RS/94/', d['ekg'])
        # panel y reporte
        ficha = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(ficha, 'Resumen cardiológico')
        self.assertContains(ficha, 'CIA ostium secundum')
        rep = self.cliente.get('/esp/cardiologia_pediatrica/reportes/?desde=2020-01-01&hasta=2030-12-31')
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.context['con_cardiopatia'], 1)
        self.assertTrue(self.cliente.get('/esp/cardiologia_pediatrica/reportes/?formato=pdf').content
                        .startswith(b'%PDF'))

    def test_calculo_en_vivo_del_eco_con_sc(self):
        p = f"s{self.s['cp.eco']}"
        r = self.cliente.post('/consultas/calcular/', {'_prefijo': p, '_paciente': self.p.pk, '_sc': '0,85 m²',
                                                       f'{p}-ad_vol': '18.9', f'{p}-ddvi': '25.8', f'{p}-dsvi': '15.1'})
        datos = r.json()
        self.assertIn('22', datos['ad_vol_index'])
        self.assertIn('74', datos['fevi_teichholz'])
        self.assertIn('FEVI: 74 %', datos['texto_informe'])

    def test_dictado_solo_si_la_plataforma_lo_activa(self):
        url = f'/pacientes/{self.p.pk}/consultas/nueva/'
        self.assertNotContains(self.cliente.get(url), 'js/dictado.js')
        from apps.configuracion.models import ConfiguracionTenant
        ConfiguracionTenant.objects.filter(tenant=self.tenant).update(dictado_activo=True)
        self.assertContains(self.cliente.get(url), 'js/dictado.js')
