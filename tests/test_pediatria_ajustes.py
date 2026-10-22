"""Ajustes de pediatría (2026-10-22): datos del menor, carnet de vacunas, atajo en la consulta, referencia con
antecedentes elegidos, historia clínica completa y registro rápido."""
from datetime import timedelta

from django.utils import timezone

from apps.especialidades.pediatria.models import Vacuna, VacunaAplicada
from apps.pacientes.models import AntecedenteBase, Paciente

from .base import BaseTest, crear_consultorio


class PediatriaAjustesTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Pediatra', 'pediatra2', especialidad='pediatria')
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.nino = Paciente.objects.create(nombres='Ana', apellidos='Paz', sexo='F',
                                                fecha_nacimiento=timezone.localdate() - timedelta(days=4 * 365))
            AntecedenteBase.objects.update_or_create(paciente=self.nino, defaults={
                'alergias': 'Penicilina <grave> & rash', 'enfermedades_cronicas': 'Asma'})

    def test_formulario_de_menor_oculta_ocupacion_y_estado_civil(self):
        r = self.cliente.get(f'/pacientes/{self.nino.pk}/editar/')
        self.assertTrue(r.context['es_menor'])
        self.assertContains(r, 'data-solo-adulto hidden')
        nuevo = self.cliente.get('/pacientes/nuevo/')
        self.assertContains(nuevo, 'Guardar y abrir historia')
        self.assertContains(nuevo, 'Guardar y agendar cita')

    def test_registro_rapido_abre_historia_o_agenda(self):
        base = {'nombres': 'Leo', 'apellidos': 'Gil', 'sexo': 'M', 'tipo_documento': 'N',
                'fecha_nacimiento': str(timezone.localdate() - timedelta(days=700)),
                'rep-nombre': 'Rosa Gil', 'rep-parentesco': 'MADRE', 'rep-tipo_documento': 'V',
                'rep-numero_documento': '12345678'}
        r = self.cliente.post('/pacientes/nuevo/', {**base, 'despues': 'historia'})
        self.assertIn('/consultas/nueva/', r['Location'])
        r = self.cliente.post('/pacientes/nuevo/', {**base, 'nombres': 'Mia', 'rep-numero_documento': '12345679',
                                                    'despues': 'agendar'})
        self.assertIn('/agenda/citas/nueva/?paciente=', r['Location'])

    def test_cargar_carnet_marca_varias_y_no_duplica(self):
        with self.en_tenant():
            ids = list(Vacuna.objects.visibles().filter(anual=False, edad_meses__lte=18).values_list('pk', flat=True))
        url = f'/esp/pediatria/pacientes/{self.nino.pk}/vacunas/carnet/'
        self.cliente.post(url, {'vacunas': ids, 'fecha': ''})
        self.cliente.post(url, {'vacunas': ids})                       # repetir no duplica
        with self.en_tenant():
            self.assertEqual(VacunaAplicada.objects.filter(paciente=self.nino).count(), len(ids))
        r = self.cliente.get(f'/esp/pediatria/pacientes/{self.nino.pk}/vacunas/')
        self.assertContains(r, 'Cargar carnet')

    def test_consulta_muestra_atajo_de_vacunas_con_aviso(self):
        r = self.cliente.get(f'/pacientes/{self.nino.pk}/consultas/nueva/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['accesos'][0]['titulo'], 'Vacunas')
        self.assertEqual(r.context['accesos'][0]['aviso'][1], 'danger')       # 4 años sin registros: atrasadas

    def test_referencia_con_antecedentes_elegidos_y_texto_con_simbolos(self):
        url = f'/documentos/emitir/referencia/?paciente={self.nino.pk}'
        r = self.cliente.get(url)
        self.assertContains(r, 'Antecedentes que se incluyen')
        self.assertContains(r, 'Antecedentes generales')
        r = self.cliente.post(url, {'paciente': self.nino.pk, 'dirigido_a': 'Neumología', 'motivo': 'Asma',
                                    'antecedentes': ['base']})
        self.assertEqual(r.status_code, 302)
        from apps.documentos.models import DocumentoEmitido
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='referencia')
        self.assertEqual(doc.datos['antecedentes_texto'][0]['clave'], 'base')
        pdf = self.cliente.get(f'/documentos/{doc.pk}/pdf/')
        self.assertTrue(pdf.content.startswith(b'%PDF'))                # «<» y «&» no rompen el PDF

    def test_historia_clinica_completa(self):
        self.cliente.post(f'/pacientes/{self.nino.pk}/consultas/nueva/', {})   # no importa si no guarda
        r = self.cliente.post(f'/documentos/emitir/historia/?paciente={self.nino.pk}',
                              {'paciente': self.nino.pk, 'incluir_antecedentes': 'on'})
        self.assertEqual(r.status_code, 302)
        from apps.documentos.models import DocumentoEmitido
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='historia')
        self.assertIn('consultas', doc.datos)
        pdf = self.cliente.get(f'/documentos/{doc.pk}/pdf/')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_calculados_en_vivo(self):
        from apps.clinica.models import SeccionClinica
        with self.en_tenant():
            s = SeccionClinica.objects.visibles().get(codigo='ped.antropometria')
        r = self.cliente.post('/consultas/calcular/', {'_prefijo': f's{s.pk}', '_paciente': self.nino.pk,
                                                       f's{s.pk}-peso_kg': '16', f's{s.pk}-talla_cm': '102'})
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertTrue(datos['imc'])
        self.assertTrue(any(v for k, v in datos.items() if k != 'imc'))       # percentiles OMS
        self.assertEqual(self.cliente.post('/consultas/calcular/', {'_prefijo': 'x'}).status_code, 400)
