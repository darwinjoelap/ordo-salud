"""
Registro de especialidades, secciones y cálculos (ADR-006).

El núcleo (`apps.clinica`) NO importa a las especialidades: cada módulo se registra a sí mismo desde su
AppConfig.ready() llamando a `registrar(...)`. `sincronizar_catalogo()` (post_migrate y el comando
`sincronizar_especialidades`) copia este registro a las tablas Especialidad y SeccionClinica.

Ver docs/05_GUIA_ESPECIALIDADES.md.
"""
from dataclasses import dataclass, field

from .esquemas import asegurar_valido


@dataclass
class SeccionDef:
    codigo: str                  # 'nucleo.signos_vitales', 'ped.antropometria'
    nombre: str
    ambito: str = 'CONSULTA'     # CONSULTA | PACIENTE
    esquema: dict = field(default_factory=lambda: {'campos': []})
    version: int = 1
    descripcion: str = ''
    tipo: str = 'MODULO'         # NUCLEO | MODULO
    orden: int = 100
    migraciones: dict = field(default_factory=dict)   # {version_origen: funcion(datos) -> datos}
    especialidad: str = ''       # lo llena `registrar()`: código de la especialidad dueña
    universal: bool = False      # True = la puede usar cualquier especialidad (queda sin especialidad)


@dataclass
class PlantillaDef:
    nombre: str
    secciones: list              # ['nucleo.motivo', ('nucleo.signos_vitales', {'obligatoria': True}), ...]
    predeterminada: bool = False
    descripcion: str = ''


@dataclass
class PanelDef:
    """Tarjeta que un módulo agrega a la ficha del paciente (p. ej. «Crecimiento», «Vacunas»)."""
    codigo: str
    titulo: str
    plantilla: str                    # template que se incluye
    contexto: object = None           # función(request, paciente) -> dict | None (None = no se muestra)
    orden: int = 100
    clinico: bool = True              # solo para quien ve la historia


@dataclass
class ReporteDef:
    """Reporte propio de una especialidad (aparece en «Reportes»)."""
    codigo: str
    titulo: str
    url: str                          # nombre de URL ('pediatria:reporte')
    icono: str = 'bi-graph-up'
    descripcion: str = ''


@dataclass
class EspecialidadDef:
    codigo: str
    nombre: str
    modulo: str = ''
    color: str = '#145F8F'
    icono: str = 'bi-heart-pulse'
    orden: int = 100
    secciones: list = field(default_factory=list)
    calculos: dict = field(default_factory=dict)
    plantillas: list = field(default_factory=list)
    documentos: list = field(default_factory=list)
    paneles: list = field(default_factory=list)
    reportes: list = field(default_factory=list)
    paginas_paciente: list = field(default_factory=list)   # nombres de URL (pk del paciente) que se precargan offline
    basica: bool = False         # registrada por `general` sin módulo propio: un módulo real la reemplaza


_especialidades: dict[str, EspecialidadDef] = {}
_secciones: dict[str, SeccionDef] = {}
_calculos: dict = {}
_plantillas_nucleo: list[PlantillaDef] = []
_al_guardar: dict = {}        # codigo_seccion → función(consulta, datos) que copia datos a tablas propias
_preparar: dict = {}          # codigo_seccion → función(consulta, datos) -> datos (completa al leer o guardar)
_inicial: dict = {}           # codigo_seccion → función(consulta) -> datos (valores al abrir la sección vacía)


def registrar_nucleo(secciones, calculos=None, plantillas=None):
    for s in secciones:
        s.tipo = 'NUCLEO'
        _registrar_seccion(s)
    _calculos.update(calculos or {})
    if plantillas:
        _plantillas_nucleo[:] = plantillas


def _registrar_seccion(s: SeccionDef):
    asegurar_valido(s.esquema, permitir_calculado=True)
    previa = _secciones.get(s.codigo)
    if previa is not None and previa is not s and previa.version > s.version:
        raise ValueError(f'La sección {s.codigo} ya está registrada con una versión mayor.')
    _secciones[s.codigo] = s


def registrar(esp: EspecialidadDef):
    previa = _especialidades.get(esp.codigo)
    if previa is not None and not previa.basica and not esp.basica and previa.modulo != esp.modulo:
        raise ValueError(f'La especialidad {esp.codigo} ya la registró {previa.modulo}.')
    if previa is not None and esp.basica and not previa.basica:
        return                    # un módulo real ya la registró: la básica no la pisa
    for s in esp.secciones:
        s.especialidad = '' if s.universal else esp.codigo
        _registrar_seccion(s)
    _calculos.update(esp.calculos)
    _especialidades[esp.codigo] = esp


def especialidades():
    return dict(_especialidades)


def paneles(codigos):
    """Paneles de la ficha del paciente de las especialidades habilitadas (códigos), ordenados."""
    salida = [p for c, e in _especialidades.items() if c in codigos for p in e.paneles]
    return sorted(salida, key=lambda p: p.orden)


def reportes(codigos):
    return [r for c, e in _especialidades.items() if c in codigos for r in e.reportes]


def especialidad(codigo):
    return _especialidades.get(codigo)


def seccion(codigo):
    return _secciones.get(codigo)


def secciones():
    return dict(_secciones)


def plantillas_nucleo():
    return list(_plantillas_nucleo)


def calcular(nombre, datos, contexto):
    """Ejecuta un cálculo registrado; nunca rompe la consulta (devuelve None si falla o faltan datos)."""
    funcion = _calculos.get(nombre)
    if funcion is None:
        return None
    try:
        return funcion(datos, contexto)
    except Exception:  # noqa: BLE001 - un cálculo con datos incompletos no debe impedir guardar
        return None


def calculos():
    return dict(_calculos)


def registrar_al_guardar(codigo_seccion, funcion):
    """Un módulo puede copiar los datos de su sección a tablas propias (p. ej. vacunas aplicadas)."""
    _al_guardar[codigo_seccion] = funcion


def registrar_preparar(codigo_seccion, funcion):
    _preparar[codigo_seccion] = funcion


def registrar_inicial(codigo_seccion, funcion):
    """Valores con los que se abre una sección de consulta aún sin guardar (p. ej. la FUR del embarazo en curso)."""
    _inicial[codigo_seccion] = funcion


def inicial(codigo_seccion):
    return _inicial.get(codigo_seccion)


def preparar(codigo_seccion):
    return _preparar.get(codigo_seccion)


def al_guardar(codigo_seccion):
    return _al_guardar.get(codigo_seccion)
