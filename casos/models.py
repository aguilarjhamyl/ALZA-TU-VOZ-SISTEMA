from django.db import models
from django.utils import timezone

from .utils import texto_catalogo


class Persona(models.Model):
    id_persona = models.BigAutoField(primary_key=True)
    nombres = models.CharField(max_length=100)
    ap_paterno = models.CharField(max_length=60, blank=True, null=True)
    ap_materno = models.CharField(max_length=60, blank=True, null=True)
    ci_numero = models.CharField(max_length=15, blank=True, null=True)
    ci_complemento = models.CharField(max_length=3, blank=True, null=True)
    id_departamento_ci = models.SmallIntegerField(blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    id_genero = models.SmallIntegerField(blank=True, null=True)
    celular = models.CharField(max_length=12, blank=True, null=True)
    correo = models.EmailField(max_length=254, unique=True, blank=True, null=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "persona"


class UsuarioDominio(models.Model):
    id_usuario = models.BigAutoField(primary_key=True)
    id_persona = models.OneToOneField(
        Persona, models.DO_NOTHING, db_column="id_persona"
    )
    password_hash = models.CharField(max_length=255)
    estado_cuenta = models.CharField(max_length=12, default="PENDIENTE")
    correo_verificado_en = models.DateTimeField(blank=True, null=True)
    aprobado_por_id = models.BigIntegerField(
        db_column="aprobado_por", blank=True, null=True
    )
    ultimo_acceso = models.DateTimeField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "usuario"


class Estudiante(models.Model):
    id_persona = models.OneToOneField(
        Persona,
        models.DO_NOTHING,
        db_column="id_persona",
        primary_key=True,
    )
    rude = models.CharField(max_length=20, unique=True, blank=True, null=True)
    fecha_ingreso = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "estudiante"


class Tutor(models.Model):
    id_persona = models.OneToOneField(
        Persona,
        models.DO_NOTHING,
        db_column="id_persona",
        primary_key=True,
    )
    ocupacion = models.CharField(max_length=80, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "tutor"


class Rol(models.Model):
    id_rol = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    es_autoridad = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "rol"


class UsuarioRol(models.Model):
    pk = models.CompositePrimaryKey("id_usuario", "id_rol")
    id_usuario = models.ForeignKey(
        UsuarioDominio, models.DO_NOTHING, db_column="id_usuario"
    )
    id_rol = models.ForeignKey(Rol, models.DO_NOTHING, db_column="id_rol")
    asignado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "usuario_rol"


class DenuncianteExterno(models.Model):
    id_denunciante_externo = models.BigAutoField(primary_key=True)
    nombres = models.CharField(max_length=120)
    relacion = models.CharField(max_length=100, blank=True, null=True)
    celular = models.CharField(max_length=12, blank=True, null=True)
    correo = models.EmailField(max_length=254, blank=True, null=True)
    codigo_seguimiento = models.UUIDField(unique=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "denunciante_externo"


class CategoriaIncidente(models.Model):
    id_categoria = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=80)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "categoria_incidente"

    def __str__(self):
        return texto_catalogo(self.nombre)


class TipoIncidente(models.Model):
    id_tipo_incidente = models.SmallAutoField(primary_key=True)
    id_categoria = models.ForeignKey(
        CategoriaIncidente, models.DO_NOTHING, db_column="id_categoria"
    )
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    riesgo_base = models.SmallIntegerField(default=0)
    involucra_personal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "tipo_incidente"
        ordering = ("id_categoria", "nombre")

    def __str__(self):
        return texto_catalogo(self.nombre)


class Frecuencia(models.Model):
    id_frecuencia = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=60, unique=True)
    puntos = models.SmallIntegerField(default=0)
    orden = models.SmallIntegerField(unique=True)

    class Meta:
        managed = False
        db_table = "frecuencia"
        ordering = ("orden",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class LugarIncidente(models.Model):
    id_lugar = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=80, unique=True)

    class Meta:
        managed = False
        db_table = "lugar_incidente"
        ordering = ("nombre",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class EstadoCaso(models.Model):
    id_estado_caso = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=60)
    color_hex = models.CharField(max_length=7, blank=True, null=True)
    permite_edicion = models.BooleanField(default=False)
    es_final = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "estado_caso"
        ordering = ("id_estado_caso",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class NivelRiesgo(models.Model):
    id_nivel_riesgo = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=30, unique=True)
    color_hex = models.CharField(max_length=7)
    puntaje_min = models.SmallIntegerField()
    puntaje_max = models.SmallIntegerField()
    orden = models.SmallIntegerField(unique=True)
    requiere_alerta = models.BooleanField()

    class Meta:
        managed = False
        db_table = "nivel_riesgo"
        ordering = ("puntaje_min",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class MotivoRechazo(models.Model):
    id_motivo_rechazo = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        managed = False
        db_table = "motivo_rechazo"
        ordering = ("nombre",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class RolParticipante(models.Model):
    id_rol_participante = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=15, unique=True)
    nombre = models.CharField(max_length=40)

    class Meta:
        managed = False
        db_table = "rol_participante"
        ordering = ("id_rol_participante",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class TipoEvidencia(models.Model):
    id_tipo_evidencia = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=40)

    class Meta:
        managed = False
        db_table = "tipo_evidencia"
        ordering = ("id_tipo_evidencia",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class TipoRespuesta(models.Model):
    id_tipo_respuesta = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=40)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "tipo_respuesta"


class Pregunta(models.Model):
    id_pregunta = models.AutoField(primary_key=True)
    id_categoria = models.ForeignKey(
        CategoriaIncidente,
        models.DO_NOTHING,
        db_column="id_categoria",
        blank=True,
        null=True,
    )
    id_tipo_incidente = models.ForeignKey(
        TipoIncidente,
        models.DO_NOTHING,
        db_column="id_tipo_incidente",
        blank=True,
        null=True,
    )
    texto = models.TextField()
    id_tipo_respuesta = models.ForeignKey(
        TipoRespuesta, models.DO_NOTHING, db_column="id_tipo_respuesta"
    )
    obligatoria = models.BooleanField(default=False)
    es_control_consistencia = models.BooleanField(default=False)
    orden = models.SmallIntegerField(default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "pregunta"
        ordering = ("-orden", "id_pregunta")

    def __str__(self):
        return texto_catalogo(self.texto)


class OpcionPregunta(models.Model):
    id_opcion = models.AutoField(primary_key=True)
    id_pregunta = models.ForeignKey(
        Pregunta, models.DO_NOTHING, db_column="id_pregunta"
    )
    texto = models.CharField(max_length=200)
    puntos_riesgo = models.SmallIntegerField(default=0)
    orden = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "opcion_pregunta"
        ordering = ("orden", "id_opcion")
        unique_together = (("id_pregunta", "id_opcion"),)

    def __str__(self):
        return texto_catalogo(self.texto)


class Curso(models.Model):
    id_curso = models.AutoField(primary_key=True)
    id_gestion = models.SmallIntegerField()
    id_grado = models.SmallIntegerField()
    id_paralelo = models.SmallIntegerField()
    id_docente_asesor = models.BigIntegerField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "curso"

    def __str__(self):
        return f"Curso {self.id_curso}"


class Caso(models.Model):
    id_caso = models.BigAutoField(primary_key=True)
    codigo_caso = models.CharField(max_length=20, unique=True)
    id_usuario_denunciante = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario_denunciante",
        blank=True,
        null=True,
    )
    id_denunciante_externo = models.ForeignKey(
        DenuncianteExterno,
        models.DO_NOTHING,
        db_column="id_denunciante_externo",
        blank=True,
        null=True,
    )
    ocultar_identidad_denunciado = models.BooleanField(default=True)
    id_tipo_incidente = models.ForeignKey(
        TipoIncidente, models.DO_NOTHING, db_column="id_tipo_incidente"
    )
    id_frecuencia = models.ForeignKey(
        Frecuencia, models.DO_NOTHING, db_column="id_frecuencia"
    )
    id_lugar = models.ForeignKey(
        LugarIncidente,
        models.DO_NOTHING,
        db_column="id_lugar",
        blank=True,
        null=True,
    )
    id_curso = models.ForeignKey(
        Curso, models.DO_NOTHING, db_column="id_curso", blank=True, null=True
    )
    fecha_hora_incidente = models.DateTimeField(blank=True, null=True)
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField()
    tiene_evidencia = models.BooleanField(default=False)
    detalle_sin_evidencia = models.TextField(blank=True, null=True)
    confirma_veracidad = models.BooleanField(default=False)
    puntaje_riesgo = models.SmallIntegerField(default=0)
    id_nivel_riesgo = models.ForeignKey(
        NivelRiesgo,
        models.DO_NOTHING,
        db_column="id_nivel_riesgo",
        blank=True,
        null=True,
    )
    id_estado_caso = models.ForeignKey(
        EstadoCaso, models.DO_NOTHING, db_column="id_estado_caso"
    )
    id_motivo_rechazo = models.ForeignKey(
        MotivoRechazo,
        models.DO_NOTHING,
        db_column="id_motivo_rechazo",
        blank=True,
        null=True,
    )
    version = models.IntegerField(default=1)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(default=timezone.now)
    eliminado_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "caso"
        ordering = ("-creado_en",)

    def __str__(self):
        return self.codigo_caso


class CasoParticipante(models.Model):
    id_participante = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_rol_participante = models.ForeignKey(
        RolParticipante, models.DO_NOTHING, db_column="id_rol_participante"
    )
    id_persona = models.BigIntegerField(blank=True, null=True)
    nombre_referencial = models.CharField(max_length=150, blank=True, null=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "caso_participante"
        unique_together = (("id_caso", "id_rol_participante", "id_persona"),)


class CasoMensaje(models.Model):
    class Autor(models.TextChoices):
        AUTORIDAD = "AUTORIDAD", "Autoridad"
        DENUNCIANTE = "DENUNCIANTE", "Denunciante"
        SISTEMA = "SISTEMA", "Sistema"

    class Tipo(models.TextChoices):
        PREGUNTA = "PREGUNTA", "Pregunta"
        RESPUESTA = "RESPUESTA", "Respuesta"
        COMENTARIO = "COMENTARIO", "Comentario"
        NOTA_INTERNA = "NOTA_INTERNA", "Nota interna"

    id_mensaje = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_mensaje_padre = models.BigIntegerField(blank=True, null=True)
    autor_tipo = models.CharField(max_length=12, choices=Autor.choices)
    id_usuario = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario",
        blank=True,
        null=True,
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    contenido = models.TextField()
    visible_para_denunciante = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "caso_mensaje"
        ordering = ("creado_en",)


class Evidencia(models.Model):
    id_evidencia = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_tipo_evidencia = models.ForeignKey(
        TipoEvidencia, models.DO_NOTHING, db_column="id_tipo_evidencia"
    )
    id_aplicacion_test = models.BigIntegerField(blank=True, null=True)
    nombre_archivo = models.CharField(max_length=255)
    ruta_archivo = models.CharField(max_length=500)
    tipo_mime = models.CharField(max_length=100, blank=True, null=True)
    tamano_bytes = models.BigIntegerField(blank=True, null=True)
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    subida_por = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="subida_por",
        blank=True,
        null=True,
    )
    subida_en = models.DateTimeField(default=timezone.now)
    eliminado_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "evidencia"
        ordering = ("subida_en",)


class RespuestaCaso(models.Model):
    id_respuesta = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_pregunta = models.IntegerField()
    id_opcion = models.IntegerField(blank=True, null=True)
    valor_texto = models.TextField(blank=True, null=True)
    valor_numerico = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True
    )
    origen = models.CharField(max_length=10, default="FORMULARIO")
    respondida_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "respuesta_caso"
        unique_together = (("id_caso", "id_pregunta"),)


class CasoHistorialEstado(models.Model):
    id_historial = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_estado_anterior = models.ForeignKey(
        EstadoCaso,
        models.DO_NOTHING,
        db_column="id_estado_anterior",
        related_name="historial_estado_anterior",
        blank=True,
        null=True,
    )
    id_estado_nuevo = models.ForeignKey(
        EstadoCaso,
        models.DO_NOTHING,
        db_column="id_estado_nuevo",
        related_name="historial_estado_nuevo",
    )
    id_usuario = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario",
        blank=True,
        null=True,
    )
    id_motivo_rechazo = models.ForeignKey(
        MotivoRechazo,
        models.DO_NOTHING,
        db_column="id_motivo_rechazo",
        blank=True,
        null=True,
    )
    observacion = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "caso_historial_estado"
        ordering = ("creado_en",)


class TransicionEstadoCaso(models.Model):
    pk = models.CompositePrimaryKey("id_estado_origen", "id_estado_destino")
    id_estado_origen = models.SmallIntegerField()
    id_estado_destino = models.SmallIntegerField()

    class Meta:
        managed = False
        db_table = "transicion_estado_caso"
        unique_together = (("id_estado_origen", "id_estado_destino"),)


class TipoAccion(models.Model):
    id_tipo_accion = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        managed = False
        db_table = "tipo_accion"
        ordering = ("nombre",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        CASO_ENVIADO = "CASO_ENVIADO", "Caso enviado a Dirección"
        CASO_ACTUALIZADO = "CASO_ACTUALIZADO", "Caso actualizado"
        CASO_RETIRADO = "CASO_RETIRADO", "Caso retirado"
        CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"
        PREGUNTA_AUTORIDAD = "PREGUNTA_AUTORIDAD", "Pregunta de autoridad"
        RESPUESTA_DENUNCIANTE = "RESPUESTA_DENUNCIANTE", "Respuesta del denunciante"
        ATENCION_CHATBOT = "ATENCION_CHATBOT", "Atención de chatbot"
        ALERTA_RIESGO = "ALERTA_RIESGO", "Alerta de riesgo"

    id_notificacion = models.BigAutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        UsuarioDominio, models.DO_NOTHING, db_column="id_usuario"
    )
    id_caso = models.ForeignKey(
        Caso, models.DO_NOTHING, db_column="id_caso", blank=True, null=True
    )
    id_conversacion = models.ForeignKey(
        "ConversacionChatbot",
        models.DO_NOTHING,
        db_column="id_conversacion",
        blank=True,
        null=True,
    )
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(default=timezone.now)
    leida_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "notificacion"
        ordering = ("-creado_en",)


class AccionSeguimiento(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        REALIZADA = "REALIZADA", "Realizada"
        CANCELADA = "CANCELADA", "Cancelada"

    id_accion = models.BigAutoField(primary_key=True)
    id_caso = models.ForeignKey(Caso, models.DO_NOTHING, db_column="id_caso")
    id_tipo_accion = models.ForeignKey(
        TipoAccion, models.DO_NOTHING, db_column="id_tipo_accion"
    )
    id_usuario_responsable = models.ForeignKey(
        UsuarioDominio, models.DO_NOTHING, db_column="id_usuario_responsable"
    )
    descripcion = models.TextField()
    fecha_programada = models.DateField(blank=True, null=True)
    fecha_realizada = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default="PENDIENTE")
    resultado = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "accion_seguimiento"
        ordering = ("-creado_en",)


class ConversacionChatbot(models.Model):
    id_conversacion = models.BigAutoField(primary_key=True)
    token = models.UUIDField(unique=True)
    id_usuario = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario",
        blank=True,
        null=True,
    )
    id_denunciante_externo = models.ForeignKey(
        DenuncianteExterno,
        models.DO_NOTHING,
        db_column="id_denunciante_externo",
        blank=True,
        null=True,
    )
    id_caso = models.ForeignKey(
        Caso, models.DO_NOTHING, db_column="id_caso", blank=True, null=True
    )
    proposito = models.CharField(max_length=20, default="APOYO_EMOCIONAL")
    canal = models.CharField(max_length=20, default="WEB")
    modelo_ia = models.CharField(max_length=80, blank=True, null=True)
    iniciada_en = models.DateTimeField(default=timezone.now)
    finalizada_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "conversacion_chatbot"
        ordering = ("-iniciada_en",)


class MensajeChatbot(models.Model):
    class Emisor(models.TextChoices):
        USUARIO = "USUARIO", "Usuario"
        BOT = "BOT", "Chatbot"
        AUTORIDAD = "AUTORIDAD", "Autoridad"

    id_mensaje_chat = models.BigAutoField(primary_key=True)
    id_conversacion = models.ForeignKey(
        ConversacionChatbot, models.DO_NOTHING, db_column="id_conversacion"
    )
    emisor = models.CharField(max_length=10, choices=Emisor.choices)
    contenido = models.TextField()
    id_pregunta = models.ForeignKey(
        Pregunta,
        models.DO_NOTHING,
        db_column="id_pregunta",
        blank=True,
        null=True,
    )
    requiere_atencion_humana = models.BooleanField(default=False)
    motivo_atencion = models.CharField(max_length=200, blank=True, null=True)
    metadatos_ia = models.JSONField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "mensaje_chatbot"
        ordering = ("creado_en",)


class TestPsicologico(models.Model):
    id_test = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    formato = models.CharField(max_length=12)
    edad_min = models.SmallIntegerField(blank=True, null=True)
    edad_max = models.SmallIntegerField(blank=True, null=True)
    nota_uso = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "test_psicologico"
        ordering = ("id_test",)

    def __str__(self):
        return texto_catalogo(self.nombre)


class TestItem(models.Model):
    id_item = models.AutoField(primary_key=True)
    id_test = models.ForeignKey(
        TestPsicologico, models.DO_NOTHING, db_column="id_test"
    )
    texto = models.TextField()
    orden = models.SmallIntegerField()
    id_tipo_respuesta = models.ForeignKey(
        TipoRespuesta, models.DO_NOTHING, db_column="id_tipo_respuesta"
    )
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "test_item"
        ordering = ("orden",)
        unique_together = (("id_test", "orden"),)


class TestOpcion(models.Model):
    id_opcion_test = models.AutoField(primary_key=True)
    id_item = models.ForeignKey(TestItem, models.DO_NOTHING, db_column="id_item")
    texto = models.CharField(max_length=200)
    puntos = models.SmallIntegerField(default=0)
    orden = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "test_opcion"
        ordering = ("orden",)
        unique_together = (("id_item", "texto"),)


class AplicacionTest(models.Model):
    id_aplicacion = models.BigAutoField(primary_key=True)
    id_test = models.ForeignKey(
        TestPsicologico, models.DO_NOTHING, db_column="id_test"
    )
    id_caso = models.ForeignKey(
        Caso, models.DO_NOTHING, db_column="id_caso", blank=True, null=True
    )
    id_estudiante = models.ForeignKey(
        Estudiante, models.DO_NOTHING, db_column="id_estudiante"
    )
    id_usuario_aplicador = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario_aplicador",
        blank=True,
        null=True,
    )
    modalidad = models.CharField(max_length=16, default="AUTOADMINISTRADO")
    iniciada_en = models.DateTimeField(default=timezone.now)
    finalizada_en = models.DateTimeField(blank=True, null=True)
    puntaje_total = models.SmallIntegerField(blank=True, null=True)
    interpretacion_orientativa = models.TextField(blank=True, null=True)
    id_nivel_riesgo_sugerido = models.ForeignKey(
        NivelRiesgo,
        models.DO_NOTHING,
        db_column="id_nivel_riesgo_sugerido",
        blank=True,
        null=True,
    )
    revisada_por_profesional = models.BooleanField(default=False)
    id_usuario_revisor = models.ForeignKey(
        UsuarioDominio,
        models.DO_NOTHING,
        db_column="id_usuario_revisor",
        related_name="tests_revisados",
        blank=True,
        null=True,
    )
    revisada_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "aplicacion_test"
        ordering = ("-iniciada_en",)


class RespuestaTest(models.Model):
    id_respuesta_test = models.BigAutoField(primary_key=True)
    id_aplicacion = models.ForeignKey(
        AplicacionTest, models.DO_NOTHING, db_column="id_aplicacion"
    )
    id_item = models.ForeignKey(TestItem, models.DO_NOTHING, db_column="id_item")
    id_opcion_test = models.ForeignKey(
        TestOpcion,
        models.DO_NOTHING,
        db_column="id_opcion_test",
        blank=True,
        null=True,
    )
    valor_texto = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "respuesta_test"
        unique_together = (("id_aplicacion", "id_item"),)


class LogAcceso(models.Model):
    id_log_acceso = models.BigAutoField(primary_key=True)
    id_usuario = models.BigIntegerField(blank=True, null=True)
    correo_intentado = models.CharField(max_length=254, blank=True, null=True)
    exitoso = models.BooleanField()
    motivo_fallo = models.CharField(max_length=100, blank=True, null=True)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "log_acceso"
        ordering = ("-creado_en",)


class LogAuditoria(models.Model):
    id_log = models.BigAutoField(primary_key=True)
    id_usuario = models.BigIntegerField(blank=True, null=True)
    accion = models.CharField(max_length=10)
    tabla = models.CharField(max_length=63)
    registro_id = models.BigIntegerField(blank=True, null=True)
    datos_anteriores = models.JSONField(blank=True, null=True)
    datos_nuevos = models.JSONField(blank=True, null=True)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "log_auditoria"
        ordering = ("-creado_en",)
