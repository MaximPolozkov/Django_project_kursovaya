from datetime import timedelta

from django import forms
from django.utils import timezone

from config.forms import StyleFormMixin
from mailing.models import Mailing, Message, Recipient

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class RecipientForm(StyleFormMixin, forms.ModelForm):
    class Meta:
        model = Recipient
        fields = ("email", "full_name", "comment")
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["placeholder"] = "client@example.com"
        self.fields["full_name"].widget.attrs["placeholder"] = "Иванов Иван Иванович"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class MessageForm(StyleFormMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ("subject", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}


class MailingForm(StyleFormMixin, forms.ModelForm):
    class Meta:
        model = Mailing
        fields = ("start_time", "end_time", "message", "recipients")
        widgets = {
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_FORMAT),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_FORMAT),
            "recipients": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("start_time", "end_time"):
            self.fields[name].input_formats = [DATETIME_FORMAT, "%Y-%m-%d %H:%M"]
        # В форме доступны только свои сообщения и получатели
        if user is not None:
            self.fields["message"].queryset = Message.objects.filter(owner=user)
            self.fields["recipients"].queryset = Recipient.objects.filter(owner=user)
        self.fields["message"].empty_label = "Выберите сообщение"
        self.fields["start_time"].help_text = "Не раньше текущего момента."
        if not self.fields["recipients"].queryset.exists():
            self.fields["recipients"].help_text = "Сначала добавьте получателей в разделе «Получатели»."

    def clean_start_time(self):
        start_time = self.cleaned_data.get("start_time")
        is_new = self.instance.pk is None
        if start_time and (is_new or "start_time" in self.changed_data):
            # Минута запаса: в поле нельзя выбрать секунды
            if start_time < timezone.now() - timedelta(minutes=1):
                raise forms.ValidationError("Дата начала не может быть в прошлом.")
        return start_time

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and start_time >= end_time:
            self.add_error("end_time", "Дата окончания должна быть позже даты начала.")
        return cleaned_data
