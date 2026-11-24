from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from casos.admin import RegistroInstitucionalAdmin
from casos.models import (
    Caso,
    CategoriaIncidente,
    LogAcceso,
    LogAuditoria,
    Rol,
    TipoIncidente,
)
from usuarios.admin import UsuarioAdmin


class DashboardInterfaceTests(TestCase):
    def test_dashboard_uses_bootstrap_and_shared_navigation(self):
        usuario = get_user_model().objects.create_user(
            username="director",
            password="Strong-Unique-9482",
            email="director@example.com",
            rol="DIRECTOR",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "bootstrap.min.css")
        self.assertContains(respuesta, "bootstrap-icons.min.css")
        self.assertContains(respuesta, "site-header")
        self.assertContains(respuesta, "site-footer")
        self.assertContains(respuesta, "dashboard-grid row g-4")
        self.assertContains(respuesta, "bi bi-clipboard-data")
        self.assertContains(respuesta, 'data-theme-toggle')
        self.assertContains(respuesta, "theme-init.js")

    def test_administrador_ve_panel_oscuro_metricas_y_tablas(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="Strong-Unique-9482",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="admin-dashboard-theme"')
        self.assertContains(respuesta, "admin-dashboard.css")
        self.assertContains(respuesta, "Panel de control")
        self.assertContains(respuesta, "CUENTAS ACTIVAS")
        self.assertContains(respuesta, "Casos por estado")
        self.assertContains(respuesta, "Gestión de tablas")
        self.assertContains(respuesta, "Bitácora de auditoría")
        self.assertContains(respuesta, "data-sidebar-toggle")
        self.assertContains(respuesta, "admin-sidebar__logout")
        self.assertNotContains(respuesta, "En construcción")
        self.assertNotContains(respuesta, "data-theme-toggle")
        self.assertEqual(respuesta.context["usuarios_activos"], 1)

    def test_modulo_administrativo_abre_la_tabla_real(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="Strong-Unique-9482",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("dashboard:modulo", args=("auditoria",))
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            reverse("dashboard:tabla", args=("logauditoria",)),
        )

    def test_tablas_administrativas_registradas_y_bitacoras_solo_lectura(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="Admin-test-123!",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        self.assertTrue(admin.site.is_registered(Caso))
        self.assertTrue(admin.site.is_registered(LogAcceso))
        self.assertTrue(admin.site.is_registered(LogAuditoria))
        self.assertEqual(
            reverse("admin:casos_caso_changelist"),
            "/admin/casos/caso/",
        )
        self.assertEqual(
            reverse("admin:casos_logauditoria_changelist"),
            "/admin/casos/logauditoria/",
        )

        request = RequestFactory().get("/")
        request.user = usuario
        caso_admin = admin.site._registry[Caso]
        auditoria_admin = admin.site._registry[LogAuditoria]
        rol_admin = admin.site._registry[Rol]
        self.assertIsInstance(caso_admin, RegistroInstitucionalAdmin)
        self.assertTrue(caso_admin.has_change_permission(request))
        self.assertFalse(caso_admin.has_delete_permission(request))
        self.assertTrue(auditoria_admin.has_view_permission(request))
        self.assertFalse(auditoria_admin.has_add_permission(request))
        self.assertFalse(auditoria_admin.has_change_permission(request))
        self.assertFalse(auditoria_admin.has_delete_permission(request))
        self.assertFalse(rol_admin.has_change_permission(request))
        self.assertFalse(rol_admin.has_delete_permission(request))

        administrador = get_user_model().objects.create_user(
            username="admin_institucional",
            password="Admin-test-123!",
            email="admin-institucional@example.com",
            rol="ADMIN",
            is_staff=True,
        )
        request.user = administrador
        usuario_admin = admin.site._registry[get_user_model()]
        self.assertIsInstance(usuario_admin, UsuarioAdmin)
        self.assertTrue(caso_admin.has_add_permission(request))
        self.assertTrue(usuario_admin.has_change_permission(request))

        usuario_director = get_user_model().objects.create_user(
            username="director",
            password="Director-test-123!",
            email="director-admin@example.com",
            rol="DIRECTOR",
        )
        request.user = usuario_director
        self.assertFalse(caso_admin.has_view_permission(request))

    def test_consola_django_carga_tema_oscuro(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="Strong-Unique-9482",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("admin:index"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "admin-dark.css")

    def test_tabla_de_modulo_no_disponible_muestra_mensaje_de_construccion(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("dashboard:tabla", args=("logauditoria",))
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "MÓDULO EN CONSTRUCCIÓN")
        self.assertContains(respuesta, "La tabla todavía no está conectada")
        self.assertContains(respuesta, "data-sidebar-toggle")
        self.assertContains(respuesta, 'id="admin-sidebar"')
        self.assertNotContains(respuesta, "django-admin")

    def test_busqueda_de_usuarios_trata_entrada_sql_como_texto(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("dashboard:tabla", args=("usuarios",)),
            {"q": "' OR '1'='1"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["pagina"].paginator.count, 0)
        self.assertContains(respuesta, "No se encontraron registros")

    def test_tabla_usuarios_pagina_de_20_y_controles_de_primera_a_ultima(self):
        administrador = get_user_model().objects.create_superuser(
            username="admin",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        for indice in range(21):
            get_user_model().objects.create_user(
                username=f"usuario-{indice:02d}",
                password="test-account-password-123!",
                email=f"usuario-{indice}@example.com",
            )
        self.client.force_login(administrador)

        primera = self.client.get(reverse("dashboard:tabla", args=("usuarios",)))
        segunda = self.client.get(
            reverse("dashboard:tabla", args=("usuarios",)),
            {"page": 2},
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(primera.context["pagina"].paginator.per_page, 20)
        self.assertEqual(len(primera.context["filas"]), 20)
        self.assertContains(primera, "Primero")
        self.assertContains(primera, "Anterior")
        self.assertContains(primera, "Siguiente")
        self.assertContains(primera, "Último")
        self.assertContains(primera, "?page=2")
        self.assertEqual(len(segunda.context["filas"]), 2)
        self.assertContains(segunda, "?page=1")

    def test_roles_muestran_un_boton_y_alternan_habilitacion(self):
        administrador = get_user_model().objects.create_superuser(
            username="admin",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        self.client.force_login(administrador)
        with connection.schema_editor() as editor:
            editor.create_model(Rol)
        try:
            rol_admin = Rol.objects.create(
                id_rol=1,
                codigo="ADMINISTRADOR",
                nombre="Administrador",
                descripcion="Acceso total",
                activo=True,
            )
            rol = Rol.objects.create(
                id_rol=2,
                codigo="DOCENTE",
                nombre="Docente",
                descripcion="Personal docente",
                activo=True,
            )
            listado = self.client.get(reverse("dashboard:tabla", args=("rol",)))

            self.assertEqual(listado.status_code, 200)
            self.assertContains(listado, "Inhabilitar rol")
            self.assertContains(listado, "Rol protegido")
            self.assertNotContains(listado, "Editar registro")
            self.assertNotContains(listado, "Eliminar registro")
            self.assertEqual(
                listado.content.count(
                    reverse("dashboard:alternar_estado_rol", args=(rol.pk,)).encode()
                ),
                1,
            )
            respuesta_admin = self.client.post(
                reverse("dashboard:alternar_estado_rol", args=(rol_admin.pk,))
            )
            self.assertEqual(respuesta_admin.status_code, 403)
            rol_admin.refresh_from_db()
            self.assertTrue(rol_admin.activo)

            respuesta = self.client.post(
                reverse("dashboard:alternar_estado_rol", args=(rol.pk,))
            )
            rol.refresh_from_db()
            self.assertRedirects(
                respuesta,
                reverse("dashboard:tabla", args=("rol",)),
            )
            self.assertFalse(rol.activo)

            listado = self.client.get(reverse("dashboard:tabla", args=("rol",)))
            self.assertContains(listado, "Habilitar rol")
            self.assertContains(listado, "Inhabilitado")
            self.client.post(
                reverse("dashboard:alternar_estado_rol", args=(rol.pk,))
            )
            rol.refresh_from_db()
            self.assertTrue(rol.activo)
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(Rol)

    def test_registros_relacionados_se_inhabilitan_y_los_sueltos_conservan_crud(self):
        administrador = get_user_model().objects.create_superuser(
            username="admin",
            password="test-password",
            email="admin@example.com",
        )
        self.client.force_login(administrador)
        with connection.schema_editor() as editor:
            editor.create_model(CategoriaIncidente)
            editor.create_model(TipoIncidente)
        try:
            relacionada = CategoriaIncidente.objects.create(
                nombre="Categoría relacionada",
                activo=True,
            )
            independiente = CategoriaIncidente.objects.create(
                nombre="Categoría independiente",
                activo=True,
            )
            TipoIncidente.objects.create(
                id_categoria=relacionada,
                nombre="Tipo relacionado",
            )

            listado = self.client.get(
                reverse("dashboard:tabla", args=("categoriaincidente",))
            )
            self.assertEqual(listado.status_code, 200)
            self.assertContains(listado, "data-sidebar-toggle")
            self.assertContains(listado, 'id="admin-sidebar"')
            filas = {
                fila["object"].pk: fila
                for fila in listado.context["filas"]
            }
            self.assertTrue(filas[relacionada.pk]["tiene_referencias"])
            self.assertFalse(filas[independiente.pk]["tiene_referencias"])
            self.assertContains(listado, "Inhabilitar registro")
            self.assertContains(listado, "Ver registro")
            self.assertContains(listado, "Editar registro")
            self.assertContains(listado, "Eliminar registro")
            respuesta_ver = self.client.get(
                reverse(
                    "dashboard:tabla_ver",
                    args=("categoriaincidente", independiente.pk),
                )
            )
            self.assertEqual(respuesta_ver.status_code, 200)
            self.assertContains(respuesta_ver, "Categoría independiente")
            self.assertContains(respuesta_ver, "data-sidebar-toggle")
            respuesta_editar = self.client.get(
                reverse(
                    "dashboard:tabla_editar",
                    args=("categoriaincidente", independiente.pk),
                )
            )
            self.assertEqual(respuesta_editar.status_code, 200)
            self.assertContains(respuesta_editar, "Editar registro")
            self.assertContains(respuesta_editar, "data-sidebar-toggle")

            respuesta = self.client.post(
                reverse(
                    "dashboard:tabla_estado",
                    args=("categoriaincidente", relacionada.pk),
                )
            )
            relacionada.refresh_from_db()
            self.assertRedirects(
                respuesta,
                reverse("dashboard:tabla", args=("categoriaincidente",)),
            )
            self.assertFalse(relacionada.activo)

            respuesta_suelta = self.client.post(
                reverse(
                    "dashboard:tabla_estado",
                    args=("categoriaincidente", independiente.pk),
                )
            )
            self.assertEqual(respuesta_suelta.status_code, 403)
            respuesta_borrar = self.client.post(
                reverse(
                    "dashboard:tabla_eliminar",
                    args=("categoriaincidente", relacionada.pk),
                )
            )
            self.assertEqual(respuesta_borrar.status_code, 403)
            respuesta_borrar_suelta = self.client.post(
                reverse(
                    "dashboard:tabla_eliminar",
                    args=("categoriaincidente", independiente.pk),
                )
            )
            self.assertRedirects(
                respuesta_borrar_suelta,
                reverse("dashboard:tabla", args=("categoriaincidente",)),
            )
            self.assertFalse(
                CategoriaIncidente.objects.filter(pk=independiente.pk).exists()
            )
        finally:
            connection.check_constraints()
            with connection.schema_editor() as editor:
                editor.delete_model(TipoIncidente)
                editor.delete_model(CategoriaIncidente)

    @patch("dashboard.views.enviar_correo_revision")
    def test_administrador_aprueba_solicitud_desde_tabla_personalizada(self, enviar):
        administrador = get_user_model().objects.create_superuser(
            username="admin",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        solicitud = get_user_model().objects.create_user(
            username="solicitud",
            password="test-account-password-123!",
            email="solicitud@example.com",
            email_verificado=False,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse(
                "dashboard:revisar_solicitud",
                args=(solicitud.pk, "aprobar"),
            )
        )

        solicitud.refresh_from_db()
        self.assertRedirects(
            respuesta,
            reverse("dashboard:tabla", args=("usuarios",)),
        )
        self.assertEqual(solicitud.estado_solicitud, "APROBADA")
        self.assertTrue(solicitud.is_active)
        enviar.assert_called_once()

    @patch("dashboard.views.logger.exception")
    @patch("dashboard.views.enviar_correo_revision", side_effect=OSError)
    def test_aprobacion_no_depende_de_que_se_envie_el_correo(
        self, enviar, registrar_error
    ):
        administrador = get_user_model().objects.create_superuser(
            username="admin_correo",
            password="test-admin-password-123!",
            email="admin@example.com",
        )
        solicitud = get_user_model().objects.create_user(
            username="solicitud_sin_verificar",
            password="test-account-password-123!",
            email="solicitud@example.com",
            email_verificado=False,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse(
                "dashboard:revisar_solicitud",
                args=(solicitud.pk, "aprobar"),
            ),
            follow=True,
        )

        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado_solicitud, "APROBADA")
        self.assertTrue(solicitud.is_active)
        self.assertContains(respuesta, "No se pudo enviar el aviso")
        enviar.assert_called_once()
        registrar_error.assert_called_once()

    def test_tabla_administrativa_exige_ser_administrador(self):
        usuario = get_user_model().objects.create_user(
            username="director",
            password="test-director-password-123!",
            email="director@example.com",
            rol="DIRECTOR",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("dashboard:tabla", args=("usuarios",))
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_modulo_administrativo_requiere_permisos_de_administrador(self):
        usuario = get_user_model().objects.create_user(
            username="director",
            password="Strong-Unique-9482",
            email="director@example.com",
            rol="DIRECTOR",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("dashboard:modulo", args=("auditoria",))
        )

        self.assertEqual(respuesta.status_code, 403)
