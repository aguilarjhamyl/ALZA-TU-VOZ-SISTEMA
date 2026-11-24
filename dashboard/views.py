import logging
import smtplib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db import connection, models, transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator
from django.http import Http404
from django.forms import ModelChoiceField, modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from casos.admin import (
    MODELOS_ADMINISTRATIVOS,
    NO_DELETE_MODELS,
    READ_ONLY_MODELS,
    SENSITIVE_FIELDS,
)
from casos.models import (
    AccionSeguimiento,
    Caso,
    EstadoCaso,
    MensajeChatbot,
    NivelRiesgo,
    Rol,
)
from casos.utils import texto_catalogo
from usuarios.emails import enviar_correo_revision
from usuarios.models import NotificacionCuenta, Usuario
from usuarios.notificaciones import notificar_usuario


REGISTROS_POR_PAGINA = 20
logger = logging.getLogger(__name__)


ADMIN_MENU_GROUPS = (
    {
        "title": "PERSONAS Y ACCESOS",
        "items": (
            ("Usuarios y solicitudes", "usuarios", "bi-people", "blue"),
            ("Roles del sistema", "rol", "bi-shield-lock", "violet"),
            ("Personas", "persona", "bi-person-vcard", "cyan"),
            ("Estudiantes", "estudiante", "bi-mortarboard", "blue"),
            ("Tutores", "tutor", "bi-person-heart", "pink"),
            ("Cuentas de dominio", "usuariodominio", "bi-person-lock", "gray"),
            ("Denunciantes externos", "denuncianteexterno", "bi-person-exclamation", "orange"),
        ),
    },
    {
        "title": "CASOS Y ATENCIÓN",
        "items": (
            ("Casos", "caso", "bi-folder2-open", "blue"),
            ("Participantes", "casoparticipante", "bi-person-lines-fill", "cyan"),
            ("Mensajes del caso", "casomensaje", "bi-chat-left-text", "violet"),
            ("Respuestas del caso", "respuestacaso", "bi-card-text", "teal"),
            ("Evidencias", "evidencia", "bi-paperclip", "orange"),
            ("Historial de estados", "casohistorialestado", "bi-clock-history", "yellow"),
        ),
    },
    {
        "title": "SEGUIMIENTO",
        "items": (
            ("Acciones de seguimiento", "accionseguimiento", "bi-list-check", "green"),
            ("Notificaciones", "notificacion", "bi-bell", "orange"),
            ("Tipos de acción", "tipoaccion", "bi-ui-checks", "teal"),
        ),
    },
    {
        "title": "CHATBOT",
        "items": (
            ("Conversaciones", "conversacionchatbot", "bi-chat-dots", "cyan"),
            ("Mensajes", "mensajechatbot", "bi-chat-left-dots", "violet"),
        ),
    },
    {
        "title": "EVALUACIONES Y FORMULARIOS",
        "items": (
            ("Tests psicológicos", "testpsicologico", "bi-clipboard2-pulse", "violet"),
            ("Preguntas de tests", "testitem", "bi-card-checklist", "blue"),
            ("Opciones de tests", "testopcion", "bi-ui-radios", "teal"),
            ("Aplicaciones de tests", "aplicaciontest", "bi-clipboard2-data", "orange"),
            ("Respuestas de tests", "respuestatest", "bi-journal-check", "yellow"),
            ("Preguntas del reporte", "pregunta", "bi-question-circle", "blue"),
            ("Opciones de preguntas", "opcionpregunta", "bi-list-ul", "green"),
        ),
    },
    {
        "title": "CATÁLOGOS INSTITUCIONALES",
        "items": (
            ("Categorías de incidentes", "categoriaincidente", "bi-collection", "teal"),
            ("Tipos de incidente", "tipoincidente", "bi-exclamation-triangle", "orange"),
            ("Frecuencias", "frecuencia", "bi-arrow-repeat", "cyan"),
            ("Lugares", "lugarincidente", "bi-geo-alt", "blue"),
            ("Estados de casos", "estadocaso", "bi-flag", "yellow"),
            ("Niveles de riesgo", "nivelriesgo", "bi-shield-exclamation", "red"),
            ("Motivos de rechazo", "motivorechazo", "bi-ban", "red"),
            ("Roles de participantes", "rolparticipante", "bi-person-badge", "violet"),
            ("Tipos de evidencia", "tipoevidencia", "bi-file-earmark", "orange"),
            ("Tipos de respuesta", "tiporespuesta", "bi-ui-radios", "green"),
            ("Cursos", "curso", "bi-easel", "cyan"),
        ),
    },
    {
        "title": "AUDITORÍA Y REGISTROS",
        "items": (
            ("Bitácora de auditoría", "logauditoria", "bi-journal-text", "teal"),
            ("Registros de acceso", "logacceso", "bi-shield-check", "blue"),
        ),
    },
)

ADMIN_MODULE_ROUTES = {
    "evaluaciones": "testpsicologico",
    "seguimiento": "accionseguimiento",
    "evidencias": "evidencia",
    "notificaciones": "notificacion",
    "catalogos": "categoriaincidente",
    "auditoria": "logauditoria",
    "logs": "logacceso",
    "reportes": "caso",
}

ADMIN_SHORTCUTS = (
    ("Casos", "caso", "bi-folder2-open", "blue"),
    ("Usuarios", "usuarios", "bi-people", "orange"),
    ("Seguimiento", "accionseguimiento", "bi-list-check", "green"),
    ("Chatbot", "conversacionchatbot", "bi-chat-dots", "violet"),
    ("Evaluaciones", "testpsicologico", "bi-clipboard2-pulse", "cyan"),
    ("Auditoría", "logauditoria", "bi-journal-text", "teal"),
)

MODELOS_POR_SLUG = {
    modelo.__name__.lower(): modelo for modelo in MODELOS_ADMINISTRATIVOS
}
TITULOS_TABLAS = {
    slug: title
    for group in ADMIN_MENU_GROUPS
    for title, slug, _icon, _color in group["items"]
}
TITULOS_TABLAS["usuarios"] = "Usuarios y solicitudes"

def _es_administrador(usuario):
    return usuario.is_superuser or usuario.is_staff or usuario.rol == "ADMIN"


def _contexto_menu_administrador():
    return {
        "admin_menu_groups": [
            {
                "title": group["title"],
                "items": [
                    {
                        "title": title,
                        "slug": slug,
                        "url": reverse("dashboard:tabla", args=(slug,)),
                        "icon": icon,
                        "color": color,
                    }
                    for title, slug, icon, color in group["items"]
                ],
            }
            for group in ADMIN_MENU_GROUPS
        ]
    }


def _tabla_disponible(modelo, tablas_disponibles):
    return modelo._meta.db_table in tablas_disponibles


def _estadisticas_administrador():
    tablas_disponibles = set(connection.introspection.table_names())
    modelo_usuario = get_user_model()

    estadisticas = {
        "usuarios_activos": modelo_usuario.objects.filter(is_active=True).count(),
        "solicitudes_pendientes": modelo_usuario.objects.filter(
            estado_solicitud="PENDIENTE"
        ).count(),
        "casos_disponibles": all(
            _tabla_disponible(modelo, tablas_disponibles)
            for modelo in (Caso, EstadoCaso, NivelRiesgo)
        ),
        "chatbot_disponible": _tabla_disponible(MensajeChatbot, tablas_disponibles),
        "seguimiento_disponible": _tabla_disponible(
            AccionSeguimiento, tablas_disponibles
        ),
    }

    estados_casos = []
    niveles_riesgo = []
    casos_recientes = []
    actividad_semanal = []
    total_casos = None
    casos_abiertos = None
    casos_prioritarios = None
    conversaciones_pendientes = None
    acciones_pendientes = None

    if estadisticas["casos_disponibles"]:
        casos = Caso.objects.filter(eliminado_en__isnull=True)
        total_casos = casos.count()
        casos_abiertos = casos.filter(id_estado_caso__es_final=False).count()
        casos_prioritarios = casos.filter(
            id_nivel_riesgo__requiere_alerta=True
        ).count()

        estados_casos = list(
            casos.values("id_estado_caso__nombre")
            .annotate(total=Count("pk"))
            .order_by("-total", "id_estado_caso__nombre")[:6]
        )
        niveles_riesgo = list(
            casos.filter(id_nivel_riesgo__isnull=False)
            .values("id_nivel_riesgo__nombre")
            .annotate(total=Count("pk"))
            .order_by("id_nivel_riesgo__orden")
        )
        maximo_riesgo = max(
            (nivel["total"] for nivel in niveles_riesgo),
            default=0,
        )
        for nivel in niveles_riesgo:
            nivel["nombre"] = nivel.pop("id_nivel_riesgo__nombre")
            nivel["porcentaje"] = (
                round(nivel["total"] * 100 / maximo_riesgo)
                if maximo_riesgo
                else 0
            )
        casos_recientes = list(
            casos.select_related("id_estado_caso", "id_nivel_riesgo")[:8]
        )

        hoy = timezone.localdate()
        desde = hoy - timedelta(days=6)
        conteo_por_dia = {
            fila["dia"]: fila["total"]
            for fila in casos.filter(creado_en__date__gte=desde)
            .annotate(dia=TruncDate("creado_en"))
            .values("dia")
            .annotate(total=Count("pk"))
        }
        dias_semana = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
        actividad_semanal = [
            {
                "etiqueta": dias_semana[(desde + timedelta(days=indice)).weekday()],
                "cantidad": conteo_por_dia.get(desde + timedelta(days=indice), 0),
            }
            for indice in range(7)
        ]
        maximo_diario = max((dia["cantidad"] for dia in actividad_semanal), default=0)
        for dia in actividad_semanal:
            dia["porcentaje"] = (
                round(dia["cantidad"] * 100 / maximo_diario)
                if maximo_diario
                else 0
            )

    if estadisticas["chatbot_disponible"]:
        conversaciones_pendientes = (
            MensajeChatbot.objects.filter(requiere_atencion_humana=True)
            .values("id_conversacion_id")
            .distinct()
            .count()
        )

    if estadisticas["seguimiento_disponible"]:
        acciones_pendientes = AccionSeguimiento.objects.filter(
            estado=AccionSeguimiento.Estado.PENDIENTE
        ).count()

    maximo_estado = max(
        (estado["total"] for estado in estados_casos),
        default=0,
    )
    for estado in estados_casos:
        estado["nombre"] = estado.pop("id_estado_caso__nombre")
        estado["porcentaje"] = (
            round(estado["total"] * 100 / maximo_estado)
            if maximo_estado
            else 0
        )

    return {
        **estadisticas,
        "total_casos": total_casos,
        "casos_abiertos": casos_abiertos,
        "casos_prioritarios": casos_prioritarios,
        "conversaciones_pendientes": conversaciones_pendientes,
        "acciones_pendientes": acciones_pendientes,
        "estados_casos": estados_casos,
        "niveles_riesgo": niveles_riesgo,
        "casos_recientes": casos_recientes,
        "actividad_semanal": actividad_semanal,
    }


@login_required
def inicio_dashboard(request):
    usuario = request.user

    if not (
        usuario.is_superuser
        or usuario.is_staff
        or usuario.rol in ("ADMIN", "DIRECTOR", "PSICOLOGO")
    ):
        raise PermissionDenied(
            "No tienes autorización para acceder al panel institucional."
        )

    contexto = {
        "usuario": usuario,
        "es_administrador": _es_administrador(usuario),
    }
    if contexto["es_administrador"]:
        contexto.update(_estadisticas_administrador())
        contexto.update(_contexto_menu_administrador())
        contexto["admin_shortcuts"] = [
            {
                "title": title,
                "url": reverse("dashboard:tabla", args=(url_name,)),
                "icon": icon,
                "color": color,
            }
            for title, url_name, icon, color in ADMIN_SHORTCUTS
        ]

    return render(request, "dashboard/inicio.html", contexto)


@login_required
def modulo_administrador(request, modulo):
    usuario = request.user
    if not _es_administrador(usuario):
        raise PermissionDenied(
            "No tienes autorización para acceder a los módulos administrativos."
        )

    tabla = ADMIN_MODULE_ROUTES.get(modulo)
    if tabla is None:
        raise Http404("El módulo administrativo solicitado no existe.")
    return redirect("dashboard:tabla", tabla=tabla)


def _columnas_tabla(modelo):
    ocultos = SENSITIVE_FIELDS.get(modelo, set())
    campos = [
        campo
        for campo in modelo._meta.concrete_fields
        if campo.name not in ocultos
    ]
    columnas = campos[:6]
    campo_estado = _campo_estado_activo(modelo)
    if campo_estado is not None and campo_estado not in columnas:
        columnas = [*campos[:5], campo_estado]
    return columnas


def _campo_estado_activo(modelo):
    for nombre in ("activo", "activa"):
        try:
            campo = modelo._meta.get_field(nombre)
        except FieldDoesNotExist:
            continue
        if isinstance(campo, models.BooleanField):
            return campo
    return None


def _ids_registros_referenciados(modelo, ids):
    ids = set(ids)
    if not ids:
        return set()

    ids_referenciados = set()
    tabla_objetivo = modelo._meta.db_table
    columna_objetivo = modelo._meta.pk.column
    tablas = connection.introspection.table_names()
    marcadores = ", ".join(["%s"] * len(ids))
    parametros = tuple(ids)

    with connection.cursor() as cursor:
        for tabla in tablas:
            restricciones = connection.introspection.get_constraints(cursor, tabla)
            for restriccion in restricciones.values():
                if restriccion.get("foreign_key") != (
                    tabla_objetivo,
                    columna_objetivo,
                ):
                    continue
                columnas = restriccion.get("columns", ())
                if len(columnas) != 1:
                    continue
                columna = columnas[0]
                tabla_sql = connection.ops.quote_name(tabla)
                columna_sql = connection.ops.quote_name(columna)
                cursor.execute(
                    f"SELECT DISTINCT {columna_sql} FROM {tabla_sql} "
                    f"WHERE {columna_sql} IN ({marcadores})",
                    parametros,
                )
                ids_referenciados.update(row[0] for row in cursor.fetchall())
    return ids_referenciados


def _filtrar_relaciones_activas(formulario, modelo, objeto):
    for campo in modelo._meta.concrete_fields:
        if not campo.many_to_one:
            continue
        campo_formulario = formulario.fields.get(campo.name)
        campo_estado = _campo_estado_activo(campo.related_model)
        if (
            not isinstance(campo_formulario, ModelChoiceField)
            or campo_estado is None
        ):
            continue

        queryset = campo_formulario.queryset
        queryset_activo = queryset.filter(**{campo_estado.name: True})
        id_actual = getattr(objeto, campo.attname, None) if objeto else None
        if id_actual is not None:
            queryset_activo |= queryset.filter(pk=id_actual)
        campo_formulario.queryset = queryset_activo.distinct()


def _valor_celda(objeto, campo):
    if campo.choices:
        return texto_catalogo(getattr(objeto, f"get_{campo.name}_display")())
    valor = getattr(objeto, campo.name)
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        if campo.name in {"activo", "activa"}:
            return "Habilitado" if valor else "Inhabilitado"
        return "Sí" if valor else "No"
    if campo.is_relation:
        valor = _etiqueta_relacionada(valor)
    return texto_catalogo(str(valor))


def _etiqueta_relacionada(objeto):
    if objeto is None:
        return None
    if type(objeto).__str__ is not models.Model.__str__:
        return str(objeto)
    for atributo in ("nombre", "nombres", "codigo"):
        valor = getattr(objeto, atributo, None)
        if valor:
            return valor
    return objeto._meta.verbose_name


def _etiqueta_columna(campo):
    etiquetas = {
        "codigo": "Código",
        "descripcion": "Descripción",
        "es_autoridad": "¿Es autoridad?",
        "activo": "Estado",
        "activa": "Estado",
        "permite_edicion": "¿Permite edición?",
        "es_final": "¿Es estado final?",
        "requiere_alerta": "¿Requiere alerta?",
        "involucra_personal": "¿Involucra personal?",
        "correo_verificado": "Correo verificado",
        "creado_en": "Fecha de creación",
        "actualizado_en": "Última actualización",
    }
    if campo.name in etiquetas:
        return etiquetas[campo.name]
    nombre = str(campo.verbose_name)
    if campo.name.startswith("id_"):
        nombre = f"ID de {nombre[3:]}"
    return texto_catalogo(nombre).capitalize()


def _contexto_tabla(modelo, slug, request):
    tabla_disponible = _tabla_disponible(
        modelo,
        set(connection.introspection.table_names()),
    )
    if not tabla_disponible:
        return {
            "tabla_titulo": TITULOS_TABLAS[slug],
            "tabla_slug": slug,
            "tabla_no_disponible": True,
            "columnas": [],
            "filas": [],
            "pagina": Paginator([], REGISTROS_POR_PAGINA).get_page(1),
            "termino": "",
            "solo_lectura": modelo in READ_ONLY_MODELS,
            "puede_eliminar": False,
            "puede_cambiar_estado": False,
            "url_nuevo": None,
            "modelo": modelo,
        }

    campos = _columnas_tabla(modelo)
    relaciones = [
        campo.name for campo in campos if campo.is_relation and campo.many_to_one
    ]
    queryset = modelo._default_manager.all()
    if modelo is Caso:
        queryset = queryset.filter(eliminado_en__isnull=True)
    if not queryset.ordered:
        queryset = queryset.order_by(modelo._meta.pk.name)
    if relaciones:
        queryset = queryset.select_related(*relaciones)

    termino = request.GET.get("q", "").strip()[:100]
    if termino:
        busqueda = Q()
        campos_busqueda = [
            campo
            for campo in modelo._meta.concrete_fields
            if campo.name not in SENSITIVE_FIELDS.get(modelo, set())
            if campo.get_internal_type()
            in {"CharField", "EmailField"}
        ]
        for campo in campos_busqueda:
            busqueda |= Q(**{f"{campo.name}__icontains": termino})
        if campos_busqueda:
            queryset = queryset.filter(busqueda)

    pagina = Paginator(queryset, REGISTROS_POR_PAGINA).get_page(
        request.GET.get("page")
    )
    objetos = list(pagina.object_list)
    ids_referenciados = _ids_registros_referenciados(
        modelo,
        (objeto.pk for objeto in objetos),
    )
    campo_estado = _campo_estado_activo(modelo)
    filas = [
        {
            "object": objeto,
            "values": [_valor_celda(objeto, campo) for campo in campos],
            "tiene_referencias": objeto.pk in ids_referenciados,
            "estado_activo": (
                getattr(objeto, campo_estado.name)
                if campo_estado is not None
                else False
            ),
            "estado_protegido": (
                modelo is EstadoCaso
                and campo_estado is not None
                and objeto.codigo == "ENVIADO"
                and getattr(objeto, campo_estado.name)
            ),
        }
        for objeto in objetos
    ]
    return {
        "tabla_titulo": TITULOS_TABLAS[slug],
        "tabla_slug": slug,
        "columnas": [_etiqueta_columna(campo) for campo in campos],
        "filas": filas,
        "pagina": pagina,
        "paginas": _paginas_visibles(pagina),
        "termino": termino,
        "solo_lectura": modelo in READ_ONLY_MODELS,
        "puede_cambiar_estado": (
            campo_estado is not None and modelo not in READ_ONLY_MODELS
        ),
        "puede_eliminar": (
            modelo not in READ_ONLY_MODELS and modelo not in NO_DELETE_MODELS
        ),
        "url_nuevo": (
            reverse("dashboard:tabla_nuevo", args=(slug,))
            if modelo not in READ_ONLY_MODELS
            else None
        ),
        "modelo": modelo,
    }


def _contexto_usuario(request):
    modelo_usuario = get_user_model()
    termino = request.GET.get("q", "").strip()[:100]
    usuarios = modelo_usuario.objects.all().order_by("-date_joined", "-pk")
    if termino:
        usuarios = usuarios.filter(
            Q(username__icontains=termino)
            | Q(email__icontains=termino)
            | Q(first_name__icontains=termino)
            | Q(last_name__icontains=termino)
        )
    pagina = Paginator(usuarios, REGISTROS_POR_PAGINA).get_page(
        request.GET.get("page")
    )
    return {
        "tabla_titulo": TITULOS_TABLAS["usuarios"],
        "tabla_slug": "usuarios",
        "columnas": (
            "Usuario",
            "Nombre",
            "Correo",
            "Rol",
            "Estado",
            "Correo verificado",
        ),
        "filas": [
            {
                "object": usuario,
                "values": (
                    usuario.username,
                    usuario.get_full_name() or "—",
                    usuario.email or "—",
                    usuario.get_rol_display(),
                    usuario.get_estado_solicitud_display(),
                    "Sí" if usuario.email_verificado else "No",
                ),
            }
            for usuario in pagina.object_list
        ],
        "pagina": pagina,
        "paginas": _paginas_visibles(pagina),
        "termino": termino,
        "solo_lectura": True,
        "puede_eliminar": False,
        "url_nuevo": None,
        "es_tabla_usuarios": True,
    }


def _paginas_visibles(pagina):
    return [
        {
            "numero": numero,
            "es_ellipsis": numero == pagina.paginator.ELLIPSIS,
            "es_actual": numero == pagina.number,
        }
        for numero in pagina.paginator.get_elided_page_range(pagina.number)
    ]


@login_required
def tabla_administrativa(request, tabla):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para acceder a las tablas administrativas."
        )
    if tabla == "usuarios":
        contexto = _contexto_usuario(request)
    else:
        modelo = MODELOS_POR_SLUG.get(tabla)
        if modelo is None:
            raise Http404("La tabla administrativa solicitada no existe.")
        contexto = _contexto_tabla(modelo, tabla, request)
    contexto.update(
        {
            "usuario": request.user,
            "es_administrador": True,
        }
    )
    contexto.update(_contexto_menu_administrador())
    return render(request, "dashboard/tabla.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def registro_administrativo(request, tabla, pk=None, solo_ver=False):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para modificar tablas administrativas."
        )
    modelo = MODELOS_POR_SLUG.get(tabla)
    if modelo is None:
        raise Http404("La tabla administrativa solicitada no existe.")
    if not _tabla_disponible(
        modelo,
        set(connection.introspection.table_names()),
    ):
        raise Http404("La tabla administrativa todavía no está conectada.")
    if solo_ver and pk is None:
        raise Http404("El registro solicitado no existe.")
    objeto = get_object_or_404(modelo, pk=pk) if pk is not None else None
    campo_estado = _campo_estado_activo(modelo)
    tiene_referencias = (
        objeto is not None
        and objeto.pk in _ids_registros_referenciados(modelo, (objeto.pk,))
    )
    solo_detalle = (
        solo_ver
        or modelo in READ_ONLY_MODELS
        or (modelo is Rol and objeto is not None)
        or (
            modelo is not Rol
            and campo_estado is not None
            and tiene_referencias
        )
    )
    if solo_detalle and request.method == "POST":
        raise PermissionDenied(
            "Los registros relacionados solo permiten consultar o cambiar su estado."
        )
    if solo_detalle:
        campos = _columnas_tabla(modelo)
        return render(
            request,
            "dashboard/registro_detalle.html",
            {
                "usuario": request.user,
                "es_administrador": True,
                **_contexto_menu_administrador(),
                "tabla_titulo": TITULOS_TABLAS[tabla],
                "tabla_slug": tabla,
                "detalle_campos": [
                    (campo.verbose_name, _valor_celda(objeto, campo))
                    for campo in campos
                ],
            },
        )

    campos_excluidos = set(SENSITIVE_FIELDS.get(modelo, set()))
    if objeto is None:
        campos_excluidos.update(
            campo.name
            for campo in modelo._meta.concrete_fields
            if campo.primary_key or campo.auto_created
        )
    formulario_modelo = modelform_factory(
        modelo,
        exclude=tuple(campos_excluidos),
    )
    formulario = formulario_modelo(
        request.POST or None,
        instance=objeto,
        files=request.FILES or None,
    )
    _filtrar_relaciones_activas(formulario, modelo, objeto)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(
            request,
            f"El registro de «{TITULOS_TABLAS[tabla]}» se guardó correctamente.",
        )
        return redirect("dashboard:tabla", tabla=tabla)

    return render(
        request,
        "dashboard/registro_form.html",
        {
            "usuario": request.user,
            "es_administrador": True,
            **_contexto_menu_administrador(),
            "tabla_titulo": TITULOS_TABLAS[tabla],
            "tabla_slug": tabla,
            "formulario": formulario,
            "es_edicion": objeto is not None,
        },
    )


@login_required
@require_POST
def eliminar_registro_administrativo(request, tabla, pk):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para eliminar registros administrativos."
        )
    modelo = MODELOS_POR_SLUG.get(tabla)
    if modelo is None:
        raise Http404("La tabla administrativa solicitada no existe.")
    if not _tabla_disponible(
        modelo,
        set(connection.introspection.table_names()),
    ):
        raise Http404("La tabla administrativa todavía no está conectada.")
    if modelo in READ_ONLY_MODELS or modelo in NO_DELETE_MODELS:
        raise PermissionDenied("Los registros de esta tabla no se pueden eliminar.")
    objeto = get_object_or_404(modelo, pk=pk)
    if objeto.pk in _ids_registros_referenciados(modelo, (objeto.pk,)):
        raise PermissionDenied(
            "El registro tiene datos relacionados; inhabilítalo en lugar de eliminarlo."
        )
    objeto.delete()
    messages.success(
        request,
        f"El registro de «{TITULOS_TABLAS[tabla]}» se eliminó correctamente.",
    )
    return redirect("dashboard:tabla", tabla=tabla)


@login_required
@require_POST
def alternar_estado_rol(request, pk):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para cambiar el estado de los roles."
        )
    rol = get_object_or_404(Rol, pk=pk)
    if rol.pk == 1 or rol.codigo == "ADMINISTRADOR":
        raise PermissionDenied("El rol administrador no se puede inhabilitar.")
    rol.activo = not rol.activo
    rol.save(update_fields=("activo",))
    messages.success(
        request,
        f"El rol «{texto_catalogo(rol.nombre)}» quedó "
        f"{'habilitado' if rol.activo else 'inhabilitado'}.",
    )
    return redirect("dashboard:tabla", tabla="rol")


@login_required
@require_POST
def alternar_estado_registro(request, tabla, pk):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para cambiar el estado de los registros."
        )
    modelo = MODELOS_POR_SLUG.get(tabla)
    if modelo is None:
        raise Http404("La tabla administrativa solicitada no existe.")
    if modelo is Rol or modelo in READ_ONLY_MODELS:
        raise PermissionDenied("Esta tabla no permite cambiar el estado por esta acción.")
    if not _tabla_disponible(
        modelo,
        set(connection.introspection.table_names()),
    ):
        raise Http404("La tabla administrativa todavía no está conectada.")

    campo_estado = _campo_estado_activo(modelo)
    if campo_estado is None:
        raise PermissionDenied("Esta tabla no tiene un estado habilitable.")
    objeto = get_object_or_404(modelo, pk=pk)
    if objeto.pk not in _ids_registros_referenciados(modelo, (objeto.pk,)):
        raise PermissionDenied(
            "Solo se puede cambiar el estado de registros relacionados."
        )
    if (
        modelo is EstadoCaso
        and objeto.codigo == "ENVIADO"
        and getattr(objeto, campo_estado.name)
    ):
        raise PermissionDenied("El estado inicial de los casos no se puede inhabilitar.")

    nuevo_estado = not getattr(objeto, campo_estado.name)
    setattr(objeto, campo_estado.name, nuevo_estado)
    objeto.save(update_fields=(campo_estado.name,))
    messages.success(
        request,
        f"El registro quedó {'habilitado' if nuevo_estado else 'inhabilitado'}.",
    )
    return redirect("dashboard:tabla", tabla=tabla)


@login_required
@require_POST
def revisar_solicitud(request, pk, accion):
    if not _es_administrador(request.user):
        raise PermissionDenied(
            "No tienes autorización para revisar solicitudes de cuenta."
        )
    if accion not in {"aprobar", "rechazar"}:
        raise Http404("La acción solicitada no existe.")
    usuario = get_object_or_404(
        get_user_model(),
        pk=pk,
        estado_solicitud=Usuario.EstadoSolicitud.PENDIENTE,
    )

    aprobado = accion == "aprobar"
    with transaction.atomic():
        usuario.estado_solicitud = (
            Usuario.EstadoSolicitud.APROBADA
            if aprobado
            else Usuario.EstadoSolicitud.RECHAZADA
        )
        usuario.is_active = aprobado
        usuario.save(update_fields=("estado_solicitud", "is_active"))
        notificar_usuario(
            usuario,
            tipo=NotificacionCuenta.Tipo.SOLICITUD_RESUELTA,
            mensaje=(
                "Tu solicitud de cuenta fue aprobada."
                if aprobado
                else "Tu solicitud de cuenta no fue aprobada."
            ),
            url=reverse("login"),
        )
    try:
        enviar_correo_revision(usuario, aprobado=aprobado)
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "No se pudo enviar el aviso de revisión para la solicitud de %s.",
            usuario.username,
        )
        messages.warning(
            request,
            "La solicitud fue aprobada."
            if aprobado
            else "La solicitud fue rechazada.",
        )
        messages.warning(
            request,
            "No se pudo enviar el aviso por correo electrónico.",
        )
    else:
        messages.success(
            request,
            "La solicitud fue aprobada y notificada."
            if aprobado
            else "La solicitud fue rechazada y notificada.",
        )
    return redirect("dashboard:tabla", tabla="usuarios")
