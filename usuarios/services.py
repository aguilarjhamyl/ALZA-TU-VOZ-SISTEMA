from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import transaction

from casos.models import Estudiante, Persona, Rol, Tutor, UsuarioDominio, UsuarioRol

from .models import PerfilDominio


@transaction.atomic
def obtener_usuario_sistema(usuario, datos_perfil=None):
    perfil, _ = PerfilDominio.objects.get_or_create(
        usuario=usuario,
    )

    if perfil.id_usuario_sistema is not None:
        cuenta = UsuarioDominio.objects.get(pk=perfil.id_usuario_sistema)
        estado = "ACTIVA" if usuario.is_active else "PENDIENTE"
        if cuenta.estado_cuenta != estado:
            UsuarioDominio.objects.filter(pk=cuenta.pk).update(
                estado_cuenta=estado
            )
            cuenta.estado_cuenta = estado
        persona = cuenta.id_persona
    else:
        email = (usuario.email or "").strip() or None
        persona = (
            Persona.objects.filter(correo__iexact=email).first()
            if email
            else None
        )

        if persona is None:
            perfil_datos = datos_perfil or {
                "celular": perfil.celular,
                "fecha_nacimiento": perfil.fecha_nacimiento,
            }
            nombres = usuario.first_name.strip() or usuario.get_username()
            persona = Persona.objects.create(
                nombres=nombres[:100],
                ap_paterno=usuario.last_name.strip()[:60] or None,
                correo=email,
                celular=perfil_datos.get("celular") or None,
                fecha_nacimiento=perfil_datos.get("fecha_nacimiento"),
            )

        cuenta = UsuarioDominio.objects.filter(id_persona=persona).first()
        if cuenta is None:
            cuenta = UsuarioDominio.objects.create(
                id_persona=persona,
                password_hash=make_password(None),
                estado_cuenta="ACTIVA" if usuario.is_active else "PENDIENTE",
            )

        if PerfilDominio.objects.filter(
            id_usuario_sistema=cuenta.pk
        ).exclude(usuario=usuario).exists():
            raise ValidationError(
                "La cuenta institucional asociada a este correo ya está vinculada."
            )

        perfil.id_usuario_sistema = cuenta.pk
        perfil.save(update_fields=("id_usuario_sistema",))

    rol_codigo = {
        "ADMIN": "ADMINISTRADOR",
        "DIRECTOR": "DIRECTOR",
        "PSICOLOGO": "PSICOLOGO",
        "DOCENTE": "DOCENTE",
        "ESTUDIANTE": "ESTUDIANTE",
    }.get(usuario.rol)
    if rol_codigo:
        rol = Rol.objects.filter(codigo=rol_codigo, activo=True).first()
        if rol:
            UsuarioRol.objects.get_or_create(id_usuario=cuenta, id_rol=rol)

    if usuario.rol == "ESTUDIANTE":
        Estudiante.objects.get_or_create(id_persona=persona)
    elif usuario.rol == "FAMILIAR":
        Tutor.objects.get_or_create(id_persona=persona)

    return cuenta


def exigir_perfil_estudiante(usuario):
    if usuario.rol != "ESTUDIANTE":
        raise ValidationError(
            "Esta herramienta está disponible únicamente para estudiantes."
        )
    return obtener_usuario_sistema(usuario)
