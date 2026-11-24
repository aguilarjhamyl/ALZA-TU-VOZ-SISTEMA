from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin

from .emails import enviar_correo_revision
from .models import Usuario


def _puede_administrar(request):
    return request.user.is_staff and (
        request.user.is_superuser or request.user.rol == "ADMIN"
    )


@admin.action(description="Aprobar solicitudes con correo confirmado")
def aprobar_solicitudes(modeladmin, request, queryset):
    aprobadas = 0
    no_verificadas = 0

    for usuario in queryset.filter(
        estado_solicitud=Usuario.EstadoSolicitud.PENDIENTE
    ):
        if not usuario.email_verificado:
            no_verificadas += 1
            continue

        enviar_correo_revision(usuario, aprobado=True)
        usuario.estado_solicitud = Usuario.EstadoSolicitud.APROBADA
        usuario.is_active = True
        usuario.save(update_fields=("estado_solicitud", "is_active"))
        aprobadas += 1

    if aprobadas:
        modeladmin.message_user(
            request,
            f"{aprobadas} solicitud(es) aprobada(s) y notificadas.",
            messages.SUCCESS,
        )
    if no_verificadas:
        modeladmin.message_user(
            request,
            f"{no_verificadas} solicitud(es) no se aprobaron porque falta "
            "confirmar el correo.",
            messages.WARNING,
        )


@admin.action(description="Rechazar solicitudes seleccionadas")
def rechazar_solicitudes(modeladmin, request, queryset):
    rechazadas = 0

    for usuario in queryset.filter(
        estado_solicitud=Usuario.EstadoSolicitud.PENDIENTE
    ):
        enviar_correo_revision(usuario, aprobado=False)
        usuario.estado_solicitud = Usuario.EstadoSolicitud.RECHAZADA
        usuario.is_active = False
        usuario.save(update_fields=("estado_solicitud", "is_active"))
        rechazadas += 1

    if rechazadas:
        modeladmin.message_user(
            request,
            f"{rechazadas} solicitud(es) rechazada(s) y notificadas.",
            messages.SUCCESS,
        )


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "rol",
        "email_verificado",
        "estado_solicitud",
        "is_active",
        "is_staff",
    )
    list_filter = (
        "rol",
        "estado_solicitud",
        "email_verificado",
        "is_active",
        "is_staff",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    actions = (aprobar_solicitudes, rechazar_solicitudes)
    readonly_fields = ("email_verificado", "estado_solicitud")
    fieldsets = UserAdmin.fieldsets + (
        ("Información institucional", {"fields": ("rol",)}),
        (
            "Validación de cuenta",
            {"fields": ("email_verificado", "estado_solicitud")},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Información personal",
            {"fields": ("first_name", "last_name", "email", "rol")},
        ),
    )

    def save_model(self, request, obj, form, change):
        if obj.estado_solicitud != Usuario.EstadoSolicitud.APROBADA:
            obj.is_active = False
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return _puede_administrar(request)

    def has_view_permission(self, request, obj=None):
        return _puede_administrar(request)

    def has_add_permission(self, request):
        return _puede_administrar(request)

    def has_change_permission(self, request, obj=None):
        return _puede_administrar(request)

    def has_delete_permission(self, request, obj=None):
        return _puede_administrar(request)
