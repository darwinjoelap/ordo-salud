from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def ping(request):
    """Respuesta mínima para medir la conexión y saber si la sesión sigue abierta."""
    user = getattr(request, 'user', None)
    return JsonResponse({'ok': True, 'auth': bool(user and user.is_authenticated and getattr(request, 'tenant', None))})


@never_cache
def precache(request):
    """Compatibilidad con clientes antiguos. Las vistas autenticadas solo se consultan en línea."""
    return JsonResponse({'urls': []})
