"""2026-11-11: en ginecología, «Antecedentes personales» como Ginea (alergias, crónicas, cirugías, medicación, grupo
sanguíneo) sin duplicar datos; nivel de instrucción en los datos del paciente; ciclo sin mínimo de 10 días."""
from django.urls import reverse

from apps.clinica.models import RegistroSeccionPaciente
from apps.pacientes.models import AntecedenteBase, Paciente

from . import test_fase14_ginecologia as go
from .base import BaseTest


class AntecedentesPersonalesTest(BaseTest):
    setUp, campo, abrir = go.GinecologiaTest.setUp, go.GinecologiaTest.campo, go.GinecologiaTest.abrir

    def post_ficha(self, codigo, **datos):
        url = reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia'])
        return self.cliente.post(url, {self.campo(codigo, k): v for k, v in datos.items()})

    def test_alergias_y_grupo_viven_en_un_solo_lugar(self):
        self.post_ficha('go.habitos', alergias='Penicilina', cirugias='Cesárea 2019', grupo_sanguineo='O+',
                        tabaquismo='si')
        with self.en_tenant():
            base = AntecedenteBase.objects.get(paciente=self.p)
            self.p.refresh_from_db()
            registro = RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.habitos'],
                                                           vigente=True)
        self.assertEqual((base.alergias, base.cirugias, self.p.grupo_sanguineo), ('Penicilina', 'Cesárea 2019', 'O+'))
        self.assertNotIn('alergias', registro.datos)                 # no se duplica en la sección
        self.assertEqual(registro.datos.get('tabaquismo'), True)
        # La consulta muestra lo mismo (y la alerta de alergias)
        c = self.abrir()
        r = self.cliente.get(f'/consultas/{c.pk}/editar/')
        self.assertContains(r, 'Penicilina')
        self.assertContains(r, 'Cesárea 2019')
        self.assertNotContains(r, 'Nivel de instrucción')

    def test_cambiar_en_antecedentes_generales_se_ve_en_personales(self):
        with self.en_tenant():
            AntecedenteBase.objects.update_or_create(paciente=self.p, defaults={'medicacion_actual': 'Levotiroxina'})
        r = self.cliente.get(reverse('clinica:ficha_especialidad', args=[self.p.pk, 'ginecologia']))
        self.assertContains(r, 'Levotiroxina')

    def test_ciclo_de_menos_de_10_dias(self):
        self.post_ficha('go.gineco', ciclo_dias='7')
        with self.en_tenant():
            datos = RegistroSeccionPaciente.objects.get(paciente=self.p, seccion_id=self.s['go.gineco'],
                                                        vigente=True).datos
        self.assertEqual(datos['ciclo_dias'], 7)

    def test_primera_consulta_no_borra_lo_oculto(self):
        with self.en_tenant():
            AntecedenteBase.objects.update_or_create(paciente=self.p, defaults={'alergias': 'Sulfas'})
        c = self.abrir('Primera consulta con ficha completa')
        item = next(i for i in c.estructura if i['codigo'] == 'nucleo.antecedentes')
        self.assertNotIn('alergias', [x['clave'] for x in item['campos']])
        self.cliente.post(f'/consultas/{c.pk}/editar/', {'accion': 'guardar',
                                                         self.campo('nucleo.antecedentes', 'hospitalizaciones'): 'No'})
        with self.en_tenant():
            self.assertEqual(AntecedenteBase.objects.get(paciente=self.p).alergias, 'Sulfas')

    def test_nivel_de_instruccion_en_datos_del_paciente(self):
        import importlib

        from django.apps import apps as registro
        with self.en_tenant():
            RegistroSeccionPaciente.objects.create(paciente=self.p, seccion_id=self.s['go.habitos'], version_seccion=1,
                                                   datos={'instruccion': 'UNIVERSITARIO'})
            Paciente.objects.filter(pk=self.p.pk).update(nivel_instruccion='')
            migracion = importlib.import_module('apps.pacientes.migrations.0004_nivel_instruccion')
            migracion.copiar_de_ginecologia(registro, None)
            self.p.refresh_from_db()
        self.assertEqual(self.p.nivel_instruccion, 'UNIVERSITARIO')
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/'), 'Universitario')
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/editar/'), 'nivel_instruccion')
