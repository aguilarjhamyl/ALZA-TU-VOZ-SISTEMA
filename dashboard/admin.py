from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group


def _puede_administrar(request):
    return request.user.is_staff and (
        request.user.is_superuser or getattr(request.user, "rol", None) == "ADMIN"
    )


admin.site.unregister(Group)


@admin.register(Group)
class GrupoAdmin(GroupAdmin):
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
