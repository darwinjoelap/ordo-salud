from django.urls import path

from . import reportes

app_name = 'cardiologia_pediatrica'
urlpatterns = [
    path('reportes/', reportes.tablero, name='reporte'),
]
