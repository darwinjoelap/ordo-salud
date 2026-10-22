from django.urls import path

from . import views

app_name = 'dictado'
urlpatterns = [
    path('', views.subir, name='subir'),
    path('<int:pk>/', views.estado, name='estado'),
]
