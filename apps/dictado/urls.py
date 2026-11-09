from django.urls import path

from . import views

app_name = 'dictado'
urlpatterns = [
    path('', views.subir, name='subir'),
    path('<int:pk>/', views.estado, name='estado'),
    path('sugerir/<int:paciente_pk>/', views.sugerir, name='sugerir'),
    path('sugerir/glosario/', views.guardar_en_glosario, name='guardar_en_glosario'),
]
