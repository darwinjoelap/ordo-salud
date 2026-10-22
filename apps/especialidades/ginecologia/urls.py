from django.urls import path

from . import reportes

app_name = 'ginecologia'
urlpatterns = [
    path('reportes/', reportes.tablero, name='reporte'),
]
