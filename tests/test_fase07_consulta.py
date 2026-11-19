"""Fase 07: consulta clínica con plantilla, cierre, enmienda, anulación, visibilidad y adjuntos."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.clinica import consultas as srv
from apps.clinica.models import (
    Consulta,
    DiagnosticoConsulta,
    Enmienda,
    ItemPrescripcion,
    RegistroSeccionPaciente,
    SeccionClinica,
    SignosVitales,
)
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import AntecedenteBase, Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest


class ConsultaTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Luis', apellidos='Mora', sexo='M',
                                                    numero_documento='9000111')
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}

    def abrir(self, cliente=None):
        r = self.iniciar_independiente(self.paciente, {'tipo': 'PRIMERA'}, cliente=cliente)
        self.assertEqual(r.status_code, 302, r.content[:300])
        with self.en_tenant():
            return Consulta.objects.latest('id')

    def campo(self, codigo, clave):
        return f's{self.s[codigo]}-{clave}'

    def datos_completos(self):
        return {
            self.campo('nucleo.motivo', 'motivo'): 'Dolor de garganta y fiebre',
            self.campo('nucleo.signos_vitales', 'peso_kg'): '72,5',
            self.campo('nucleo.signos_vitales', 'talla_cm'): '170',
            self.campo('nucleo.signos_vitales', 'pa_sistolica'): '120',
            self.campo('nucleo.signos_vitales', 'pa_diastolica'): '80',
            self.campo('nucleo.antecedentes', 'alergias'): 'Penicilina',
            self.campo('gen.habitos', 'tabaco'): 'NUNCA',
            self.campo('nucleo.diagnosticos', 'diagnosticos__0__codigo'): 'j02.9',
            self.campo('nucleo.diagnosticos', 'diagnosticos__0__descripcion'): '',
            self.campo('nucleo.diagnosticos', 'diagnosticos__0__certeza'): 'DEFINITIVO',
            self.campo('nucleo.prescripcion', 'medicamentos__0__medicamento'): 'Ibuprofeno 400 mg',
            self.campo('nucleo.prescripcion', 'medicamentos__0__frecuencia'): 'Cada 8 horas',
        }

    def test_abrir_congela_la_plantilla(self):
        c = self.abrir()
        self.assertEqual(c.estado, Consulta.Estado.BORRADOR)
        codigos = [i['codigo'] for i in c.estructura]
        self.assertIn('nucleo.signos_vitales', codigos)
        self.assertTrue(all(i['campos'] for i in c.estructura))

    def test_guardar_copia_a_tablas_y_cerrar(self):
        c = self.abrir()
        r = self.cliente.post(f'/consultas/{c.pk}/editar/', {**self.datos_completos(), 'accion': 'cerrar'})
        self.assertRedirects(r, f'/consultas/{c.pk}/', fetch_redirect_response=False)
        with self.en_tenant():
            c.refresh_from_db()
            self.assertEqual(c.estado, Consulta.Estado.CERRADA)
            self.assertEqual(c.motivo, 'Dolor de garganta y fiebre')
            sv = SignosVitales.objects.get(consulta=c)
            self.assertEqual(float(sv.imc), 25.1)
            dx = DiagnosticoConsulta.objects.get(consulta=c)
            self.assertEqual(dx.codigo, 'J02.9')
            self.assertEqual(dx.descripcion, 'Faringitis aguda, no especificada')    # tomado del catálogo
            self.assertIn('Faringitis', c.diagnostico)
            self.assertEqual(ItemPrescripcion.objects.get(consulta=c).frecuencia, 'Cada 8 horas')
            self.assertEqual(AntecedenteBase.objects.get(paciente=self.paciente).alergias, 'Penicilina')
            self.assertTrue(RegistroSeccionPaciente.objects.filter(paciente=self.paciente, vigente=True).exists())
        r = self.cliente.get(f'/consultas/{c.pk}/')
        self.assertContains(r, 'Faringitis')
        self.assertContains(self.cliente.get(f'/consultas/{c.pk}/imprimir/'), 'Ibuprofeno 400 mg')
        self.assertContains(self.cliente.get(f'/pacientes/{self.paciente.pk}/'), 'Evolución de signos vitales')

    def test_no_cierra_sin_diagnostico_obligatorio(self):
        c = self.abrir()
        datos = {k: v for k, v in self.datos_completos().items() if 'diagnosticos' not in k}
        self.cliente.post(f'/consultas/{c.pk}/editar/', {**datos, 'accion': 'cerrar'})
        with self.en_tenant():
            c.refresh_from_db()
            self.assertEqual(c.estado, Consulta.Estado.BORRADOR)
            self.assertEqual(c.motivo, 'Dolor de garganta y fiebre')    # sí se guardó

    def test_error_de_validacion_no_guarda_nada(self):
        c = self.abrir()
        datos = {**self.datos_completos(), self.campo('nucleo.signos_vitales', 'temperatura'): '60'}
        r = self.cliente.post(f'/consultas/{c.pk}/editar/', datos)
        self.assertContains(r, 'no se guardó nada')
        with self.en_tenant():
            self.assertFalse(c.registros.exists())

    def test_antecedentes_de_especialidad_pasan_a_la_siguiente_consulta(self):
        c1 = self.abrir()
        self.cliente.post(f'/consultas/{c1.pk}/editar/', self.datos_completos())
        c2 = self.abrir()
        r = self.cliente.get(f'/consultas/{c2.pk}/editar/')
        self.assertContains(r, 'value="NUNCA" id="id_s{}-tabaco_0" checked'.format(
            self.s['gen.habitos']), html=False)

    def test_consulta_cerrada_no_se_edita_y_se_enmienda(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', {**self.datos_completos(), 'accion': 'cerrar'})
        with self.en_tenant():
            c.refresh_from_db()
            with self.assertRaises(ErrorDeNegocio):
                srv.guardar_secciones(c, {self.s['nucleo.motivo']: {'motivo': 'otro'}})
        self.assertRedirects(self.cliente.get(f'/consultas/{c.pk}/editar/'), f'/consultas/{c.pk}/',
                             fetch_redirect_response=False)
        sid = self.s['nucleo.motivo']
        r = self.cliente.post(f'/consultas/{c.pk}/enmendar/{sid}/', {f's{sid}-motivo': 'Odinofagia y fiebre',
                                                                     'motivo': 'Error de transcripción'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            e = Enmienda.objects.get(consulta=c)
            self.assertEqual(e.antes['motivo'], 'Dolor de garganta y fiebre')
            self.assertEqual(e.despues['motivo'], 'Odinofagia y fiebre')
            c.refresh_from_db()
            self.assertEqual(c.motivo, 'Odinofagia y fiebre')

    def test_anular_conserva_la_consulta(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/anular/', {'motivo': 'Paciente equivocado'})
        with self.en_tenant():
            c.refresh_from_db()
            self.assertEqual(c.estado, Consulta.Estado.ANULADA)

    def test_cierre_automatico_por_plazo(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/editar/', self.datos_completos())
        with self.en_tenant():
            Consulta.objects.filter(pk=c.pk).update(fecha_hora=timezone.now() - timedelta(hours=30))
        self.assertEqual(srv.cerrar_vencidas(), 1)
        with self.en_tenant():
            c.refresh_from_db()
            self.assertEqual(c.estado, Consulta.Estado.CERRADA)
            self.assertIsNone(c.cerrada_por)

    def test_adjunto_solo_con_permiso(self):
        c = self.abrir()
        self.cliente.post(f'/consultas/{c.pk}/adjuntar/', {'archivo': SimpleUploadedFile(
            'eco.pdf', b'%PDF-1.4 prueba', content_type='application/pdf')})
        with self.en_tenant():
            a = c.adjuntos.get()
        self.assertEqual(self.cliente.get(f'/adjuntos/{a.pk}/').status_code, 200)

    def test_cie10_sugerencias(self):
        r = self.cliente.get('/cie10/?q=faringitis')
        self.assertContains(r, 'J02.9 · Faringitis aguda')


class VisibilidadTest(BaseTest):
    def setUp(self):
        super().setUp()
        esp = Especialidad.objects.get(codigo='cardiologia')
        self.tenant.especialidades.add(esp)
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'cardio', 'Rosa', 'Díaz', Rol.MEDICO, especialidad=esp)
        m.usuario.set_password(clave)
        m.usuario.debe_cambiar_clave = False
        m.usuario.save()
        self.cardio = self.entrar(self.tenant, 'cardio', clave)
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Ana', apellidos='Ruiz', sexo='F')
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            self.consulta = srv.abrir_consulta(paciente=self.paciente, profesional=perfil)
            # la paciente está citada con la cardióloga: es «su» paciente (alcance de pacientes)
            from datetime import time

            from apps.agenda.models import Cita
            Cita.objects.create(paciente=self.paciente, profesional=m.perfil, especialidad=esp,
                                fecha=timezone.localdate(), hora_inicio=time(9), hora_fin=time(9, 30))

    def visibilidad(self, modo):
        config = self.tenant.configuracion
        config.visibilidad_historia = modo
        config.save()

    def test_compartida(self):
        self.visibilidad('COMPARTIDA')
        self.assertEqual(self.cardio.get(f'/consultas/{self.consulta.pk}/').status_code, 200)

    def test_por_especialidad_y_privada(self):
        for modo in ('POR_ESPECIALIDAD', 'PRIVADA'):
            self.visibilidad(modo)
            self.assertEqual(self.cardio.get(f'/consultas/{self.consulta.pk}/').status_code, 403)
            r = self.cardio.get(f'/pacientes/{self.paciente.pk}/')
            self.assertContains(r, 'de otros médicos no visibles')

    def test_otro_medico_no_edita(self):
        self.assertRedirects(self.cardio.get(f'/consultas/{self.consulta.pk}/editar/'),
                             f'/consultas/{self.consulta.pk}/', fetch_redirect_response=False)

    def test_cardiologa_usa_plantilla_de_su_especialidad(self):
        r = self.iniciar_independiente(self.paciente, {'tipo': 'PRIMERA'}, cliente=self.cardio)
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            c = Consulta.objects.latest('id')
            self.assertEqual(c.especialidad.codigo, 'cardiologia')
