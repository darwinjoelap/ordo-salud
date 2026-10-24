"""
Carga pacientes FICTICIOS de cardiología pediátrica para el demo (nunca datos reales de los modelos de la doctora).

    python manage.py demo_cardiologia --consultorio dra-sierra
    python manage.py demo_cardiologia --consultorio dra-sierra --crear --usuario lsierra --clave "Clave-segura-123"
    python manage.py demo_cardiologia --consultorio dra-sierra --borrar

Cada paciente queda marcado en «Observaciones administrativas» con [DEMO]; --borrar elimina solo esos.
"""
import contextlib
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.clinica import consultas as srv
from apps.clinica.formularios import FormularioSeccion
from apps.clinica.models import NotaEvolucion, PlantillaHistoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.tenancy import usando_tenant
from apps.pacientes.models import Paciente, Representante
from apps.plataforma.models import Especialidad, Tenant

MARCA = '[DEMO] Paciente ficticio para demostración.'

BASE_ECO = {'situs': 'SOLITUS', 'apex': 'LEVO', 'rvs': 'NORMALES', 'vci_colapso': 'MAYOR', 'rvp': 'NORMALES',
            'conexion_av': 'CONCORDANTE', 'conexion_va': 'CONCORDANTE', 'ao_valva': 'TRIVALVA', 'arco': 'IZQUIERDO',
            'arco_obstruccion': 'NO', 'ramas': 'CONFLUENTES', 'derrame': 'NO', 'trombos': 'no', 'vegetaciones': 'no'}

CASOS = [
    {'paciente': {'nombres': 'Valentina', 'apellidos': 'Rojas Méndez', 'sexo': 'F', 'fecha_nacimiento': date(2017, 3, 14),
                  'ciudad': 'Ejido', 'telefono': '0414-0000001'},
     'madre': ('Carolina Méndez', '00000001'), 'dias': 20,
     'antecedentes': {'edad_madre': 24, 'gestas': 2, 'embarazo': 'SIMPLE', 'termino': 'TERMINO', 'semanas': 39,
                      'via_parto': 'EUTOCICO', 'respiro_lloro': 'si', 'pan': 3150, 'tan': 50,
                      'egreso': 'Egresó con la madre a las 24 horas', 'inmunizaciones': 'COMPLETO',
                      'inmunizaciones_documentado': 'si'},
     'motivo': {'motivo': 'Soplo cardíaco', 'enfermedad_actual': 'Escolar referida por pediatra por soplo sistólico '
                'en foco pulmonar detectado en control de niño sano. Asintomática, buena tolerancia al ejercicio.'},
     'signos': {'peso_kg': '24.5', 'talla_cm': '128', 'fc': '92', 'spo2': '98', 'pa_sistolica': '100',
                'pa_diastolica': '62'},
     'examen': {'general': 'Eutrófica, activa, rosada, hidratada.',
                'cardiopulmonar': 'Ruidos cardíacos rítmicos, desdoblamiento fijo del 2R, soplo sistólico II/VI en '
                                  'foco pulmonar. Pulsos periféricos simétricos.'},
     'ekg': {'ritmo': 'RS', 'fc': '90', 'pr': '0.14', 'qrs': '0.08', 'qt': '0.34', 'eje_p': '45', 'eje_qrs': '110',
             'trazo': 'Bloqueo incompleto de rama derecha'},
     'eco': {'vci': '9.5', 'tia': 'DEFECTO', 'cia_tipo': 'OS', 'cia_mm1': '11.2', 'cia_mm2': '10.4', 'cia_shunt': 'ID',
             'qpqs': '2.1', 'ad_vol': '24', 'ai_vol': '16.5', 'tiv': 'INTACTO', 'vd_estado': 'LEVE', 'tapse': '19.5',
             'tric_anillo': '24', 'mit_anillo': '20', 'sivd': '6.2', 'ddvi': '34', 'ppd': '6', 'dsvi': '21',
             'pulm_anillo': '17', 'pulm_vmax': '1.4', 'tap_mm': '19', 'rd_mm': '10.5', 'ri_mm': '10',
             'ductus': 'NO', 'ao_anillo': '15', 'ao_sv': '20', 'ao_ust': '17', 'ao_asc': '18', 'ao_vmax': '1.1'},
     'plan': {'plan': 'CIA ostium secundum con repercusión hemodinámica (Qp:Qs 2.1:1). Se refiere para cierre '
                      'percutáneo. Se revalorará en 3 meses.'},
     'nota': 'Se entrega informe para la junta de hemodinamia.'},
    {'paciente': {'nombres': 'Santiago', 'apellidos': 'Pérez Linares', 'sexo': 'M', 'fecha_nacimiento': date(2025, 8, 2),
                  'ciudad': 'Mérida', 'telefono': '0424-0000002'},
     'madre': ('Andreína Linares', '00000002'), 'dias': 9,
     'antecedentes': {'edad_madre': 31, 'gestas': 1, 'embarazo': 'SIMPLE', 'termino': 'TERMINO', 'semanas': 38,
                      'via_parto': 'CESAREA', 'respiro_lloro': 'si', 'pan': 2900, 'tan': 49,
                      'inmunizaciones': 'COMPLETO', 'inmunizaciones_documentado': 'si'},
     'motivo': {'motivo': 'Control de CIV', 'enfermedad_actual': 'Lactante con CIV perimembranosa diagnosticada al '
                'mes de vida. Buena ganancia ponderal, sin diaforesis con las tomas.'},
     'signos': {'peso_kg': '9.8', 'talla_cm': '76', 'fc': '118', 'spo2': '99'},
     'examen': {'general': 'Eutrófico, activo.',
                'cardiopulmonar': 'Soplo holosistólico III/VI en mesocardio irradiado en barra. Pulsos normales.'},
     'ekg': {'ritmo': 'RS', 'fc': '120', 'pr': '0.10', 'qrs': '0.06', 'qt': '0.28', 'eje_p': '50', 'eje_qrs': '90'},
     'eco': {'vci': '6', 'tia': 'INTACTO', 'tiv': 'DEFECTO', 'civ_tipo': 'PERIMEMBRANOSA', 'civ_mm': '3.5',
             'civ_shunt': 'ID', 'ad_vol': '7', 'ai_vol': '6.5', 'tapse': '14', 'tric_anillo': '16', 'mit_anillo': '15',
             'sivd': '4.5', 'ddvi': '27', 'ppd': '4.2', 'dsvi': '17', 'pulm_anillo': '11', 'tap_mm': '12',
             'rd_mm': '7', 'ri_mm': '6.8', 'ductus': 'NO', 'ao_anillo': '10', 'ao_vmax': '1.0'},
     'plan': {'plan': 'CIV perimembranosa restrictiva sin repercusión. Profilaxis de endocarditis según pautas. '
                      'Se revalorará en 6 meses.'}},
    {'paciente': {'nombres': 'Mateo', 'apellidos': 'Contreras Díaz', 'sexo': 'M', 'fecha_nacimiento': date(2021, 5, 20),
                  'ciudad': 'Tovar', 'telefono': '0416-0000003'},
     'madre': ('Yusmary Díaz', '00000003'), 'dias': 3,
     'antecedentes': {'edad_madre': 38, 'gestas': 4, 'gestas_detalle': 'I Aborto', 'embarazo': 'SIMPLE',
                      'termino': 'PRETERMINO', 'semanas': 36, 'via_parto': 'CESAREA', 'respiro_lloro': 'si',
                      'pan': 2450, 'tan': 46, 'inmunizaciones': 'INCOMPLETO', 'inmunizaciones_documentado': 'si'},
     'motivo': {'motivo': 'Control POP tardío de Tetralogía de Fallot', 'enfermedad_actual': 'Preescolar con '
                'corrección total de Tetralogía de Fallot a los 11 meses. Asintomático.'},
     'signos': {'peso_kg': '16.2', 'talla_cm': '103', 'fc': '98', 'spo2': '97'},
     'examen': {'general': 'Eutrófico.', 'cardiopulmonar': 'Cicatriz de esternotomía. Soplo sistólico II/VI y '
                                                            'diastólico I/VI en foco pulmonar.'},
     'ekg': {'ritmo': 'RS', 'fc': '96', 'pr': '0.13', 'qrs': '0.12', 'qt': '0.36', 'eje_p': '40', 'eje_qrs': '120',
             'trazo': 'BCRDHH'},
     'eco': {'vci': '8', 'tia': 'INTACTO', 'tiv': 'CERRADO', 'tiv_detalle': 'Parche normoposicionado, sin shunt '
             'residual', 'vd_estado': 'MODERADO', 'tapse': '15', 'vd_area_d': '11.5', 'vd_area_s': '6.4',
             'tric_anillo': '19', 'tric_ir': 'LEVE', 'tric_vmax': '2.3', 'mit_anillo': '17', 'sivd': '5',
             'ddvi': '29', 'ppd': '5', 'dsvi': '18.5', 'pulm_anillo': '10', 'pulm_vmax': '2.2', 'pulm_ip': 'MODERADA',
             'tap_mm': '11', 'rd_mm': '7.5', 'ri_mm': '7', 'ductus': 'LIGADO', 'ao_anillo': '14', 'ao_sv': '19',
             'ao_vmax': '1.2'},
     'plan': {'plan': 'POP tardío de Tetralogía de Fallot con insuficiencia pulmonar moderada y VD moderadamente '
                      'dilatado. Holter de 24 horas. Se revalorará en 4 meses.'},
     'nota': 'Holter: ritmo sinusal, extrasístoles ventriculares aisladas (< 1 %).'},
    {'paciente': {'nombres': 'Isabella', 'apellidos': 'Molina Uzcátegui', 'sexo': 'F',
                  'fecha_nacimiento': date.today() - timedelta(days=24), 'ciudad': 'Mérida', 'telefono': '0412-0000004'},
     'madre': ('Daniela Uzcátegui', '00000004'), 'dias': 1,
     'antecedentes': {'edad_madre': 28, 'gestas': 1, 'embarazo': 'SIMPLE', 'termino': 'TERMINO', 'semanas': 40,
                      'via_parto': 'EUTOCICO', 'respiro_lloro': 'si', 'pan': 3600, 'tan': 51,
                      'inmunizaciones': 'COMPLETO', 'inmunizaciones_documentado': 'no'},
     'motivo': {'motivo': 'Soplo en la recién nacida', 'enfermedad_actual': 'Neonato referida desde retén por soplo '
                'continuo. Alimentación con lactancia materna exclusiva, buena succión.'},
     'signos': {'peso_kg': '3.6', 'talla_cm': '59', 'fc': '142', 'spo2': '98'},
     'examen': {'general': 'Activa, rosada.', 'cardiopulmonar': 'Soplo continuo II/VI infraclavicular izquierdo.'},
     'ekg': {'ritmo': 'RS', 'fc': '145', 'pr': '0.10', 'qrs': '0.06', 'qt': '0.26', 'eje_p': '60', 'eje_qrs': '120'},
     'eco': {'vci': '4', 'tia': 'FOP', 'tiv': 'INTACTO', 'tapse': '9', 'tric_anillo': '12', 'mit_anillo': '10.5',
             'sivd': '3', 'ddvi': '18', 'ppd': '2.8', 'dsvi': '11.5', 'pulm_anillo': '7.5', 'tap_mm': '8',
             'rd_mm': '4.5', 'ri_mm': '4.3', 'ductus': 'PERMEABLE', 'ductus_mm': '2.2', 'ductus_shunt': 'ID',
             'ao_anillo': '7', 'ao_vmax': '0.9'},
     'plan': {'plan': 'Ductus arterioso permeable pequeño sin repercusión. Se revalorará en 2 meses.'}},
]


class Command(BaseCommand):
    help = 'Carga pacientes ficticios de cardiología pediátrica (demo).'

    def add_arguments(self, parser):
        parser.add_argument('--consultorio', default='dra-sierra', help='Enlace del consultorio (slug).')
        parser.add_argument('--crear', action='store_true', help='Crea el consultorio si no existe.')
        parser.add_argument('--usuario', default='lsierra')
        parser.add_argument('--clave', help='Clave del titular al crearlo.')
        parser.add_argument('--borrar', action='store_true', help='Borra solo los pacientes [DEMO].')

    def handle(self, consultorio, crear, usuario, clave, borrar, **op):
        tenant = Tenant.objects.filter(slug=consultorio).first()
        if tenant is None:
            if not crear:
                raise CommandError(f'No existe «{consultorio}». Usa --crear --usuario … --clave …')
            tenant = self._crear(consultorio, usuario, clave)
        with usando_tenant(tenant):
            if borrar:
                n = self._borrar()
                self.stdout.write(self.style.SUCCESS(f'Borrados {n} pacientes demo y todo lo suyo.'))
                return
            membresia = tenant.membresias.filter(activa=True, perfil__especialidad__codigo='cardiologia_pediatrica')\
                .select_related('perfil').first()
            if membresia is None or membresia.perfil is None:
                raise CommandError('El consultorio no tiene un profesional de cardiología pediátrica.')
            plantilla = PlantillaHistoria.objects.filter(
                activa=True, nombre='Consulta de cardiología pediátrica').first()
            if plantilla is None:
                raise CommandError('Falta la plantilla. Corre sincronizar_especialidades y refrescar_plantillas.')
            creados = 0
            for caso in CASOS:
                if Paciente.objects.filter(nombres=caso['paciente']['nombres'],
                                           apellidos=caso['paciente']['apellidos']).exists():
                    continue
                self._caso(caso, membresia.perfil, plantilla)
                creados += 1
        self.stdout.write(self.style.SUCCESS(f'{creados} pacientes demo creados en «{tenant}».'))

    @staticmethod
    @transaction.atomic
    def _borrar():
        from django.apps import apps
        demo = Paciente.objects.filter(observaciones__startswith='[DEMO]')
        n = demo.count()
        for modelo in ('documentos.DocumentoEmitido', 'agenda.Cita', 'dictado.SesionDictado'):
            with contextlib.suppress(LookupError):
                apps.get_model(modelo).todos.filter(paciente__in=demo).delete()
        apps.get_model('clinica.Consulta').todos.filter(paciente__in=demo).delete()
        demo.delete()
        return n

    def _crear(self, slug, usuario, clave):
        from apps.plataforma import servicios
        if not clave:
            raise CommandError('Para crear el consultorio indica --clave.')
        esp = Especialidad.objects.filter(codigo='cardiologia_pediatrica').first()
        if esp is None:
            raise CommandError('Corre primero `python manage.py sincronizar_especialidades`.')
        tenant, titular, _ = servicios.crear_tenant({
            'nombre': 'Consultorio Dra. Lyna Sierra (demo)', 'slug': servicios.validar_enlace(slug),
            'usuario_titular': usuario, 'nombre_titular': 'Lyna', 'apellido_titular': 'Sierra',
            'titular_es_profesional': True, 'especialidad_titular': esp, 'titulo_titular': 'Dra.',
            'especialidades': [esp]})
        titular.set_password(clave)
        titular.debe_cambiar_clave = False
        titular.save(update_fields=['password', 'debe_cambiar_clave'])
        return tenant

    @transaction.atomic
    def _caso(self, caso, perfil, plantilla):
        p = Paciente.objects.create(**caso['paciente'], observaciones=MARCA)
        nombre, ci = caso['madre']
        Representante.objects.create(paciente=p, nombre=nombre, parentesco='MADRE', tipo_documento='V',
                                     numero_documento=ci)
        fecha = timezone.now() - timedelta(days=caso['dias'])
        consulta = srv.abrir_consulta(paciente=p, profesional=perfil, plantilla=plantilla, fecha_hora=fecha)
        valores = {'cp.antecedentes': caso['antecedentes'], 'nucleo.motivo': caso['motivo'],
                   'nucleo.signos_vitales': caso['signos'], 'nucleo.examen_fisico': caso['examen'],
                   'cp.ekg': caso['ekg'], 'cp.eco': {**BASE_ECO, **caso['eco']}, 'nucleo.plan': caso['plan']}
        for _ in range(2):          # la 2.ª vuelta ya tiene la SC de los signos guardados (Z-score, indexados)
            srv.guardar_secciones(consulta, self._limpios(consulta, valores))
        if caso.get('nota'):
            NotaEvolucion.objects.create(consulta=consulta, paciente=p, fecha=(fecha + timedelta(days=2)).date(),
                                         texto=caso['nota'])
        if caso['dias'] > 2:
            with contextlib.suppress(ErrorDeNegocio):
                srv.cerrar_consulta(consulta)

    @staticmethod
    def _limpios(consulta, valores):
        contexto = srv.contexto_calculo(consulta)
        salida = {}
        for item in consulta.estructura:
            datos = valores.get(item['codigo'])
            if not datos:
                continue
            prefijo = f"s{item['seccion_id']}"
            form = FormularioSeccion(item['campos'], {f'{prefijo}-{k}': v for k, v in datos.items()},
                                     prefix=prefijo, contexto=contexto, exigir_requeridos=False)
            if not form.is_valid():
                raise CommandError(f"{item['codigo']}: {form.errors.as_text()}")
            salida[item['seccion_id']] = form.datos_limpios
        return salida
