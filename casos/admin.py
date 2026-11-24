from django.contrib import admin
from django.db import models

from . import models as casos_models


READ_ONLY_MODELS = {
    casos_models.AplicacionTest,
    casos_models.CasoHistorialEstado,
    casos_models.CasoMensaje,
    casos_models.ConversacionChatbot,
    casos_models.DenuncianteExterno,
    casos_models.Evidencia,
    casos_models.LogAcceso,
    casos_models.LogAuditoria,
    casos_models.MensajeChatbot,
    casos_models.RespuestaCaso,
    casos_models.RespuestaTest,
    casos_models.UsuarioDominio,
}

NO_DELETE_MODELS = {casos_models.Caso, casos_models.Rol}
SENSITIVE_FIELDS = {casos_models.UsuarioDominio: {"password_hash"}}


def _puede_administrar(request):
    return request.user.is_staff and (
        request.user.is_superuser or getattr(request.user, "rol", None) == "ADMIN"
    )


class RegistroInstitucionalAdmin(admin.ModelAdmin):
    list_per_page = 25
    list_max_show_all = 100
    save_on_top = True
    actions = None

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        sensitive_fields = SENSITIVE_FIELDS.get(model, set())
        concrete_fields = [
            field
            for field in model._meta.concrete_fields
            if field.name not in sensitive_fields
        ]
        display_types = {
            "BooleanField",
            "CharField",
            "DateField",
            "DateTimeField",
            "DecimalField",
            "EmailField",
            "IntegerField",
            "SmallIntegerField",
            "UUIDField",
        }
        display_fields = [
            field.name
            for field in concrete_fields
            if field.primary_key or field.get_internal_type() in display_types
        ]
        self.list_display = tuple(display_fields[:6])
        self.search_fields = tuple(
            field.name
            for field in concrete_fields
            if isinstance(field, (models.CharField, models.EmailField))
            and field.get_internal_type() != "TextField"
        )[:4]
        self.list_filter = tuple(
            field.name
            for field in concrete_fields
            if isinstance(field, (models.BooleanField, models.DateField))
            or field.choices
        )[:3]
        self.list_select_related = True

        if model in READ_ONLY_MODELS:
            self.readonly_fields = tuple(field.name for field in concrete_fields)
            self.exclude = tuple(sensitive_fields)

    def has_module_permission(self, request):
        return _puede_administrar(request)

    def has_view_permission(self, request, obj=None):
        return _puede_administrar(request)

    def has_add_permission(self, request):
        return _puede_administrar(request) and self.model not in READ_ONLY_MODELS

    def has_change_permission(self, request, obj=None):
        return (
            _puede_administrar(request)
            and self.model not in READ_ONLY_MODELS
            and self.model is not casos_models.Rol
        )

    def has_delete_permission(self, request, obj=None):
        return (
            _puede_administrar(request)
            and self.model not in READ_ONLY_MODELS
            and self.model not in NO_DELETE_MODELS
        )


MODELOS_ADMINISTRATIVOS = (
    casos_models.Persona,
    casos_models.UsuarioDominio,
    casos_models.Estudiante,
    casos_models.Tutor,
    casos_models.Rol,
    casos_models.DenuncianteExterno,
    casos_models.CategoriaIncidente,
    casos_models.TipoIncidente,
    casos_models.Frecuencia,
    casos_models.LugarIncidente,
    casos_models.EstadoCaso,
    casos_models.NivelRiesgo,
    casos_models.MotivoRechazo,
    casos_models.RolParticipante,
    casos_models.TipoEvidencia,
    casos_models.TipoRespuesta,
    casos_models.Pregunta,
    casos_models.OpcionPregunta,
    casos_models.Curso,
    casos_models.Caso,
    casos_models.CasoParticipante,
    casos_models.CasoMensaje,
    casos_models.Evidencia,
    casos_models.RespuestaCaso,
    casos_models.CasoHistorialEstado,
    casos_models.TipoAccion,
    casos_models.Notificacion,
    casos_models.AccionSeguimiento,
    casos_models.ConversacionChatbot,
    casos_models.MensajeChatbot,
    casos_models.TestPsicologico,
    casos_models.TestItem,
    casos_models.TestOpcion,
    casos_models.AplicacionTest,
    casos_models.RespuestaTest,
    casos_models.LogAcceso,
    casos_models.LogAuditoria,
)

for modelo in MODELOS_ADMINISTRATIVOS:
    admin.site.register(modelo, RegistroInstitucionalAdmin)
