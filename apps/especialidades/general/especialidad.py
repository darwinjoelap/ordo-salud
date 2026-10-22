"""
Medicina general + especialidades «básicas».

Las básicas existen desde el día 1 con las secciones generales para que cualquier especialista pueda usar Ordo Salud
mientras su módulo no existe. Cuando se instala el módulo real (pediatría, ginecología, cardiología…), éste
reemplaza a la básica con el mismo código y aporta sus secciones y plantillas (docs/05_GUIA_ESPECIALIDADES.md).
"""
from apps.clinica.registro import EspecialidadDef, PlantillaDef, registrar

from .secciones import HABITOS, REVISION_SISTEMAS

PRIMERA = ['nucleo.motivo', 'nucleo.antecedentes', 'gen.habitos', 'nucleo.signos_vitales', 'gen.revision_sistemas',
           'nucleo.examen_fisico', 'nucleo.paraclinicos', ('nucleo.diagnosticos', {'obligatoria': True}),
           'nucleo.plan', 'nucleo.prescripcion', 'nucleo.ordenes']
CONTROL = ['nucleo.motivo', 'nucleo.signos_vitales', 'nucleo.examen_fisico', 'nucleo.paraclinicos',
           ('nucleo.diagnosticos', {'obligatoria': True}), 'nucleo.plan', 'nucleo.prescripcion', 'nucleo.ordenes']

PLANTILLAS = [
    PlantillaDef('Primera consulta', PRIMERA, predeterminada=True),
    PlantillaDef('Control', CONTROL),
]

registrar(EspecialidadDef(
    codigo='medicina_general', nombre='Medicina general', modulo='apps.especialidades.general', orden=10,
    icono='bi-heart-pulse', secciones=[HABITOS, REVISION_SISTEMAS], plantillas=PLANTILLAS,
))

# (código, nombre, ícono, color)
BASICAS = [
    ('medicina_interna', 'Medicina interna', 'bi-clipboard2-pulse', '#145F8F'),
    ('pediatria', 'Pediatría', 'bi-balloon-heart', '#2AACA8'),
    ('ginecologia', 'Ginecología y obstetricia', 'bi-gender-female', '#B04A86'),
    ('cardiologia', 'Cardiología', 'bi-heart-pulse-fill', '#C0392B'),
    ('dermatologia', 'Dermatología', 'bi-bandaid', '#B9770E'),
    ('traumatologia', 'Traumatología y ortopedia', 'bi-person-walking', '#5D6D7E'),
    ('neurologia', 'Neurología', 'bi-cpu', '#6C3483'),
    ('gastroenterologia', 'Gastroenterología', 'bi-capsule', '#A04000'),
    ('endocrinologia', 'Endocrinología', 'bi-droplet-half', '#1E8449'),
    ('neumologia', 'Neumonología', 'bi-lungs', '#2874A6'),
    ('urologia', 'Urología', 'bi-droplet', '#1F618D'),
    ('otorrinolaringologia', 'Otorrinolaringología', 'bi-ear', '#7D6608'),
    ('oftalmologia', 'Oftalmología', 'bi-eye', '#117864'),
    ('psiquiatria', 'Psiquiatría', 'bi-chat-heart', '#884EA0'),
    ('nutricion', 'Nutrición', 'bi-egg-fried', '#239B56'),
    ('fisiatria', 'Fisiatría y rehabilitación', 'bi-activity', '#2E86C1'),
]

for orden, (codigo, nombre, icono, color) in enumerate(BASICAS, 20):
    registrar(EspecialidadDef(codigo=codigo, nombre=nombre, icono=icono, color=color, orden=orden, basica=True,
                              plantillas=PLANTILLAS))
