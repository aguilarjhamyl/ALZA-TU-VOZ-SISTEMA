import json
from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django.db.models import Q

from .models import (
    AccionSeguimiento,
    Caso,
    Curso,
    Frecuencia,
    LugarIncidente,
    MotivoRechazo,
    OpcionPregunta,
    Pregunta,
    RespuestaCaso,
    RolParticipante,
    TipoAccion,
    TipoIncidente,
    EstadoCaso,
    TransicionEstadoCaso,
)
from .utils import texto_catalogo


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput
    extensiones_permitidas = {
        ".jpg", ".jpeg", ".png", ".webp", ".pdf", ".mp3", ".wav",
        ".m4a", ".mp4", ".webm", ".mov", ".doc", ".docx",
    }

    def clean(self, data, initial=None):
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            archivos = [super().clean(item, initial) for item in data]
        else:
            archivos = [super().clean(data, initial)]
        for archivo in archivos:
            if archivo.size > settings.MAX_UPLOAD_SIZE:
                raise ValidationError(
                    "Cada archivo debe pesar como máximo 25 MB."
                )
            if Path(archivo.name).suffix.lower() not in self.extensiones_permitidas:
                raise ValidationError(
                    "El tipo de archivo no está permitido."
                )
        return archivos


class ReporteCasoForm(forms.ModelForm):
    archivos = MultipleFileField(
        label="Adjuntar evidencias (opcional)",
        required=False,
        help_text=(
            "Puedes adjuntar imágenes, audio, video o documentos. "
            "Máximo 25 MB por archivo."
        ),
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
                "accept": ".jpg,.jpeg,.png,.webp,.pdf,.mp3,.wav,.m4a,"
                ".mp4,.webm,.mov,.doc,.docx",
            }
        ),
    )

    class Meta:
        model = Caso
        fields = (
            "titulo",
            "descripcion",
            "id_tipo_incidente",
            "id_frecuencia",
            "id_lugar",
            "id_curso",
            "fecha_hora_incidente",
            "ocultar_identidad_denunciado",
            "tiene_evidencia",
            "detalle_sin_evidencia",
            "confirma_veracidad",
        )
        labels = {
            "titulo": "Asunto",
            "descripcion": "Cuéntanos qué ocurrió",
            "id_tipo_incidente": "Tipo de situación",
            "id_frecuencia": "¿Con qué frecuencia ocurre?",
            "id_lugar": "¿Dónde ocurrió?",
            "id_curso": "Curso (opcional)",
            "fecha_hora_incidente": "Fecha y hora aproximadas (opcional)",
            "ocultar_identidad_denunciado": "Mantener reservada la identidad de la persona señalada",
            "tiene_evidencia": "Tengo archivos que pueden ayudar a comprender la situación",
            "detalle_sin_evidencia": "Si no tienes archivos, agrega más detalles",
            "confirma_veracidad": "Confirmo que la información es verdadera según mi conocimiento",
        }
        help_texts = {
            "descripcion": "Incluye al menos 30 caracteres. No compartas datos que no sean necesarios.",
            "ocultar_identidad_denunciado": (
                "El personal autorizado podrá revisar el caso de acuerdo con sus permisos."
            ),
            "detalle_sin_evidencia": (
                "Si no adjuntas archivos, este campo debe describir la situación "
                "con al menos 30 caracteres."
            ),
        }
        widgets = {
            "titulo": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 150}),
            "descripcion": forms.Textarea(attrs={"rows": 5, "minlength": 30}),
            "fecha_hora_incidente": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "detalle_sin_evidencia": forms.Textarea(attrs={"rows": 3, "minlength": 30}),
            "ocultar_identidad_denunciado": forms.CheckboxInput(),
            "tiene_evidencia": forms.CheckboxInput(),
            "confirma_veracidad": forms.CheckboxInput(),
        }

    def __init__(
        self,
        *args,
        evidencias_existentes=None,
        evidencias_eliminables=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        tipos_activos = TipoIncidente.objects.filter(
            activo=True,
            id_categoria__activo=True,
        )
        if self.instance.pk and self.instance.id_tipo_incidente_id:
            tipos_activos = tipos_activos | TipoIncidente.objects.filter(
                pk=self.instance.id_tipo_incidente_id
            )
        self.fields["id_tipo_incidente"].queryset = tipos_activos.select_related(
            "id_categoria"
        )
        if self.instance.pk:
            self.fields["id_tipo_incidente"].disabled = True
            self.fields["id_tipo_incidente"].help_text = (
                "El tipo no se puede cambiar porque determina las preguntas "
                "complementarias del reporte."
            )
        self.fields["id_frecuencia"].queryset = Frecuencia.objects.all()
        self.fields["id_lugar"].queryset = LugarIncidente.objects.all()
        cursos_activos = Curso.objects.filter(activo=True)
        if self.instance.pk and self.instance.id_curso_id:
            cursos_activos = cursos_activos | Curso.objects.filter(
                pk=self.instance.id_curso_id
            )
        self.fields["id_curso"].queryset = cursos_activos
        self.fields["id_lugar"].required = False
        self.fields["id_curso"].required = False
        self.fields["fecha_hora_incidente"].required = False
        self.fields["ocultar_identidad_denunciado"].initial = True
        self.fields["tiene_evidencia"].required = False
        self.evidencias_existentes = evidencias_existentes
        if evidencias_existentes is not None:
            eliminables = (
                evidencias_eliminables
                if evidencias_eliminables is not None
                else evidencias_existentes.none()
            )
            self.fields["eliminar_evidencias"] = forms.MultipleChoiceField(
                label="Quitar archivos adjuntos",
                choices=[
                    (str(evidencia.pk), evidencia.nombre_archivo)
                    for evidencia in eliminables
                ],
                required=False,
                help_text=(
                    "Los archivos se retiran del reporte, pero se conservan "
                    "para auditoría."
                ),
                widget=forms.CheckboxSelectMultiple,
            )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif field is not self.fields["archivos"]:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned_data = super().clean()
        tiene_evidencia = cleaned_data.get("tiene_evidencia")
        archivos = cleaned_data.get("archivos") or []
        detalle = (cleaned_data.get("detalle_sin_evidencia") or "").strip()
        evidencias_eliminadas = cleaned_data.get("eliminar_evidencias", [])
        quedan_evidencias = bool(
            self.evidencias_existentes is not None
            and self.evidencias_existentes.exclude(
                pk__in=evidencias_eliminadas
            ).exists()
        )
        hay_evidencias = bool(archivos) or quedan_evidencias

        if len((cleaned_data.get("descripcion") or "").strip()) < 30:
            self.add_error("descripcion", "Describe la situación con al menos 30 caracteres.")

        if tiene_evidencia and not hay_evidencias:
            self.add_error(
                "archivos",
                "Adjunta un archivo o desmarca la opción de evidencias.",
            )
        if not tiene_evidencia and hay_evidencias:
            self.add_error(
                "tiene_evidencia",
                "Marca esta opción mientras haya archivos adjuntos.",
            )
        if not tiene_evidencia and len(detalle) < 30:
            self.add_error(
                "detalle_sin_evidencia",
                "Agrega al menos 30 caracteres o indica que adjuntas evidencias.",
            )
        return cleaned_data


class ParticipanteForm(forms.Form):
    id_rol_participante = forms.ModelChoiceField(
        label="Participación",
        queryset=RolParticipante.objects.none(),
        required=False,
        empty_label="Selecciona una opción",
    )
    nombre_referencial = forms.CharField(
        label="Nombre o referencia",
        max_length=150,
        required=False,
    )
    descripcion = forms.CharField(
        label="Detalle (opcional)",
        max_length=255,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["id_rol_participante"].queryset = RolParticipante.objects.all()
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(
                field.widget, forms.Select
            ) else "form-control"

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("id_rol_participante") and not cleaned_data.get(
            "nombre_referencial"
        ):
            self.add_error(
                "nombre_referencial",
                "Escribe un nombre o referencia para esta persona.",
            )
        if cleaned_data.get("nombre_referencial") and not cleaned_data.get(
            "id_rol_participante"
        ):
            self.add_error(
                "id_rol_participante",
                "Selecciona cómo participa esta persona.",
            )
        return cleaned_data


ParticipanteFormSet = formset_factory(
    ParticipanteForm,
    extra=2,
    max_num=5,
    validate_max=True,
)


class RespuestasCasoForm(forms.Form):
    def __init__(self, *args, tipo_incidente_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.preguntas = []
        if not tipo_incidente_id and self.is_bound:
            tipo_incidente_id = self.data.get("id_tipo_incidente")

        preguntas = Pregunta.objects.filter(
            activa=True,
            id_tipo_respuesta__activo=True,
        )
        generales = Q(id_categoria__isnull=True, id_tipo_incidente__isnull=True)
        if tipo_incidente_id:
            tipo = TipoIncidente.objects.filter(
                pk=tipo_incidente_id, activo=True
            ).first()
            if tipo:
                preguntas = preguntas.filter(
                    generales
                    | Q(
                        id_categoria=tipo.id_categoria_id,
                        id_categoria__activo=True,
                    )
                    | Q(id_tipo_incidente=tipo.pk)
                )
            else:
                preguntas = preguntas.filter(generales)
        else:
            preguntas = preguntas.filter(generales)

        for pregunta in preguntas.select_related("id_tipo_respuesta"):
            opciones = OpcionPregunta.objects.filter(id_pregunta=pregunta)
            nombre = f"pregunta_{pregunta.pk}"
            tipo_respuesta = pregunta.id_tipo_respuesta.codigo
            opciones_html = [
                (str(opcion.pk), texto_catalogo(opcion.texto))
                for opcion in opciones
            ]
            requerido = pregunta.obligatoria

            if tipo_respuesta == "TEXTO":
                field = forms.CharField(
                    label=texto_catalogo(pregunta.texto),
                    required=requerido,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            elif tipo_respuesta == "ESCALA":
                field = forms.DecimalField(
                    label=texto_catalogo(pregunta.texto),
                    required=requerido,
                    min_value=0,
                    max_value=100,
                    decimal_places=2,
                )
            elif tipo_respuesta == "OPCION_MULTIPLE":
                field = forms.MultipleChoiceField(
                    label=texto_catalogo(pregunta.texto),
                    required=requerido,
                    choices=opciones_html,
                    widget=forms.CheckboxSelectMultiple,
                )
            else:
                field = forms.ChoiceField(
                    label=texto_catalogo(pregunta.texto),
                    required=requerido,
                    choices=[("", "Selecciona una respuesta"), *opciones_html],
                    widget=forms.RadioSelect,
                )
            field.help_text = ""
            self.fields[nombre] = field
            self.preguntas.append((pregunta, nombre, tipo_respuesta))

    def guardar_respuestas(self, caso):
        respuestas = []
        for pregunta, nombre, tipo_respuesta in self.preguntas:
            valor = self.cleaned_data.get(nombre)
            if valor in (None, "", []):
                continue
            respuesta = RespuestaCaso(
                id_caso=caso,
                id_pregunta=pregunta.pk,
                origen="FORMULARIO",
            )
            if tipo_respuesta == "TEXTO":
                respuesta.valor_texto = valor
            elif tipo_respuesta == "ESCALA":
                respuesta.valor_numerico = valor
            elif tipo_respuesta == "OPCION_MULTIPLE":
                respuesta.valor_texto = json.dumps(valor)
            else:
                respuesta.id_opcion = int(valor)
            respuestas.append(respuesta)
        RespuestaCaso.objects.bulk_create(respuestas)


class CasoMensajeForm(forms.Form):
    contenido = forms.CharField(
        label="Mensaje",
        max_length=5000,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3}
        ),
    )


class EstadoCasoForm(forms.Form):
    estado = forms.ChoiceField(label="Nuevo estado")
    motivo_rechazo = forms.ModelChoiceField(
        label="Motivo de rechazo",
        queryset=MotivoRechazo.objects.all(),
        required=False,
        empty_label="Selecciona un motivo",
    )
    observacion = forms.CharField(
        label="Nota para el historial",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, caso, *args, **kwargs):
        super().__init__(*args, **kwargs)
        destino_ids = TransicionEstadoCaso.objects.filter(
            id_estado_origen=caso.id_estado_caso_id
        ).values_list("id_estado_destino", flat=True)
        self.fields["estado"].choices = [
            ("", "Selecciona un estado"),
            *(
                (str(estado.pk), estado.nombre)
                for estado in EstadoCaso.objects.filter(
                    pk__in=destino_ids,
                    activo=True,
                )
            ),
        ]
        self.fields["estado"].widget.attrs["class"] = "form-select"
        self.fields["motivo_rechazo"].widget.attrs["class"] = "form-select"
        self.fields["observacion"].widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        estado_id = cleaned_data.get("estado")
        if estado_id:
            estado = EstadoCaso.objects.filter(pk=estado_id).first()
            if estado and estado.codigo == "RECHAZADO" and not cleaned_data.get(
                "motivo_rechazo"
            ):
                self.add_error(
                    "motivo_rechazo",
                    "Indica el motivo para rechazar el caso.",
                )
        return cleaned_data


class AccionSeguimientoForm(forms.ModelForm):
    class Meta:
        model = AccionSeguimiento
        fields = (
            "id_tipo_accion",
            "descripcion",
            "fecha_programada",
            "estado",
            "resultado",
        )
        labels = {
            "id_tipo_accion": "Tipo de acción",
            "descripcion": "Acción de acompañamiento",
            "fecha_programada": "Fecha programada",
            "estado": "Estado",
            "resultado": "Resultado (opcional)",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "fecha_programada": forms.DateInput(attrs={"type": "date"}),
            "estado": forms.Select(),
            "resultado": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["id_tipo_accion"].queryset = TipoAccion.objects.all()
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(
                field.widget, forms.Select
            ) else "form-control"


class MensajeCasoAutoridadForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Tipo de mensaje",
        choices=(
            ("PREGUNTA", "Pregunta para el denunciante"),
            ("COMENTARIO", "Comentario visible"),
            ("NOTA_INTERNA", "Nota interna (solo personal autorizado)"),
        ),
    )
    contenido = forms.CharField(
        label="Mensaje",
        max_length=5000,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3}
        ),
    )


class RespuestaCasoMensajeForm(forms.Form):
    contenido = forms.CharField(
        label="Tu respuesta",
        max_length=5000,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3}
        ),
    )


class MensajeChatbotForm(forms.Form):
    contenido = forms.CharField(
        label="Escribe tu mensaje",
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "maxlength": 2000,
                "placeholder": "Cuéntame qué te gustaría conversar...",
                "class": "form-control",
            }
        ),
    )


class AplicarTestForm(forms.Form):
    def __init__(self, test, *args, casos_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.test = test
        self.items = []
        self.fields["id_caso"] = forms.ModelChoiceField(
            label="Caso relacionado",
            queryset=casos_queryset if casos_queryset is not None else Caso.objects.none(),
            required=test.formato == "DIBUJO",
            empty_label="Selecciona un caso" if test.formato == "DIBUJO" else "Ninguno",
        )
        self.fields["id_caso"].widget.attrs["class"] = "form-select"

        if test.formato == "DIBUJO":
            self.fields["dibujo"] = MultipleFileField(
                label="Adjunta tu dibujo",
                required=True,
                help_text="Sube una imagen o documento, máximo 25 MB.",
                widget=MultipleFileInput(
                    attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,.webp,.pdf"}
                ),
            )
            self.fields["dibujo"].extensiones_permitidas = {
                ".jpg", ".jpeg", ".png", ".webp", ".pdf"
            }
            return

        for item in test.testitem_set.select_related("id_tipo_respuesta").filter(
            activo=True,
            id_tipo_respuesta__activo=True,
        ):
            opciones = item.testopcion_set.all()
            opciones_html = [
                (str(opcion.pk), texto_catalogo(opcion.texto))
                for opcion in opciones
            ]
            nombre = f"item_{item.pk}"
            if opciones_html:
                field = forms.ChoiceField(
                    label=texto_catalogo(item.texto),
                    choices=[("", "Selecciona una respuesta"), *opciones_html],
                    widget=forms.RadioSelect,
                    required=True,
                )
            else:
                field = forms.CharField(
                    label=texto_catalogo(item.texto),
                    widget=forms.Textarea(attrs={"rows": 2}),
                    required=True,
                )
            self.fields[nombre] = field
            self.items.append((item, nombre, bool(opciones_html)))

        for field in self.fields.values():
            if not isinstance(
                field.widget,
                (forms.RadioSelect, forms.CheckboxSelectMultiple),
            ):
                field.widget.attrs.setdefault("class", "form-control")

        if not self.items:
            raise ValidationError(
                "Este cuestionario todavía no tiene preguntas configuradas."
            )

    def guardar_respuestas(self, aplicacion):
        puntaje = 0
        respuestas = []
        for item, nombre, tiene_opciones in self.items:
            valor = self.cleaned_data[nombre]
            respuesta = RespuestaTest(
                id_aplicacion=aplicacion,
                id_item=item.pk,
            )
            if tiene_opciones:
                opcion = TestOpcion.objects.get(
                    pk=int(valor),
                    id_item=item,
                )
                respuesta.id_opcion_test = opcion
                puntaje += opcion.puntos
            else:
                respuesta.valor_texto = valor
            respuestas.append(respuesta)
        RespuestaTest.objects.bulk_create(respuestas)
        return puntaje
