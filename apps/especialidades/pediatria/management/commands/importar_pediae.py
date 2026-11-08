"""
Migra UN consultorio de Pediae a Ordo Salud (Fase 18a, docs/roadmap/18_migracion_pediae.md).

Lee la base de Pediae (solo SELECT) y crea en Ordo Salud: consultorio, médica (con la misma contraseña), configuración,
lugares, servicios, pacientes con sus representantes y ficha pediátrica, citas, consultas cerradas (percentiles
recalculados con OMS), cargos y pagos, adjuntos (Cloudinary → R2), vacunas, pesquisas, glosario y procedimientos.

    python manage.py importar_pediae --origen "postgresql://...pediae..." --slug dra-anaisbaez \\
        --nombres C:\\proyectos\\respaldos\\pediae_nombres.csv --nube <cuenta-cloudinary>

    --ensayo        hace todo y al final deshace (nada queda guardado; los archivos no se suben)
    --sin-archivos  no descarga de Cloudinary (adjuntos e imágenes quedan fuera)

Todo va en una transacción: si algo falla, no queda nada a medias. Si el consultorio ya existe en Ordo Salud, se detiene.
"""
import contextlib
import csv
import re
import unicodedata
from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

SECCIONES_FICHA = ['nucleo.antecedentes', 'ped.perinatales', 'ped.alimentacion', 'ped.desarrollo_hitos', 'ped.entorno',
                   'ped.familiares', 'ped.patologicos']
ESTADOS_CITA = {'tentativa': 'TENTATIVA', 'programada': 'PROGRAMADA', 'confirmada': 'CONFIRMADA',
                'en_sala': 'EN_SALA', 'atendida': 'ATENDIDA', 'cancelada': 'CANCELADA', 'no_asistio': 'NO_ASISTIO'}
PARENTESCO = {'madre': 'MADRE', 'padre': 'PADRE', 'abuelo': 'ABUELO', 'abuela': 'ABUELO', 'tio': 'TIO', 'tia': 'TIO',
              'hermano': 'HERMANO', 'hermana': 'HERMANO', 'tutor': 'TUTOR'}


class Fallo(Exception):
    pass


def sin_acentos(t):
    return unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode().lower().strip()


def opcion(valor):
    """'estreñimiento' → 'ESTRENIMIENTO'; vacío → None."""
    v = sin_acentos(str(valor or '')).replace(' ', '_')
    return v.upper() or None


def si_no(valor):
    return None if valor is None else ('si' if valor else 'no')


def texto(*partes, sep='\n'):
    return sep.join(str(p).strip() for p in partes if p not in (None, '') and str(p).strip())


def documento(cedula):
    """'V-12.345.678' → ('V', '12345678'); vacío → ('', '')."""
    c = (cedula or '').strip().upper().replace('.', '').replace(' ', '')
    m = re.match(r'^([VEP])-?(\d+)$', c)
    if m:
        return m.group(1), m.group(2)
    digitos = re.sub(r'\D', '', c)
    return ('V', digitos) if digitos else ('', '')


def tension(ta):
    m = re.match(r'^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$', ta or '')
    return (m.group(1), m.group(2)) if m else (None, None)


class Command(BaseCommand):
    help = 'Migra un consultorio de Pediae a Ordo Salud.'

    def add_arguments(self, parser):
        parser.add_argument('--origen', required=True, help='URL de la base PostgreSQL de Pediae (solo lectura).')
        parser.add_argument('--slug', required=True, help='Consultorio de Pediae (también será el enlace nuevo).')
        parser.add_argument('--nombres', required=True, help='CSV revisado con nombres/apellidos (punto y coma).')
        parser.add_argument('--cloudinary', help='Archivo con CLOUDINARY_URL=cloudinary://KEY:SECRET@CLOUD.')
        parser.add_argument('--nube', help='O solo el nombre de la cuenta de Cloudinary (los archivos son públicos).')
        parser.add_argument('--sin-archivos', action='store_true')
        parser.add_argument('--ensayo', action='store_true', help='Deshace todo al final.')

    # ── Lectura de Pediae ───────────────────────────────────────────────────────────────────────────────────────
    def leer(self, sql, params=()):
        with self.con.cursor() as cur:
            cur.execute(sql, params)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, fila, strict=True)) for fila in cur.fetchall()]

    def handle(self, origen, slug, nombres, cloudinary, nube, sin_archivos, ensayo, **op):
        import psycopg

        from apps.clinica import registro
        self.avisos, self.cuenta, self.descartados = [], {}, []
        self.nombres = self._leer_nombres(nombres)
        self.cloud = None if (sin_archivos or ensayo) else (nube or self._cloud(cloudinary))
        self.con = psycopg.connect(origen)
        self.con.read_only = True
        t = self.leer('select * from tenant_tenant where slug=%s', [slug])
        if not t:
            raise CommandError(f'No existe «{slug}» en Pediae.')
        self.t = t[0]
        from apps.plataforma.models import Tenant
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f'«{slug}» ya existe en Ordo Salud: no se migra dos veces.')
        # «Próximo control» crea citas tentativas: en la migración no (las citas vienen de Pediae).
        gancho_plan = registro._al_guardar.pop('nucleo.plan', None)
        try:
            with transaction.atomic():
                self._migrar()
                self._resumen()
                if ensayo:
                    raise Fallo('ensayo')
        except Fallo:
            self.stdout.write(self.style.WARNING('ENSAYO: se deshizo todo; no quedó nada guardado.'))
        finally:
            if gancho_plan:
                registro._al_guardar['nucleo.plan'] = gancho_plan
            self.con.close()

    def _leer_nombres(self, ruta):
        try:
            with open(ruta, encoding='utf-8-sig') as f:
                filas = list(csv.DictReader(f, delimiter=';'))
        except OSError as e:
            raise CommandError(f'No se pudo leer {ruta}: {e}') from e
        salida = {}
        for fila in filas:
            n, a = (fila.get('nombres') or '').strip(), (fila.get('apellidos') or '').strip()
            if not n:
                raise CommandError(f"Paciente {fila.get('id_pediae')}: falta «nombres» en el CSV.")
            salida[int(fila['id_pediae'])] = (n, a)
        return salida

    def _cloud(self, ruta):
        if not ruta:
            raise CommandError('Falta --nube o --cloudinary (o usa --sin-archivos).')
        with open(ruta, encoding='utf-8-sig') as f:
            lineas = f.read().splitlines()
        for linea in lineas:
            if linea.strip().startswith('CLOUDINARY_URL='):
                return linea.split('@')[-1].strip().strip('"\'')
        raise CommandError(f'{ruta} no tiene CLOUDINARY_URL.')

    def _contar(self, clave, n=1):
        self.cuenta[clave] = self.cuenta.get(clave, 0) + n

    # ── Archivos de Cloudinary ──────────────────────────────────────────────────────────────────────────────────
    def descargar(self, public_id, tipo='image'):
        """(bytes, content_type) o None. Los archivos de Pediae son públicos: basta el nombre de la cuenta."""
        import requests
        if not self.cloud or not public_id:
            return None
        tipos = ['raw', 'image'] if tipo == 'raw' else ['image', 'raw']
        for t in tipos:
            r = requests.get(f'https://res.cloudinary.com/{self.cloud}/{t}/upload/{public_id}', timeout=60)
            if r.status_code == 200 and r.content:
                return r.content, r.headers.get('Content-Type', '')
        self.avisos.append(f'Archivo no encontrado en Cloudinary: {public_id}')
        return None

    def _imagen(self, campo, public_id, nombre):
        datos = self.descargar(public_id)
        if datos:
            ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(datos[1].split(';')[0], '.png')
            campo.save(f'{nombre}{ext}', ContentFile(datos[0]), save=False)
            self._contar('imágenes de perfil')

    # ── Migración ───────────────────────────────────────────────────────────────────────────────────────────────
    def _migrar(self):
        from apps.core.tenancy import usando_tenant
        self._consultorio()
        with usando_tenant(self.tenant):
            self._lugares_y_servicios()
            self._pacientes()
            self._glosario()
            self._citas()
            self._consultas()
            self._vacunas_y_pesquisas()
            self._procedimientos()

    def _consultorio(self):
        from apps.configuracion.models import ConfiguracionTenant
        from apps.plataforma import servicios as plataforma
        from apps.plataforma.models import Especialidad
        tid = self.t['id']
        medicos = self.leer('select * from accounts_usuario where tenant_id=%s order by id', [tid])
        if len(medicos) != 1:
            raise CommandError(f'Se esperaba 1 usuario en «{self.t["slug"]}» y hay {len(medicos)}.')
        u = medicos[0]
        self.medico_origen = u['id']
        cfg = (self.leer('select * from configuracion_configconsultorio where tenant_id=%s', [tid]) or [{}])[0]
        esp = Especialidad.objects.get(codigo='pediatria')
        titulo = 'Dra.' if (u.get('sexo') or '').upper().startswith('F') else 'Dr.'
        self.tenant, titular, _ = plataforma.crear_tenant({
            'nombre': (cfg.get('nombre_consultorio') or self.t['nombre'])[:150], 'slug': self.t['slug'],
            'usuario_titular': u['username'], 'nombre_titular': u['first_name'], 'apellido_titular': u['last_name'],
            'email_titular': u['email'], 'titular_es_profesional': True, 'especialidad_titular': esp,
            'titulo_titular': titulo, 'especialidades': [esp], 'notas': 'Migrado de Pediae.'})
        # Misma contraseña que en Pediae (mismo formato de Django): entra con su clave de siempre.
        get_user_model().objects.filter(pk=titular.pk).update(
            password=u['password'], debe_cambiar_clave=False, telefono=(u.get('telefono') or '')[:25],
            date_joined=u['date_joined'])
        self.usuario = titular
        from apps.equipo.models import PerfilProfesional
        self.perfil = PerfilProfesional.todos.get(membresia__usuario=titular)
        p = self.perfil
        p.credenciales = (u.get('credenciales') or '')[:p._meta.get_field('credenciales').max_length]
        p.numero_mpps = (u.get('numero_mpps') or '')[:p._meta.get_field('numero_mpps').max_length]
        p.telefono_consulta = (u.get('telefono') or '')[:p._meta.get_field('telefono_consulta').max_length]
        self._imagen(p.firma, u.get('firma_public_id'), 'firma')
        self._imagen(p.sello, u.get('sello_public_id'), 'sello')
        self._imagen(p.membrete, u.get('banner_public_id'), 'banner')
        p.usar_membrete_propio = bool(u.get('usar_banner') and p.membrete)
        p.save()
        c = ConfiguracionTenant.objects.get(tenant=self.tenant)
        c.nombre_mostrar = (cfg.get('nombre_consultorio') or '')[:150]
        c.direccion = cfg.get('direccion') or ''
        c.telefono = (cfg.get('telefono') or '')[:40]
        c.email = cfg.get('email') or ''
        c.whatsapp = re.sub(r'\D', '', cfg.get('whatsapp_numero') or '')[:20]
        c.mensaje_whatsapp = cfg.get('whatsapp_mensaje') or ''
        if re.match(r'^#[0-9A-Fa-f]{6}$', cfg.get('color_primario') or ''):
            c.color_primario = cfg['color_primario']
        c.hora_inicio_agenda, c.hora_fin_agenda = cfg.get('horario_inicio'), cfg.get('horario_fin')
        if cfg.get('duracion_cita_minutos'):
            c.duracion_cita_min = cfg['duracion_cita_minutos']
        self._imagen(c.logo, cfg.get('logo_public_id'), 'logo')
        self._imagen(c.membrete, cfg.get('membrete_public_id'), 'membrete')
        c.save()
        self._contar('consultorio')

    def _lugares_y_servicios(self):
        from apps.cobros.models import Servicio
        from apps.configuracion.models import Lugar
        tid = self.t['id']
        self.lugares = {}
        for r in self.leer('select * from agenda_lugarconsulta where tenant_id=%s order by orden, id', [tid]):
            self.lugares[r['id']] = Lugar.objects.create(
                nombre=r['nombre'][:100], ciudad=(r.get('ciudad') or '')[:100], direccion=(r.get('direccion') or '')[:200],
                telefono=(r.get('telefono') or '')[:40], activo=r['activo'], orden=r.get('orden') or 0)
            self._contar('lugares')
        self.servicios = {}
        for r in self.leer('select * from servicios_servicio where tenant_id=%s order by id', [tid]):
            nombre, n = r['nombre'][:150], 2
            while Servicio.objects.filter(nombre=nombre).exists():
                nombre, n = f"{r['nombre'][:140]} ({n})", n + 1
            self.servicios[r['id']] = Servicio.objects.create(
                nombre=nombre, descripcion=(r.get('descripcion') or '')[:250], precio_usd=r['precio_usd'] or 0,
                costo_usd=r.get('costo_adquisicion_usd'), activo=r['activo'])
            self._contar('servicios')

    # ── Pacientes y ficha ───────────────────────────────────────────────────────────────────────────────────────
    def _pacientes(self):
        from apps.clinica import esquemas
        from apps.clinica.consultas import items_ficha
        from apps.clinica.models import SeccionClinica
        from apps.pacientes.models import Paciente, Representante
        self.pacientes = {}
        items = {i['codigo']: i for i in items_ficha('pediatria')}
        ant = SeccionClinica.objects.visibles().get(codigo='nucleo.antecedentes')
        items['nucleo.antecedentes'] = {'seccion_id': ant.pk, 'codigo': ant.codigo, 'nombre': ant.nombre,
                                        'version': ant.version, 'ambito': 'PACIENTE',
                                        'campos': esquemas.campos_efectivos(ant.esquema)}
        self.items_ficha = items
        filas = self.leer('select * from pacientes_paciente where tenant_id=%s order by id', [self.t['id']])
        faltan = [r['id'] for r in filas if r['id'] not in self.nombres]
        if faltan:
            raise CommandError(f'El CSV de nombres no tiene {len(faltan)} pacientes (ids {faltan[:5]}…).')
        for r in filas:
            nombres, apellidos = self.nombres[r['id']]
            tipo, numero = documento(r.get('cedula'))
            if r.get('no_cedulado') or not numero:
                tipo, numero = 'N', ''
            gs = r.get('grupo_sanguineo') or ''
            p = Paciente.objects.create(
                nombres=nombres[:120], apellidos=apellidos[:120], sexo=(r.get('sexo') or '')[:1].upper(),
                fecha_nacimiento=r.get('fecha_nacimiento'), tipo_documento=tipo, numero_documento=numero,
                telefono=(r.get('telefono') or '')[:25], email=r.get('email') or '',
                direccion=(r.get('direccion') or '')[:250], contacto_emergencia=(r.get('contacto_emergencia') or '')[:150],
                seguro=(r.get('seguro_medico') or '')[:100], grupo_sanguineo=gs if gs in dict(
                    Paciente.Grupo.choices) else '', observaciones=f"Migrado de Pediae (n.º {r['id']}).")
            Paciente.objects.filter(pk=p.pk).update(creado_en=r['creado_en'])
            self.pacientes[r['id']] = p
            self._contar('pacientes')
            self._representantes(p, r, Representante)
            self._ficha(p, r)

    def _representantes(self, p, r, Representante):
        principal = (r.get('nombre_representante') or '').strip()
        nombres_hechos = set()
        if principal:
            tipo, numero = documento(r.get('cedula_representante'))
            filiacion = sin_acentos(r.get('filiacion_representante') or r.get('parentesco_representante') or '')
            Representante.objects.create(
                paciente=p, nombre=principal[:150], parentesco=PARENTESCO.get(filiacion, 'OTRO'),
                tipo_documento=tipo, numero_documento=numero, telefono=(r.get('telefono_representante') or '')[:25],
                ocupacion=(r.get('ocupacion_representante') or '')[:100], es_principal=True)
            nombres_hechos.add(sin_acentos(principal))
            self._contar('representantes')
        for campo, parentesco, ocup in (('nombre_madre', 'MADRE', 'ocupacion_madre'),
                                        ('nombre_padre', 'PADRE', 'ocupacion_padre')):
            nombre = (r.get(campo) or '').strip()
            if nombre and sin_acentos(nombre) not in nombres_hechos:
                Representante.objects.create(paciente=p, nombre=nombre[:150], parentesco=parentesco,
                                             ocupacion=(r.get(ocup) or '')[:100], es_principal=not nombres_hechos)
                nombres_hechos.add(sin_acentos(nombre))
                self._contar('representantes')

    def _ficha(self, p, r):
        from apps.clinica.consultas import _guardar_paciente
        fam = [k for k, c in (('DIABETES', 'antec_diabetes'), ('HTA', 'antec_hipertension'),
                              ('CARDIOPATIAS', 'antec_cardiopatias'), ('EPILEPSIA', 'antec_epilepsia'),
                              ('ASMA_ATOPIA', 'antec_asma_atopia'), ('ONCOLOGICO', 'antec_oncologico')) if r.get(c)]
        compl = [k for k, c in (('OLIGOAMNIOS', 'complicacion_oligoamnios'), ('PREECLAMPSIA', 'complicacion_preeclampsia'),
                                ('INFECCIONES', 'complicacion_infecciones')) if r.get(c)]
        neo = [k for k, c in (('ICTERICIA', 'neonatal_ictericia'), ('SEPSIS', 'neonatal_sepsis'),
                              ('DIF_RESP', 'neonatal_dificultad_respiratoria')) if r.get(c)]
        valores = {
            'nucleo.antecedentes': {'alergias': r.get('alergias'), 'medicacion_actual': r.get('medicacion_actual'),
                                    'enfermedades_cronicas': r.get('enfermedades_cronicas'),
                                    'cirugias': r.get('cirugias_previas'),
                                    'otros': texto(r.get('antec_otros'), r.get('observaciones'))},
            'ped.familiares': {'antecedentes': fam, 'oncologico_rama': opcion(r.get('antec_oncologico_rama')),
                               'autoinmunes': r.get('antec_autoinmunes'), 'geneticas': r.get('antec_geneticas')},
            'ped.perinatales': {
                'edad_materna': r.get('edad_materna_embarazo'), 'numero_gestacion': r.get('numero_gestacion'),
                'control_prenatal': si_no(r.get('control_prenatal')),
                'consultas_prenatales': r.get('num_consultas_prenatales'), 'complicaciones_embarazo': compl,
                'complicacion_otra': r.get('complicacion_embarazo_otra'),
                'semanas_gestacion': r.get('semanas_gestacion'), 'via_parto': opcion(r.get('via_parto')),
                'indicacion_cesarea': r.get('indicacion_cesarea'), 'peso_nacer_g': r.get('peso_nacer'),
                'talla_nacer_cm': r.get('talla_nacer'),
                'complicaciones_neonatales': si_no(r.get('complicaciones_neonatales')), 'neonatales': neo,
                'neonatal_otra': r.get('neonatal_otra_complicacion'), 'onfalorrexis': opcion(r.get('onfalorrexis')),
                'prueba_talon': opcion(r.get('prueba_talon')), 'prueba_talon_detalle': r.get('prueba_talon_detalle'),
                'notas': texto(r.get('antec_embarazo'), r.get('antec_parto'), r.get('antec_neonatal'))},
            'ped.alimentacion': {
                'lme': si_no(r.get('lme')), 'lme_meses': r.get('lme_meses'), 'formula': si_no(r.get('uso_formula')),
                'formula_nombre': r.get('nombre_formula'), 'formula_causa': opcion(r.get('causa_formula')),
                'alimentacion_actual': opcion(r.get('alimentacion_actual')),
                'alimentacion_detalle': r.get('alimentacion_actual_detalle'), 'notas': r.get('antec_alimentacion')},
            'ped.desarrollo_hitos': {
                'neuromotor_adecuado': si_no(r.get('desarrollo_psicomotor_adecuado')),
                'esfinter_vesical': si_no(r.get('esfinter_vesical_logrado')),
                'esfinter_vesical_edad': r.get('esfinter_vesical_edad'),
                'esfinter_anal': si_no(r.get('esfinter_anal_logrado')), 'esfinter_anal_edad': r.get('esfinter_anal_edad'),
                'notas': texto(r.get('desarrollo_area_afectada'), r.get('antec_desarrollo'))},
            'ped.entorno': {
                'edad_madre': r.get('edad_madre'), 'ocupacion_madre': r.get('ocupacion_madre'),
                'edad_padre': r.get('edad_padre'), 'ocupacion_padre': r.get('ocupacion_padre'),
                'patron_sueno': opcion(r.get('patron_sueno')), 'patron_evacuacion': opcion(r.get('patron_evacuacion')),
                'patron_miccion': opcion(r.get('patron_miccion')), 'tabaquismo_pasivo': si_no(r.get('tabaquismo_pasivo')),
                'agua': opcion(r.get('agua_consumo')), 'mascotas': si_no(r.get('mascotas')),
                'mascotas_tipo': r.get('mascotas_tipo')},
            'ped.patologicos': {
                'traumatismos': si_no(r.get('traumatismos')), 'traumatismos_detalle': r.get('traumatismos_detalle'),
                'exantematicas': si_no(r.get('enfermedades_exantematicas')),
                'exantematicas_detalle': r.get('exantematicas_detalle')},
        }
        for codigo, datos in valores.items():
            item = self.items_ficha.get(codigo)
            if item is None:
                continue
            limpio = self._limpiar(item, datos, {'paciente': p, 'sexo': p.sexo}, f"paciente n.º {r['id']} de Pediae")
            if limpio:
                _guardar_paciente(None, item, limpio, paciente=p)

    def _limpiar(self, item, datos, contexto, donde):
        """Valida con el mismo formulario de la historia; lo que no pasa se quita y se avisa."""
        from apps.clinica.formularios import FormularioSeccion
        prefijo = f"s{item['seccion_id']}"
        post = {}
        for k, v in datos.items():
            if v in (None, '', []):
                continue
            if isinstance(v, list):
                if v and isinstance(v[0], dict):            # tabla
                    for i, fila in enumerate(v):
                        for sub, val in fila.items():
                            post[f'{prefijo}-{k}__{i}__{sub}'] = str(val)
                else:
                    post[f'{prefijo}-{k}'] = v
            else:
                post[f'{prefijo}-{k}'] = str(v)
        if not post:
            return {}
        from django.utils.datastructures import MultiValueDict
        data = MultiValueDict({k: (v if isinstance(v, list) else [v]) for k, v in post.items()})
        for _ in range(2):
            form = FormularioSeccion(item['campos'], data, prefix=prefijo, contexto=contexto, exigir_requeridos=False)
            if form.is_valid():
                return {k: v for k, v in form.datos_limpios.items() if v not in (None, '', [])}
            for campo in form.errors:
                clave = f'{prefijo}-{campo}'
                if clave in data:
                    self.descartados.append(f"{item['nombre']} · {campo} = {data.get(clave)}")
                    self.avisos.append(f"{donde} · {item['nombre']} · {campo} = «{data.get(clave)}»: no se cargó "
                                       f"({'; '.join(form.errors[campo])})")
                    del data[clave]
        return {}

    # ── Glosario, citas ─────────────────────────────────────────────────────────────────────────────────────────
    def _glosario(self):
        from apps.clinica.models import Medicamento
        for r in self.leer('select * from consultas_medicamento where tenant_id=%s order by orden, id', [self.t['id']]):
            modo = {'peso': 'PESO', 'fija': 'FIJA', 'edad': 'EDAD'}.get((r.get('modo_calculo') or 'peso').lower(), 'PESO')
            rangos = [{'min': r.get(f'rango{i}_edad_min'), 'max': r.get(f'rango{i}_edad_max'),
                       'dosis': r.get(f'rango{i}_dosis')} for i in (1, 2, 3) if r.get(f'rango{i}_dosis')]
            Medicamento.objects.create(
                profesional=self.perfil, nombre=r['nombre'][:150], presentacion=(r.get('presentacion') or '')[:150],
                modo=modo, unidad_kg=r.get('unidad_dosis_kg') or 'mg', dosis_kg_min=r.get('dosis_mg_kg_min'),
                dosis_kg_max=r.get('dosis_mg_kg_max'), concentracion_mg=r.get('concentracion_mg'),
                volumen_ml=r.get('volumen_ml'), unidad_resultado=r.get('unidad_resultado') or 'mg',
                dosis_max=r.get('dosis_max_absoluta'), dosis_fija=(r.get('dosis_fija') or '')[:150],
                rangos_edad=rangos, frecuencia_horas=r.get('frecuencia_horas'), duracion_dias=r.get('duracion_dias'),
                indicaciones=r.get('indicaciones') or '', edad_min_meses=r.get('edad_min_meses'),
                edad_max_meses=r.get('edad_max_meses'), peso_min_kg=r.get('peso_min_kg'), activo=r['activo'])
            self._contar('medicamentos del glosario')

    def _citas(self):
        from apps.agenda.models import Cita
        self.citas = {}
        for r in self.leer('select * from agenda_cita where tenant_id=%s order by id', [self.t['id']]):
            p = self.pacientes.get(r['paciente_id'])
            if p is None:
                continue
            try:
                with transaction.atomic():
                    c = Cita.objects.create(
                        paciente=p, profesional=self.perfil, especialidad=self.perfil.especialidad,
                        lugar=self.lugares.get(r.get('lugar_id')), fecha=r['fecha'], hora_inicio=r.get('hora_inicio'),
                        hora_fin=r.get('hora_fin'), estado=ESTADOS_CITA.get(r.get('estado'), 'PROGRAMADA'),
                        motivo=(r.get('motivo') or '')[:200], notas=r.get('notas') or '')
                    Cita.objects.filter(pk=c.pk).update(creado_en=r['creado_en'])
            except IntegrityError as e:
                self.avisos.append(f"Cita {r['id']} del {r['fecha']}: no se pudo crear ({e.__class__.__name__}).")
                continue
            self.citas[r['id']] = c
            self._contar('citas')

    # ── Consultas, cobros, adjuntos ─────────────────────────────────────────────────────────────────────────────
    def _consultas(self):
        from apps.clinica import consultas as srv
        from apps.clinica.models import Consulta, PlantillaHistoria
        plantilla = PlantillaHistoria.objects.get(nombre='Consulta pediátrica', profesional__isnull=True)
        vistos = set()
        filas = self.leer('select * from consultas_consulta where tenant_id=%s order by fecha, id', [self.t['id']])
        servicios = {}
        for s in self.leer('select cs.* from consultas_consultaservicio cs join consultas_consulta c on c.id=cs.consulta_id '
                           'where c.tenant_id=%s order by cs.id', [self.t['id']]):
            servicios.setdefault(s['consulta_id'], []).append(s)
        adjuntos = {}
        for a in self.leer('select a.* from consultas_adjuntoconsulta a join consultas_consulta c on c.id=a.consulta_id '
                           'where c.tenant_id=%s order by a.id', [self.t['id']]):
            adjuntos.setdefault(a['consulta_id'], []).append(a)
        for r in filas:
            p = self.pacientes.get(r['paciente_id'])
            if p is None:
                self.avisos.append(f"Consulta {r['id']}: paciente {r['paciente_id']} no encontrado; no se migró.")
                continue
            creada = timezone.localtime(r['creado_en'])
            hora = creada.time() if creada.date() == r['fecha'] else time(9, 0)
            fecha_hora = timezone.make_aware(datetime.combine(r['fecha'], hora))
            tipo = Consulta.Tipo.CONTROL if p.pk in vistos else Consulta.Tipo.PRIMERA
            vistos.add(p.pk)
            c = srv.abrir_consulta(paciente=p, profesional=self.perfil, plantilla=plantilla, tipo=tipo,
                                   lugar=self.lugares.get(r.get('lugar_id')), fecha_hora=fecha_hora)
            self._secciones_consulta(c, r)
            cita = self.citas.get(r.get('cita_id'))
            if cita is not None and cita.consulta_id is None:
                cita.consulta = c
                cita.estado = 'ATENDIDA'
                cita.save(update_fields=['consulta', 'estado'])
            with contextlib.suppress(Exception), transaction.atomic():
                srv.cerrar_consulta(c)
            Consulta.objects.filter(pk=c.pk).update(estado=Consulta.Estado.CERRADA, cerrada_en=fecha_hora,
                                                    creado_en=r['creado_en'])
            self._contar('consultas')
            self._cobros(p, r, servicios.get(r['id'], []), consulta=c)
            for a in adjuntos.get(r['id'], []):
                self._adjunto(p, c, a)

    def _secciones_consulta(self, c, r):
        from apps.clinica import consultas as srv
        sis, dia = tension(r.get('tension_arterial'))
        if r.get('tension_arterial') and sis is None:
            self.avisos.append(f"Consulta {r['id']}: TA «{r['tension_arterial']}» no se pudo separar (va al plan).")
        diag = (r.get('diagnostico') or '').strip()
        valores = {
            'ped.tipo': {'tipo': opcion(r.get('tipo_consulta'))},
            'ped.antropometria': {'peso_kg': r.get('peso'), 'talla_cm': r.get('talla'),
                                  'pc_cm': r.get('perimetro_cefalico')},
            'nucleo.signos_vitales': {'pa_sistolica': sis, 'pa_diastolica': dia, 'fc': r.get('frecuencia_cardiaca'),
                                      'fr': r.get('frecuencia_respiratoria'), 'temperatura': r.get('temperatura'),
                                      'spo2': r.get('saturacion_oxigeno')},
            'nucleo.motivo': {'motivo': r.get('motivo_consulta'), 'enfermedad_actual': r.get('sintomas_actuales')},
            'nucleo.examen_fisico': {'general': r.get('examen_fisico')},
            'ped.desarrollo': {'desarrollo': r.get('desarrollo_psicomotor')},
            'nucleo.diagnosticos': {'diagnosticos': [{'descripcion': diag[:250]}] if diag else []},
            'nucleo.plan': {'indicaciones': texto(r.get('tratamiento'), r.get('indicaciones')),
                            'plan': texto(r.get('observaciones'),
                                          f"TA: {r['tension_arterial']}" if (r.get('tension_arterial') and sis is None)
                                          else '', r.get('notas_pago') and f"Pago: {r['notas_pago']}"),
                            'proximo_control': r.get('proxima_cita')},
            'nucleo.ordenes': {'laboratorio': r.get('laboratorio')},
            'ped.habitos': {
                'tipo_alimentacion': opcion(r.get('tipo_alimentacion')), 'apetito': opcion(r.get('apetito')),
                'comidas_dia': r.get('num_comidas'), 'notas_alimentacion': r.get('notas_alimentacion'),
                'horas_sueno': r.get('horas_sueno_nocturno'), 'siestas': r.get('num_siestas'),
                'duracion_siesta': r.get('duracion_siesta'), 'notas_sueno': r.get('notas_sueno'),
                'deposiciones': opcion(r.get('frecuencia_deposiciones')),
                'consistencia': opcion(r.get('consistencia_deposiciones')),
                'control_esfinteres': si_no(r.get('control_esfinteres')), 'notas_eliminacion': r.get('notas_eliminacion')},
        }
        contexto = srv.contexto_calculo(c)
        salida = {}
        self.descartados = []
        for vuelta in range(2):          # 2.ª vuelta: con signos ya guardados (SC, percentiles con la fecha correcta)
            for item in c.estructura:
                datos = valores.get(item['codigo'])
                if not datos or item['ambito'] == 'PACIENTE':
                    continue
                donde = f"consulta n.º {r['id']} del {r['fecha']:%d/%m/%Y}"
                limpio = self._limpiar(item, datos, contexto, donde) if vuelta == 0 else \
                    self._limpiar_silencioso(item, datos, contexto)
                if limpio:
                    salida[item['seccion_id']] = limpio
            if vuelta == 0 and self.descartados:      # que no se pierda: queda escrito en el plan de esa consulta
                plan = valores['nucleo.plan']
                plan['plan'] = texto(plan['plan'], 'Dato de Pediae fuera de rango (no cargado): '
                                     + '; '.join(self.descartados))
            srv.guardar_secciones(c, salida)
            contexto = srv.contexto_calculo(c)

    def _limpiar_silencioso(self, item, datos, contexto):
        cantidad = len(self.avisos)
        limpio = self._limpiar(item, datos, contexto, '')
        del self.avisos[cantidad:]
        return limpio

    def _cobros(self, p, r, servicios, consulta=None, procedimiento=None):
        from apps.cobros.models import Cargo, Pago, PagoAplicado
        from apps.cobros.servicios import _actualizar_estado
        cargos = []
        for s in servicios:
            serv = self.servicios.get(s.get('servicio_id'))
            precio = Decimal(s.get('precio_usd') or 0)
            descuento = min(Decimal(s.get('descuento_usd') or 0), precio)
            cargo = Cargo.objects.create(
                paciente=p, consulta=consulta, procedimiento=procedimiento, profesional=self.perfil, servicio=serv,
                fecha=r['fecha'], descripcion=(serv.nombre if serv else 'Servicio')[:200], precio_usd=precio,
                descuento_usd=descuento, exonerado=bool(s.get('exonerado')), costo_usd=s.get('costo_adquisicion_usd'),
                tasa=s.get('tasa_cambio') or None)
            _actualizar_estado(cargo)
            cargos.append(cargo)
            self._contar('cargos')
        if not r.get('pagado') or not cargos:
            return
        total = sum((c.saldo_usd for c in cargos), Decimal('0'))
        if total <= 0:
            return
        tasa = next((c.tasa for c in cargos if c.tasa), None)
        pago = Pago.objects.create(paciente=p, fecha=r['fecha'], moneda=Pago.Moneda.USD, monto=total, tasa=tasa,
                                   monto_usd=total, metodo=Pago.Metodo.OTRO,
                                   notas=('Migrado de Pediae. ' + (r.get('notas_pago') or ''))[:200])
        for c in cargos:
            if c.saldo_usd > 0:
                PagoAplicado.objects.create(pago=pago, cargo=c, monto_usd=c.saldo_usd)
                _actualizar_estado(c)
        self._contar('pagos')

    def _adjunto(self, p, c, a):
        from apps.clinica.models import Adjunto
        datos = self.descargar(a['drive_file_id'], 'raw' if a.get('tipo') == 'pdf' else 'image')
        if not datos:
            if self.cloud:
                self.avisos.append(f"Adjunto «{a.get('nombre_original')}» (consulta {a['consulta_id']}): no se descargó.")
            return
        nombre = (a.get('nombre_original') or a['drive_file_id'].split('/')[-1])[:200]
        adj = Adjunto(paciente=p, consulta=c, nombre=nombre, tipo_contenido=datos[1][:100], tamano=len(datos[0]))
        adj.archivo.save(nombre, ContentFile(datos[0]), save=False)
        adj.save()
        self._contar('adjuntos')

    # ── Vacunas, pesquisas, procedimientos ──────────────────────────────────────────────────────────────────────
    def _vacunas_y_pesquisas(self):
        from apps.especialidades.pediatria.models import Pesquisa, PesquisaRealizada, Vacuna, VacunaAplicada
        tid = self.t['id']
        catalogo = {(sin_acentos(v.nombre), v.dosis): v for v in Vacuna.objects.filter(tenant__isnull=True)}
        origen = {v['id']: v for v in self.leer(
            'select * from pacientes_vacuna where tenant_id is null or tenant_id=%s', [tid])}
        for r in self.leer('select * from pacientes_vacunaaplicada where tenant_id=%s order by id', [tid]):
            v = origen.get(r['vacuna_id'])
            p = self.pacientes.get(r['paciente_id'])
            if not v or not p:
                continue
            vac = catalogo.get((sin_acentos(v['nombre']), v.get('dosis_numero')))
            if vac is None:
                vac = Vacuna.objects.create(tenant=self.tenant, nombre=v['nombre'][:100],
                                            enfermedad=v.get('enfermedad') or '', dosis=v.get('dosis_numero') or 1,
                                            edad_meses=v.get('edad_recomendada_meses') or 0,
                                            edad_max_meses=v.get('edad_max_meses'), grupo=v.get('grupo_etario') or '',
                                            anual=bool(v.get('es_anual')), orden=v.get('orden') or 0)
                catalogo[(sin_acentos(v['nombre']), v.get('dosis_numero'))] = vac
                self.avisos.append(f"Vacuna «{v['nombre']} #{v.get('dosis_numero')}» no está en el catálogo: se creó "
                                   'como vacuna propia del consultorio.')
            VacunaAplicada.objects.create(paciente=p, vacuna=vac, fecha=r.get('fecha'), lote=(r.get('lote') or '')[:60],
                                          observaciones=(r.get('observaciones') or '')[:300], registrada_por=self.usuario)
            self._contar('vacunas aplicadas')
        pesq = {sin_acentos(x.nombre): x for x in Pesquisa.objects.filter(tenant__isnull=True)}
        origen = {x['id']: x for x in self.leer(
            'select * from pacientes_pesquisa where tenant_id is null or tenant_id=%s', [tid])}
        for r in self.leer('select * from pacientes_pesquisarealizada where tenant_id=%s order by id', [tid]):
            x, p = origen.get(r['pesquisa_id']), self.pacientes.get(r['paciente_id'])
            if not x or not p:
                continue
            destino = pesq.get(sin_acentos(x['nombre']))
            if destino is None:
                destino = Pesquisa.objects.create(tenant=self.tenant, nombre=x['nombre'][:100],
                                                  descripcion=(x.get('descripcion') or '')[:200])
                pesq[sin_acentos(x['nombre'])] = destino
            PesquisaRealizada.objects.create(paciente=p, pesquisa=destino, fecha=r.get('fecha'),
                                             resultado=(r.get('comentario') or '')[:300], registrada_por=self.usuario)
            self._contar('pesquisas')

    def _procedimientos(self):
        from apps.clinica.models import Procedimiento
        tid = self.t['id']
        servicios = {}
        for s in self.leer('select ps.* from consultas_procedimientoservicio ps join consultas_procedimiento p '
                           'on p.id=ps.procedimiento_id where p.tenant_id=%s', [tid]):
            servicios.setdefault(s['procedimiento_id'], []).append(s)
        for r in self.leer('select * from consultas_procedimiento where tenant_id=%s order by fecha, id', [tid]):
            p = self.pacientes.get(r['paciente_id'])
            if p is None:
                continue
            nombres = [self.servicios[s['servicio_id']].nombre for s in servicios.get(r['id'], [])
                       if s.get('servicio_id') in self.servicios]
            proc = Procedimiento.objects.create(paciente=p, profesional=self.perfil, cita=self.citas.get(r.get('cita_id')),
                                                fecha=r['fecha'], descripcion=(', '.join(nombres) or 'Procedimiento')[:200],
                                                notas=r.get('notas') or '')
            self._contar('procedimientos')
            self._cobros(p, r, servicios.get(r['id'], []), procedimiento=proc)

    # ── Resumen ─────────────────────────────────────────────────────────────────────────────────────────────────
    def _resumen(self):
        tid = self.t['id']
        origen = {
            'pacientes': 'pacientes_paciente', 'citas': 'agenda_cita', 'consultas': 'consultas_consulta',
            'vacunas aplicadas': 'pacientes_vacunaaplicada', 'pesquisas': 'pacientes_pesquisarealizada',
            'procedimientos': 'consultas_procedimiento', 'medicamentos del glosario': 'consultas_medicamento',
            'servicios': 'servicios_servicio', 'lugares': 'agenda_lugarconsulta'}
        self.stdout.write(f"\nConsultorio «{self.tenant.nombre}» → enlace «{self.tenant.slug}»\n")
        self.stdout.write(f"{'':28}{'Pediae':>8}{'Ordo Salud':>12}")
        for clave, tabla in origen.items():
            n = self.leer(f'select count(*) n from {tabla} where tenant_id=%s', [tid])[0]['n']
            hecho = self.cuenta.get(clave, 0)
            marca = '' if hecho == n else '  ⚠'
            self.stdout.write(f'{clave:28}{n:>8}{hecho:>12}{marca}')
        n_adj = self.leer('select count(*) n from consultas_adjuntoconsulta a join consultas_consulta c on '
                          'c.id=a.consulta_id where c.tenant_id=%s', [tid])[0]['n']
        self.stdout.write(f"{'adjuntos':28}{n_adj:>8}{self.cuenta.get('adjuntos', 0):>12}")
        for clave in ('representantes', 'cargos', 'pagos', 'imágenes de perfil'):
            self.stdout.write(f"{clave:28}{'':>8}{self.cuenta.get(clave, 0):>12}")
        if self.avisos:
            self.stdout.write(self.style.WARNING(f'\n{len(self.avisos)} avisos (datos que no se cargaron tal cual):'))
            for a in self.avisos:
                self.stdout.write(f'  - {a}')
        self.stdout.write(self.style.SUCCESS('\nMigración terminada.'))
