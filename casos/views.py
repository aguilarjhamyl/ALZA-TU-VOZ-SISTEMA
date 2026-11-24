import hashlib
import json
import mimetypes
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import connection, transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from usuarios.models import NotificacionCuenta, PerfilDominio
from usuarios.notificaciones import notificar_personal, notificar_usuario
from usuarios.services import exigir_perfil_estudiante, obtener_usuario_sistema

from .forms import (
    AccionSeguimientoForm,
    AplicarTestForm,
    EstadoCasoForm,
    MensajeCasoAutoridadForm,
    MensajeChatbotForm,
    ParticipanteFormSet,
    ReporteCasoForm,
    RespuestasCasoForm,
    RespuestaCasoMensajeForm,
)
from .models import (
    AccionSeguimiento,
    AplicacionTest,
    Caso,
    CasoHistorialEstado,
    CasoMensaje,
    CasoParticipante,
    ConversacionChatbot,
    DenuncianteExterno,
    Estudiante,
    EstadoCaso,
    Evidencia,
    MensajeChatbot,
    Notificacion,
    OpcionPregunta,
    Pregunta,
    RespuestaCaso,
    TestPsicologico,
    TransicionEstadoCaso,
    TipoEvidencia,
    UsuarioDominio,
)
from .utils import texto_catalogo


CHATBOT_MAX_MENSAJES_POR_CONVERSACION = 20
CHATBOT_MAX_CONVERSACIONES_POR_DIA = 10
PLAZO_EDICION_REPORTE = timedelta(days=7)

EXTENSION_A_TIPO_EVIDENCIA = {
    ".jpg": "IMAGEN",
    ".jpeg": "IMAGEN",
    ".png": "IMAGEN",
    ".webp": "IMAGEN",
    ".mp3": "AUDIO",
    ".wav": "AUDIO",
    ".m4a": "AUDIO",
    ".mp4": "VIDEO",
    ".webm": "VIDEO",
    ".mov": "VIDEO",
    ".pdf": "DOCUMENTO",
    ".doc": "DOCUMENTO",
    ".docx": "DOCUMENTO",
}


def _caso_en_ventana_de_edicion(caso, ahora=None):
    ahora = ahora or timezone.now()
    return bool(
        caso.eliminado_en is None
        and caso.id_estado_caso.permite_edicion
        and ahora < caso.creado_en + PLAZO_EDICION_REPORTE
    )


def _establecer_contexto_auditoria(request, usuario_sistema, observacion):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_contexto_auditoria(%s, %s, %s, %s)",
            [
                usuario_sistema.pk,
                request.META.get("REMOTE_ADDR"),
                request.META.get("HTTP_USER_AGENT"),
                observacion,
            ],
        )


def _notificar_directores(caso, tipo):
    etiquetas = {
        Notificacion.Tipo.CASO_ENVIADO: "fue enviado para revisión",
        Notificacion.Tipo.CASO_ACTUALIZADO: "fue actualizado por quien lo reportó",
        Notificacion.Tipo.CASO_RETIRADO: "fue retirado por quien lo reportó",
    }
    Usuario = get_user_model()
    directores = Usuario.objects.filter(
        rol="DIRECTOR",
        is_active=True,
        estado_solicitud="APROBADA",
    ).order_by("pk")
    notificados = 0
    for director in directores:
        cuenta = obtener_usuario_sistema(director)
        Notificacion.objects.create(
            id_usuario=cuenta,
            id_caso=caso,
            tipo=tipo,
            mensaje=f"El reporte {caso.codigo_caso} {etiquetas[tipo]}.",
        )
        notificados += 1
    return notificados


def _registrar_evento_caso(caso, usuario_sistema, contenido):
    return CasoMensaje.objects.create(
        id_caso=caso,
        autor_tipo=CasoMensaje.Autor.SISTEMA,
        id_usuario=usuario_sistema,
        tipo=CasoMensaje.Tipo.COMENTARIO,
        contenido=contenido,
        visible_para_denunciante=True,
    )


def _respuestas_iniciales_caso(caso):
    iniciales = {}
    respuestas = RespuestaCaso.objects.filter(
        id_caso=caso,
        origen="FORMULARIO",
    )
    preguntas = {
        pregunta.pk: pregunta.id_tipo_respuesta.codigo
        for pregunta in Pregunta.objects.filter(
            pk__in=respuestas.values("id_pregunta")
        ).select_related("id_tipo_respuesta")
    }
    for respuesta in respuestas:
        tipo = preguntas.get(respuesta.id_pregunta)
        if tipo is None:
            continue
        if tipo == "OPCION_MULTIPLE":
            valor = json.loads(respuesta.valor_texto or "[]")
        elif tipo == "ESCALA":
            valor = respuesta.valor_numerico
        elif respuesta.id_opcion is not None:
            valor = str(respuesta.id_opcion)
        else:
            valor = respuesta.valor_texto
        iniciales[f"pregunta_{respuesta.id_pregunta}"] = valor
    return iniciales


def _es_propietario_del_caso(usuario, caso):
    perfil = PerfilDominio.objects.filter(usuario=usuario).first()
    return bool(
        perfil
        and perfil.id_usuario_sistema is not None
        and perfil.id_usuario_sistema == caso.id_usuario_denunciante_id
    )


def _guardar_participantes(caso, participantes):
    CasoParticipante.objects.filter(id_caso=caso).delete()
    nuevos = []
    for participante_form in participantes:
        datos = participante_form.cleaned_data
        rol = datos.get("id_rol_participante")
        nombre = (datos.get("nombre_referencial") or "").strip()
        if not rol or not nombre:
            continue
        nuevos.append(
            CasoParticipante(
                id_caso=caso,
                id_rol_participante=rol,
                nombre_referencial=nombre,
                descripcion=(datos.get("descripcion") or "").strip() or None,
            )
        )
    CasoParticipante.objects.bulk_create(nuevos)


def es_personal_autorizado(usuario):
    return bool(
        usuario.is_authenticated
        and (
            usuario.is_staff
            or usuario.is_superuser
            or usuario.rol in {"DIRECTOR", "PSICOLOGO"}
        )
    )


def obtener_codigo_caso():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 'AV-' || to_char(CURRENT_DATE, 'YYYY') || '-' || "
            "lpad(nextval('public.seq_codigo_caso')::text, 6, '0')"
        )
        return cursor.fetchone()[0]


def guardar_evidencias(
    caso, archivos, usuario_sistema, storage, rutas_guardadas
):
    for archivo in archivos:
        extension = Path(archivo.name).suffix.lower()
        nombre = get_valid_filename(Path(archivo.name).name)[:180]
        ruta = f"casos/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}_{nombre}"

        digest = hashlib.sha256()
        for fragmento in archivo.chunks():
            digest.update(fragmento)
        archivo.seek(0)

        ruta_guardada = storage.save(ruta, archivo)
        rutas_guardadas.append(ruta_guardada)
        tipo_codigo = EXTENSION_A_TIPO_EVIDENCIA.get(extension, "OTRO")
        evidencia = Evidencia(
            id_caso=caso,
            id_tipo_evidencia=TipoEvidencia.objects.get(codigo=tipo_codigo),
            nombre_archivo=nombre[:255],
            ruta_archivo=ruta_guardada,
            tipo_mime=archivo.content_type
            or mimetypes.guess_type(nombre)[0]
            or "application/octet-stream",
            tamano_bytes=archivo.size,
            hash_sha256=digest.hexdigest(),
            subida_por=usuario_sistema,
        )
        evidencia.save()
    return rutas_guardadas


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def reportar_caso(request):
    tipo_inicial = request.GET.get("tipo")
    form = ReporteCasoForm(
        request.POST or None,
        request.FILES or None,
        initial={"id_tipo_incidente": tipo_inicial} if tipo_inicial else None,
    )
    participantes = ParticipanteFormSet(request.POST or None, prefix="participantes")
    respuestas = RespuestasCasoForm(
        request.POST or None,
        tipo_incidente_id=tipo_inicial,
    )

    if request.method == "POST":
        if (
            form.is_valid()
            and participantes.is_valid()
            and respuestas.is_valid()
        ):
            storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
            rutas_guardadas = []
            guardado = False
            directores_notificados = 0
            try:
                with transaction.atomic():
                    usuario_sistema = obtener_usuario_sistema(request.user)
                    _establecer_contexto_auditoria(
                        request,
                        usuario_sistema,
                        "Reporte enviado por su titular.",
                    )

                    caso = form.save(commit=False)
                    caso.codigo_caso = obtener_codigo_caso()
                    caso.id_usuario_denunciante = usuario_sistema
                    caso.id_denunciante_externo = None
                    caso.id_estado_caso = get_object_or_404(
                        EstadoCaso, codigo="ENVIADO", activo=True
                    )
                    caso.save()

                    _guardar_participantes(caso, participantes)
                    respuestas.guardar_respuestas(caso)
                    archivos = form.cleaned_data.get("archivos") or []
                    rutas_guardadas = guardar_evidencias(
                        caso,
                        archivos,
                        usuario_sistema,
                        storage,
                        rutas_guardadas,
                    )
                    directores_notificados = _notificar_directores(
                        caso,
                        Notificacion.Tipo.CASO_ENVIADO,
                    )
                    notificar_personal(
                        tipo=NotificacionCuenta.Tipo.CASO_NUEVO,
                        mensaje=(
                            f"Se envió el caso {caso.codigo_caso} para revisión."
                        ),
                        url=reverse("casos:detalle", args=(caso.pk,)),
                        roles=("ADMIN", "PSICOLOGO"),
                    )
                    notificar_usuario(
                        request.user,
                        tipo=NotificacionCuenta.Tipo.CASO_REGISTRADO,
                        mensaje=(
                            f"Tu reporte {caso.codigo_caso} fue registrado."
                        ),
                        url=reverse("casos:detalle", args=(caso.pk,)),
                    )
                    if directores_notificados:
                        contenido_evento = (
                            "Reporte enviado a Dirección y notificado a "
                            f"{directores_notificados} Director(es) activo(s)."
                        )
                    else:
                        contenido_evento = (
                            "Reporte registrado, pero no se encontró ningún "
                            "Director activo y aprobado para notificar."
                        )
                    _registrar_evento_caso(
                        caso,
                        usuario_sistema,
                        contenido_evento,
                    )
                guardado = True
            finally:
                if not guardado:
                    for ruta in rutas_guardadas:
                        storage.delete(ruta)

            if directores_notificados:
                messages.success(
                    request,
                    "Tu reporte fue enviado a Dirección. Puedes consultar "
                    "su historial desde tu cuenta.",
                )
            else:
                messages.warning(
                    request,
                    "Tu reporte fue guardado, pero no se notificó a Dirección "
                    "porque no hay Directores activos y aprobados.",
                )
            return render(
                request,
                "casos/reporte_enviado.html",
                {
                    "caso": caso,
                    "mostrar_chatbot": request.user.rol == "ESTUDIANTE",
                },
            )

    return render(
        request,
        "casos/crear.html",
        {
            "form": form,
            "participantes": participantes,
            "respuestas": respuestas,
            "personal_autorizado": es_personal_autorizado(request.user),
        },
    )


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def editar_caso(request, id_caso):
    caso = get_object_or_404(
        Caso.objects.select_related("id_estado_caso"),
        pk=id_caso,
        eliminado_en__isnull=True,
    )
    if not _es_propietario_del_caso(request.user, caso):
        raise PermissionDenied
    ahora = timezone.now()
    if not _caso_en_ventana_de_edicion(caso, ahora):
        messages.error(
            request,
            "Este reporte ya no puede modificarse por el plazo vencido o "
            "por su estado actual.",
        )
        return redirect("casos:detalle", id_caso=caso.pk)

    evidencias_existentes = Evidencia.objects.filter(
        id_caso=caso,
        eliminado_en__isnull=True,
    )
    evidencias_eliminables = evidencias_existentes.filter(
        id_aplicacion_test__isnull=True,
        subida_por_id=caso.id_usuario_denunciante_id,
    )
    participantes_iniciales = list(
        CasoParticipante.objects.filter(id_caso=caso).values(
            "id_rol_participante",
            "nombre_referencial",
            "descripcion",
        )
    )
    form = ReporteCasoForm(
        request.POST or None,
        request.FILES or None,
        instance=caso,
        evidencias_existentes=evidencias_existentes,
        evidencias_eliminables=evidencias_eliminables,
    )
    participantes = ParticipanteFormSet(
        request.POST or None,
        prefix="participantes",
        initial=participantes_iniciales,
    )
    respuestas = RespuestasCasoForm(
        request.POST or None,
        tipo_incidente_id=caso.id_tipo_incidente_id,
        initial=_respuestas_iniciales_caso(caso),
    )

    if request.method == "POST":
        if (
            form.is_valid()
            and participantes.is_valid()
            and respuestas.is_valid()
        ):
            storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
            rutas_guardadas = []
            guardado = False
            try:
                with transaction.atomic():
                    caso_actual = get_object_or_404(
                        Caso.objects.select_for_update().select_related(
                            "id_estado_caso"
                        ),
                        pk=caso.pk,
                        eliminado_en__isnull=True,
                    )
                    ahora = timezone.now()
                    if not _es_propietario_del_caso(
                        request.user, caso_actual
                    ):
                        raise PermissionDenied
                    if not _caso_en_ventana_de_edicion(caso_actual, ahora):
                        messages.error(
                            request,
                            "El estado del reporte cambió y ya no permite editarlo.",
                        )
                        return redirect(
                            "casos:detalle",
                            id_caso=caso_actual.pk,
                        )
                    usuario_sistema = obtener_usuario_sistema(request.user)
                    _establecer_contexto_auditoria(
                        request,
                        usuario_sistema,
                        "Reporte actualizado por su titular.",
                    )
                    cambios = form.save(commit=False)
                    for nombre_campo in form.Meta.fields:
                        setattr(
                            caso_actual,
                            nombre_campo,
                            getattr(cambios, nombre_campo),
                        )
                    caso_actual.actualizado_en = ahora
                    caso_actual.save(
                        update_fields=(*form.Meta.fields, "actualizado_en")
                    )
                    caso = caso_actual
                    _guardar_participantes(caso, participantes)
                    RespuestaCaso.objects.filter(
                        id_caso=caso,
                        origen="FORMULARIO",
                    ).delete()
                    respuestas.guardar_respuestas(caso)

                    eliminadas = form.cleaned_data.get(
                        "eliminar_evidencias", []
                    )
                    if eliminadas:
                        evidencias_eliminables.filter(
                            pk__in=eliminadas
                        ).update(eliminado_en=timezone.now())
                    guardar_evidencias(
                        caso,
                        form.cleaned_data.get("archivos") or [],
                        usuario_sistema,
                        storage,
                        rutas_guardadas,
                    )
                    notificados = _notificar_directores(
                        caso,
                        Notificacion.Tipo.CASO_ACTUALIZADO,
                    )
                    if notificados:
                        detalle_notificacion = (
                            f"Dirección notificada ({notificados} Director(es))."
                        )
                    else:
                        detalle_notificacion = (
                            "No había Directores activos y aprobados para notificar."
                        )
                    _registrar_evento_caso(
                        caso,
                        usuario_sistema,
                        "Reporte y evidencias actualizados por su titular; "
                        + detalle_notificacion,
                    )
                guardado = True
            finally:
                if not guardado:
                    for ruta in rutas_guardadas:
                        storage.delete(ruta)
            if notificados:
                messages.success(
                    request,
                    "El reporte se actualizó, quedó registrado en el historial "
                    "y se notificó a Dirección.",
                )
            else:
                messages.warning(
                    request,
                    "El reporte se actualizó y quedó registrado, pero no se "
                    "notificó a Dirección porque no hay Directores activos y aprobados.",
                )
            return redirect("casos:detalle", id_caso=caso.pk)

    return render(
        request,
        "casos/crear.html",
        {
            "caso": caso,
            "edicion": True,
            "form": form,
            "participantes": participantes,
            "respuestas": respuestas,
        },
    )


@login_required(login_url="login")
@require_POST
def retirar_caso(request, id_caso):
    caso = get_object_or_404(
        Caso.objects.select_related("id_estado_caso"),
        pk=id_caso,
        eliminado_en__isnull=True,
    )
    if not _es_propietario_del_caso(request.user, caso):
        raise PermissionDenied
    with transaction.atomic():
        caso = get_object_or_404(
            Caso.objects.select_for_update().select_related("id_estado_caso"),
            pk=id_caso,
            eliminado_en__isnull=True,
        )
        if not _es_propietario_del_caso(request.user, caso):
            raise PermissionDenied
        ahora = timezone.now()
        estado_retirado = get_object_or_404(
            EstadoCaso, codigo="RETIRADO"
        )
        puede_transicionar = TransicionEstadoCaso.objects.filter(
            id_estado_origen=caso.id_estado_caso_id,
            id_estado_destino=estado_retirado.pk,
        ).exists()
        if (
            not _caso_en_ventana_de_edicion(caso, ahora)
            or not puede_transicionar
        ):
            messages.error(
                request,
                "Este reporte ya no puede retirarse por el plazo vencido o "
                "por su estado actual.",
            )
            return redirect("casos:detalle", id_caso=caso.pk)
        usuario_sistema = obtener_usuario_sistema(request.user)
        _establecer_contexto_auditoria(
            request,
            usuario_sistema,
            "Reporte retirado por su titular.",
        )
        caso.id_estado_caso = estado_retirado
        caso.eliminado_en = ahora
        caso.actualizado_en = ahora
        caso.save(
            update_fields=(
                "id_estado_caso",
                "eliminado_en",
                "actualizado_en",
            )
        )
        notificados = _notificar_directores(
            caso,
            Notificacion.Tipo.CASO_RETIRADO,
        )
        if notificados:
            detalle_notificacion = (
                f"Dirección notificada ({notificados} Director(es))."
            )
        else:
            detalle_notificacion = (
                "No había Directores activos y aprobados para notificar."
            )
        _registrar_evento_caso(
            caso,
            usuario_sistema,
            "Reporte retirado por su titular. "
            + detalle_notificacion
            + " El contenido se conserva para auditoría.",
        )
    if notificados:
        messages.success(
            request,
            "El reporte se retiró de tu lista, se notificó a Dirección y su "
            "historial se conserva para auditoría.",
        )
    else:
        messages.warning(
            request,
            "El reporte se retiró de tu lista y su historial se conserva, "
            "pero no había Directores activos y aprobados para notificar.",
        )
    return redirect("casos:mis_casos")


@login_required
def mis_casos(request):
    if es_personal_autorizado(request.user):
        casos = Caso.objects.filter(eliminado_en__isnull=True)
    else:
        perfil = PerfilDominio.objects.filter(usuario=request.user).first()
        if not perfil:
            casos = Caso.objects.none()
        else:
            casos = Caso.objects.filter(
                id_usuario_denunciante_id=perfil.id_usuario_sistema,
                eliminado_en__isnull=True,
            )
    casos = casos.select_related(
        "id_estado_caso",
        "id_tipo_incidente",
        "id_frecuencia",
    )
    return render(request, "casos/lista.html", {"casos": casos})


def puede_ver_caso(usuario, caso):
    if es_personal_autorizado(usuario):
        return True
    if not usuario.is_authenticated:
        return False
    perfil = PerfilDominio.objects.filter(usuario=usuario).first()
    return bool(
        perfil
        and caso.id_usuario_denunciante_id == perfil.id_usuario_sistema
    )


def respuestas_visibles(caso):
    items = []
    for respuesta in RespuestaCaso.objects.filter(
        id_caso=caso,
        origen="FORMULARIO",
    ):
        pregunta = Pregunta.objects.filter(pk=respuesta.id_pregunta).first()
        opcion = (
            OpcionPregunta.objects.filter(pk=respuesta.id_opcion).first()
            if respuesta.id_opcion
            else None
        )
        valor = (
            texto_catalogo(opcion.texto)
            if opcion
            else respuesta.valor_texto or respuesta.valor_numerico
        )
        items.append({"pregunta": pregunta, "valor": valor})
    return items


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def detalle_caso(request, id_caso):
    caso = get_object_or_404(
        Caso.objects.select_related(
            "id_estado_caso",
            "id_tipo_incidente",
            "id_frecuencia",
            "id_lugar",
            "id_usuario_denunciante",
            "id_denunciante_externo",
        ),
        pk=id_caso,
    )
    if not puede_ver_caso(request.user, caso):
        raise PermissionDenied

    personal = es_personal_autorizado(request.user)
    propietario = _es_propietario_del_caso(request.user, caso)
    usuario_sistema = (
        obtener_usuario_sistema(request.user) if personal else None
    )
    puede_modificar = propietario and _caso_en_ventana_de_edicion(caso)
    puede_retirar = False
    fecha_limite_edicion = caso.creado_en + PLAZO_EDICION_REPORTE
    if propietario and caso.eliminado_en is None:
        estado_retirado = EstadoCaso.objects.filter(codigo="RETIRADO").first()
        puede_retirar = bool(
            estado_retirado
            and _caso_en_ventana_de_edicion(caso)
            and TransicionEstadoCaso.objects.filter(
                id_estado_origen=caso.id_estado_caso_id,
                id_estado_destino=estado_retirado.pk,
            ).exists()
        )
    estado_form = EstadoCasoForm(caso)
    accion_form = AccionSeguimientoForm()
    pregunta_form = MensajeCasoAutoridadForm()
    respuesta_form = RespuestaCasoMensajeForm()

    if request.method == "POST":
        if caso.eliminado_en is not None:
            raise PermissionDenied
        accion = request.POST.get("accion")
        if not personal:
            if accion != "responder" or caso.id_estado_caso.codigo != "CON_PREGUNTA":
                raise PermissionDenied
            respuesta_form = RespuestaCasoMensajeForm(request.POST)
            if respuesta_form.is_valid():
                pregunta = (
                    caso.casomensaje_set.filter(
                        autor_tipo=CasoMensaje.Autor.AUTORIDAD,
                        tipo=CasoMensaje.Tipo.PREGUNTA,
                        visible_para_denunciante=True,
                    )
                    .order_by("-creado_en")
                    .first()
                )
                CasoMensaje.objects.create(
                    id_caso=caso,
                    id_mensaje_padre=pregunta.pk if pregunta else None,
                    autor_tipo=CasoMensaje.Autor.DENUNCIANTE,
                    tipo=CasoMensaje.Tipo.RESPUESTA,
                    contenido=respuesta_form.cleaned_data["contenido"],
                    visible_para_denunciante=True,
                )
                messages.success(request, "Tu respuesta fue enviada.")
                return redirect("casos:detalle", id_caso=caso.pk)
        elif accion == "estado":
            estado_form = EstadoCasoForm(caso, request.POST)
            if estado_form.is_valid():
                estado = get_object_or_404(
                    EstadoCaso, pk=estado_form.cleaned_data["estado"]
                )
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('alza.id_usuario', %s, true), "
                            "set_config('alza.observacion', %s, true)",
                            [
                                str(usuario_sistema.pk),
                                estado_form.cleaned_data["observacion"] or "",
                            ],
                        )
                    caso.id_estado_caso = estado
                    caso.id_motivo_rechazo = (
                        estado_form.cleaned_data["motivo_rechazo"]
                        if estado.codigo == "RECHAZADO"
                        else None
                    )
                    caso.actualizado_en = timezone.now()
                    caso.save(
                        update_fields=(
                            "id_estado_caso",
                            "id_motivo_rechazo",
                            "actualizado_en",
                        )
                    )
                messages.success(request, "Se actualizó el estado del caso.")
                return redirect("casos:detalle", id_caso=caso.pk)
        elif accion == "mensaje":
            pregunta_form = MensajeCasoAutoridadForm(request.POST)
            if pregunta_form.is_valid():
                tipo = pregunta_form.cleaned_data["tipo"]
                CasoMensaje.objects.create(
                    id_caso=caso,
                    autor_tipo=CasoMensaje.Autor.AUTORIDAD,
                    id_usuario=usuario_sistema,
                    tipo=tipo,
                    contenido=pregunta_form.cleaned_data["contenido"],
                    visible_para_denunciante=tipo != CasoMensaje.Tipo.NOTA_INTERNA,
                )
                messages.success(request, "El mensaje quedó registrado.")
                return redirect("casos:detalle", id_caso=caso.pk)
        elif accion == "seguimiento":
            accion_form = AccionSeguimientoForm(request.POST)
            if accion_form.is_valid():
                seguimiento = accion_form.save(commit=False)
                seguimiento.id_caso = caso
                seguimiento.id_usuario_responsable = usuario_sistema
                seguimiento.save()
                messages.success(request, "La acción de seguimiento fue registrada.")
                return redirect("casos:detalle", id_caso=caso.pk)

    mensajes = caso.casomensaje_set.select_related("id_usuario").order_by(
        "creado_en"
    )
    if not personal:
        mensajes = mensajes.filter(visible_para_denunciante=True)
    evidencias = caso.evidencia_set.filter(
        eliminado_en__isnull=True,
        id_aplicacion_test__isnull=True,
    )
    participantes = caso.casoparticipante_set.select_related(
        "id_rol_participante"
    )
    historial = CasoHistorialEstado.objects.filter(id_caso=caso).select_related(
        "id_estado_anterior", "id_estado_nuevo"
    )
    acciones = AccionSeguimiento.objects.filter(id_caso=caso).select_related(
        "id_tipo_accion", "id_usuario_responsable"
    )
    return render(
        request,
        "casos/detalle.html",
        {
            "caso": caso,
            "personal_autorizado": personal,
            "caso_final": (
                caso.eliminado_en is not None
                or caso.id_estado_caso.es_final
            ),
            "puede_modificar": puede_modificar,
            "puede_retirar": puede_retirar,
            "fecha_limite_edicion": fecha_limite_edicion,
            "puede_descargar_evidencias": (
                personal or caso.eliminado_en is None
            ),
            "estado_form": estado_form,
            "accion_form": accion_form,
            "pregunta_form": pregunta_form,
            "respuesta_form": respuesta_form,
            "mensajes_caso": mensajes,
            "evidencias": evidencias,
            "participantes": participantes,
            "historial": historial,
            "acciones": acciones,
            "respuestas": respuestas_visibles(caso),
        },
    )


@login_required(login_url="login")
def seguimiento_externo(request, token):
    if not es_personal_autorizado(request.user):
        raise PermissionDenied
    denunciante = get_object_or_404(
        DenuncianteExterno, codigo_seguimiento=token
    )
    caso = get_object_or_404(
        Caso.objects.select_related("id_estado_caso", "id_tipo_incidente"),
        id_denunciante_externo=denunciante,
        eliminado_en__isnull=True,
    )
    return render(
        request,
        "casos/seguimiento_externo.html",
        {"caso": caso},
    )


@login_required
def descargar_evidencia(request, id_evidencia):
    evidencia = get_object_or_404(
        Evidencia.objects.select_related("id_caso"),
        pk=id_evidencia,
        eliminado_en__isnull=True,
        id_aplicacion_test__isnull=True,
    )
    if not puede_ver_caso(request.user, evidencia.id_caso):
        raise PermissionDenied
    if (
        evidencia.id_caso.eliminado_en is not None
        and not es_personal_autorizado(request.user)
    ):
        raise Http404
    storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
    try:
        archivo = storage.open(evidencia.ruta_archivo, "rb")
    except FileNotFoundError as error:
        raise Http404("El archivo ya no está disponible.") from error
    return FileResponse(
        archivo,
        as_attachment=True,
        filename=evidencia.nombre_archivo,
        content_type="application/octet-stream",
    )


@login_required
@require_http_methods(["GET", "POST"])
def inicio_chatbot(request):
    usuario_sistema = obtener_usuario_sistema(request.user)
    conversaciones = ConversacionChatbot.objects.filter(
        id_usuario=usuario_sistema,
        proposito="APOYO_EMOCIONAL",
    )
    conversaciones_hoy = conversaciones.filter(
        iniciada_en__date=timezone.localdate()
    ).count()
    return render(
        request,
        "chatbot/inicio.html",
        {
            "conversaciones": conversaciones,
            "puede_iniciar_conversacion": (
                conversaciones_hoy < CHATBOT_MAX_CONVERSACIONES_POR_DIA
            ),
            "limite_conversaciones_diarias": CHATBOT_MAX_CONVERSACIONES_POR_DIA,
        },
    )


@login_required
@require_POST
def nueva_conversacion(request):
    usuario_sistema = obtener_usuario_sistema(request.user)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        conversaciones_hoy = ConversacionChatbot.objects.filter(
            id_usuario=usuario_sistema,
            proposito="APOYO_EMOCIONAL",
            iniciada_en__date=timezone.localdate(),
        ).count()
        if conversaciones_hoy >= CHATBOT_MAX_CONVERSACIONES_POR_DIA:
            messages.error(
                request,
                "Alcanzaste el límite de 10 conversaciones nuevas por día.",
            )
            return redirect("casos:chatbot")
        conversacion = ConversacionChatbot.objects.create(
            token=uuid.uuid4(),
            id_usuario=usuario_sistema,
            proposito="APOYO_EMOCIONAL",
            canal="WEB",
        )
        MensajeChatbot.objects.create(
            id_conversacion=conversacion,
            emisor=MensajeChatbot.Emisor.BOT,
            contenido=(
                "Hola. Puedo escucharte y compartir orientación general. "
                "No soy un profesional ni puedo diagnosticar. Evita escribir "
                "nombres completos, teléfonos u otros datos personales."
            ),
        )
    return redirect(
        "casos:conversacion_chatbot",
        id_conversacion=conversacion.pk,
    )


def respuesta_chatbot(texto):
    mensaje = texto.casefold()
    terminos_urgencia = (
        "suicid",
        "quitarme la vida",
        "no quiero vivir",
        "hacerme daño",
        "hacerme dano",
        "estoy en peligro",
        "me están golpeando",
        "me estan golpeando",
        "abuso sexual",
    )
    if any(termino in mensaje for termino in terminos_urgencia):
        return (
            "Gracias por contarlo. Si estás en peligro inmediato, busca ahora "
            "a una persona adulta de confianza y pide ayuda presencial a tu "
            "unidad educativa o a los servicios de emergencia de tu localidad. "
            "No tienes que manejar esto a solas. Esta conversación quedará "
            "marcada para revisión del personal autorizado.",
            True,
            "El mensaje puede requerir apoyo inmediato.",
        )
    if any(termino in mensaje for termino in ("acoso", "bullying", "burlas", "golpe")):
        respuesta = (
            "Siento que estés pasando por eso. Si puedes, conversa con una "
            "persona adulta de confianza o con el equipo de tu unidad educativa. "
            "También puedes registrar una situación desde la sección de reportes. "
            "¿Te sientes seguro/a en este momento?"
        )
    elif any(termino in mensaje for termino in ("triste", "ansiedad", "miedo", "solo", "sola")):
        respuesta = (
            "Gracias por compartir cómo te sientes. Puede ayudar hablar con "
            "alguien de confianza y contarle qué necesitas. No puedo evaluar "
            "ni diagnosticar, pero sí animarte a buscar apoyo humano."
        )
    else:
        respuesta = (
            "Gracias por contármelo. ¿Qué es lo que más te preocupa ahora? "
            "Puedes compartir solo lo que te resulte cómodo. Recuerda que "
            "este chatbot ofrece orientación general y no sustituye a una "
            "persona adulta o profesional."
        )
    return respuesta, False, None


@login_required
@require_http_methods(["GET", "POST"])
def conversacion_chatbot(request, id_conversacion):
    usuario_sistema = obtener_usuario_sistema(request.user)
    conversacion = get_object_or_404(
        ConversacionChatbot.objects.prefetch_related("mensajechatbot_set"),
        pk=id_conversacion,
    )
    personal = es_personal_autorizado(request.user)
    es_propietario = conversacion.id_usuario_id == usuario_sistema.pk
    requiere_atencion = conversacion.mensajechatbot_set.filter(
        requiere_atencion_humana=True
    ).exists()
    if not es_propietario and not (personal and requiere_atencion):
        raise PermissionDenied

    form = MensajeChatbotForm(request.POST or None)
    mensajes_usuario = conversacion.mensajechatbot_set.filter(
        emisor=MensajeChatbot.Emisor.USUARIO
    ).count()
    limite_mensajes_alcanzado = (
        es_propietario
        and mensajes_usuario >= CHATBOT_MAX_MENSAJES_POR_CONVERSACION
    )
    if request.method == "POST" and form.is_valid():
        texto = form.cleaned_data["contenido"].strip()
        if personal and not es_propietario:
            MensajeChatbot.objects.create(
                id_conversacion=conversacion,
                emisor=MensajeChatbot.Emisor.AUTORIDAD,
                contenido=texto,
            )
            messages.success(request, "La respuesta quedó registrada.")
        elif es_propietario:
            with transaction.atomic():
                ConversacionChatbot.objects.select_for_update().get(
                    pk=conversacion.pk
                )
                mensajes_usuario = MensajeChatbot.objects.filter(
                    id_conversacion=conversacion,
                    emisor=MensajeChatbot.Emisor.USUARIO,
                ).count()
                if mensajes_usuario >= CHATBOT_MAX_MENSAJES_POR_CONVERSACION:
                    messages.error(
                        request,
                        "Esta conversación alcanzó el límite de 20 mensajes tuyos.",
                    )
                    return redirect(
                        "casos:conversacion_chatbot",
                        id_conversacion=conversacion.pk,
                    )
                MensajeChatbot.objects.create(
                    id_conversacion=conversacion,
                    emisor=MensajeChatbot.Emisor.USUARIO,
                    contenido=texto,
                )
                contestacion, requiere, motivo = respuesta_chatbot(texto)
                MensajeChatbot.objects.create(
                    id_conversacion=conversacion,
                    emisor=MensajeChatbot.Emisor.BOT,
                    contenido=contestacion,
                    requiere_atencion_humana=requiere,
                    motivo_atencion=motivo,
                )
        return redirect(
            "casos:conversacion_chatbot",
            id_conversacion=conversacion.pk,
        )

    return render(
        request,
        "chatbot/conversacion.html",
        {
            "conversacion": conversacion,
            "mensajes_chatbot": conversacion.mensajechatbot_set.all(),
            "form": form,
            "personal_autorizado": personal,
            "es_propietario": es_propietario,
            "limite_mensajes_alcanzado": limite_mensajes_alcanzado,
        },
    )


@login_required
def atencion_chatbot(request):
    if not es_personal_autorizado(request.user):
        raise PermissionDenied
    conversaciones = (
        ConversacionChatbot.objects.filter(
            mensajechatbot__requiere_atencion_humana=True
        )
        .distinct()
        .order_by("-iniciada_en")
    )
    return render(
        request,
        "chatbot/atencion.html",
        {"conversaciones": conversaciones},
    )


@login_required
def lista_tests(request):
    try:
        usuario_sistema = exigir_perfil_estudiante(request.user)
    except ValidationError as error:
        raise PermissionDenied(str(error)) from error
    tests = TestPsicologico.objects.filter(activo=True)
    aplicaciones = AplicacionTest.objects.filter(
        id_estudiante_id=usuario_sistema.id_persona_id
    ).select_related("id_test")
    return render(
        request,
        "evaluaciones/lista.html",
        {"tests": tests, "aplicaciones": aplicaciones},
    )


@login_required
@require_GET
def bienestar_calma(request):
    if request.user.rol != "ESTUDIANTE":
        raise PermissionDenied(
            "Esta actividad está disponible únicamente para estudiantes."
        )
    return render(request, "evaluaciones/calma.html")


@login_required
@require_http_methods(["GET", "POST"])
def aplicar_test(request, id_test):
    try:
        usuario_sistema = exigir_perfil_estudiante(request.user)
    except ValidationError as error:
        raise PermissionDenied(str(error)) from error
    estudiante = get_object_or_404(
        Estudiante,
        pk=usuario_sistema.id_persona_id,
    )
    test = get_object_or_404(TestPsicologico, pk=id_test, activo=True)
    casos = Caso.objects.filter(id_usuario_denunciante=usuario_sistema)
    form = AplicarTestForm(
        test,
        request.POST or None,
        request.FILES or None,
        casos_queryset=casos,
    )
    if request.method == "POST" and form.is_valid():
        caso = form.cleaned_data.get("id_caso")
        archivos = form.cleaned_data.get("dibujo") or []
        with transaction.atomic():
            aplicacion = AplicacionTest.objects.create(
                id_test=test,
                id_caso=caso,
                id_estudiante=estudiante,
                id_usuario_aplicador=usuario_sistema,
                modalidad="AUTOADMINISTRADO",
                iniciada_en=timezone.now(),
            )
            if test.formato == "DIBUJO":
                almacenamiento = FileSystemStorage(
                    location=settings.PRIVATE_UPLOAD_ROOT
                )
                rutas_guardadas = []
                guardado = False
                try:
                    for archivo in archivos:
                        guardar_evidencias(
                            caso,
                            [archivo],
                            usuario_sistema,
                            almacenamiento,
                            rutas_guardadas,
                        )
                        Evidencia.objects.filter(
                            id_caso=caso,
                            ruta_archivo=rutas_guardadas[-1],
                        ).update(id_aplicacion_test=aplicacion.pk)
                    aplicacion.finalizada_en = timezone.now()
                    aplicacion.interpretacion_orientativa = (
                        "El dibujo es material de apoyo para una conversación "
                        "con personal autorizado. No debe interpretarse como "
                        "diagnóstico."
                    )
                    aplicacion.save(
                        update_fields=(
                            "finalizada_en",
                            "interpretacion_orientativa",
                        )
                    )
                    guardado = True
                finally:
                    if not guardado:
                        for ruta in rutas_guardadas:
                            almacenamiento.delete(ruta)
            else:
                puntaje = form.guardar_respuestas(aplicacion)
                aplicacion.puntaje_total = puntaje
                aplicacion.finalizada_en = timezone.now()
                aplicacion.interpretacion_orientativa = (
                    f"Puntaje referencial: {puntaje}. Esta herramienta no es "
                    "un diagnóstico y sus resultados deben ser revisados por "
                    "un profesional."
                )
                aplicacion.save(
                    update_fields=(
                        "puntaje_total",
                        "finalizada_en",
                        "interpretacion_orientativa",
                    )
                )
        messages.success(request, "La actividad se guardó correctamente.")
        return redirect(
            "casos:resultado_test",
            id_aplicacion=aplicacion.pk,
        )
    return render(
        request,
        "evaluaciones/aplicar.html",
        {
            "test": test,
            "form": form,
            "campos_test": [
                (item, form[nombre], es_opcion)
                for item, nombre, es_opcion in form.items
            ],
        },
    )


@login_required
def resultado_test(request, id_aplicacion):
    try:
        usuario_sistema = exigir_perfil_estudiante(request.user)
    except ValidationError as error:
        raise PermissionDenied(str(error)) from error
    aplicacion = get_object_or_404(
        AplicacionTest.objects.select_related("id_test", "id_caso"),
        pk=id_aplicacion,
        id_estudiante_id=usuario_sistema.id_persona_id,
    )
    return render(
        request,
        "evaluaciones/resultado.html",
        {"aplicacion": aplicacion},
    )


@login_required
@require_http_methods(["GET", "POST"])
def notificaciones(request):
    usuario_sistema = obtener_usuario_sistema(request.user)
    avisos_legacy = Notificacion.objects.filter(id_usuario=usuario_sistema)
    avisos_cuenta = NotificacionCuenta.objects.filter(usuario=request.user)
    if request.method == "POST":
        accion = request.POST.get("accion")
        ahora = timezone.now()
        if accion == "limpiar":
            with transaction.atomic():
                avisos_legacy.delete()
                avisos_cuenta.delete()
            messages.success(request, "Se eliminaron tus notificaciones.")
        elif accion == "marcar_leidas":
            avisos_legacy.filter(leida=False).update(
                leida=True,
                leida_en=ahora,
            )
            avisos_cuenta.filter(leida=False).update(
                leida=True,
                leida_en=ahora,
            )
            messages.success(
                request,
                "Las notificaciones se marcaron como leídas.",
            )
        else:
            return HttpResponseBadRequest("La acción de notificaciones no es válida.")
        return redirect("casos:notificaciones")
    avisos = [
        {
            "tipo": aviso.get_tipo_display(),
            "mensaje": aviso.mensaje,
            "creado_en": aviso.creado_en,
            "leida": aviso.leida,
            "url": (
                reverse("casos:detalle", args=(aviso.id_caso_id,))
                if aviso.id_caso_id
                else reverse(
                    "casos:conversacion_chatbot",
                    args=(aviso.id_conversacion_id,),
                )
                if aviso.id_conversacion_id
                else ""
            ),
            "enlace": "Ver caso" if aviso.id_caso_id else "Ver conversación",
        }
        for aviso in avisos_legacy
    ]
    avisos.extend(
        {
            "tipo": aviso.get_tipo_display(),
            "mensaje": aviso.mensaje,
            "creado_en": aviso.creado_en,
            "leida": aviso.leida,
            "url": aviso.url,
            "enlace": "Ver detalle",
        }
        for aviso in avisos_cuenta
    )
    avisos.sort(key=lambda aviso: aviso["creado_en"], reverse=True)
    return render(
        request,
        "casos/notificaciones.html",
        {"notificaciones": avisos},
    )


@login_required
@require_GET
def contar_notificaciones_no_leidas(request):
    usuario_sistema = obtener_usuario_sistema(request.user)
    cantidad_legacy = Notificacion.objects.filter(
        id_usuario=usuario_sistema,
        leida=False,
    ).count()
    cantidad_cuenta = NotificacionCuenta.objects.filter(
        usuario=request.user,
        leida=False,
    ).count()
    respuesta = JsonResponse(
        {"sin_leer": cantidad_legacy + cantidad_cuenta}
    )
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
