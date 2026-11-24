from urllib.parse import urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .emails import enviar_correo_verificacion
from .forms import RegistroUsuarioForm
from .models import NotificacionCuenta
from .notificaciones import notificar_personal


class RegistroUsuarioTests(TestCase):
    def setUp(self):
        self.url = reverse("registro")
        self.datos = {
            "first_name": "Alicia",
            "last_name": "Flores",
            "username": "alicia_f",
            "email": "alicia@patacamayaconvenio.edu.bo",
            "rol": "ESTUDIANTE",
            "password1": "Strong-Unique-9482",
            "password2": "Strong-Unique-9482",
            "cf-turnstile-response": "test-token",
        }

    def test_muestra_formulario_de_registro(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Crear cuenta")
        self.assertContains(respuesta, "cf-turnstile")
        self.assertContains(respuesta, "bootstrap.min.css")
        self.assertContains(respuesta, "bootstrap-icons.min.css")
        self.assertContains(respuesta, "row g-3")
        self.assertContains(respuesta, "nombre@correo.com")
        self.assertContains(respuesta, 'name="celular"')
        self.assertContains(respuesta, 'name="fecha_nacimiento"')

    def test_acepta_y_normaliza_celular_con_o_sin_prefijo(self):
        for celular, esperado in (
            ("71234567", "+59171234567"),
            ("+591 61234567", "+59161234567"),
        ):
            with self.subTest(celular=celular):
                formulario = RegistroUsuarioForm(
                    data={**self.datos, "celular": celular}
                )

                self.assertTrue(formulario.is_valid(), formulario.errors)
                self.assertEqual(formulario.cleaned_data["celular"], esperado)

    def test_rechaza_celular_que_no_tiene_ocho_digitos(self):
        formulario = RegistroUsuarioForm(
            data={**self.datos, "celular": "7123456"}
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("celular", formulario.errors)

    def test_login_usa_shell_compartido_y_formularios_bootstrap(self):
        respuesta = self.client.get(reverse("login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "site-header")
        self.assertContains(respuesta, "site-footer")
        self.assertContains(respuesta, "bootstrap.min.css")
        self.assertContains(respuesta, "class=\"form-control\"")
        self.assertContains(respuesta, "bi bi-shield-lock")
        self.assertContains(respuesta, 'data-theme-toggle')
        self.assertContains(respuesta, 'aria-label="Cambiar a modo oscuro"')
        self.assertContains(respuesta, "theme-init.js")

    def test_visitante_solo_ve_login_al_intentar_crear_reporte(self):
        respuesta = self.client.get(reverse("casos:crear"))

        self.assertRedirects(
            respuesta,
            f"{reverse('login')}?next={reverse('casos:crear')}",
        )
        login_respuesta = self.client.get(respuesta.url)
        self.assertEqual(login_respuesta.status_code, 200)
        self.assertContains(login_respuesta, "Acceso al sistema")
        self.assertContains(
            login_respuesta,
            f'<input type="hidden" name="next" value="{reverse("casos:crear")}">',
            html=True,
        )

    def test_visitante_no_puede_enviar_reporte_por_post(self):
        respuesta = self.client.post(reverse("casos:crear"), {"titulo": "Reporte"})

        self.assertRedirects(
            respuesta,
            f"{reverse('login')}?next={reverse('casos:crear')}",
        )

    @patch("usuarios.views.enviar_correo_verificacion")
    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_crea_cuenta_pendiente_y_envia_confirmacion(
        self, validar_captcha, enviar_confirmacion
    ):
        administrador = get_user_model().objects.create_superuser(
            username="admin_solicitudes",
            password="Admin-Segura-9482",
            email="admin@example.com",
        )
        respuesta = self.client.post(self.url, self.datos, follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Te enviamos un enlace")
        usuario = get_user_model().objects.get(username="alicia_f")
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(usuario.estado_solicitud, "PENDIENTE")
        self.assertEqual(usuario.rol, "ESTUDIANTE")
        self.assertTrue(usuario.check_password(self.datos["password1"]))
        validar_captcha.assert_called_once_with("test-token")
        enviar_confirmacion.assert_called_once()
        self.assertTrue(
            NotificacionCuenta.objects.filter(
                usuario=administrador,
                tipo=NotificacionCuenta.Tipo.SOLICITUD_REGISTRO,
            ).exists()
        )
        self.assertTrue(
            NotificacionCuenta.objects.filter(
                usuario=usuario,
                tipo=NotificacionCuenta.Tipo.SOLICITUD_RECIBIDA,
            ).exists()
        )

    def test_notifica_solo_a_roles_de_personal_configurados(self):
        administrador = get_user_model().objects.create_user(
            username="admin_notificaciones",
            password="Admin-Segura-9482",
            email="admin@example.com",
            rol="ADMIN",
        )
        psicologo = get_user_model().objects.create_user(
            username="psicologo_notificaciones",
            password="Psico-Segura-9482",
            email="psicologo@example.com",
            rol="PSICOLOGO",
        )
        director = get_user_model().objects.create_user(
            username="director_notificaciones",
            password="Director-Segura-9482",
            email="director@example.com",
            rol="DIRECTOR",
        )

        notificar_personal(
            tipo=NotificacionCuenta.Tipo.CASO_NUEVO,
            mensaje="Nuevo caso para revisión.",
            roles=("ADMIN", "PSICOLOGO"),
        )

        self.assertTrue(
            NotificacionCuenta.objects.filter(usuario=administrador).exists()
        )
        self.assertTrue(
            NotificacionCuenta.objects.filter(usuario=psicologo).exists()
        )
        self.assertFalse(
            NotificacionCuenta.objects.filter(usuario=director).exists()
        )

    @patch("usuarios.views.enviar_correo_verificacion")
    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_acepta_correo_de_otro_dominio(
        self, validar_captcha, enviar_confirmacion
    ):
        datos = {**self.datos, "email": "alicia@gmail.com"}

        respuesta = self.client.post(self.url, datos, follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Te enviamos un enlace para confirmar tu correo",
        )
        usuario = get_user_model().objects.get(username="alicia_f")
        self.assertEqual(usuario.email, "alicia@gmail.com")
        validar_captcha.assert_called_once_with("test-token")
        enviar_confirmacion.assert_called_once()

    def test_acepta_correos_de_distintos_proveedores(self):
        for email in (
            "alicia@gmail.com",
            "alicia@hotmail.com",
            "alicia@patacamayaconvenio.edu.bo",
        ):
            with self.subTest(email=email):
                formulario = RegistroUsuarioForm(
                    data={**self.datos, "email": email}
                )

                self.assertTrue(formulario.is_valid(), formulario.errors)

    @patch("usuarios.views.logger.exception")
    @patch("usuarios.views.enviar_correo_verificacion", side_effect=OSError)
    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_no_crea_cuenta_si_falla_el_envio_de_confirmacion(
        self, validar_captcha, enviar_confirmacion, registrar_error
    ):
        respuesta = self.client.post(self.url, self.datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo enviar el correo")
        self.assertFalse(
            get_user_model().objects.filter(username="alicia_f").exists()
        )
        enviar_confirmacion.assert_called_once()
        registrar_error.assert_called_once()

    @patch("usuarios.views.enviar_correo_verificacion")
    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_guarda_datos_adicionales_del_perfil(
        self, validar_captcha, enviar_confirmacion
    ):
        datos = {
            **self.datos,
            "celular": "+59171234567",
            "fecha_nacimiento": "2008-05-14",
        }

        respuesta = self.client.post(self.url, datos, follow=True)

        self.assertEqual(respuesta.status_code, 200)
        perfil = get_user_model().objects.get(
            username="alicia_f"
        ).perfil_dominio
        self.assertEqual(perfil.celular, "+59171234567")
        self.assertEqual(perfil.fecha_nacimiento.isoformat(), "2008-05-14")

    def test_confirma_correo_sin_activar_cuenta(self):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=False,
            email_verificado=False,
            estado_solicitud="PENDIENTE",
        )
        request = RequestFactory().get("/")
        enviar_correo_verificacion(request, usuario)
        enlace = next(
            linea
            for linea in mail.outbox[0].body.splitlines()
            if "/confirmar-correo/" in linea
        )

        respuesta = self.client.get(
            urlsplit(enlace).path,
            follow=True,
        )

        self.assertEqual(mail.outbox[0].to, [usuario.email])
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Correo confirmado")
        usuario.refresh_from_db()
        self.assertTrue(usuario.email_verificado)
        self.assertFalse(usuario.is_active)
        self.assertEqual(usuario.estado_solicitud, "PENDIENTE")

    def test_no_confirma_correo_con_token_invalido(self):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=False,
            estado_solicitud="PENDIENTE",
        )
        uid = urlsafe_base64_encode(force_bytes(usuario.pk))

        respuesta = self.client.get(
            reverse("confirmar_correo", args=(uid, "token-invalido")),
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no es válido")
        usuario.refresh_from_db()
        self.assertFalse(usuario.email_verificado)

    @patch("usuarios.admin.enviar_correo_revision")
    def test_administracion_aprueba_solicitud_verificada(self, enviar_revision):
        Usuario = get_user_model()
        usuario = Usuario.objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=True,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )
        administrador = Usuario.objects.create_superuser(
            username="admin",
            password="Admin-Unique-9482",
            email="admin@patacamayaconvenio.edu.bo",
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("admin:usuarios_usuario_changelist"),
            {
                "action": "aprobar_solicitudes",
                "_selected_action": str(usuario.pk),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario.refresh_from_db()
        self.assertTrue(usuario.is_active)
        self.assertEqual(usuario.estado_solicitud, "APROBADA")
        enviar_revision.assert_called_once_with(usuario, aprobado=True)

    @patch("usuarios.admin.enviar_correo_revision")
    def test_administracion_no_aprueba_solicitud_sin_verificar(
        self, enviar_revision
    ):
        Usuario = get_user_model()
        usuario = Usuario.objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=False,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )
        administrador = Usuario.objects.create_superuser(
            username="admin",
            password="Admin-Unique-9482",
            email="admin@patacamayaconvenio.edu.bo",
        )
        self.client.force_login(administrador)

        self.client.post(
            reverse("admin:usuarios_usuario_changelist"),
            {
                "action": "aprobar_solicitudes",
                "_selected_action": str(usuario.pk),
            },
        )

        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.assertEqual(usuario.estado_solicitud, "PENDIENTE")
        enviar_revision.assert_not_called()

    @patch("usuarios.admin.enviar_correo_revision")
    def test_administracion_rechaza_y_notifica_solicitud(self, enviar_revision):
        Usuario = get_user_model()
        usuario = Usuario.objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=True,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )
        administrador = Usuario.objects.create_superuser(
            username="admin",
            password="Admin-Unique-9482",
            email="admin@patacamayaconvenio.edu.bo",
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("admin:usuarios_usuario_changelist"),
            {
                "action": "rechazar_solicitudes",
                "_selected_action": str(usuario.pk),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.assertEqual(usuario.estado_solicitud, "RECHAZADA")
        enviar_revision.assert_called_once_with(usuario, aprobado=False)

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_no_permite_registrar_rol_institucional(self, validar_captcha):
        datos = {**self.datos, "rol": "ADMIN"}
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(username="alicia_f").exists()
        )
        self.assertIn("rol", respuesta.context["form"].errors)

    @patch("usuarios.views.validar_turnstile", return_value=False)
    def test_no_crea_cuenta_sin_validar_captcha(self, validar_captcha):
        respuesta = self.client.post(self.url, self.datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(username="alicia_f").exists()
        )
        self.assertContains(respuesta, "verificación antirrobot")

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_estudiante_activo_puede_iniciar_sesion(self, validar_captcha):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": usuario.username,
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
            },
        )

        self.assertRedirects(respuesta, reverse("inicio"))
        validar_captcha.assert_called_once_with("test-token")

    @override_settings(
        DEBUG=True,
        TURNSTILE_SITE_KEY="1x00000000000000000000AA",
        TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    )
    def test_login_local_con_llaves_turnstile_de_prueba_no_requiere_token(self):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": usuario.username,
                "password": "Strong-Unique-9482",
            },
        )

        self.assertRedirects(respuesta, reverse("inicio"))

    @override_settings(
        DEBUG=False,
        TURNSTILE_SITE_KEY="1x00000000000000000000AA",
        TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    )
    def test_login_no_omite_turnstile_fuera_de_modo_desarrollo(self):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": usuario.username,
                "password": "Strong-Unique-9482",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "verificación antirrobot")
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_login_busca_nombre_de_usuario_sin_distinguir_mayusculas(
        self, validar_captcha
    ):
        get_user_model().objects.create_user(
            username="Admin",
            password="Strong-Unique-9482",
            email="admin@patacamayaconvenio.edu.bo",
            rol="ADMIN",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": "admin",
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
            },
        )

        self.assertRedirects(respuesta, reverse("dashboard:inicio"))
        validar_captcha.assert_called_once_with("test-token")

    def test_administrador_autenticado_que_abre_login_ve_su_dashboard(self):
        usuario = get_user_model().objects.create_user(
            username="admin",
            password="Strong-Unique-9482",
            email="admin@patacamayaconvenio.edu.bo",
            rol="ADMIN",
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("login"))

        self.assertRedirects(respuesta, reverse("dashboard:inicio"))

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_login_no_elige_entre_nombres_ambiguos_sin_distinguir_mayusculas(
        self, validar_captcha
    ):
        Usuario = get_user_model()
        Usuario.objects.create_user(
            username="Admin",
            password="Strong-Unique-9482",
            email="admin-1@patacamayaconvenio.edu.bo",
            is_active=True,
        )
        Usuario.objects.create_user(
            username="admin",
            password="Strong-Unique-9482",
            email="admin-2@patacamayaconvenio.edu.bo",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": "ADMIN",
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Las credenciales no son correctas")
        self.assertNotIn("_auth_user_id", self.client.session)
        validar_captcha.assert_called_once_with("test-token")

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_login_devuelve_a_la_pagina_requerida(
        self, validar_captcha
    ):
        get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": "alicia_f",
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
                "next": reverse("casos:crear"),
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("casos:crear"),
            fetch_redirect_response=False,
        )
        validar_captcha.assert_called_once_with("test-token")

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_login_ignora_redireccion_fuera_del_sitio(
        self, validar_captcha
    ):
        get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": "alicia_f",
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
                "next": "https://example.com/",
            },
        )

        self.assertRedirects(respuesta, reverse("inicio"))
        validar_captcha.assert_called_once_with("test-token")

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_solicitud_pendiente_no_inicia_sesion_y_muestra_estado(
        self, validar_captcha
    ):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=True,
            estado_solicitud="PENDIENTE",
            is_active=False,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": usuario.email,
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "pendiente de aprobación")
        self.assertNotIn("_auth_user_id", self.client.session)
        validar_captcha.assert_called_once_with("test-token")

    @patch("usuarios.views.validar_turnstile", return_value=True)
    def test_solicitud_rechazada_muestra_estado_aunque_correo_no_verificado(
        self, validar_captcha
    ):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            email_verificado=False,
            estado_solicitud="RECHAZADA",
            is_active=False,
        )

        respuesta = self.client.post(
            reverse("login"),
            {
                "correo": usuario.email,
                "password": "Strong-Unique-9482",
                "cf-turnstile-response": "test-token",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tu solicitud no fue aprobada")
        self.assertNotIn("_auth_user_id", self.client.session)
        validar_captcha.assert_called_once_with("test-token")

    def test_usuario_puede_cerrar_sesion_con_post(self):
        usuario = get_user_model().objects.create_user(
            username="alicia_f",
            password="Strong-Unique-9482",
            email="alicia@patacamayaconvenio.edu.bo",
            rol="ESTUDIANTE",
            is_active=True,
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(reverse("logout"))

        self.assertRedirects(respuesta, reverse("inicio"))
        self.assertNotIn("_auth_user_id", self.client.session)
