from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_verification_token


def enviar_correo_verificacion(request, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = email_verification_token.make_token(usuario)
    enlace = request.build_absolute_uri(
        reverse("confirmar_correo", kwargs={"uidb64": uid, "token": token})
    )
    send_mail(
        "Confirma tu correo electrónico | Alza Tu Voz",
        (
            f"Hola {usuario.first_name},\n\n"
            "Para confirmar que controlas este correo, abre el siguiente "
            f"enlace:\n{enlace}\n\n"
            "Después de confirmar, administración revisará tu solicitud. "
            "Tu cuenta seguirá inactiva hasta que sea aprobada."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
        fail_silently=False,
    )


def enviar_correo_revision(usuario, aprobado):
    if aprobado:
        asunto = "Tu cuenta fue aprobada | Alza Tu Voz"
        mensaje = (
            f"Hola {usuario.first_name},\n\n"
            "Administración aprobó tu solicitud. Ya puedes iniciar sesión "
            "en Alza Tu Voz."
        )
    else:
        asunto = "Actualización de tu solicitud | Alza Tu Voz"
        mensaje = (
            f"Hola {usuario.first_name},\n\n"
            "Administración no aprobó tu solicitud de cuenta. Para consultar "
            "el motivo o pedir orientación, comunícate con la institución."
        )

    send_mail(
        asunto,
        mensaje,
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
        fail_silently=False,
    )
