
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator


class Usuario(AbstractUser):

    class Rol(models.TextChoices):
        ADMINISTRADOR = "ADMIN", "Administrador"
        DIRECTOR = "DIRECTOR", "Director"
        PSICOLOGO = "PSICOLOGO", "Psicólogo/a"
        DOCENTE = "DOCENTE", "Docente"
        ESTUDIANTE = "ESTUDIANTE", "Estudiante"
        FAMILIAR = "FAMILIAR", "Familiar"

    class EstadoSolicitud(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    rol = models.CharField(
        max_length=15,
        choices=Rol.choices,
        default=Rol.ESTUDIANTE,
        verbose_name="Rol institucional",
    )
    email_verificado = models.BooleanField(
        default=False,
        verbose_name="Correo verificado",
    )
    estado_solicitud = models.CharField(
        max_length=12,
        choices=EstadoSolicitud.choices,
        default=EstadoSolicitud.APROBADA,
        verbose_name="Estado de solicitud",
    )

    def __str__(self):
        return f"{self.username} - {self.get_rol_display()}"

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"


class PerfilDominio(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_dominio",
    )
    id_usuario_sistema = models.BigIntegerField(unique=True, blank=True, null=True)
    celular = models.CharField(
        max_length=12,
        blank=True,
        validators=[
            RegexValidator(regex=r"^\+591[0-9]{8}$")
        ],
    )
    fecha_nacimiento = models.DateField(blank=True, null=True)

    class Meta:
        db_table = "usuarios_perfil_dominio"
        verbose_name = "Vínculo de cuenta institucional"
        verbose_name_plural = "Vínculos de cuentas institucionales"


class NotificacionCuenta(models.Model):
    class Tipo(models.TextChoices):
        SOLICITUD_REGISTRO = "SOLICITUD_REGISTRO", "Nueva solicitud"
        SOLICITUD_RECIBIDA = "SOLICITUD_RECIBIDA", "Solicitud recibida"
        SOLICITUD_RESUELTA = "SOLICITUD_RESUELTA", "Solicitud revisada"
        CASO_NUEVO = "CASO_NUEVO", "Nuevo caso"
        CASO_REGISTRADO = "CASO_REGISTRADO", "Caso registrado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificaciones_cuenta",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    mensaje = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    leida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    leida_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "usuarios_notificacion_cuenta"
        ordering = ("-creado_en",)
        verbose_name = "Notificación de cuenta"
        verbose_name_plural = "Notificaciones de cuenta"
