from django.urls import path

from . import reportes, views

app_name = 'pediatria'
urlpatterns = [
    path('pacientes/<int:pk>/vacunas/', views.vacunas, name='vacunas'),
    path('pacientes/<int:pk>/vacunas/carnet/', views.vacunas_lote, name='vacunas_lote'),
    path('pacientes/<int:pk>/vacunas/registrar/', views.vacuna_registrar, name='vacuna_registrar'),
    path('pacientes/<int:pk>/vacunas/<int:va_pk>/eliminar/', views.vacuna_eliminar, name='vacuna_eliminar'),
    path('pacientes/<int:pk>/pesquisas/registrar/', views.pesquisa_registrar, name='pesquisa_registrar'),
    path('pacientes/<int:pk>/pesquisas/<int:pr_pk>/eliminar/', views.pesquisa_eliminar, name='pesquisa_eliminar'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('reportes/', reportes.tablero, name='reporte'),
]
