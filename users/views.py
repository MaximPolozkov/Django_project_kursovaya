import logging
import secrets
import smtplib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from users.forms import (
    StyledPasswordResetForm,
    StyledSetPasswordForm,
    UserLoginForm,
    UserProfileForm,
    UserRegisterForm,
)
from users.models import User

logger = logging.getLogger(__name__)


class RegisterView(CreateView):
    """Регистрация. Аккаунт активируется только после перехода по ссылке из письма."""

    model = User
    form_class = UserRegisterForm
    template_name = "users/register.html"
    success_url = reverse_lazy("users:login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("mailing:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False
        user.token = secrets.token_urlsafe(32)
        user.save()
        self.object = user

        confirm_url = self.request.build_absolute_uri(
            reverse("users:email_confirm", args=[user.token])
        )
        try:
            send_mail(
                subject="Подтвердите регистрацию в MailFlow",
                message=(
                    "Здравствуйте!\n\n"
                    "Чтобы завершить регистрацию в MailFlow, перейдите по ссылке:\n"
                    f"{confirm_url}\n\n"
                    "Если вы не регистрировались, просто проигнорируйте это письмо."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except (smtplib.SMTPException, OSError) as error:
            logger.exception("Не удалось отправить письмо подтверждения: %s", error)
            messages.error(
                self.request,
                "Аккаунт создан, но письмо с подтверждением отправить не удалось. "
                "Проверьте настройки почты и обратитесь к администратору.",
            )
        else:
            messages.success(
                self.request,
                f"Почти готово! Мы отправили письмо на {user.email} — перейдите по ссылке из него, чтобы подтвердить email.",
            )
        return redirect(self.get_success_url())


class EmailConfirmView(View):
    def get(self, request, token):
        user = get_object_or_404(User, token=token)
        user.is_active = True
        user.token = None
        user.save(update_fields=["is_active", "token"])
        messages.success(request, "Email подтверждён. Теперь можно войти.")
        return redirect("users:login")


class UserLoginView(auth_views.LoginView):
    form_class = UserLoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, "Вы вошли в аккаунт.")
        return super().form_valid(form)


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "users/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Профиль сохранён.")
        return super().form_valid(form)


# --- Восстановление пароля (стандартные представления Django со своими шаблонами) ---


class UserPasswordResetView(auth_views.PasswordResetView):
    form_class = StyledPasswordResetForm
    template_name = "users/password_reset_form.html"
    email_template_name = "users/password_reset_email.txt"
    subject_template_name = "users/password_reset_subject.txt"
    success_url = reverse_lazy("users:password_reset_done")


class UserPasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "users/password_reset_done.html"


class UserPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = StyledSetPasswordForm
    template_name = "users/password_reset_confirm.html"
    success_url = reverse_lazy("users:password_reset_complete")


class UserPasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "users/password_reset_complete.html"


# --- Менеджер: список пользователей и блокировка ---


class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "users_list"
    permission_required = "users.can_view_users"
    paginate_by = 30


class UserBlockToggleView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Блокирует или разблокирует пользователя (только POST)."""

    permission_required = "users.can_block_user"

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "Нельзя заблокировать самого себя.")
        elif target.is_superuser:
            messages.error(request, "Нельзя заблокировать администратора.")
        elif target.token:
            messages.error(request, "Пользователь ещё не подтвердил email — блокировать нечего.")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            action = "разблокирован" if target.is_active else "заблокирован"
            messages.success(request, f"Пользователь {target.email} {action}.")
        return redirect("users:user_list")
