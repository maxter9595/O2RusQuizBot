import re
from itertools import groupby

from django.db import models
from django.apps import apps
from django.db.models import Sum
from django.utils import timezone
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save, post_migrate, post_save, post_delete
from django.contrib.auth.models import AbstractUser, Group, Permission

from tgbot.apps import BotConfig


def validate_date_of_birth(value):
    """"
    Проверяет, что дата рождения введена корректно
    """
    if value > timezone.now().date():
        raise ValidationError(
            'Дата рождения не может быть в будущем'
        )
    if value < timezone.datetime(year=1900, month=1, day=1).date():
        raise ValidationError(
            'Слишком ранняя дата рождения'
        )


def validate_phone_number(value):
    """"
    Проверяет, что телефонный номер введен корректно (8xxxxxxxxxx)
    """
    phone_regex = r'^8\d{10}$'
    if not re.match(phone_regex, value):
        raise ValidationError(
            'Неверный формат номера телефона. Пожалуйста, введите номер в формате "8xxxxxxxxxx".'
        )


def format_phone_number(phone_number):
    """"
    Форматирует телефонные номера (+7, 8, -)
    """
    phone_number = phone_number.replace("+7", "8").replace(" ", "").replace("-", "")
    if len(phone_number) == 10:
        phone_number = "8" + phone_number
    return phone_number


class Role(models.Model):
    """
    Формирует модель с ролями пользователей (админ, директор, участник)
    role_name - название роли (админ, директор, участник)
    is_active - статус активности (активен, неактивен при работе с приложением)
    is_staff - статус сотрудника
    is_superuser - статус суперпользователя
    """
    role_name = models.CharField(
        null=False,
        max_length=20
    )
    is_active = models.BooleanField(
        default=False
    )
    is_staff = models.BooleanField(
        default=False
    )
    is_superuser = models.BooleanField(
        default=False
    )

    def __str__(self):
        return self.role_name


@receiver(post_migrate)
def create_default_roles(sender, **kwargs):
    """"
    Создает роли по умолчанию при первом запуске сервера
    """
    if sender.name == apps.get_app_config(BotConfig.name).name:
        roles = [
            {'role_name': 'Админ', 'is_active': True, 'is_staff': True, 'is_superuser': True},
            {'role_name': 'Директор', 'is_active': True, 'is_staff': True, 'is_superuser': False},
            {'role_name': 'Участник', 'is_active': True, 'is_staff': False, 'is_superuser': False}
        ]

        for role_data in roles:
            role_name = role_data['role_name']
            is_active = role_data['is_active']
            is_staff = role_data['is_staff']
            is_superuser = role_data['is_superuser']

            if not Role.objects.filter(role_name=role_name).exists():
                Role.objects.create(
                    role_name=role_name,
                    is_active=is_active,
                    is_staff=is_staff,
                    is_superuser=is_superuser
                )


class Authorization(models.Model):
    """"
    Содержит данные зарегистрированных пользователей
    uid - уникальный идентификатор пользователя
    registration_datetime - дата регистрации
    full_name - ФИО
    date_of_birth - дата рождения
    phone_number - номер телефона
    telegram_nickname - никнейм в телеграм
    telegram_id - идентификатор пользователя в телеграме
    role - роль пользователя в виде ID (1 - админ, 2 - директор, 3 - участник)
    """
    uid = models.CharField(
        null=False,
        unique=True,
        max_length=50
    )
    registration_datetime = models.DateTimeField(
        null=False,
        auto_now_add=True
    )
    full_name = models.CharField(
        null=False,
        max_length=100
    )
    date_of_birth = models.DateField(
        null=False,
        validators=[validate_date_of_birth]
    )
    phone_number = models.CharField(
        null=False,
        unique=True,
        max_length=11,
        validators=[validate_phone_number]
    )
    telegram_nickname = models.CharField(
        null=False,
        unique=True,
        max_length=100
    )
    telegram_id = models.CharField(
        null=False,
        unique=True,
        max_length=50
    )
    role = models.ForeignKey(
        to=Role,
        on_delete=models.CASCADE
    )

    def __str__(self):
        return f'{self.full_name} ({self.telegram_nickname}, {self.telegram_id})'

    def save(self, *args, **kwargs):
        self.phone_number = format_phone_number(self.phone_number)
        auth = Authorization
        super(auth, self).save(*args, **kwargs)


class CustomUser(AbstractUser):
    """"
    Содержит допольнительные сведения зарегистрированных пользователей, связанных с авторизацией
    role - роль пользователя в виде ID
    username - ID пользователя в таблице Authorization
    is_authorized - статус авторизации пользователя (1 - авторизован, 0 - не авторизован)
    groups - поле `ManyToManyField`, связывающее пользователя с группами
    user_permissions - поле `ManyToManyField`, которое связывает пользователя с разрешениями напрямую
    """
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE
    )
    username = models.ForeignKey(
        Authorization,
        on_delete=models.CASCADE
    )
    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_set',
        blank=True
    )
    is_authorized = models.BooleanField(
        null=False,
        default=False
    )

    first_name = None
    last_name = None
    email = None

    def __str__(self):
        return f'{self.username} ({self.role})'

    def get_is_active(self):
        return self.role.is_active

    def set_is_active(self, value):
        self.role.is_active = value
        self.role.save()

    def get_is_staff(self):
        return self.role.is_staff

    def set_is_staff(self, value):
        self.role.is_staff = value
        self.role.save()

    def get_is_superuser(self):
        return self.role.is_superuser

    def set_is_superuser(self, value):
        self.role.is_superuser = value
        self.role.save()


@receiver(post_save, sender=Authorization)
def update_custom_user(sender, instance, created, **kwargs):
    """"
    Создает нового пользователя в таблице CustomUser при создании нового пользователя в таблице Authorization
    """
    if created:
        role_id = instance.role_id
        custom_user = CustomUser.objects.filter(
            username_id=instance.telegram_id
        ).first()

        if custom_user is None:
            new_custom_user = CustomUser()
            new_custom_user.username = instance
            new_custom_user.role = instance.role

            if role_id == 1:
                new_custom_user.is_active = True
                new_custom_user.is_staff = True
                new_custom_user.is_superuser = True

            elif role_id == 2:
                new_custom_user.is_active = True
                new_custom_user.is_staff = True
                new_custom_user.is_superuser = False

            elif role_id == 3:
                new_custom_user.is_active = True
                new_custom_user.is_staff = False
                new_custom_user.is_superuser = False

            new_custom_user.save()


@receiver(post_delete, sender=CustomUser)
def delete_related_user(sender, instance, **kwargs):
    """
    Удаляет пользователя в модели Authorization после его удаления в CustomUser
    """
    Authorization.objects.filter(id=instance.username_id).delete()


@receiver(pre_save, sender=CustomUser)
def update_is_authorized(sender, instance, **kwargs):
    """
    Разавторизирует пользователя в модели CustomUser в случае изменения его роли
    """
    auth_obj = Authorization.objects.get(
        id=instance.username_id
    )
    if instance.role_id != auth_obj.role_id:
        instance.is_authorized = False


@receiver(pre_save, sender=CustomUser)
def update_authorization_role_id(sender, instance, **kwargs):
    """
    Обновляет роль пользователя в модели Authorization в случае изменения его идентификатора роли в CustomUser
    """
    auth_obj = Authorization.objects.get(
        id=instance.username_id
    )
    auth_obj.role_id = instance.role_id
    auth_obj.save()


class Question(models.Model):
    """"
    Содержит данные по вопросам и ответам на них
    tour_id - номер тура
    tour_question_number_id - номер вопроса в туре
    question_text - текст вопроса
    answer_a - вариант ответа A
    answer_b - вариант ответа B
    answer_c - вариант ответа C
    answer_d - вариант ответа D
    correct_answer - столбец, обозначающий правильный ответ (A, B, C, D)
    explanation - объяснение к правильному ответу
    image - картинка вопроса
    """
    tour_id = models.PositiveIntegerField(
        null=False
    )
    tour_question_number_id = models.PositiveIntegerField(
        null=False
    )
    question_text = models.TextField(
        null=False
    )
    answer_a = models.CharField(
        null=False,
        max_length=250
    )
    answer_b = models.CharField(
        null=False,
        max_length=250
    )
    answer_c = models.CharField(
        null=False,
        max_length=250
    )
    answer_d = models.CharField(
        null=False,
        max_length=250
    )
    correct_answer = models.CharField(
        max_length=1,
        choices=[
            ('A', 'A'),
            ('B', 'B'),
            ('C', 'C'),
            ('D', 'D')
        ])
    explanation = models.TextField(
        null=True,
        max_length=1500
    )
    image = models.ImageField(
        null=True,
        upload_to='questions_images/'
    )

    def __str__(self):
        return f'Question {self.id}'


class PointsTransaction(models.Model):
    """"
    Содержит данные о начисленных и списанных баллах в рамках викторины
    points_datetime - дата и время начисления или списания баллов
    tournament_points - количество баллов, начисленных по 1-му типу (порядковый номер занятого места с шагом 5 баллов)
    points_received_or_transferred - количество баллов, начисленных по 2-му типу (РОТ/ПОТ)
    bonuses - количество баллов, начисленных по 3-му типу (бонусы)
    transfer_datetime - дата и время списания баллов (применим к 4-му типу начисления баллов)
    sender_telegram - Telegram ID отправителя баллов по 4-му типу (перекидывание баллов от одного участника к другому)
    points_transferred - количество баллов, списанных по 4-му типу (перекидывание баллов от одного участника к другому)
    receiver_telegram - Telegram ID получателя баллов по 4-му типу (перекидывание баллов от одного участника к другому)
    transferor_telegram -  Telegram ID директора, ответственного за перекидывание баллов по 4-му типу
    question - ID вопроса из таблицы Question
    """
    points_datetime = models.DateTimeField(
        null=False,
        auto_now_add=True
    )
    tournament_points = models.PositiveIntegerField(
        null=True
    )
    points_received_or_transferred = models.PositiveIntegerField(
        null=True
    )
    bonuses = models.PositiveIntegerField(
        null=True
    )
    transfer_datetime = models.DateTimeField(
        null=True
    )
    sender_telegram = models.ForeignKey(
        'Authorization',
        related_name='sender_transactions1',
        on_delete=models.CASCADE,
        to_field='telegram_id'
    )
    points_transferred = models.PositiveIntegerField(
        null=True
    )
    receiver_telegram = models.ForeignKey(
        'Authorization',
        related_name='receiver_transactions1',
        on_delete=models.CASCADE,
        null=True,
        to_field='telegram_id'
    )
    transferor_telegram = models.ForeignKey(
        'Authorization',
        related_name='transferor_transactions1',
        on_delete=models.CASCADE,
        null=True,
        to_field='telegram_id'
    )
    question = models.ForeignKey(
        'Question',
        related_name='question',
        on_delete=models.CASCADE,
        null=False,
        to_field='id'
    )
    is_answered = models.BooleanField(
        null=False,
        default=False,
        choices=[(True, 'Да'), (False, 'Нет')]
    )
    is_done = models.BooleanField(
        null=False,
        default=False,
        choices=[(True, 'Да'), (False, 'Нет')]
    )

    def __str__(self):
        return f'Transaction {self.id}'


@receiver(pre_save, sender=PointsTransaction)
def update_transfer_datetime(sender, instance, **kwargs):
    """"
    Обновляет дату и время списания баллов при перекидывании баллов
    """
    if instance.points_transferred is not None:
        instance.transfer_datetime = timezone.now()


@receiver(pre_save, sender=Authorization)
def delete_point_records(sender, instance, **kwargs):
    """"
    Удаляет баллы пользователя после изменения его роли на "Директора" или "Админа"
    """
    if instance.role_id != 3:
        PointsTransaction.objects.filter(
            sender_telegram_id=instance.telegram_id,
        ).delete()

        PointsTransaction.objects.filter(
            receiver_telegram_id=instance.telegram_id,
        ).delete()

    elif instance.role_id != 2:
        PointsTransaction.objects.filter(
            transferor_telegram_id=instance.telegram_id,
        ).delete()


class Tournament(models.Model):
    tournament_name = models.CharField(
        max_length=150,
        null=False
    )
    description = models.TextField(
        null=True,
        max_length=1500
    )


class PointsTournament(models.Model):
    """"
    Содержит данные о начисленных и списанных баллах в рамках турнира
    points_datetime - дата и время начисления или списания баллов
    tournament_points - количество баллов, начисленных по 1-му типу (порядковый номер занятого места с шагом 5 баллов)
    points_received_or_transferred - количество баллов, начисленных по 2-му типу (РОТ/ПОТ)
    bonuses - количество баллов, начисленных по 3-му типу (бонусы)
    transfer_datetime - дата и время списания баллов (применим к 4-му типу начисления баллов)
    sender_telegram - Telegram ID отправителя баллов по 4-му типу (перекидывание баллов от одного участника к другому)
    points_transferred - количество баллов, списанных по 4-му типу (перекидывание баллов от одного участника к другому)
    receiver_telegram - Telegram ID получателя баллов по 4-му типу (перекидывание баллов от одного участника к другому)
    transferor_telegram -  Telegram ID директора, ответственного за перекидывание баллов по 4-му типу
    is_done - столбец для пометки пройден ли турнир участником или нет (0 - участник дал ответ на вопрос, 1 - наоборот)
    tournament - номер турнира, связываемый с моделью Tournament
    """
    points_datetime = models.DateTimeField(
        null=False,
        auto_now_add=True
    )
    tournament_points = models.PositiveIntegerField(
        null=True
    )
    points_received_or_transferred = models.PositiveIntegerField(
        null=True
    )
    bonuses = models.PositiveIntegerField(
        null=True
    )
    transfer_datetime = models.DateTimeField(
        null=True
    )
    sender_telegram = models.ForeignKey(
        'Authorization',
        related_name='sender_transactions2',
        on_delete=models.CASCADE,
        to_field='telegram_id'
    )
    points_transferred = models.PositiveIntegerField(
        null=True
    )
    receiver_telegram = models.ForeignKey(
        'Authorization',
        related_name='receiver_transactions2',
        on_delete=models.CASCADE,
        null=True,
        to_field='telegram_id'
    )
    transferor_telegram = models.ForeignKey(
        'Authorization',
        related_name='transferor_transactions2',
        on_delete=models.CASCADE,
        null=True,
        to_field='telegram_id'
    )
    is_done = models.BooleanField(
        null=False,
        default=False,
        choices=[(True, 'Да'), (False, 'Нет')]
    )
    tournament = models.ForeignKey(
        'Tournament',
        related_name='tournament',
        on_delete=models.CASCADE,
        null=False,
    )

    def __str__(self):
        return f'Transaction {self.id}'


@receiver(pre_save, sender=PointsTournament)
def update_transfer_datetime(sender, instance, **kwargs):
    """"
    Обновляет дату и время списания баллов при перекидывании баллов
    """
    if instance.points_transferred is not None:
        instance.transfer_datetime = timezone.now()


@receiver(pre_save, sender=Authorization)
def delete_point_records(sender, instance, **kwargs):
    """"
    Удаляет баллы пользователя после изменения его роли на "Директора" или "Админа"
    """
    if instance.role_id != 3:
        PointsTournament.objects.filter(
            sender_telegram_id=instance.telegram_id,
        ).delete()

        PointsTournament.objects.filter(
            receiver_telegram_id=instance.telegram_id,
        ).delete()

    elif instance.role_id != 2:
        PointsTournament.objects.filter(
            transferor_telegram_id=instance.telegram_id,
        ).delete()


class Standings(models.Model):
    """
    participant_telegram
    """
    participant_telegram = models.CharField(
        null=False,
        unique=True,
        max_length=100
    )
    full_name = models.CharField(
        max_length=100,
        null=False
    )
    total_points = models.IntegerField(
        default=0,
        null=False
    )
    final_place = models.IntegerField(
        default=0,
        null=False
    )
    tournament_points = models.IntegerField(
        default=0,
        null=False
    )
    tournament_place = models.IntegerField(
        default=0,
        null=False
    )
    quiz_points = models.IntegerField(
        default=0,
        null=True
    )
    quiz_place = models.IntegerField(
        default=0,
        null=False
    )

    def save(self, *args, **kwargs):
        if 'tournament_place' in kwargs.get('update_fields', []):
            super(Standings, self).save(*args, **kwargs)

        else:
            standings_list = Standings.objects.order_by('-tournament_points')
            quiz_standings_list = Standings.objects.order_by('-quiz_points')
            total_standings_list = Standings.objects.order_by('-total_points', 'full_name')

            for index, standings_group in enumerate(groupby(standings_list, key=lambda x: x.tournament_points),
                                                    start=1):
                for standings in standings_group[1]:
                    standings.tournament_place = index

            for index, quiz_standings_group in enumerate(groupby(quiz_standings_list, key=lambda x: x.quiz_points),
                                                         start=1):
                for quiz_standings in quiz_standings_group[1]:
                    quiz_standings.quiz_place = index

            for index, total_standings_group in enumerate(
                    groupby(total_standings_list, key=lambda x: (x.total_points, x.full_name)), start=1):
                for total_standings in total_standings_group[1]:
                    total_standings.final_place = index

            Standings.objects.bulk_update(standings_list, ['tournament_place'])
            Standings.objects.bulk_update(quiz_standings_list, ['quiz_place'])
            Standings.objects.bulk_update(total_standings_list, ['final_place'])

    class Meta:
        ordering = ['-total_points', 'full_name']

    def __str__(self):
        return self.full_name


@receiver(post_save, sender=Authorization)
def get_users(sender, instance, created, **kwargs):
    """"
    Добавялет пользователя после его регистрации
    """
    if created:
        user = Standings.objects.filter(
            participant_telegram=instance.telegram_id,
        )

        if not user.exists():
            new_user = Standings()
            new_user.participant_telegram_id = instance.telegram_id
            new_user.full_name = instance.full_name
            new_user.save()


# @receiver(post_save, sender=Standings)
# def check_standings_table(sender, instance, **kwargs):
#     """"
#     Проверяет по Telegram ID отсутствие пользователя в PointsTransaction и PointsTournament
#     """
#     sender_quiz = PointsTransaction.objects.filter(
#         sender_telegram_id=instance.participant_telegram
#     )
#
#     receiver_quiz = PointsTransaction.objects.filter(
#         receiver_telegram_id=instance.participant_telegram
#     )
#
#     if not sender_quiz.exists() and not receiver_quiz.exists():
#         instance.quiz_points = 0
#         instance.save()
#
#     sender_tournament = PointsTournament.objects.filter(
#         sender_telegram_id=instance.participant_telegram,
#     )
#
#     receiver_tournament = PointsTournament.objects.filter(
#         receiver_telegram_id=instance.participant_telegram
#     )
#
#     if not sender_tournament.exists() and not receiver_tournament.exists():
#         instance.tournament_points = 0
#         instance.save()


# @receiver(post_save, sender=Authorization)
# def delete_point_records(sender, instance, **kwargs):
#     """"
#     Удаляет баллы пользователя после изменения его роли на "Директора" или "Админа"
#     """
#     if instance and instance.role.id != 3:
#         Standings.objects.filter(
#             participant_telegram=instance,
#         ).delete()
