from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator
from django.utils import timezone


Usuario = get_user_model()


class RegistroUsuarioForm(UserCreationForm):
    celular = forms.CharField(
        label="Celular (opcional)",
        required=False,
        max_length=13,
        validators=[
            RegexValidator(
                regex=r"^(?:\+591 ?)?[0-9]{8}$",
                message=(
                    "Ingresa 8 dígitos, con el prefijo +591 opcional "
                    "(ej.: +591 71234567)."
                ),
            )
        ],
    )
    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    rol = forms.ChoiceField(
        choices=(
            (Usuario.Rol.ESTUDIANTE, "Estudiante"),
            (Usuario.Rol.FAMILIAR, "Familiar"),
        ),
        label="Tipo de cuenta",
    )

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "celular",
            "fecha_nacimiento",
            "rol",
        )
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "username": "Nombre de usuario",
            "email": "Correo electrónico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = "Puedes usar cualquier correo válido."
        self.fields["email"].widget.attrs["placeholder"] = "nombre@correo.com"
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["username"].help_text = (
            "Elige un nombre de usuario único para iniciar sesión."
        )
        self.fields["password1"].label = "Contraseña"
        self.fields["password1"].help_text = (
            "Usa una contraseña segura y evita datos personales."
        )
        self.fields["password2"].label = "Confirmar contraseña"
        self.fields["password2"].help_text = ""
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["celular"].widget.attrs["autocomplete"] = "tel"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        for field in self.fields.values():
            css_class = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs["class"] = css_class

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get("fecha_nacimiento")
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError(
                "La fecha de nacimiento no puede ser futura."
            )
        return fecha

    def clean_celular(self):
        celular = self.cleaned_data["celular"].replace(" ", "")
        if celular and not celular.startswith("+591"):
            celular = f"+591{celular}"
        return celular

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Ya existe una cuenta con este correo electrónico."
            )
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data["email"]
        usuario.is_active = False
        usuario.email_verificado = False
        usuario.estado_solicitud = Usuario.EstadoSolicitud.PENDIENTE
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario
