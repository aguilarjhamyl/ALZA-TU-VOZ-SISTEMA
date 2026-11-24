from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.models import NotificacionCuenta

from .forms import MensajeChatbotForm, MultipleFileField
from .utils import texto_catalogo
from .views import (
    _caso_en_ventana_de_edicion,
    es_personal_autorizado,
    respuesta_chatbot,
)


class RespuestaChatbotTests(SimpleTestCase):
    def test_solicita_apoyo_humano_ante_un_mensaje_urgente(self):
        respuesta, requiere_atencion, motivo = respuesta_chatbot(
            "Estoy en peligro"
        )

        self.assertTrue(requiere_atencion)
        self.assertIsNotNone(motivo)
        self.assertIn("busca ahora", respuesta)
        self.assertIn("servicios de emergencia", respuesta)

    def test_respuesta_general_aclara_que_no_es_diagnostico(self):
        respuesta, requiere_atencion, motivo = respuesta_chatbot(
            "Quiero hablar de mi día"
        )

        self.assertFalse(requiere_atencion)
        self.assertIsNone(motivo)
        self.assertIn("no sustituye", respuesta)


class LimitesChatbotTests(SimpleTestCase):
    def test_rechaza_mensajes_mayores_a_2000_caracteres(self):
        form = MensajeChatbotForm({"contenido": "a" * 2001})

        self.assertFalse(form.is_valid())

    def test_acepta_mensajes_de_hasta_2000_caracteres(self):
        form = MensajeChatbotForm({"contenido": "a" * 2000})

        self.assertTrue(form.is_valid())


class LimitesChatbotVistasTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="chat_usuario",
            password="Clave-Segura-9281",
            rol="ESTUDIANTE",
        )
        self.client.force_login(self.usuario)
        self.usuario_sistema = SimpleNamespace(pk=42)

    @patch("casos.views.MensajeChatbot.objects.create")
    @patch("casos.views.ConversacionChatbot.objects.create")
    @patch("casos.views.ConversacionChatbot.objects.filter")
    @patch("casos.views.obtener_usuario_sistema")
    def test_bloquea_una_decima_primera_conversacion_diaria(
        self,
        obtener_cuenta,
        filtrar_conversaciones,
        crear_conversacion,
        crear_mensaje,
    ):
        obtener_cuenta.return_value = self.usuario_sistema
        filtrar_conversaciones.return_value.count.return_value = 10

        respuesta = self.client.post(reverse("casos:nueva_conversacion"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("casos:chatbot"))
        crear_conversacion.assert_not_called()
        crear_mensaje.assert_not_called()

    @patch("casos.views.MensajeChatbot.objects.create")
    @patch("casos.views.MensajeChatbot.objects.filter")
    @patch("casos.views.ConversacionChatbot.objects.select_for_update")
    @patch("casos.views.get_object_or_404")
    @patch("casos.views.obtener_usuario_sistema")
    def test_bloquea_mensajes_al_alcanzar_el_limite_por_conversacion(
        self,
        obtener_cuenta,
        obtener_conversacion,
        bloquear_conversacion,
        filtrar_mensajes,
        crear_mensaje,
    ):
        obtener_cuenta.return_value = self.usuario_sistema
        mensajes = Mock()
        mensajes.filter.return_value.exists.return_value = False
        mensajes.filter.return_value.count.return_value = 20
        conversacion = SimpleNamespace(
            pk=55,
            id_conversacion=55,
            id_usuario_id=self.usuario_sistema.pk,
            mensajechatbot_set=mensajes,
        )
        obtener_conversacion.return_value = conversacion
        bloquear_conversacion.return_value.get.return_value = conversacion
        filtrar_mensajes.return_value.count.return_value = 20

        respuesta = self.client.post(
            reverse("casos:conversacion_chatbot", args=(55,)),
            {"contenido": "Un mensaje más"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            reverse("casos:conversacion_chatbot", args=(55,)),
        )
        crear_mensaje.assert_not_called()


class VentanaEdicionReporteTests(SimpleTestCase):
    def test_reporte_es_editable_antes_de_cumplir_siete_dias(self):
        ahora = timezone.now()
        caso = SimpleNamespace(
            eliminado_en=None,
            creado_en=ahora - timedelta(days=6),
            id_estado_caso=SimpleNamespace(permite_edicion=True),
        )

        self.assertTrue(_caso_en_ventana_de_edicion(caso, ahora))

    def test_reporte_deja_de_ser_editable_al_cumplir_siete_dias(self):
        ahora = timezone.now()
        caso = SimpleNamespace(
            eliminado_en=None,
            creado_en=ahora - timedelta(days=7),
            id_estado_caso=SimpleNamespace(permite_edicion=True),
        )

        self.assertFalse(_caso_en_ventana_de_edicion(caso, ahora))

    def test_reporte_no_es_editable_si_el_estado_no_lo_permite(self):
        ahora = timezone.now()
        caso = SimpleNamespace(
            eliminado_en=None,
            creado_en=ahora - timedelta(days=1),
            id_estado_caso=SimpleNamespace(permite_edicion=False),
        )

        self.assertFalse(_caso_en_ventana_de_edicion(caso, ahora))


class PermisosCasoTests(SimpleTestCase):
    def test_psicologo_y_director_pueden_atender_casos(self):
        for rol in ("DIRECTOR", "PSICOLOGO"):
            usuario = SimpleNamespace(
                is_authenticated=True,
                is_staff=False,
                is_superuser=False,
                rol=rol,
            )
            with self.subTest(rol=rol):
                self.assertTrue(es_personal_autorizado(usuario))

    def test_rol_administrador_no_da_acceso_a_casos_por_si_solo(self):
        usuario = SimpleNamespace(
            is_authenticated=True,
            is_staff=False,
            is_superuser=False,
            rol="ADMIN",
        )

        self.assertFalse(es_personal_autorizado(usuario))


class MultipleFileFieldTests(SimpleTestCase):
    @override_settings(MAX_UPLOAD_SIZE=2)
    def test_rechaza_archivos_mayores_al_limite(self):
        archivo = SimpleUploadedFile("evidencia.pdf", b"123")

        with self.assertRaises(ValidationError):
            MultipleFileField().clean(archivo)

    def test_rechaza_extensiones_no_permitidas(self):
        archivo = SimpleUploadedFile("programa.exe", b"contenido")

        with self.assertRaises(ValidationError):
            MultipleFileField().clean(archivo)


class TextoCatalogoTests(SimpleTestCase):
    def test_normaliza_caracteres_mal_codificados_del_esquema(self):
        self.assertEqual(
            texto_catalogo("¨Cu ndo fue la primera vez que ocurri¢?"),
            "¿Cuándo fue la primera vez que ocurrió?",
        )

    def test_normaliza_enyes_tildes_y_signos_en_valores_de_tabla(self):
        self.assertEqual(
            texto_catalogo("Psic¢logo/a; se¤ales de riesgo; S¡ / No"),
            "Psicólogo/a; señales de riesgo; Sí / No",
        )


class NotificacionesPublicasTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="estudiante",
            password="Clave-Segura-9281",
            email="estudiante@example.com",
            rol="ESTUDIANTE",
        )
        self.client.force_login(self.usuario)
        self.url = reverse("casos:contar_notificaciones_no_leidas")

    @patch("casos.views.Notificacion.objects.filter")
    @patch("casos.views.obtener_usuario_sistema")
    def test_devuelve_el_total_sin_leer_de_la_cuenta_actual(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        cuenta = SimpleNamespace(pk=18)
        obtener_cuenta.return_value = cuenta
        filtrar_notificaciones.return_value.count.return_value = 3

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"sin_leer": 3})
        obtener_cuenta.assert_called_once_with(self.usuario)
        filtrar_notificaciones.assert_called_once_with(
            id_usuario=cuenta,
            leida=False,
        )
        self.assertEqual(respuesta["Cache-Control"], "private, no-store")

    @patch("casos.views.Notificacion.objects.filter")
    @patch("casos.views.obtener_usuario_sistema")
    def test_usuario_sin_avisos_no_leidos_recibe_cero(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        obtener_cuenta.return_value = SimpleNamespace(pk=18)
        filtrar_notificaciones.return_value.count.return_value = 0
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"sin_leer": 0})
        filtrar_notificaciones.assert_called_once_with(
            id_usuario=obtener_cuenta.return_value,
            leida=False,
        )

    @patch("casos.views.Notificacion.objects.filter")
    @patch("casos.views.obtener_usuario_sistema")
    def test_contador_incluye_notificaciones_de_cuenta(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        obtener_cuenta.return_value = SimpleNamespace(pk=18)
        filtrar_notificaciones.return_value.count.return_value = 2
        NotificacionCuenta.objects.create(
            usuario=self.usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Tu solicitud fue aprobada.",
        )

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.json(), {"sin_leer": 3})

    @patch("casos.views.Notificacion.objects.filter", return_value=[])
    @patch("casos.views.obtener_usuario_sistema")
    def test_notificaciones_de_cuenta_solo_muestran_las_del_usuario(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        otro_usuario = get_user_model().objects.create_user(
            username="otra_cuenta",
            password="Clave-Segura-9281",
            email="otra@example.com",
            rol="ESTUDIANTE",
        )
        NotificacionCuenta.objects.create(
            usuario=self.usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Tu solicitud fue aprobada.",
        )
        NotificacionCuenta.objects.create(
            usuario=otro_usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Aviso privado de otra cuenta.",
        )
        obtener_cuenta.return_value = SimpleNamespace(pk=18)

        respuesta = self.client.get(reverse("casos:notificaciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tu solicitud fue aprobada.")
        self.assertNotContains(respuesta, "Aviso privado de otra cuenta.")
        self.assertEqual(len(respuesta.context["notificaciones"]), 1)

    @patch("casos.views.Notificacion.objects.filter", return_value=[])
    @patch("casos.views.obtener_usuario_sistema")
    def test_limpiar_borra_solo_notificaciones_de_la_cuenta_actual(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        otro_usuario = get_user_model().objects.create_user(
            username="cuenta_sin_limpiar",
            password="Clave-Segura-9281",
            email="otra@example.com",
            rol="ESTUDIANTE",
        )
        NotificacionCuenta.objects.create(
            usuario=self.usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Notificación propia.",
        )
        NotificacionCuenta.objects.create(
            usuario=otro_usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Notificación ajena.",
        )
        cuenta = SimpleNamespace(pk=18)
        avisos_legacy = Mock()
        obtener_cuenta.return_value = cuenta
        filtrar_notificaciones.return_value = avisos_legacy

        respuesta = self.client.post(
            reverse("casos:notificaciones"),
            {"accion": "limpiar"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            NotificacionCuenta.objects.filter(usuario=self.usuario).count(),
            0,
        )
        self.assertEqual(
            NotificacionCuenta.objects.filter(usuario=otro_usuario).count(),
            1,
        )
        filtrar_notificaciones.assert_called_once_with(id_usuario=cuenta)
        avisos_legacy.delete.assert_called_once_with()

    @patch("casos.views.Notificacion.objects.filter", return_value=[])
    @patch("casos.views.obtener_usuario_sistema")
    def test_pagina_notificaciones_muestra_boton_limpiar_con_confirmacion(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        obtener_cuenta.return_value = SimpleNamespace(pk=18)
        NotificacionCuenta.objects.create(
            usuario=self.usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje="Notificación propia.",
        )

        respuesta = self.client.get(reverse("casos:notificaciones"))

        self.assertContains(respuesta, ">Limpiar</button>", html=False)
        self.assertContains(
            respuesta,
            "¿Deseas limpiar todas tus notificaciones?",
            html=False,
        )

    @patch("casos.views.Notificacion.objects.filter")
    @patch("casos.views.obtener_usuario_sistema")
    def test_todos_los_roles_pueden_consultar_sus_notificaciones(
        self, obtener_cuenta, filtrar_notificaciones
    ):
        roles = (
            "ESTUDIANTE",
            "FAMILIAR",
            "DOCENTE",
            "DIRECTOR",
            "PSICOLOGO",
            "ADMIN",
        )
        for indice, rol in enumerate(roles, start=1):
            usuario = get_user_model().objects.create_user(
                username=f"cuenta_{indice}",
                password="Clave-Segura-9281",
                email=f"cuenta_{indice}@example.com",
                rol=rol,
            )
            obtener_cuenta.return_value = SimpleNamespace(pk=indice)
            filtrar_notificaciones.return_value.count.return_value = indice
            self.client.force_login(usuario)

            with self.subTest(rol=rol):
                respuesta = self.client.get(self.url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.json(), {"sin_leer": indice})

    def test_pagina_publica_presenta_el_nombre_del_sistema_sin_titulo_academico(self):
        respuesta = self.client.get(reverse("inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "<title>Alza TU Voz</title>", html=True)
        self.assertContains(respuesta, "Alza TU Voz")
        self.assertNotContains(respuesta, "Desarrollo de un Sistema Web Inteligente")
        self.assertNotContains(respuesta, "Gestión Integral de Casos")
        self.assertContains(respuesta, "Unidad Educativa Patacamaya de Convenio")
        self.assertContains(respuesta, "No realiza diagnósticos clínicos")
        self.assertNotContains(respuesta, reverse("casos:chatbot"))


class CasoRequiereCuentaTests(TestCase):
    def test_visitante_no_puede_abrir_detalle_de_caso(self):
        respuesta = self.client.get(
            reverse("casos:detalle", args=(1,))
        )

        self.assertRedirects(
            respuesta,
            f"{reverse('login')}?next={reverse('casos:detalle', args=(1,))}",
        )


    def test_visitante_no_puede_abrir_seguimiento_por_token(self):
        token = "1a34ec18-6ef0-40e4-86bf-228fb6aef160"
        respuesta = self.client.get(
            reverse("casos:seguimiento_externo", args=(token,))
        )

        self.assertRedirects(
            respuesta,
            f"{reverse('login')}?next="
            f"{reverse('casos:seguimiento_externo', args=(token,))}",
        )

    def test_confirmacion_ofrece_chatbot_como_apoyo_despues_del_reporte(self):
        caso = SimpleNamespace(
            codigo_caso="AV-2026-000001",
            id_estado_caso=SimpleNamespace(
                color_hex="#287c72",
                nombre="Enviado",
            ),
            id_caso=1,
        )

        html = render_to_string(
            "casos/reporte_enviado.html",
            {"caso": caso, "mostrar_chatbot": True},
        )

        self.assertIn("Tu reporte fue enviado", html)
        self.assertIn("Abrir chatbot de apoyo", html)
        self.assertIn("no diagnostica", html)

    def test_confirmacion_no_ofrece_chatbot_a_otros_roles(self):
        caso = SimpleNamespace(
            codigo_caso="AV-2026-000001",
            id_estado_caso=SimpleNamespace(
                color_hex="#287c72",
                nombre="Enviado",
            ),
            id_caso=1,
        )

        html = render_to_string(
            "casos/reporte_enviado.html",
            {"caso": caso, "mostrar_chatbot": False},
        )

        self.assertNotIn("Abrir chatbot de apoyo", html)


class BienestarCalmaAccessTests(TestCase):
    @patch("casos.views.AplicacionTest.objects.filter")
    @patch("casos.views.TestPsicologico.objects.filter", return_value=[])
    @patch("casos.views.exigir_perfil_estudiante")
    def test_lista_actividades_filtra_por_id_de_estudiante(
        self, exigir_estudiante, filtrar_tests, filtrar_aplicaciones
    ):
        usuario = get_user_model().objects.create_user(
            username="estudiante_actividades",
            password="Clave-Segura-9281",
            rol="ESTUDIANTE",
        )
        self.client.force_login(usuario)
        exigir_estudiante.return_value = SimpleNamespace(id_persona_id=11)
        filtrar_aplicaciones.return_value.select_related.return_value = []

        respuesta = self.client.get(reverse("casos:tests"))

        self.assertEqual(respuesta.status_code, 200)
        filtrar_aplicaciones.assert_called_once_with(id_estudiante_id=11)

    def test_la_actividad_de_calma_solo_esta_disponible_para_estudiantes(self):
        estudiante = get_user_model().objects.create_user(
            username="estudiante_calma",
            password="Clave-Segura-9281",
            rol="ESTUDIANTE",
        )
        self.client.force_login(estudiante)

        respuesta = self.client.get(reverse("casos:bienestar_calma"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "data-breathing-exercise")
        self.assertContains(respuesta, "Detener")

    def test_familiar_no_puede_abrir_la_actividad_de_calma(self):
        familiar = get_user_model().objects.create_user(
            username="familiar_calma",
            password="Clave-Segura-9281",
            rol="FAMILIAR",
        )
        self.client.force_login(familiar)

        respuesta = self.client.get(reverse("casos:bienestar_calma"))

        self.assertEqual(respuesta.status_code, 403)
