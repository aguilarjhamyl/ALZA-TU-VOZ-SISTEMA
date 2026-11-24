from django.urls import path

from . import views


app_name = "casos"

urlpatterns = [
    path("casos/nuevo/", views.reportar_caso, name="crear"),
    path("casos/mis-casos/", views.mis_casos, name="mis_casos"),
    path(
        "casos/<int:id_caso>/editar/",
        views.editar_caso,
        name="editar",
    ),
    path(
        "casos/<int:id_caso>/retirar/",
        views.retirar_caso,
        name="retirar",
    ),
    path(
        "casos/seguimiento/<uuid:token>/",
        views.seguimiento_externo,
        name="seguimiento_externo",
    ),
    path(
        "casos/evidencia/<int:id_evidencia>/",
        views.descargar_evidencia,
        name="descargar_evidencia",
    ),
    path("casos/<int:id_caso>/", views.detalle_caso, name="detalle"),
    path("orientacion/", views.inicio_chatbot, name="chatbot"),
    path(
        "orientacion/nueva/",
        views.nueva_conversacion,
        name="nueva_conversacion",
    ),
    path(
        "orientacion/atencion/",
        views.atencion_chatbot,
        name="atencion_chatbot",
    ),
    path(
        "orientacion/<int:id_conversacion>/",
        views.conversacion_chatbot,
        name="conversacion_chatbot",
    ),
    path("evaluaciones/", views.lista_tests, name="tests"),
    path(
        "evaluaciones/calma/",
        views.bienestar_calma,
        name="bienestar_calma",
    ),
    path(
        "evaluaciones/<int:id_test>/",
        views.aplicar_test,
        name="aplicar_test",
    ),
    path(
        "evaluaciones/resultado/<int:id_aplicacion>/",
        views.resultado_test,
        name="resultado_test",
    ),
    path(
        "notificaciones/sin-leer/",
        views.contar_notificaciones_no_leidas,
        name="contar_notificaciones_no_leidas",
    ),
    path("notificaciones/", views.notificaciones, name="notificaciones"),
]
