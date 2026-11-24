import os
import sys
from pathlib import Path

# Directorio principal del proyecto.
BASE_DIR = Path(__file__).resolve().parent

# Permitir que Python encuentre las aplicaciones Django.
sys.path.insert(0, str(BASE_DIR))

# Configurar Django.
# Configurar Django.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
django.setup()

# Recién después importar modelos y servicios.
import csv
import secrets
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings

from usuarios.services import obtener_usuario_sistema
from usuarios.models import PerfilDominio
from casos.models import Persona, UsuarioDominio, Estudiante, Tutor


# ============================================================
# CONFIGURACIÓN
# ============================================================

Usuario = get_user_model()

CUENTAS_POR_ROL = 10

CORREO_ESTUDIANTES = "email.com"
CORREO_FAMILIARES = "email.com"

CARPETA_PROYECTO = Path(settings.BASE_DIR)

ARCHIVO_CREDENCIALES = CARPETA_PROYECTO / (
    "credenciales_demo_alza_tu_voz_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + ".csv"
)

# ============================================================
# DATOS DE DEMOSTRACIÓN
# ============================================================

cuentas = []

for numero in range(1, CUENTAS_POR_ROL + 1):

    cuentas.append({
        "username": f"estudiante{numero:02d}",
        "email": f"estudiante{numero:02d}@{CORREO_ESTUDIANTES}",
        "first_name": f"Estudiante Demo {numero:02d}",
        "last_name": "Prueba",
        "rol": "ESTUDIANTE",
    })

    cuentas.append({
        "username": f"familiar{numero:02d}",
        "email": f"familiar{numero:02d}@{CORREO_FAMILIARES}",
        "first_name": f"Familiar Demo {numero:02d}",
        "last_name": "Prueba",
        "rol": "FAMILIAR",
    })


# ============================================================
# VALIDACIONES PREVIAS
# ============================================================

print("\n" + "=" * 65)
print("ALZA TU VOZ - GENERACIÓN DE CUENTAS DE DEMOSTRACIÓN")
print("=" * 65)

if ARCHIVO_CREDENCIALES.exists():
    raise FileExistsError(
        f"El archivo de credenciales ya existe: {ARCHIVO_CREDENCIALES}"
    )

# Comprobar que no existan nombres de usuario duplicados
usuarios_objetivo = [c["username"] for c in cuentas]

if len(usuarios_objetivo) != len(set(usuarios_objetivo)):
    raise ValueError("Hay nombres de usuario repetidos en la configuración.")

# Comprobar correos duplicados
correos_objetivo = [c["email"].lower() for c in cuentas]

if len(correos_objetivo) != len(set(correos_objetivo)):
    raise ValueError("Hay correos repetidos en la configuración.")

# Comprobar conflictos con cuentas existentes
conflictos = []

for datos in cuentas:
    existente = Usuario.objects.filter(
        username__iexact=datos["username"]
    ).first()

    correo_existente = Usuario.objects.filter(
        email__iexact=datos["email"]
    ).first()

    if existente:
        if existente.rol != datos["rol"]:
            conflictos.append(
                f"{datos['username']}: existe con otro rol."
            )
        elif existente.email.lower() != datos["email"].lower():
            conflictos.append(
                f"{datos['username']}: ya tiene otro correo."
            )

    if correo_existente and (
        correo_existente.username.lower()
        != datos["username"].lower()
    ):
        conflictos.append(
            f"{datos['email']}: ya pertenece a otra cuenta."
        )

if conflictos:
    print("\nSe encontraron conflictos:")
    for conflicto in conflictos:
        print(" -", conflicto)

    raise ValueError(
        "Se canceló el proceso para evitar modificar cuentas existentes."
    )


# ============================================================
# GENERACIÓN DE CONTRASEÑAS
# ============================================================

for datos in cuentas:
    datos["password"] = secrets.token_urlsafe(18)


# ============================================================
# CREACIÓN DE CUENTAS Y VÍNCULOS INSTITUCIONALES
# ============================================================

credenciales_nuevas = []
creadas = 0
existentes = 0

try:

    with transaction.atomic():

        for datos in cuentas:

            username = datos["username"]
            email = datos["email"]
            rol = datos["rol"]

            usuario = Usuario.objects.filter(
                username__iexact=username
            ).first()

            if usuario:

                # No cambiar contraseña ni estado de una cuenta existente.
                existentes += 1

                print(
                    f"[EXISTENTE] {username} - "
                    "No se modificó la cuenta."
                )

            else:

                usuario = Usuario.objects.create_user(
                    username=username,
                    email=email,
                    password=datos["password"],
                    first_name=datos["first_name"],
                    last_name=datos["last_name"],
                    rol=rol,
                    is_active=False,
                    email_verificado=False,
                    estado_solicitud="PENDIENTE",
                )

                creadas += 1

                credenciales_nuevas.append({
                    "usuario": username,
                    "correo": email,
                    "rol": rol,
                    "contrasena": datos["password"],
                })

                print(
                    f"[CREADA] {username} - "
                    "Solicitud pendiente."
                )

            # Crear o completar el perfil y los registros
            # Los familiares necesitan celular porque PostgreSQL
            # exige ese dato al crear un registro en la tabla tutor.

            from usuarios.models import PerfilDominio
            from casos.models import Persona, UsuarioDominio

            perfil, _ = PerfilDominio.objects.get_or_create(
                usuario=usuario
            )

            datos_perfil = {
                "celular": perfil.celular,
                "fecha_nacimiento": perfil.fecha_nacimiento,
            }

            if usuario.rol == "FAMILIAR":
                # Número ficticio para demostración.
                # No utilizar para llamadas ni mensajes reales.
                numero = int(username[-2:])
                celular_demo = f"+591000000{numero:02d}"

                # Guardar el celular en el perfil Django.
                perfil.celular = celular_demo
                perfil.save(update_fields=["celular"])

                datos_perfil["celular"] = celular_demo

                # Si ya existe una Persona con el mismo correo,
                # completar su celular antes de crear el Tutor.
                persona_existente = Persona.objects.filter(
                    correo__iexact=usuario.email
                ).first()

                # Si el perfil ya está vinculado a una cuenta institucional,
                # recuperar también su Persona.
                if perfil.id_usuario_sistema is not None:
                    cuenta_previa = UsuarioDominio.objects.select_related(
                        "id_persona"
                    ).get(pk=perfil.id_usuario_sistema)

                    persona_existente = cuenta_previa.id_persona

                if persona_existente and not persona_existente.celular:
                    Persona.objects.filter(
                        pk=persona_existente.pk
                    ).update(celular=celular_demo)

            # Crear o completar la cuenta institucional.
            cuenta_institucional = obtener_usuario_sistema(
                usuario,
                datos_perfil=datos_perfil,
            )

            perfil.refresh_from_db()


            perfil = PerfilDominio.objects.get(usuario=usuario)

            persona = cuenta_institucional.id_persona

            if persona is None:
                raise ValueError(
                    f"No se creó la Persona de {username}."
                )

            if rol == "ESTUDIANTE":

                if not Estudiante.objects.filter(
                    id_persona=persona
                ).exists():
                    raise ValueError(
                        f"No se creó el registro Estudiante de {username}."
                    )

            elif rol == "FAMILIAR":

                if not Tutor.objects.filter(
                    id_persona=persona
                ).exists():
                    raise ValueError(
                        f"No se creó el registro Tutor de {username}."
                    )

            if perfil.id_usuario_sistema != cuenta_institucional.pk:
                raise ValueError(
                    f"El vínculo institucional de {username} no coincide."
                )

    # ========================================================
    # GUARDAR CREDENCIALES DE LAS CUENTAS NUEVAS
    # ========================================================

    with open(
        ARCHIVO_CREDENCIALES,
        "x",
        newline="",
        encoding="utf-8"
    ) as archivo:

        campos = [
            "usuario",
            "correo",
            "rol",
            "contrasena",
        ]

        escritor = csv.DictWriter(
            archivo,
            fieldnames=campos
        )

        escritor.writeheader()
        escritor.writerows(credenciales_nuevas)

except Exception:

    if ARCHIVO_CREDENCIALES.exists():
        ARCHIVO_CREDENCIALES.unlink()

    raise


# ============================================================
# RESUMEN FINAL
# ============================================================

print("\n" + "=" * 65)
print("PROCESO FINALIZADO")
print("=" * 65)

print(f"Cuentas nuevas: {creadas}")
print(f"Cuentas existentes sin modificar: {existentes}")
print(f"Total revisado: {len(cuentas)}")

print("\nESTADO DE LAS CUENTAS NUEVAS:")
print(" - is_active: False")
print(" - email_verificado: False")
print(" - estado_solicitud: PENDIENTE")

print("\nREGISTROS INSTITUCIONALES:")
print(" - Estudiantes: registros en tabla estudiante.")
print(" - Familiares: registros en tabla tutor.")
print(" - Perfiles: vinculados con UsuarioDominio.")
print(" - Contraseñas: almacenadas mediante el hash de Django.")

print("\nARCHIVO DE CREDENCIALES:")
print(ARCHIVO_CREDENCIALES)

print("\nNo se enviaron correos electrónicos.")
print("Las cuentas nuevas requieren aprobación administrativa.")
print("=" * 65)
