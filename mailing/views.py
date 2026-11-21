from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from mailing.forms import MailingForm, MessageForm, RecipientForm
from mailing.models import Mailing, Message, Recipient
from mailing.services import MailingSendError, get_home_stats, get_user_stats, send_mailing

VIEW_ALL_MAILINGS = "mailing.can_view_all_mailings"
VIEW_ALL_RECIPIENTS = "mailing.can_view_all_recipients"
DISABLE_MAILING = "mailing.can_disable_mailing"


# ---------- Общие примеси ----------


class OwnerQuerysetMixin:
    """Пользователь видит только своё; менеджер с правом view_all_permission — всё."""

    view_all_permission = None

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if self.view_all_permission and user.has_perm(self.view_all_permission):
            return queryset
        return queryset.filter(owner=user)


class OwnerRequiredMixin(UserPassesTestMixin):
    """Изменять и удалять объект может только его владелец (менеджер — нет)."""

    def test_func(self):
        return self.get_object().owner_id == self.request.user.pk


class OwnerCreateMixin:
    """Владельцем нового объекта становится текущий пользователь."""

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class FormPageMixin:
    """Заголовок и ссылка «Отмена» для общего шаблона form.html."""

    template_name = "form.html"
    title = ""
    cancel_url = reverse_lazy("mailing:home")
    success_message = ""

    def get_cancel_url(self):
        return self.cancel_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        context["cancel_url"] = self.get_cancel_url()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response


class DeletePageMixin:
    """Подтверждение удаления в общем шаблоне confirm_delete.html."""

    template_name = "confirm_delete.html"
    object_label = ""
    delete_warning = ""
    detail_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object_label"] = self.object_label
        context["delete_warning"] = self.delete_warning
        context["cancel_url"] = reverse(self.detail_url_name, args=[self.object.pk])
        return context

    def form_valid(self, form):
        label = str(self.object)
        response = super().form_valid(form)
        messages.success(self.request, f"Удалено: {label}.")
        return response


# ---------- Главная и статистика ----------


@method_decorator(vary_on_cookie, name="dispatch")
@method_decorator(cache_control(private=True, max_age=60), name="dispatch")
class HomeView(TemplateView):
    """Главная: общее число рассылок, активные рассылки, уникальные получатели.

    Серверный кеш — показатели в Redis (get_home_stats),
    клиентский — браузер может хранить страницу 60 секунд (Cache-Control).
    """

    template_name = "mailing/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = get_home_stats()
        return context


@method_decorator(vary_on_cookie, name="dispatch")
@method_decorator(cache_control(private=True, max_age=30), name="dispatch")
class StatisticsView(LoginRequiredMixin, TemplateView):
    template_name = "mailing/statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = get_user_stats(self.request.user)
        return context


# ---------- Получатели ----------


class RecipientListView(LoginRequiredMixin, OwnerQuerysetMixin, ListView):
    model = Recipient
    template_name = "mailing/recipient_list.html"
    context_object_name = "recipients"
    view_all_permission = VIEW_ALL_RECIPIENTS
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().select_related("owner")


class RecipientDetailView(LoginRequiredMixin, OwnerQuerysetMixin, DetailView):
    model = Recipient
    template_name = "mailing/recipient_detail.html"
    context_object_name = "recipient"
    view_all_permission = VIEW_ALL_RECIPIENTS


class RecipientCreateView(LoginRequiredMixin, OwnerCreateMixin, FormPageMixin, CreateView):
    model = Recipient
    form_class = RecipientForm
    title = "Новый получатель"
    cancel_url = reverse_lazy("mailing:recipient_list")
    success_message = "Получатель добавлен."

    def get_success_url(self):
        return reverse("mailing:recipient_detail", args=[self.object.pk])


class RecipientUpdateView(LoginRequiredMixin, OwnerRequiredMixin, FormPageMixin, UpdateView):
    model = Recipient
    form_class = RecipientForm
    title = "Редактирование получателя"
    success_message = "Получатель сохранён."

    def get_cancel_url(self):
        return reverse("mailing:recipient_detail", args=[self.object.pk])

    def get_success_url(self):
        return reverse("mailing:recipient_detail", args=[self.object.pk])


class RecipientDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeletePageMixin, DeleteView):
    model = Recipient
    detail_url_name = "mailing:recipient_detail"
    object_label = "получателя"
    success_url = reverse_lazy("mailing:recipient_list")


# ---------- Сообщения (видны только владельцу) ----------


class MessageListView(LoginRequiredMixin, OwnerQuerysetMixin, ListView):
    model = Message
    template_name = "mailing/message_list.html"
    context_object_name = "mail_messages"
    paginate_by = 20


class MessageDetailView(LoginRequiredMixin, OwnerQuerysetMixin, DetailView):
    model = Message
    template_name = "mailing/message_detail.html"
    context_object_name = "mail_message"


class MessageCreateView(LoginRequiredMixin, OwnerCreateMixin, FormPageMixin, CreateView):
    model = Message
    form_class = MessageForm
    title = "Новое сообщение"
    cancel_url = reverse_lazy("mailing:message_list")
    success_message = "Сообщение создано."

    def get_success_url(self):
        return reverse("mailing:message_detail", args=[self.object.pk])


class MessageUpdateView(LoginRequiredMixin, OwnerRequiredMixin, FormPageMixin, UpdateView):
    model = Message
    form_class = MessageForm
    title = "Редактирование сообщения"
    success_message = "Сообщение сохранено."

    def get_cancel_url(self):
        return reverse("mailing:message_detail", args=[self.object.pk])

    def get_success_url(self):
        return reverse("mailing:message_detail", args=[self.object.pk])


class MessageDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeletePageMixin, DeleteView):
    model = Message
    detail_url_name = "mailing:message_detail"
    object_label = "сообщение"
    delete_warning = "Вместе с сообщением удалятся все рассылки, в которых оно используется."
    success_url = reverse_lazy("mailing:message_list")


# ---------- Рассылки ----------


class MailingListView(LoginRequiredMixin, OwnerQuerysetMixin, ListView):
    model = Mailing
    template_name = "mailing/mailing_list.html"
    context_object_name = "mailings"
    view_all_permission = VIEW_ALL_MAILINGS
    paginate_by = 20

    def get_queryset(self):
        Mailing.update_all_statuses()
        return super().get_queryset().select_related("message", "owner")


class MailingDetailView(LoginRequiredMixin, OwnerQuerysetMixin, DetailView):
    model = Mailing
    template_name = "mailing/mailing_detail.html"
    context_object_name = "mailing"
    view_all_permission = VIEW_ALL_MAILINGS

    def get_object(self, queryset=None):
        mailing = super().get_object(queryset)
        mailing.update_status()  # статус пересчитывается при каждом просмотре
        return mailing

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mailing = self.object
        user = self.request.user
        is_owner = mailing.owner_id == user.pk
        context["is_owner"] = is_owner
        context["can_send"] = is_owner and mailing.is_active and mailing.is_running_now
        context["can_disable"] = user.has_perm(DISABLE_MAILING)
        context["recipients"] = mailing.recipients.all()
        context["attempts"] = mailing.attempts.select_related("recipient")[:50]
        return context


class MailingCreateView(LoginRequiredMixin, OwnerCreateMixin, FormPageMixin, CreateView):
    model = Mailing
    form_class = MailingForm
    title = "Новая рассылка"
    cancel_url = reverse_lazy("mailing:mailing_list")
    success_message = "Рассылка создана."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.status = form.instance.calculate_status()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("mailing:mailing_detail", args=[self.object.pk])


class MailingUpdateView(LoginRequiredMixin, OwnerRequiredMixin, FormPageMixin, UpdateView):
    model = Mailing
    form_class = MailingForm
    title = "Редактирование рассылки"
    success_message = "Рассылка сохранена."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.status = form.instance.calculate_status()
        return super().form_valid(form)

    def get_cancel_url(self):
        return reverse("mailing:mailing_detail", args=[self.object.pk])

    def get_success_url(self):
        return reverse("mailing:mailing_detail", args=[self.object.pk])


class MailingDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeletePageMixin, DeleteView):
    model = Mailing
    detail_url_name = "mailing:mailing_detail"
    object_label = "рассылку"
    delete_warning = "История попыток этой рассылки тоже удалится."
    success_url = reverse_lazy("mailing:mailing_list")


class MailingSendView(LoginRequiredMixin, View):
    """Ручной запуск рассылки владельцем (только POST)."""

    def post(self, request, pk):
        mailing = get_object_or_404(Mailing.objects.select_related("message"), pk=pk)
        if mailing.owner_id != request.user.pk:
            messages.error(request, "Запускать можно только свои рассылки.")
            return redirect("mailing:mailing_detail", pk=pk)
        try:
            success, failure = send_mailing(mailing)
        except MailingSendError as error:
            messages.error(request, str(error))
        else:
            if failure:
                messages.warning(
                    request,
                    f"Рассылка выполнена: успешно — {success}, с ошибкой — {failure}. "
                    "Подробности — в истории попыток.",
                )
            else:
                messages.success(request, f"Рассылка выполнена: отправлено писем — {success}.")
        return redirect("mailing:mailing_detail", pk=pk)


class MailingToggleActiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Менеджер отключает или снова включает рассылку (только POST)."""

    permission_required = DISABLE_MAILING

    def post(self, request, pk):
        mailing = get_object_or_404(Mailing, pk=pk)
        mailing.is_active = not mailing.is_active
        mailing.save(update_fields=["is_active"])
        action = "включена" if mailing.is_active else "отключена"
        messages.success(request, f"Рассылка №{mailing.pk} {action}.")
        return redirect("mailing:mailing_detail", pk=pk)
