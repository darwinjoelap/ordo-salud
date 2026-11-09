from django.urls import path

from . import views

app_name = 'plataforma'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('nuevo/', views.nuevo, name='nuevo'),
    path('<int:pk>/', views.editar, name='editar'),
    path('<int:pk>/renovar/', views.renovar, name='renovar'),
    path('<int:pk>/entrar/', views.entrar, name='entrar'),
    path('<int:pk>/acceso/<int:membresia_pk>/', views.acceso, name='acceso'),
    path('salir/', views.salir, name='salir'),
    path('tasas/', views.tasas, name='tasas'),
    path('suscripciones/', views.suscripciones, name='suscripciones'),
    path('renovaciones/<int:pk>/anular/', views.anular_renovacion, name='anular_renovacion'),
    path('planes/', views.planes, name='planes'),
    path('planes/nuevo/', views.plan_form, name='plan_nuevo'),
    path('planes/<int:pk>/', views.plan_form, name='plan_editar'),
]
