from django.contrib import admin
from django.contrib.auth.hashers import make_password

from tgbot.models import Role, Authorization, CustomUser, Question


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """"
    Настраивает админку для модели Role
    """
    list_display = [
        'role_name',
        'is_active',
        'is_staff',
        'is_superuser'
    ]
    list_filter = [
        'is_active',
        'is_staff',
        'is_superuser'
    ]
    search_fields = [
        'role_name'
    ]


@admin.register(Authorization)
class AuthorizationAdmin(admin.ModelAdmin):
    """"
    Настраивает админку для модели Authorization
    """
    list_display = [
        'telegram_id',
        'full_name',
        'telegram_nickname',
        'date_of_birth',
        'phone_number',
        'role'
    ]
    search_fields = [
        'uid',
        'registration_datetime',
        'full_name',
        'date_of_birth',
        'phone_number',
        'telegram_nickname',
        'telegram_id',
        'role',
        'password'
    ]


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """"
    Настраивает админку для модели CustomUser
    """
    list_display = [
        'username',
        'role'
    ]

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('password'):
            obj.password = make_password(form.cleaned_data['password'])
        obj.save()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """"
    Настраивает админку для модели Question
    """
    list_display = [
        'id',
        'tour_id',
        'tour_question_number_id',
        'question_text',
        'correct_answer'
    ]
    list_filter = [
        'tour_id'
    ]
    search_fields = [
        'question_text'
    ]
    list_per_page = 20
