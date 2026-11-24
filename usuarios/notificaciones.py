from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import NotificacionCuenta, Usuario


def notificar_usuario(usuario, tipo, mensaje, url=""):
    return NotificacionCuenta.objects.create(
        usuario=usuario,
        tipo=tipo,
        mensaje=mensaje,
        url=url,
    )


def notificar_personal(tipo, mensaje, url="", roles=()):
    usuarios = (
        get_user_model()
        .objects.filter(
            is_active=True,
            estado_solicitud=Usuario.EstadoSolicitud.APROBADA,
        )
        .filter(
            Q(is_staff=True)
            | Q(is_superuser=True)
            | Q(rol__in=roles)
        )
        .distinct()
    )
    return [
        notificar_usuario(usuario, tipo, mensaje, url)
        for usuario in usuarios
    ]
