from django.urls import path
from .views import (
    eliminar_registro_administrativo,
    inicio_dashboard,
    modulo_administrador,
    registro_administrativo,
    alternar_estado_rol,
    alternar_estado_registro,
    revisar_solicitud,
    tabla_administrativa,
)

app_name = "dashboard"

urlpatterns = [
    path("", inicio_dashboard, name="inicio"),
    path("modulo/<slug:modulo>/", modulo_administrador, name="modulo"),
    path("tabla/<slug:tabla>/", tabla_administrativa, name="tabla"),
    path(
        "tabla/<slug:tabla>/nuevo/",
        registro_administrativo,
        name="tabla_nuevo",
    ),
    path(
        "tabla/<slug:tabla>/<str:pk>/ver/",
        registro_administrativo,
        {"solo_ver": True},
        name="tabla_ver",
    ),
    path(
        "tabla/<slug:tabla>/<str:pk>/",
        registro_administrativo,
        name="tabla_editar",
    ),
    path(
        "tabla/<slug:tabla>/<str:pk>/eliminar/",
        eliminar_registro_administrativo,
        name="tabla_eliminar",
    ),
    path(
        "solicitud/<int:pk>/<slug:accion>/",
        revisar_solicitud,
        name="revisar_solicitud",
    ),
    path(
        "roles/<int:pk>/alternar-estado/",
        alternar_estado_rol,
        name="alternar_estado_rol",
    ),
    path(
        "tabla/<slug:tabla>/<str:pk>/alternar-estado/",
        alternar_estado_registro,
        name="tabla_estado",
    ),
]
