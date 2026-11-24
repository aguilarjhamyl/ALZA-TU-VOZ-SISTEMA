
import json
import logging
import smtplib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .emails import enviar_correo_verificacion
from .forms import RegistroUsuarioForm
from .models import NotificacionCuenta, PerfilDominio
from .notificaciones import notificar_personal, notificar_usuario
from .tokens import email_verification_token


logger = logging.getLogger(__name__)


def _es_administrador(usuario):
    return (
        usuario.is_staff
        or usuario.is_superuser
        or getattr(usuario, "rol", None) == "ADMIN"
    )


def inicio(request):
    """Muestra la página principal de Alza Tu Voz."""
    return render(request, "inicio.html")


@require_http_methods(["GET", "POST"])
def registro_usuario(request):
    """Registra estudiantes y familiares para aprobación administrativa."""
    if request.user.is_authenticated:
        return redirect("inicio")

    form = RegistroUsuarioForm(request.POST or None)
    if request.method == "POST":
        if not validar_turnstile(request.POST.get("cf-turnstile-response", "")):
            messages.error(
                request,
                "Completa la verificación antirrobot e inténtalo nuevamente.",
            )
        elif form.is_valid():
            try:
                with transaction.atomic():
                    usuario = form.save()
                    PerfilDominio.objects.create(
                        usuario=usuario,
                        celular=form.cleaned_data.get("celular") or "",
                        fecha_nacimiento=form.cleaned_data.get("fecha_nacimiento"),
                    )
                    notificar_personal(
                        tipo=NotificacionCuenta.Tipo.SOLICITUD_REGISTRO,
                        mensaje=(
                            f"Hay una nueva solicitud de cuenta de "
                            f"{usuario.get_username()}."
                        ),
                        url=reverse(
                            "dashboard:tabla",
                            kwargs={"tabla": "usuarios"},
                        ),
                        roles=("ADMIN",),
                    )
                    notificar_usuario(
                        usuario,
                        tipo=NotificacionCuenta.Tipo.SOLICITUD_RECIBIDA,
                        mensaje=(
                            "Recibimos tu solicitud de cuenta. "
                            "Administración la revisará."
                        ),
                        url=reverse("login"),
                    )
                    enviar_correo_verificacion(request, usuario)
            except (OSError, smtplib.SMTPException):
                logger.exception(
                    "No se pudo enviar el correo de verificación para la "
                    "solicitud de usuario %s.",
                    form.cleaned_data["username"],
                )
                messages.error(
                    request,
                    "No se pudo enviar el correo de verificación. "
                    "No se creó la cuenta; inténtalo nuevamente más tarde.",
                )
                return render(
                    request,
                    "registro.html",
                    {
                        "form": form,
                        "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
                    },
                )
            messages.success(
                request,
                "Te enviamos un enlace para confirmar tu correo. "
                "Administración revisará tu solicitud.",
            )
            return redirect("registro")

    return render(
        request,
        "registro.html",
        {
            "form": form,
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
        },
    )


@require_GET
def confirmar_correo(request, uidb64, token):
    """Confirma el correo electrónico sin activar la cuenta."""
    Usuario = get_user_model()
    try:
        usuario_id = force_str(urlsafe_base64_decode(uidb64))
        usuario = Usuario.objects.get(pk=usuario_id)
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeDecodeError,
        Usuario.DoesNotExist,
    ):
        usuario = None

    if usuario is None or not email_verification_token.check_token(usuario, token):
        messages.error(
            request,
            "El enlace de verificación no es válido o ya venció. "
            "Si necesitas ayuda, contacta a administración.",
        )
        return redirect("login")

    if not usuario.email_verificado:
        usuario.email_verificado = True
        usuario.save(update_fields=("email_verificado",))

    messages.success(
        request,
        "Correo confirmado. Tu cuenta permanecerá inactiva mientras "
        "administración revisa tu solicitud.",
    )
    return redirect("login")


def redireccion_siguiente_segura(request, destino):
    if destino and url_has_allowed_host_and_scheme(
        url=destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return None


@require_POST
def logout_usuario(request):
    """Cierra la sesión del usuario actual."""
    logout(request)
    return redirect("inicio")


def validar_turnstile(token, ip=None):
    """Valida el token antirrobot directamente con Cloudflare."""
    if (
        settings.DEBUG
        and settings.TURNSTILE_SITE_KEY == settings.TURNSTILE_TEST_SITE_KEY
        and settings.TURNSTILE_SECRET_KEY == settings.TURNSTILE_TEST_SECRET_KEY
    ):
        return True

    if not token or not settings.TURNSTILE_SECRET_KEY:
        return False

    datos = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }

    if ip:
        datos["remoteip"] = ip

    solicitud = Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=urlencode(datos).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(solicitud, timeout=8) as respuesta:
            resultado = json.loads(respuesta.read().decode("utf-8"))
        return resultado.get("success", False) is True
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False


@require_http_methods(["GET", "POST"])
def login_usuario(request):
    """Permite el acceso de cuentas activas según su rol."""
    siguiente = redireccion_siguiente_segura(
        request,
        request.POST.get("next") or request.GET.get("next", ""),
    )
    if request.user.is_authenticated:
        if siguiente:
            return redirect(siguiente)
        if _es_administrador(request.user):
            return redirect("dashboard:inicio")
        return redirect("inicio")

    correo_ingresado = ""

    if request.method == "POST":
        identificador = request.POST.get("correo", "").strip()
        password = request.POST.get("password", "")
        recordar = request.POST.get("remember_me") == "on"
        token = request.POST.get("cf-turnstile-response", "")

        correo_ingresado = identificador

        # No autenticar si la verificación antirrobot falla.
        if not validar_turnstile(token):
            messages.error(
                request,
                "Completa la verificación antirrobot e inténtalo nuevamente.",
            )
            return render(
                request,
                "login.html",
                {
                    "correo_ingresado": correo_ingresado,
                    "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
                    "next": siguiente,
                },
            )

        Usuario = get_user_model()
        usuario = authenticate(
            request,
            username=identificador,
            password=password,
        )

        # Resolver el identificador sin distinguir mayúsculas solo si es único.
        if usuario is None:
            coincidencias = (
                Usuario.objects.filter(email__iexact=identificador)
                if "@" in identificador
                else Usuario.objects.filter(username__iexact=identificador)
            )

            if coincidencias.count() == 1:
                usuario = authenticate(
                    request,
                    username=coincidencias.first().get_username(),
                    password=password,
                )

        # Los backends estándar omiten cuentas inactivas; validar contraseña
        # aparte permite comunicarles el estado sin abrir una sesión.
        if usuario is None:
            candidatos = (
                Usuario.objects.filter(email__iexact=identificador)
                if "@" in identificador
                else Usuario.objects.filter(username__iexact=identificador)
            )
            if candidatos.count() == 1:
                candidato = candidatos.first()
                if candidato.check_password(password):
                    usuario = candidato

        if usuario is None:
            messages.error(
                request,
                "Las credenciales no son correctas.",
            )
        elif (
            not usuario.is_active
            or usuario.estado_solicitud != "APROBADA"
        ):
            if usuario.estado_solicitud == "RECHAZADA":
                mensaje = (
                    "Tu solicitud no fue aprobada. Contacta a la institución "
                    "para recibir orientación."
                )
            elif usuario.estado_solicitud == "PENDIENTE":
                mensaje = "Tu solicitud está pendiente de aprobación por administración."
            else:
                mensaje = "La cuenta está desactivada. Contacta al administrador."
            messages.error(request, mensaje)
        elif not (
            usuario.is_superuser
            or usuario.is_staff
            or usuario.rol in ("ADMIN", "DIRECTOR", "PSICOLOGO")
            or usuario.rol in ("ESTUDIANTE", "FAMILIAR")
        ):
            messages.error(
                request,
                "Esta cuenta no tiene autorización para iniciar sesión.",
            )
        else:
            login(request, usuario)

            # Recordar la sesión durante 30 días o hasta cerrar el navegador.
            if recordar:
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                request.session.set_expiry(0)

            messages.success(request, "Acceso autorizado.")

            if siguiente:
                return redirect(siguiente)
            if _es_administrador(usuario):
                return redirect("dashboard:inicio")

            return redirect("inicio")

    return render(
        request,
        "login.html",
        {
            "correo_ingresado": correo_ingresado,
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
            "next": siguiente,
        }
    )
