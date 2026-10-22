from django.urls import path

from . import views_consultas as vc
from . import views_medicamentos as vm
from . import views_plantillas as vp
from . import views_procedimientos as vpr

app_name = 'clinica'

urlpatterns = [
    path('pacientes/<int:paciente_pk>/procedimientos/nuevo/', vpr.nuevo, name='procedimiento_nuevo'),
    path('procedimientos/<int:pk>/anular/', vpr.anular, name='procedimiento_anular'),
    path('medicamentos/', vm.lista, name='medicamentos'),
    path('medicamentos/nuevo/', vm.editar, name='medicamento_nuevo'),
    path('medicamentos/<int:pk>/', vm.editar, name='medicamento'),
    path('medicamentos/<int:pk>/activar/', vm.activar, name='medicamento_activar'),
    path('medicamentos/<int:pk>/calcular/', vm.calcular_json, name='medicamento_calcular'),
    path('plantillas/', vp.plantillas, name='plantillas'),
    path('plantillas/nueva/', vp.plantilla_nueva, name='plantilla_nueva'),
    path('plantillas/<int:pk>/', vp.plantilla, name='plantilla'),
    path('plantillas/<int:pk>/accion/', vp.plantilla_accion, name='plantilla_accion'),
    path('plantillas/<int:pk>/copiar/', vp.plantilla_copiar, name='plantilla_copiar'),
    path('plantillas/<int:pk>/vista-previa/', vp.plantilla_vista_previa, name='plantilla_vista_previa'),
    path('plantillas/<int:pk>/secciones/<int:item_pk>/', vp.plantilla_item, name='plantilla_item'),
    path('secciones/', vp.secciones, name='secciones'),
    path('secciones/nueva/', vp.seccion_editar, name='seccion_nueva'),
    path('secciones/<int:pk>/', vp.seccion_vista, name='seccion_vista'),
    path('secciones/<int:pk>/editar/', vp.seccion_editar, name='seccion_editar'),
    path('secciones/<int:pk>/activa/', vp.seccion_activa, name='seccion_activa'),
    path('pacientes/<int:paciente_pk>/consultas/nueva/', vc.nueva, name='consulta_nueva'),
    path('pacientes/<int:paciente_pk>/ficha/<slug:codigo>/', vc.ficha_especialidad, name='ficha_especialidad'),
    path('consultas/<int:pk>/', vc.detalle, name='consulta'),
    path('consultas/<int:pk>/editar/', vc.editar, name='consulta_editar'),
    path('consultas/<int:pk>/imprimir/', vc.imprimir, name='consulta_imprimir'),
    path('consultas/<int:pk>/anular/', vc.anular, name='consulta_anular'),
    path('consultas/<int:pk>/adjuntar/', vc.adjuntar, name='consulta_adjuntar'),
    path('consultas/<int:pk>/enmendar/<int:seccion_id>/', vc.enmendar, name='consulta_enmendar'),
    path('adjuntos/<int:pk>/', vc.adjunto, name='adjunto'),
    path('cie10/', vc.cie10, name='cie10'),
]
