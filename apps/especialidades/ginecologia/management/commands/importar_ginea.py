"""
Migra UN consultorio de Ginea a Ordo Salud (Fase 18b, docs/roadmap/18_migracion_pediae.md §7).

Mismo motor que importar_pediae (una transacción, solo lectura en el origen, --ensayo, --unir, --sin-archivos, --nube);
cambian la ficha (gineco-obstétrica), la consulta (prenatal, ecografía, colposcopia…), el glosario y los procedimientos.

    python manage.py importar_ginea --origen "postgresql://...ginea..." --slug <consultorio> --nombres ginea_nombres.csv \\
        --nube <cuenta-cloudinary> [--ensayo]

En Ginea los sí/no de la ficha eran casillas (desmarcada = «no» o «no preguntado», no se distingue): solo se pasan los
«sí». Gestas/partos/cesáreas/abortos (por defecto 0) se pasan si alguno es mayor que 0 o hay otro dato gineco-obstétrico.
"""
from decimal import Decimal

from django.core.management.base import CommandError

from apps.especialidades.pediatria.management.commands.importar_pediae import Command as Base
from apps.especialidades.pediatria.management.commands.importar_pediae import opcion, sin_acentos, tension, texto

ESTADO_CIVIL = {'soltera': 'SOLTERO', 'casada': 'CASADO', 'union_libre': 'UNION', 'divorciada': 'DIVORCIADO',
                'viuda': 'VIUDO'}
PRESENTACION = {'cefalica': 'CEFALICA', 'cefalico': 'CEFALICA', 'pelvica': 'PELVICA', 'pelvico': 'PELVICA',
                'podalica': 'PELVICA', 'podalico': 'PELVICA', 'transversa': 'TRANSVERSA', 'transverso': 'TRANSVERSA'}


def si(valor):
    """Casilla de Ginea: solo el «sí» es un dato."""
    return 'si' if valor else None


class Command(Base):
    help = 'Migra un consultorio de Ginea a Ordo Salud.'
    ORIGEN = 'Ginea'
    ESPECIALIDAD = 'ginecologia'
    PLANTILLA = 'Consulta ginecológica'
    SEXO_POR_DEFECTO = 'F'
    DESCARTES = ('go.notas', 'observaciones')
    TABLAS_RESUMEN = {
        'pacientes': 'pacientes_paciente', 'citas': 'agenda_cita', 'consultas': 'consultas_consulta',
        'procedimientos': 'consultas_procedimiento', 'medicamentos del glosario': 'consultas_medicamento',
        'servicios': 'servicios_servicio', 'lugares': 'agenda_lugarconsulta'}

    def _usuario_origen(self):
        """Titular = el médico con más consultas. Los demás usuarios se crean después (_equipo)."""
        tid = self.t['id']
        self.usuarios_origen = self.leer('select * from accounts_usuario where tenant_id=%s order by id', [tid])
        medicos = [u for u in self.usuarios_origen if u.get('rol') == 'medico']
        if not medicos:
            raise CommandError(f'«{self.t["slug"]}» no tiene usuario médico en Ginea.')
        cuenta = {r['medico_id']: r['n'] for r in self.leer(
            'select medico_id, count(*) n from consultas_consulta where tenant_id=%s group by 1', [tid])}
        return max(medicos, key=lambda u: (cuenta.get(u['id'], 0), -u['id']))

    def _consultorio(self):
        super()._consultorio()
        self.perfiles = {self.medico_origen: self.perfil}
        self._equipo()

    def _equipo(self):
        """Resto del equipo con su misma clave: médicos → profesionales de ginecología; asistentes → asistentes."""
        from django.contrib.auth import get_user_model

        from apps.core.permisos import Rol
        from apps.core.tenancy import usando_tenant
        from apps.equipo.models import Membresia, PerfilProfesional
        from apps.equipo.servicios import _asegurar_plantillas
        U = get_user_model()

        def largo(campo):
            return PerfilProfesional._meta.get_field(campo).max_length

        for u in self.usuarios_origen:
            if u['id'] == self.medico_origen or u.get('is_superuser'):
                continue
            medico = u.get('rol') == 'medico'
            usuario = U.objects.create(
                username=u['username'], password=u['password'], tenant_cuenta=self.tenant, email=u['email'] or '',
                first_name=u['first_name'], last_name=u['last_name'], is_active=u['is_active'],
                telefono=(u.get('telefono') or '')[:25], date_joined=u['date_joined'], debe_cambiar_clave=False)
            m = Membresia.objects.create(usuario=usuario, tenant=self.tenant, rol=Rol.MEDICO if medico else Rol.ASISTENTE,
                                         activa=u['is_active'])
            self._contar('usuarios del equipo')
            if not medico:
                continue
            with usando_tenant(self.tenant):
                perfil = PerfilProfesional.todos.create(
                    membresia=m, tenant=self.tenant, especialidad=self.perfil.especialidad, activo=True,
                    titulo='Dra.' if (u.get('sexo') or '').upper().startswith('F') else 'Dr.',
                    credenciales=(u.get('credenciales') or '')[:largo('credenciales')],
                    numero_mpps=(u.get('numero_mpps') or '')[:largo('numero_mpps')])
                self._imagen(perfil.firma, u.get('firma_public_id'), 'firma')
                self._imagen(perfil.sello, u.get('sello_public_id'), 'sello')
                self._imagen(perfil.membrete, u.get('banner_public_id'), 'banner')
                perfil.usar_membrete_propio = bool(u.get('usar_banner') and perfil.membrete)
                perfil.save()
            _asegurar_plantillas(perfil)
            self.perfiles[u['id']] = perfil

    def _perfil_de(self, r):
        return self.perfiles.get(r.get('medico_id')) or self.perfil

    def _perfil_cita(self, r):
        """Ginea no guarda médico en la cita: el de su consulta; si no, el de la última consulta de la paciente."""
        if not hasattr(self, '_medico_por_cita'):
            self._medico_por_cita, self._medico_por_paciente = {}, {}
            for c in self.leer('select cita_id, paciente_id, medico_id from consultas_consulta where tenant_id=%s '
                               'and medico_id is not null order by fecha, id', [self.t['id']]):
                if c['cita_id']:
                    self._medico_por_cita[c['cita_id']] = c['medico_id']
                self._medico_por_paciente[c['paciente_id']] = c['medico_id']
        medico = self._medico_por_cita.get(r['id']) or self._medico_por_paciente.get(r['paciente_id'])
        return self.perfiles.get(medico) or self.perfil

    def _pacientes(self):
        super()._pacientes()
        from apps.pacientes.models import Paciente
        filas = self.leer('select id, estado_civil, ocupacion from pacientes_paciente where tenant_id=%s', [self.t['id']])
        for r in filas:
            p = self.pacientes.get(r['id'])
            ec = ESTADO_CIVIL.get(r.get('estado_civil') or '')
            instruccion = opcion(r.get('nivel_instruccion')) or ''
            if instruccion not in dict(Paciente.INSTRUCCION):
                instruccion = ''
            if p is not None and (ec or r.get('ocupacion') or instruccion):
                Paciente.objects.filter(pk=p.pk).update(estado_civil=ec or '', ocupacion=(r.get('ocupacion') or '')[:100],
                                                        nivel_instruccion=instruccion)

    def _ficha(self, p, r):
        from apps.clinica.consultas import _guardar_paciente
        fam = [k for k, c in (('CA_MAMA', 'antec_cancer_mama'), ('CA_CUELLO', 'antec_cancer_cuello'),
                              ('DIABETES', 'antec_diabetes'), ('HTA', 'antec_hipertension')) if r.get(c)]
        g = [r.get(k) or 0 for k in ('gestas', 'partos', 'cesareas', 'abortos')]
        hay_gineco = any(g) or any(r.get(k) for k in ('menarquia', 'fur', 'fecha_ultimo_parto', 'ciclo_dias'))
        vih = r.get('vih_resultado')
        ciclo = r.get('ciclo_dias')
        valores = {
            'nucleo.antecedentes': {'alergias': r.get('alergias'), 'medicacion_actual': r.get('medicacion_actual'),
                                    'enfermedades_cronicas': r.get('enfermedades_cronicas'),
                                    'cirugias': r.get('cirugias_previas')},
            'go.habitos': {'tabaquismo': si(r.get('tabaquismo')), 'alcohol': si(r.get('alcoholismo')),
                           'transfusiones': si(r.get('transfusiones'))},
            'go.familiares': {'antecedentes': fam, 'autoinmunes': r.get('antec_autoinmunes'),
                              'geneticas': r.get('antec_geneticas'), 'otros': r.get('antec_otros')},
            'go.gineco': {
                'menarquia': r.get('menarquia'), 'histerectomia': si(r.get('histerectomia')),
                # En Ginea «Duración del ciclo» se usó casi siempre para la duración del sangrado (3–7 días)
                'ciclo_dias': ciclo if ciclo and ciclo >= 10 else None,
                'ciclo_regular': ('si' if r.get('ciclo_regular') else 'no') if (
                    ciclo or r.get('ciclo_caracteristicas')) else None,
                'fur': r.get('fur'),
                'ciclo_caracteristicas': texto(f'Duración: {ciclo} días' if ciclo and ciclo < 10 else '',
                                               r.get('ciclo_caracteristicas'), sep='. '),
                **({'gestas': g[0], 'partos': g[1], 'cesareas': g[2], 'abortos': g[3]} if hay_gineco else {}),
                'fecha_ultimo_parto': r.get('fecha_ultimo_parto'),
                'citologia_fecha': r.get('ultima_citologia_fecha'),
                'citologia_resultado': r.get('ultima_citologia_resultado'),
                'citologia_hace': r.get('ultima_citologia_hace'),
                'vph_diagnostico': si(r.get('vph_diagnostico')), 'vph_vacuna': si(r.get('vph_vacuna')),
                'vih_resultado': opcion(vih) if (vih and vih != 'no_realizado') or r.get('vih_fecha') else None,
                'vih_fecha': r.get('vih_fecha'), 'its_previas': r.get('its_previas'),
                'inicio_vida_sexual': r.get('inicio_vida_sexual'), 'num_parejas': r.get('num_parejas'),
                'dispareunia': si(r.get('dispareunia')), 'menopausia': si(r.get('menopausia')),
                'menopausia_edad': r.get('menopausia_edad'), 'menopausia_sintomas': r.get('menopausia_sintomas')},
            'go.planificacion': {
                'metodo': r.get('metodo_anticonceptivo'), 'tiempo_uso': r.get('metodo_tiempo_uso'),
                'metodos_anteriores': r.get('metodos_anteriores'), 'deseo_embarazo': si(r.get('deseo_embarazo')),
                'ligadura': si(r.get('ligadura')), 'diu_tipo': r.get('diu_tipo'), 'diu_fecha': r.get('diu_fecha')},
            'go.observaciones': {'observaciones': r.get('observaciones')},
        }
        for codigo, datos in valores.items():
            item = self.items_ficha.get(codigo)
            if item is None:
                continue
            limpio = self._limpiar(item, datos, {'paciente': p, 'sexo': p.sexo}, f"paciente n.º {r['id']} de Ginea")
            if limpio:
                _guardar_paciente(None, item, limpio, paciente=p)

    def _plantilla(self, r):
        return 'Control prenatal' if r.get('es_prenatal') else self.PLANTILLA

    def _valores_consulta(self, r):
        sis, dia = tension(r.get('tension_arterial'))
        if r.get('tension_arterial') and sis is None:
            self.avisos.append(f"Consulta {r['id']}: TA «{r['tension_arterial']}» no se pudo separar (va al plan).")
        diag = (r.get('diagnostico') or '').strip()
        prenatal_nota = ''
        if r.get('es_prenatal') and (r.get('semanas_gestacion') or r.get('fpp')):
            # Ordo calcula EG y FPP desde FUR/eco; lo que Ginea guardó queda escrito tal cual
            prenatal_nota = texto(r.get('semanas_gestacion') and f"EG registrada: {r['semanas_gestacion']} semanas",
                                  r.get('fpp') and f"FPP registrada: {r['fpp']:%d/%m/%Y}", sep=' · ')
        edemas = r.get('edemas')
        pres = PRESENTACION.get(sin_acentos(r.get('presentacion_fetal')))
        return {
            'go.tipo': {'tipo': 'PRENATAL' if r.get('es_prenatal') else 'GINECOLOGICA'},
            'nucleo.signos_vitales': {'peso_kg': r.get('peso'), 'pa_sistolica': sis, 'pa_diastolica': dia},
            'nucleo.motivo': {'motivo': r.get('motivo_consulta'), 'enfermedad_actual': r.get('sintomas_actuales')},
            'nucleo.examen_fisico': {'general': r.get('examen_fisico')},
            'go.estudios': {'ecografia': r.get('ecografia'), 'colposcopia': r.get('colposcopia'),
                            'imagenes': r.get('imagenes'), 'laboratorio': None if r.get('es_prenatal')
                            else r.get('laboratorio')},
            'nucleo.diagnosticos': {'diagnosticos': [{'descripcion': diag[:250]}] if diag else []},
            'nucleo.plan': {'plan': r.get('tratamiento'), 'indicaciones': r.get('indicaciones'),
                            'proximo_control': r.get('proxima_cita')},
            'nucleo.ordenes': {'laboratorio': r.get('examenes_solicitados')},
            'go.prenatal': {
                'altura_uterina': r.get('altura_uterina'), 'fcf': r.get('fcf'),
                'presentacion': pres,
                'edemas': 'NO' if edemas is False else None,      # «sí» sin grado: va a observaciones
                'laboratorio': r.get('laboratorio') if r.get('es_prenatal') else None,
            } if r.get('es_prenatal') else {},
            'go.notas': {'observaciones': texto(
                r.get('observaciones'), prenatal_nota,
                f"Presentación registrada: {r['presentacion_fetal']}" if (r.get('presentacion_fetal') and not pres)
                else '',
                'Edemas: sí' if edemas else '',
                f"TA: {r['tension_arterial']}" if (r.get('tension_arterial') and sis is None) else '',
                r.get('notas_pago') and f"Pago: {r['notas_pago']}")},
        }

    def _glosario(self):
        from apps.clinica.models import Medicamento
        for r in self.leer('select * from consultas_medicamento where tenant_id=%s order by orden, id', [self.t['id']]):
            Medicamento.objects.create(profesional=self.perfil, nombre=r['nombre'][:150], modo=Medicamento.Modo.FIJA,
                                       indicaciones=r.get('indicaciones') or '', activo=r['activo'])
            self._contar('medicamentos del glosario')

    def _vacunas_y_pesquisas(self):
        pass

    def _procedimientos(self):
        from apps.clinica.models import Procedimiento
        for r in self.leer('select * from consultas_procedimiento where tenant_id=%s order by fecha, id', [self.t['id']]):
            p = self.pacientes.get(r['paciente_id'])
            if p is None:
                continue
            serv = self.servicios.get(r.get('servicio_id'))
            proc = Procedimiento.objects.create(
                paciente=p, profesional=self.perfil, cita=self.citas.get(r.get('cita_id')), fecha=r['fecha'],
                descripcion=(serv.nombre if serv else 'Procedimiento')[:200], notas=r.get('notas') or '')
            self._contar('procedimientos')
            linea = {'servicio_id': r.get('servicio_id'), 'precio_usd': r.get('precio_usd') or Decimal('0'),
                     'tasa_cambio': r.get('tasa_cambio')}
            self._cobros(p, r, [linea], procedimiento=proc)
