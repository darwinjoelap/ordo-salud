from django.urls import path

from . import views

app_name = 'agenda'

urlpatterns = [
    path('', views.dia, name='dia'),
    path('semana/', views.semana, name='semana'),
    path('horas/', views.horas, name='horas'),
    path('citas/nueva/', views.cita_form, name='cita_nueva'),
    path('citas/<int:pk>/', views.cita, name='cita'),
    path('citas/<int:pk>/editar/', views.cita_form, name='cita_editar'),
    path('citas/<int:pk>/estado/', views.cita_estado, name='cita_estado'),
    path('citas/<int:pk>/atender/', views.atender, name='atender'),
    path('citas/<int:pk>/cobrar/', views.cobrar_cita, name='cobrar_cita'),
    path('citas/<int:pk>/recordatorio/', views.recordatorio, name='recordatorio'),
    path('citas/<int:pk>/eliminar/', views.cita_eliminar, name='cita_eliminar'),
    path('recordatorios/<int:pk>/<str:ultima>/<int:meses>/', views.recordatorio_inactividad,
         name='recordatorio_inactividad'),
    path('cumpleanos/<int:pk>/<str:fecha>/contacto/', views.contacto_cumpleanos, name='contacto_cumpleanos'),
    path('horarios/', views.horarios, name='horarios'),
    path('horarios/<int:pk>/eliminar/', views.horario_eliminar, name='horario_eliminar'),
    path('tipos/', views.tipos, name='tipos'),
    path('tipos/<int:pk>/', views.tipos, name='tipo_editar'),
    path('bloqueos/', views.bloqueos, name='bloqueos'),
    path('bloqueos/<int:pk>/eliminar/', views.bloqueo_eliminar, name='bloqueo_eliminar'),
]
