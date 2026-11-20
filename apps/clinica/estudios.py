"""Catálogo clínico de exámenes, independiente del catálogo facturable."""
import unicodedata

from django.db import IntegrityError, transaction

from apps.core.excepciones import ErrorDeNegocio

from .models.consulta import EstudioCatalogo


def normalizar_nombre(nombre):
    texto = unicodedata.normalize('NFKD', ' '.join((nombre or '').split()).casefold())
    return ''.join(letra for letra in texto if not unicodedata.combining(letra))


def catalogo_activo():
    """El manager TenantModel falla cerrado fuera del tenant actual."""
    return EstudioCatalogo.objects.filter(activo=True).order_by('categoria', 'nombre')


def filas_para_preoperatorio(valoracion):
    """Mantiene estudios históricos y agrega las opciones actuales sin duplicarlos."""
    from .preoperatorio import datos_estudios

    actuales = [{**fila, 'control_seleccion': True, 'seleccionado': True}
                for fila in datos_estudios(valoracion)]
    referidos = {fila.get('catalogo') for fila in actuales if fila.get('catalogo')}
    opciones = list(actuales)
    for estudio in catalogo_activo():
        if estudio.pk not in referidos:
            opciones.append({
                'catalogo': estudio.pk, 'nombre': estudio.nombre, 'tipo': estudio.categoria,
                'control_seleccion': True, 'seleccionado': False,
            })
    return opciones


@transaction.atomic
def registrar_examen(form):
    """Solo altas explícitas, con unicidad concurrente por consultorio."""
    if not form.is_valid():
        raise ErrorDeNegocio('Revisa el nombre y la categoría del examen.')
    registro = form.save(commit=False)
    registro.nombre_normalizado = normalizar_nombre(registro.nombre)
    if EstudioCatalogo.objects.filter(nombre_normalizado=registro.nombre_normalizado).exists():
        raise ErrorDeNegocio('Ese examen ya está registrado en el catálogo del consultorio.')
    try:
        with transaction.atomic():
            registro.save()
    except IntegrityError as error:
        raise ErrorDeNegocio('Ese examen ya está registrado en el catálogo del consultorio.') from error
    return registro
