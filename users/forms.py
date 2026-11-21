import re

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.files.uploadedfile import UploadedFile

from config.forms import StyleFormMixin
from users.models import User

MAX_AVATAR_SIZE_MB = 5


class UserRegisterForm(StyleFormMixin, UserCreationForm):
    """Регистрация: email, пароль и подтверждение пароля."""

    class Meta:
        model = User
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {"placeholder": "you@example.com", "autofocus": True}
        )
        self.fields["password1"].label = "Пароль"
        self.fields["password2"].label = "Подтверждение пароля"
        self.fields["password2"].help_text = "Введите тот же пароль ещё раз."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Пользователь с таким email уже зарегистрирован. Войдите или восстановите пароль."
            )
        return email


class UserLoginForm(StyleFormMixin, AuthenticationForm):
    """Вход по email и паролю."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "placeholder": "you@example.com"}),
    )

    error_messages = {
        "invalid_login": "Неверный email или пароль. Проверьте данные и попробуйте снова.",
        "inactive": "Этот аккаунт заблокирован.",
        "not_confirmed": "Email не подтверждён. Перейдите по ссылке из письма, которое пришло после регистрации.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].label = "Пароль"

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            # Стандартный вход не отличает «неверный пароль» от «аккаунт неактивен».
            # Если пароль верный, а аккаунт выключен — объясняем причину.
            email = self.cleaned_data.get("username")
            password = self.cleaned_data.get("password")
            user = User.objects.filter(email__iexact=email).first() if email else None
            if user and password and not user.is_active and user.check_password(password):
                code = "not_confirmed" if user.token else "inactive"
                raise forms.ValidationError(self.error_messages[code], code=code)
            raise


class UserProfileForm(StyleFormMixin, forms.ModelForm):
    """Редактирование профиля."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone_number", "country", "avatar")
        labels = {"first_name": "Имя", "last_name": "Фамилия"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].widget.attrs["placeholder"] = "+7 900 000-00-00"
        self.fields["avatar"].widget.attrs["accept"] = "image/jpeg,image/png"
        self.fields["avatar"].help_text = f"JPEG или PNG, не больше {MAX_AVATAR_SIZE_MB} МБ."

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        if phone and not re.fullmatch(r"\+?[\d\s\-()]{10,20}", phone):
            raise forms.ValidationError(
                "Введите телефон: только цифры, пробелы, «+», «-» и скобки, от 10 символов."
            )
        return phone or None

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not isinstance(avatar, UploadedFile):
            return avatar
        if getattr(avatar, "content_type", "") not in ("image/jpeg", "image/png"):
            raise forms.ValidationError("Аватар должен быть в формате JPEG или PNG.")
        if avatar.size > MAX_AVATAR_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(f"Файл больше {MAX_AVATAR_SIZE_MB} МБ.")
        return avatar


class StyledPasswordResetForm(StyleFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["placeholder"] = "you@example.com"


class StyledSetPasswordForm(StyleFormMixin, SetPasswordForm):
    pass
