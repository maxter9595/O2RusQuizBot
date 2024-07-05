import os
import time
import random
import re

import django
import telebot
from telebot import types
from openpyxl import Workbook
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

os.environ.setdefault(
    key='DJANGO_SETTINGS_MODULE',
    value='quiz.settings'
)
django.setup()

from quiz.settings import BOT_TOKEN
from tgbot.models import Authorization, CustomUser, PointsTransaction, Question, Tournament, PointsTournament, Standings

bot = telebot.TeleBot(BOT_TOKEN)


def update_tournament_points(telegram_id):
    """"
    Выводит общие очки, набранные пользователем во время турнира
    """
    auth_data = Authorization.objects.filter(
        telegram_id=telegram_id,
    )
    telegram_id = auth_data.first()

    tournament_sender_data = PointsTournament.objects.filter(
        sender_telegram_id=telegram_id,
    )

    if tournament_sender_data:
        tournament_points = 0
        points_received_or_transferred = 0
        bonuses = 0
        total_transfer_loss = 0
        total_transfer_income = 0

        for item in tournament_sender_data:
            tournament_points += item.tournament_points if item.tournament_points else 0
            points_received_or_transferred += item.points_received_or_transferred if item.points_received_or_transferred else 0
            bonuses += item.bonuses if item.bonuses else 0
            total_transfer_loss += item.points_transferred if item.points_transferred else 0

        sender_data_vals = [
            tournament_points,
            points_received_or_transferred,
            bonuses,
        ]

        tournament_receiver_data = PointsTournament.objects.filter(
            receiver_telegram_id=telegram_id,
        )

        if tournament_receiver_data:
            for item in tournament_receiver_data:
                total_transfer_income += item.points_transferred if item.points_transferred else 0

        standing_participant = Standings.objects.filter(
            participant_telegram=telegram_id,
        )

        auth_data = Authorization.objects.filter(
            telegram_id=telegram_id,
        )

        if not standing_participant.exists() and auth_data.exists():
            standing_participant = Standings(
                participant_telegram=telegram_id,
                full_name=auth_data.first().full_name,
            ).save()

            standing_participant = Standings.objects.filter(
                participant_telegram=telegram_id,
            )

        if standing_participant:
            standing_participant.update(
                tournament_points=sum(
                    sender_data_vals
                ) + (
                    total_transfer_income - total_transfer_loss
                ),
            )

            standing_participant.update(
                total_points=standing_participant.first().quiz_points + standing_participant.first().tournament_points
            )


def update_quiz_points(telegram_id):
    """"
    Выводит общие очки, набранные пользователем во время викторины
    """
    auth_data = Authorization.objects.filter(
        telegram_id=telegram_id,
    )
    telegram_id = auth_data.first()

    tournament_sender_data = PointsTransaction.objects.filter(
        sender_telegram_id=telegram_id,
    )

    if tournament_sender_data:
        tournament_points = 0
        points_received_or_transferred = 0
        bonuses = 0
        total_transfer_loss = 0
        total_transfer_income = 0

        for item in tournament_sender_data:
            tournament_points += item.tournament_points if item.tournament_points else 0
            points_received_or_transferred += item.points_received_or_transferred if item.points_received_or_transferred else 0
            bonuses += item.bonuses if item.bonuses else 0
            total_transfer_loss += item.points_transferred if item.points_transferred else 0

        sender_data_vals = [
            tournament_points,
            points_received_or_transferred,
            bonuses,
        ]

        tournament_receiver_data = PointsTransaction.objects.filter(
            receiver_telegram_id=telegram_id,
        )

        if tournament_receiver_data:
            for item in tournament_receiver_data:
                total_transfer_income += item.points_transferred if item.points_transferred else 0

        standing_participant = Standings.objects.filter(
            participant_telegram=telegram_id,
        )

        auth_data = Authorization.objects.filter(
            telegram_id=telegram_id,
        )

        if not standing_participant.exists() and auth_data.exists():
            standing_participant = Standings(
                participant_telegram=telegram_id,
                full_name=auth_data.first().full_name,
            ).save()

            standing_participant = Standings.objects.filter(
                participant_telegram=telegram_id,
            )

        if standing_participant:
            standing_participant.update(
                quiz_points=sum(
                    sender_data_vals
                ) + (
                    total_transfer_income - total_transfer_loss
                )
            )

            standing_participant.update(
                total_points=standing_participant.first().quiz_points + standing_participant.first().tournament_points
            )


@bot.message_handler(commands=['start'])
def start(message):
    """
    Запускает бота для регистрации и авторизации пользователей
    """
    markup_start = True
    user_auth = Authorization.objects.filter(telegram_id=message.from_user.id)

    if user_auth.exists():
        user_id = user_auth.first().id
        custom_user = CustomUser.objects.filter(id=user_id)

        if custom_user.exists():
            if custom_user.first().is_authorized:
                bot.send_message(
                    chat_id=message.chat.id,
                    text='Вы уже авторизованы',
                )
                markup_start = False

    if markup_start:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message=message,
            text='\n'.join([
                'Добро пожаловать!',
                '📝 Для регистрации введите /register',
                '🔒 Для авторизации введите /login',
                '🔒 Для изменения пароля введите /password'
            ]),
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: "Регистрация" in message.text or message.text == "/register")
def register(message):
    """
    Проверяет зарегистрирован ли пользователь. Если нет, то начинает серию вопросов
    """
    chat_id = message.chat.id
    uid = message.from_user.id

    if Authorization.objects.filter(telegram_id=uid).exists():
        response = bot.reply_to(
            message=message,
            text="Вы уже зарегистрированы!"
        )

    else:
        response = bot.reply_to(
            message=message,
            text="Введите ваше ФИО (пример - Иванов Иван Иванович):"
        )
        bot.register_next_step_handler(
            response,
            process_full_name
        )


def process_full_name(message):
    """
    Получает информацию о ФИО пользователя, запрашивает дату рождения
    """
    full_name = message.text

    response = bot.reply_to(
        message=message,
        text="Введите вашу дату рождения в формате ДД.ММ.ГГГГ (пример - 07.07.2007):"
    )

    bot.register_next_step_handler(
        response,
        process_date_of_birth,
        full_name=full_name
    )


def process_date_of_birth(message, full_name):
    """
    Получает информацию о дате рождения, запрашивает номер телефона
    """
    date_of_birth = message.text
    date_pattern = re.compile(r'\d{2}.\d{2}.\d{4}')

    if date_pattern.fullmatch(date_of_birth):
        date_of_birth = '-'.join(date_of_birth.split('.')[::-1])

        response = bot.reply_to(
            message=message,
            text="Введите ваш номер телефона в формате 8xxxxxxxxxx (пример - 89053743009):"
        )
        bot.register_next_step_handler(
            response,
            process_phone_number,
            full_name=full_name,
            date_of_birth=date_of_birth
        )

    else:
        bot.reply_to(
            message=message,
            text="Введенная дата рождения некорректна"
        )


def process_phone_number(message, full_name, date_of_birth):
    """
    Получает информацию о номере телефона, запрашивает будущий пароль пользователя
    """
    phone_number = message.text
    phone_pattern = re.compile(r'^[8-9]\d{10}$')

    if phone_pattern.match(phone_number):
        response = bot.reply_to(
            message=message,
            text="Введите ваш пароль для авторизации:"
        )
        bot.register_next_step_handler(
            response,
            process_password_registration,
            full_name=full_name,
            date_of_birth=date_of_birth,
            phone_number=phone_number
        )

    else:
        bot.reply_to(
            message=message,
            text="Введенный номер телефона некорректен"
        )


def process_password_registration(message, full_name, date_of_birth, phone_number):
    """
    Получает информацию о пароле пользователя, создает запись о пользователе в таблице Authorization
    """
    password = message.text
    hashed_password = make_password(password)
    uid = message.from_user.id

    authorization = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if not authorization.exists():
        auth_user = Authorization.objects.create(
            uid=message.from_user.id,
            registration_datetime=timezone.now(),
            full_name=full_name,
            date_of_birth=date_of_birth,
            phone_number=phone_number,
            telegram_nickname=message.from_user.username,
            telegram_id=message.from_user.id,
            role_id=3
        )

        CustomUser.objects.filter(
            username_id=auth_user.id
        ).update(
            password=hashed_password
        )

        bot.reply_to(
            message=message,
            text="Регистрация прошла успешно. Авторизируйтесь через команду /login"
        )

    else:
        bot.reply_to(
            message,
            "Пользователь уже существует"
        )


@bot.message_handler(func=lambda message: "Авторизация" in message.text or message.text == "/login")
def login(message):
    """
    Начинает процесс авторизации пользователя
    """
    uid = message.from_user.id
    auth_data = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if not auth_data.exists():
        bot.reply_to(
            message=message,
            text="Вы не зарегистрированы. Для регистрации введите /register"
        )

    else:
        auth_obj = auth_data.first()
        custom_user = CustomUser.objects.filter(
            username_id=auth_obj.id
        ).first()

        if custom_user.is_authorized:
            bot.reply_to(
                message,
                "Вы уже авторизованы."
            )
        else:
            process_login_data(
                message,
                custom_user
            )


def process_login_data(message, custom_user):
    """
    Просит пользователю ввести пароль для авторизации, если он не авторизован
    """
    response = bot.reply_to(
        message,
        "Введите ваш пароль:"
    )

    bot.register_next_step_handler(
        response,
        process_password,
        custom_user=custom_user
    )


def process_password(message, custom_user):
    """
    Осуществляет вход пользователя в приложение, если пароль верный
    """
    input_password = message.text
    actual_password = custom_user.password

    if check_password(input_password, actual_password):
        custom_user.last_login = timezone.now()
        custom_user.is_authorized = True
        custom_user.save()

        main_menu(message)

    else:
        bot.reply_to(
            message,
            "Неправильный пароль"
        )


@bot.message_handler(func=lambda message: "Забыл пароль" in message.text or message.text == "/password")
def change_password(message):
    """
    Меняет пароль в случае, если пользователь забыл его
    """
    uid = message.from_user.id
    auth_data = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if not auth_data.exists():
        bot.reply_to(
            message=message,
            text="Вы не зарегистрированы. Для регистрации введите /register"
        )

    else:
        custom_user = CustomUser.objects.get(
            username_id=auth_data.first().id
        )

        if custom_user:
            if custom_user.is_authorized == False:
                response = bot.reply_to(
                    message,
                    "Введите ваш новый пароль:"
                )

                bot.register_next_step_handler(
                    response,
                    callback=get_new_password,
                )

            else:
                bot.reply_to(
                    message,
                    "Вы авторизованы. Разавторизируйтесь для получения нового пароля: /logout"
                )


def get_new_password(message):
    """
    Позволяет получить новый пароль
    """
    new_password = message.text

    hashed_password = make_password(new_password)
    uid = message.from_user.id

    auth_user = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if auth_user.exists():
        CustomUser.objects.filter(
            username_id=auth_user.first().id
        ).update(
            password=hashed_password
        )

        bot.reply_to(
            message=message,
            text="Изменение пароля прошло успешно. Авторизируйтесь через команду /login"
        )



@bot.message_handler(func=lambda message: "Главное меню" in message.text or message.text == "/main_menu")
def main_menu(message):
    """
    Отображает главное меню пользователя
    """
    uid = message.from_user.id
    auth_data = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if not auth_data.exists():
        bot.reply_to(
            message=message,
            text="Вы не зарегистрированы. Для регистрации введите /register"
        )

    else:
        auth_obj = auth_data.first()
        custom_user = CustomUser.objects.filter(
            username_id=auth_obj.id
        ).first()

        if not custom_user.is_authorized:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            btn_start_quiz = types.KeyboardButton(
                text='Начать викторину'
            )

            btn_add_points1 = types.KeyboardButton(
                text='Добавить очки за викторину'
            )

            btn_add_points2 = types.KeyboardButton(
                text='Добавить очки за турнир'
            )

            btn_tournament_rating1 = types.KeyboardButton(
                text='Общий рейтинг по баллам (викторина)'
            )

            btn_tournament_rating2 = types.KeyboardButton(
                text='Общий рейтинг по баллам (турнир)'
            )

            btn_participant_rating1 = types.KeyboardButton(
                text='Мое место в рейтинге по баллам (викторина)'
            )

            btn_participant_rating2 = types.KeyboardButton(
                text='Мое место в рейтинге по баллам (турнир)'
            )

            btn_answers_rating = types.KeyboardButton(
                text='Общий рейтинг по верным ответам (викторина)'
            )

            btn_tour_statistics1 = types.KeyboardButton(
                text='Общий рейтинг тура по баллам (викторина)'
            )

            btn_tour_statistics2 = types.KeyboardButton(
                text='Общий рейтинг турнира по баллам (турнир)'
            )

            btn_tours_statistics1 = types.KeyboardButton(
                text='Общий рейтинг по всем турам (викторина)'
            )

            btn_tours_statistics2 = types.KeyboardButton(
                text='Общий рейтинг по всем турнирам (турнир)'
            )

            if custom_user.role_id == 2:
                markup.add(
                    btn_logout,
                    btn_add_points1,
                    btn_add_points2,
                    btn_tournament_rating1,
                    btn_tournament_rating2,
                    btn_participant_rating1,
                    btn_participant_rating2,
                    btn_answers_rating,
                    btn_tour_statistics1,
                    btn_tour_statistics2,
                    btn_tours_statistics1,
                    btn_tours_statistics2
                )

            else:
                markup.add(
                    btn_logout,
                    btn_start_quiz,
                    btn_tournament_rating1,
                    btn_tournament_rating2,
                    btn_participant_rating1,
                    btn_participant_rating2,
                    btn_answers_rating,
                    btn_tour_statistics1,
                    btn_tour_statistics2,
                    btn_tours_statistics1,
                    btn_tours_statistics2
                )

            bot.reply_to(
                message,
                "Главное меню",
                reply_markup=markup,
            )


@bot.message_handler(func=lambda message: 'Выход' in message.text or message.text == '/logout')
def logout(message):
    """
    Осуществляет выход пользователя из приложения, если он авторизован
    """
    uid = message.from_user.id
    auth_data = Authorization.objects.filter(
        telegram_id=str(uid)
    )

    if auth_data.exists():
        username_id = auth_data.first().id

        custom_user = CustomUser.objects.get(
            username_id=username_id
        )

        if custom_user.is_authorized:
            custom_user.is_authorized = False
            custom_user.save()

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы успешно вышли из аккаунта.",
                reply_markup=markup,
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: 'Добавить очки за викторину' in message.text or message.text == '/add_quiz_points')
def add_points_check_quiz(message):
    """
    Проверяет, является ли пользователь директором. Если директор, то запрашивает тип начисления баллов участнику
    """
    is_AttributeError = False
    uid = message.from_user.id

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        username_id = user_auth_data.first().id
        custom_user = CustomUser.objects.get(
            username_id=username_id
        )

    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            user_auth_data = user_auth_data.first()

            if user_auth_data.role_id == 2:
                markup = types.ReplyKeyboardMarkup(
                    resize_keyboard=True
                )

                btn_main_menu = types.KeyboardButton(
                    text='Главное меню'
                )

                btn_logout = types.KeyboardButton(
                    text='Выход'
                )

                markup.add(
                    btn_main_menu,
                    btn_logout
                )

                text = '\n'.join([
                    'Введдите тип начисления баллов в виде числа:',
                    '1 - порядковый номер занятого места с шагом 5 баллов',
                    '2 - РОТ (ПОТ) [указываем общую цифру, делим на /50 и зачисляем полученные баллы]',
                    '3 - произвольная цифра (бонусы)',
                    '4 - перевод баллов между участниками'
                ])

                response = bot.reply_to(
                    message,
                    text,
                    reply_markup=markup,
                )

                bot.register_next_step_handler(
                    response,
                    process_add_tour_quiz,
                    uid=uid
                )

            else:
                bot.reply_to(
                    message,
                    "Вы не являетесь директором. Вы не можете начислять баллы"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


def process_add_tour_quiz(message, **kwargs):
    """"
    Запрашивает у директора номер тура
    """
    uid = kwargs.get('uid')
    points_type = message.text

    if points_type == "Главное меню":
        main_menu(message)

    elif points_type == "Выход":
        logout(message)

    else:
        reply = bot.reply_to(
            message,
            "Введите номер тура:"
        )

        bot.register_next_step_handler(
            reply,
            process_add_question_number_quiz,
            uid=uid,
            points_type=points_type
        )


def process_add_question_number_quiz(message, **kwargs):
    """"
    Запрашивает у директора номер вопроса в рамках выбранного тура
    """
    points_type = kwargs.get('points_type')
    uid = kwargs.get('uid')
    tour = message.text

    if tour == "Главное меню":
        main_menu(message)

    elif tour == "Выход":
        logout(message)

    else:
        if tour.isdigit():
            if int(tour) > 0:
                reply = bot.reply_to(
                    message,
                    "Введите номер вопроса:"
                )

                bot.register_next_step_handler(
                    reply,
                    process_add_points_type_quiz,
                    uid=uid,
                    tour=tour,
                    points_type=points_type
                )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод номера тура (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод номера тура (должно быть число)"
            )


def process_add_points_type_quiz(message, **kwargs):
    """"
    Проверяет корректность введенного типа начисления баллов и в зависимости от него запрашивает у директора информацию
    """
    add_points_type = kwargs.get('points_type')
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = message.text

    if question_number == "Главное меню":
        main_menu(message)

    elif question_number == "Выход":
        logout(message)

    else:
        if question_number.isdigit():
            if int(question_number) > 0:
                if add_points_type in ('1', '2', '3', '4'):
                    participants = Authorization.objects.all().filter(
                        role=3
                    )

                    participants_list = []
                    if participants:
                        for participant in participants:
                            part_id = participant.id
                            part_name = participant.full_name
                            part_nick = participant.telegram_nickname
                            part_tel_id = participant.telegram_id

                            participants_list.append(
                                f"{part_id}: {part_name}" + f" (Telegram: {part_nick}, {part_tel_id})"
                            )

                        total_participants = len(participants_list)
                        participants_list = "\n".join(participants_list)

                        bot.reply_to(
                            message,
                            f"Список участников: \n{participants_list}"
                        )

                        if len(participants_list) >= 1:
                            if add_points_type == '1':
                                response = bot.reply_to(
                                    message,
                                    f"Выберите по ID участника, которому будем ставить место в рейтинге:"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_1_place_quiz,
                                    tour=tour,
                                    question_number=question_number,
                                    uid=uid,
                                    total_participants=total_participants,
                                )

                            elif add_points_type == '2':
                                response = bot.reply_to(
                                    message,
                                    "Выберите по ID участника, которому назначаем баллы"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_2_digit_quiz,
                                    tour=tour,
                                    question_number=question_number,
                                    uid=uid,
                                )

                            elif add_points_type == '3':
                                response = bot.reply_to(
                                    message,
                                    f"Выберите по ID участника, которому назначаем баллы:"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_3_bonuses_quiz,
                                    tour=tour,
                                    question_number=question_number,
                                    uid=uid,
                                )

                            elif add_points_type == '4':
                                if len(participants_list) >= 2:
                                    response = bot.reply_to(
                                        message,
                                        f"Выберите участника, у которого забираем баллы по его ID в БД:"
                                    )

                                    bot.register_next_step_handler(
                                        response,
                                        process_points_type_4_receiver_quiz,
                                        tour=tour,
                                        question_number=question_number,
                                        uid=uid,
                                    )

                                else:
                                    bot.reply_to(
                                        message,
                                        "Недостаточное количество участников для начисления баллов"
                                    )

                    else:
                        bot.reply_to(
                            message,
                            "У вас отсутствуют участники"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Некорректный тип начисления баллов. Пожалуйста, выберите один из предложенных вариантов"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод номера вопроса (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод номера вопроса (должно быть число)"
            )


def process_points_type_1_place_quiz(message, **kwargs):
    """
    Запрашивает у директора место в рейтинге, за которое он будем начислять баллы (1-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    total_participants = kwargs.get('total_participants')
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    text1 = 'Введите номер места в рейтинге для следующего участника:'
                    text2 = 'На текущий момент можно ввести место в диапазоне от 1 до'
                    part_name = participant.full_name
                    part_nick = participant.telegram_nickname
                    part_tel_id = participant.telegram_id

                    response = bot.reply_to(
                        message,
                        f"{text1} {part_name} (Telegram: {part_nick}, {part_tel_id}). {text2} {total_participants}"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_1_place_points_quiz,
                        uid=uid,
                        tour=tour,
                        question_number=question_number,
                        participant=participant,
                        total_participants=total_participants
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_1_place_points_quiz(message, **kwargs):
    """
    Добавляет баллы участнику и заносит их в таблицу PointsTransaction (1-й тип начисления баллов)
    """

    def create_points_dict(points=100, step=5, max_place=30):
        """
        Создает словарь с баллами, начисляемыми по определенным местам
        """
        points_dict = {}
        for place in range(1, max_place + 1):
            points_dict[place] = points
            points -= step
            if points < step:
                points = step
        return points_dict

    def calculate_points(points_dict, place):
        """
        Выводит очки за конкретно занятое место
        """
        return points_dict.get(place, 0)

    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant = kwargs.get('participant')
    total_participants = kwargs.get('total_participants')
    place = message.text

    if place == "Главное меню":
        main_menu(message)

    elif place == "Выход":
        logout(message)

    else:
        if place.isdigit():
            if int(place) > 0:
                if int(place) <= total_participants:
                    if total_participants <= 30:
                        points_dict = create_points_dict()
                    else:
                        points_dict = create_points_dict(
                            max_place=total_participants
                        )

                    points = calculate_points(
                        points_dict,
                        int(place)
                    )

                    transferor = Authorization.objects.get(
                        telegram_id=uid
                    )

                    question = Question.objects.get(
                        tour_id=int(tour),
                        tour_question_number_id=int(question_number)
                    )

                    if question:
                        participant_row = PointsTransaction.objects.filter(
                            sender_telegram_id=participant.telegram_id,
                            transferor_telegram_id=transferor.telegram_id,
                            question_id=question.id,
                        )

                        if not participant_row.exists():
                            PointsTransaction.objects.create(
                                sender_telegram_id=participant.telegram_id,
                                transferor_telegram_id=transferor.telegram_id,
                                question_id=question.id,
                                tournament_points=points,
                            )

                            update_quiz_points(
                                telegram_id=participant.telegram_id,
                            )

                        else:
                            participant_row.update(
                                tournament_points=points,
                                points_datetime=timezone.now(),
                            )

                            update_quiz_points(
                                telegram_id=participant.telegram_id,
                            )

                        bot.reply_to(
                            message,
                            f"Участник {participant.full_name} получил {points} баллов за {place} место в рейтине"
                        )

                    else:
                        bot.reply_to(
                            message,
                            "Пара 'тур-вопрос' не существует в БД"
                        )

                else:
                    bot.reply_to(
                        message,
                        f"Место в рейтинге должно быть в диапазоне от 1 до {total_participants}"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод места в рейтинге (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод места в рейтинге (число должно быть числом)"
            )


def process_points_type_2_digit_quiz(message, **kwargs):
    """
    Запрашивает общую цифру для начисления баллов (2-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    response = bot.reply_to(
                        message,
                        "Введите общую цифру для начисления баллов:"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_2_pot_quiz,
                        uid=uid,
                        tour=tour,
                        question_number=question_number,
                        participant=participant,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_2_pot_quiz(message, **kwargs):
    """
    Делим цифру на 50 и начисляем баллы. Фиксируем баллы в таблице PointsTransaction (2-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant = kwargs.get('participant')
    digit = message.text

    if digit == "Главное меню":
        main_menu(message)

    elif digit == "Выход":
        logout(message)

    else:
        if digit.isdigit():
            if int(digit) > 0:
                points = int(digit) / 50
                transferor = Authorization.objects.get(
                    telegram_id=uid
                )

                question = Question.objects.get(
                    tour_id=int(tour),
                    tour_question_number_id=int(question_number)
                )

                if question:
                    participant_row = PointsTransaction.objects.filter(
                        sender_telegram_id=participant.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        question_id=question.id,
                    )

                    if not participant_row.exists():
                        PointsTransaction.objects.create(
                            sender_telegram_id=participant.telegram_id,
                            transferor_telegram_id=transferor.telegram_id,
                            question_id=question.id,
                            points_received_or_transferred=points,
                        )

                        update_quiz_points(
                            telegram_id=participant.telegram_id,
                        )

                    else:
                        participant_row.update(
                            points_received_or_transferred=points,
                            points_datetime=timezone.now(),
                        )

                        update_quiz_points(
                            telegram_id=participant.telegram_id,
                        )

                    bot.reply_to(
                        message,
                        f"Участник {participant.full_name} получил {int(points)} баллов"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод общей цифры (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод общей цифры (нужно именно число)"
            )


def process_points_type_3_bonuses_quiz(message, **kwargs):
    """
    Запрашивает размер бонуса для начисления баллов (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    response = bot.reply_to(
                        message,
                        f"Введите размер бонуса (если хотите автоматом задать рандомное число введите 'random'):"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_3_random_quiz,
                        uid=uid,
                        tour=tour,
                        question_number=question_number,
                        participant=participant
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_3_random_quiz(message, **kwargs):
    """
    Запрашивает диапазон для рандомного бонуса, если пользователь ввел 'random' (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant = kwargs.get('participant')
    bonuses = message.text

    if bonuses == "Главное меню":
        main_menu(message)

    elif bonuses == "Выход":
        logout(message)

    else:
        if bonuses.isdigit():
            if int(bonuses) > 0:
                bonuses = int(bonuses)

                process_points_type_3_result_quiz(
                    message,
                    uid=uid,
                    tour=tour,
                    question_number=question_number,
                    participant=participant,
                    bonuses=bonuses
                )

            else:
                bot.reply_to(
                    message,
                    "Размер бонуса должен быть больше нуля"
                )

        else:
            if bonuses == 'random':
                response = bot.reply_to(
                    message,
                    'Введите минимальный и максимальный возможный размер бонуса через запятую (пример - 1, 100):'
                )

                bot.register_next_step_handler(
                    response,
                    process_points_type_3_result_quiz,
                    uid=uid,
                    tour=tour,
                    question_number=question_number,
                    participant=participant,
                    bonuses=None
                )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод размера бонуса"
                )


def process_points_type_3_result_quiz(message, **kwargs):
    """
    Заносит бонусы в таблицу PointsTransaction (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    participant = kwargs.get('participant')
    bonuses = kwargs.get('bonuses')

    if bonuses is None:
        random_bonuses = message.text

        if random_bonuses == "Главное меню":
            main_menu(message)

        elif random_bonuses == "Выход":
            logout(message)

        else:
            random_bonuses = random_bonuses.replace(' ', '').split(',')
            a = random_bonuses[0]
            b = random_bonuses[1]

            if a.isdigit() and b.isdigit():
                a = int(a)
                b = int(b)

                if a > 0 and b > 0:
                    if b > a:
                        bonuses = random.randint(a=a, b=b)

                    else:
                        bot.reply_to(
                            message,
                            "Диапазон бонуса должен быть указан от меньшего к большему в формате 'a, b'"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Принимаются только положительные числа"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод диапазона бонуса"
                )

    if bonuses:
        transferor = Authorization.objects.get(
            telegram_id=uid
        )

        question = Question.objects.get(
            tour_id=int(tour),
            tour_question_number_id=int(question_number)
        )

        if question and transferor:
            participant_row = PointsTransaction.objects.filter(
                sender_telegram_id=participant.telegram_id,
                transferor_telegram_id=transferor.telegram_id,
                question_id=question.id
            )

            if not participant_row.exists():
                PointsTransaction.objects.create(
                    sender_telegram_id=participant.telegram_id,
                    transferor_telegram_id=transferor.telegram_id,
                    question_id=question.id,
                    bonuses=bonuses
                )

                update_quiz_points(
                    telegram_id=participant.telegram_id,
                )

            else:
                participant_row.update(
                    bonuses=bonuses,
                    points_datetime=timezone.now(),
                )

                update_quiz_points(
                    telegram_id=participant.telegram_id,
                )

            bot.reply_to(
                message,
                f"Баллы начислены участнику {participant.full_name} в размере {bonuses} баллов/балла"
            )


def process_points_type_4_receiver_quiz(message, **kwargs):
    """
    Запрашивает ID участника, которому начисляем баллы (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    sender_id = message.text

    if sender_id == "Главное меню":
        main_menu(message)

    elif sender_id == "Выход":
        logout(message)

    else:
        if sender_id.isdigit():
            if int(sender_id) > 0:
                sender = Authorization.objects.get(
                    id=sender_id
                )

                if sender:
                    response_receiver = bot.reply_to(
                        message,
                        f"Выберите участника, которому начисляем баллы по его ID в БД:"
                    )

                    bot.register_next_step_handler(
                        response_receiver,
                        process_points_type_4_amount_quiz,
                        tour=tour,
                        question_number=question_number,
                        uid=uid,
                        sender=sender,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_4_amount_quiz(message, **kwargs):
    """
    Запрашивает количество начисляемых баллов (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    sender = kwargs.get('sender')
    receiver_id = message.text

    if receiver_id == "Главное меню":
        main_menu(message)

    elif receiver_id == "Выход":
        logout(message)

    else:
        receiver = Authorization.objects.get(
            id=receiver_id
        )

        if int(receiver.telegram_id) != int(sender.telegram_id):
            if receiver:
                if receiver.role_id == 3:
                    response = bot.reply_to(
                        message,
                        f"Введите количество начисляемых баллов:"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_4_result_quiz,
                        tour=tour,
                        question_number=question_number,
                        uid=uid,
                        sender=sender,
                        receiver=receiver,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Я принимаю только участников"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ID участника"
                )

        else:
            bot.reply_to(
                message,
                "Нельзя переводить баллы самому себе"
            )


def process_points_type_4_result_quiz(message, **kwargs):
    """
    Фиксирует факт перевода баллов в таблицу PointsTransaction (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tour = kwargs.get('tour')
    question_number = kwargs.get('question_number')
    sender = kwargs.get('sender')
    receiver = kwargs.get('receiver')
    amount = message.text

    if amount == "Главное меню":
        main_menu(message)

    elif amount == "Выход":
        logout(message)

    else:
        if amount.isdigit():
            amount = int(amount)
            if amount > 0:
                transferor = Authorization.objects.get(
                    telegram_id=uid
                )

                question = Question.objects.get(
                    tour_id=int(tour),
                    tour_question_number_id=int(question_number)
                )

                if question:
                    transaction_row11 = PointsTransaction.objects.filter(
                        sender_telegram_id=sender.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        question_id=question.id,
                    )

                    transaction_row12 = PointsTransaction.objects.filter(
                        sender_telegram_id=sender.telegram_id,
                        receiver_telegram_id=receiver.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        question_id=question.id,
                    )

                    if not transaction_row11.exists():
                        PointsTransaction.objects.create(
                            transfer_datetime=timezone.now(),
                            sender_telegram=sender.telegram_id,
                            receiver_telegram=receiver.telegram_id,
                            points_transferred=amount,
                            transferor_telegram=transferor.telegram_id,
                            question_id=question.id,
                        )

                        update_quiz_points(
                            telegram_id=sender.telegram_id,
                        )

                        update_quiz_points(
                            telegram_id=receiver.telegram_id,
                        )

                    else:
                        if not transaction_row12.exists():
                            transaction_row11.update(
                                receiver_telegram_id=receiver.telegram_id,
                            )

                        transaction_row12.update(
                            points_transferred=amount,
                            transfer_datetime=timezone.now(),
                            points_datetime=timezone.now(),
                        )

                        update_quiz_points(
                            telegram_id=sender.telegram_id,
                        )

                        update_quiz_points(
                            telegram_id=receiver.telegram_id,
                        )

                    bot.reply_to(
                        message,
                        f"Баллы начислены участнику {receiver.full_name} в размере {amount} баллов/балла"
                    )

            else:
                bot.reply_to(
                    message,
                    "Количество начисляемых баллов должно быть больше 0"
                )

        else:
            bot.reply_to(
                message,
                "Количество начисляемых баллов должно быть числом"
            )


@bot.message_handler(func=lambda message: 'Добавить очки за турнир' in message.text or message.text == '/add_tournam_points')
def add_points_check(message):
    """
    Проверяет, является ли пользователь директором. Если директор, то запрашивает тип начисления баллов участнику
    """
    is_AttributeError = False
    uid = message.from_user.id

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        username_id = user_auth_data.first().id
        custom_user = CustomUser.objects.get(
            username_id=username_id
        )

    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            user_auth_data = user_auth_data.first()

            if user_auth_data.role_id == 2:
                markup = types.ReplyKeyboardMarkup(
                    resize_keyboard=True
                )

                btn_main_menu = types.KeyboardButton(
                    text='Главное меню'
                )

                btn_logout = types.KeyboardButton(
                    text='Выход'
                )

                markup.add(
                    btn_main_menu,
                    btn_logout
                )

                text = '\n'.join([
                    'Введдите тип начисления баллов в виде числа:',
                    '1 - порядковый номер занятого места с шагом 5 баллов',
                    '2 - РОТ (ПОТ) [указываем общую цифру, делим на /50 и зачисляем полученные баллы]',
                    '3 - произвольная цифра (бонусы)',
                    '4 - перевод баллов между участниками'
                ])

                response = bot.reply_to(
                    message,
                    text,
                    reply_markup=markup,
                )

                bot.register_next_step_handler(
                    response,
                    process_add_tournament,
                    uid=uid
                )

            else:
                bot.reply_to(
                    message,
                    "Вы не являетесь директором. Вы не можете начислять баллы"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


def process_add_tournament(message, **kwargs):
    """"
    Запрашивает у директора номер тура
    """
    uid = kwargs.get('uid')
    points_type = message.text

    if points_type == "Главное меню":
        main_menu(message)

    elif points_type == "Выход":
        logout(message)

    else:
        reply = bot.reply_to(
            message,
            "Введите номер турнира:"
        )

        bot.register_next_step_handler(
            reply,
            process_add_points_type,
            uid=uid,
            points_type=points_type
        )


def process_add_points_type(message, **kwargs):
    """"
    Проверяет корректность введенного типа начисления баллов и в зависимости от него запрашивает у директора информацию
    """
    add_points_type = kwargs.get('points_type')
    uid = kwargs.get('uid')
    tournament_number = message.text

    if tournament_number == "Главное меню":
        main_menu(message)

    elif tournament_number == "Выход":
        logout(message)

    else:
        if tournament_number.isdigit():
            if int(tournament_number) > 0:
                if add_points_type in ('1', '2', '3', '4'):
                    participants = Authorization.objects.all().filter(
                        role=3
                    )

                    participants_list = []
                    if participants:
                        for participant in participants:
                            part_id = participant.id
                            part_name = participant.full_name
                            part_nick = participant.telegram_nickname
                            part_tel_id = participant.telegram_id

                            participants_list.append(
                                f"{part_id}: {part_name}" + f" (Telegram: {part_nick}, {part_tel_id})"
                            )

                        total_participants = len(participants_list)
                        participants_list = "\n".join(participants_list)

                        bot.reply_to(
                            message,
                            f"Список участников: \n{participants_list}"
                        )

                        if len(participants_list) >= 1:
                            if add_points_type == '1':
                                response = bot.reply_to(
                                    message,
                                    f"Выберите по ID участника, которому будем ставить место в рейтинге:"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_1_place,
                                    tournament_number=tournament_number,
                                    uid=uid,
                                    total_participants=total_participants,
                                )

                            elif add_points_type == '2':
                                response = bot.reply_to(
                                    message,
                                    "Выберите по ID участника, которому назначаем баллы"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_2_digit,
                                    tournament_number=tournament_number,
                                    uid=uid,
                                )

                            elif add_points_type == '3':
                                response = bot.reply_to(
                                    message,
                                    f"Выберите по ID участника, которому назначаем баллы:"
                                )

                                bot.register_next_step_handler(
                                    response,
                                    process_points_type_3_bonuses,
                                    tournament_number=tournament_number,
                                    uid=uid,
                                )

                            elif add_points_type == '4':
                                if len(participants_list) >= 2:
                                    response = bot.reply_to(
                                        message,
                                        f"Выберите участника, у которого забираем баллы по его ID в БД:"
                                    )

                                    bot.register_next_step_handler(
                                        response,
                                        process_points_type_4_receiver,
                                        tournament_number=tournament_number,
                                        uid=uid,
                                    )

                                else:
                                    bot.reply_to(
                                        message,
                                        "Недостаточное количество участников для начисления баллов"
                                    )

                    else:
                        bot.reply_to(
                            message,
                            "У вас отсутствуют участники"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Некорректный тип начисления баллов. Пожалуйста, выберите один из предложенных вариантов"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод номера вопроса (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод номера вопроса (должно быть число)"
            )


def process_points_type_1_place(message, **kwargs):
    """
    Запрашивает у директора место в рейтинге, за которое он будем начислять баллы (1-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    total_participants = kwargs.get('total_participants')
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    text1 = 'Введите номер места в рейтинге для следующего участника:'
                    text2 = 'На текущий момент можно ввести место в диапазоне от 1 до'
                    part_name = participant.full_name
                    part_nick = participant.telegram_nickname
                    part_tel_id = participant.telegram_id

                    response = bot.reply_to(
                        message,
                        f"{text1} {part_name} (Telegram: {part_nick}, {part_tel_id}). {text2} {total_participants}"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_1_place_points,
                        uid=uid,
                        tournament_number=tournament_number,
                        participant=participant,
                        total_participants=total_participants
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_1_place_points(message, **kwargs):
    """
    Добавляет баллы участнику и заносит их в таблицу PointsTournament (1-й тип начисления баллов)
    """
    def create_points_dict(points=100, step=5, max_place=30):
        """
        Создает словарь баллов в зависимости от места
        """
        points_dict = {}
        for place in range(1, max_place + 1):
            points_dict[place] = points
            points -= step
            if points < step:
                points = step
        return points_dict

    def calculate_points(points_dict, place):
        """
        Выводит баллы в зависимости от конкретно занятого места
        """
        return points_dict.get(place, 0)

    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    participant = kwargs.get('participant')
    total_participants = kwargs.get('total_participants')
    place = message.text

    if place == "Главное меню":
        main_menu(message)

    elif place == "Выход":
        logout(message)

    else:
        if place.isdigit():
            if int(place) > 0:
                if int(place) <= total_participants:
                    if total_participants <= 30:
                        points_dict = create_points_dict()
                    else:
                        points_dict = create_points_dict(
                            max_place=total_participants
                        )

                    points = calculate_points(
                        points_dict,
                        int(place)
                    )

                    transferor = Authorization.objects.get(
                        telegram_id=uid
                    )

                    tournament = Tournament.objects.get(
                        id=int(tournament_number)
                    )

                    if tournament:
                        participant_row = PointsTournament.objects.filter(
                            sender_telegram_id=participant.telegram_id,
                            transferor_telegram_id=transferor.telegram_id,
                            tournament_id=tournament.id,
                        )

                        if not participant_row.exists():
                            PointsTournament.objects.create(
                                sender_telegram_id=participant.telegram_id,
                                transferor_telegram_id=transferor.telegram_id,
                                tournament_id=tournament.id,
                                tournament_points=points,
                            )

                            update_tournament_points(
                                telegram_id=participant.telegram_id,
                            )

                        else:
                            participant_row.update(
                                tournament_points=points,
                                points_datetime=timezone.now(),
                            )

                            update_tournament_points(
                                telegram_id=participant.telegram_id,
                            )

                        bot.reply_to(
                            message,
                            f"Участник {participant.full_name} получил {points} баллов за {place} место в рейтине"
                        )

                    else:
                        bot.reply_to(
                            message,
                            "Пара 'тур-вопрос' не существует в БД"
                        )

                else:
                    bot.reply_to(
                        message,
                        f"Место в рейтинге должно быть в диапазоне от 1 до {total_participants}"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод места в рейтинге (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод места в рейтинге (число должно быть числом)"
            )


def process_points_type_2_digit(message, **kwargs):
    """
    Запрашивает общую цифру для начисления баллов (2-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    response = bot.reply_to(
                        message,
                        "Введите общую цифру для начисления баллов:"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_2_pot,
                        uid=uid,
                        tournament_number=tournament_number,
                        participant=participant,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_2_pot(message, **kwargs):
    """
    Делим цифру на 50 и начисляем баллы. Фиксируем баллы в таблице PointsTournament (2-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    participant = kwargs.get('participant')
    digit = message.text

    if digit == "Главное меню":
        main_menu(message)

    elif digit == "Выход":
        logout(message)

    else:
        if digit.isdigit():
            if int(digit) > 0:
                points = int(digit) / 50
                transferor = Authorization.objects.get(
                    telegram_id=uid
                )

                tournament = Tournament.objects.get(
                    id=int(tournament_number)
                )

                if tournament:
                    participant_row = PointsTournament.objects.filter(
                        sender_telegram_id=participant.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        tournament_id=tournament.id,
                    )

                    if not participant_row.exists():
                        PointsTournament.objects.create(
                            sender_telegram_id=participant.telegram_id,
                            transferor_telegram_id=transferor.telegram_id,
                            tournament_id=tournament.id,
                            points_received_or_transferred=points,
                        )

                        update_tournament_points(
                            telegram_id=participant.telegram_id,
                        )

                    else:
                        participant_row.update(
                            points_received_or_transferred=points,
                            points_datetime=timezone.now(),
                        )

                        update_tournament_points(
                            telegram_id=participant.telegram_id,
                        )

                    bot.reply_to(
                        message,
                        f"Участник {participant.full_name} получил {int(points)} баллов"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод общей цифры (число должно быть больше нуля)"
                )

        else:
            bot.reply_to(
                message,
                "Некорректный ввод общей цифры (нужно именно число)"
            )


def process_points_type_3_bonuses(message, **kwargs):
    """
    Запрашивает размер бонуса для начисления баллов (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number'),
    participant_id = message.text

    if participant_id == "Главное меню":
        main_menu(message)

    elif participant_id == "Выход":
        logout(message)

    else:
        if participant_id.isdigit():
            if int(participant_id) > 0:
                participant = Authorization.objects.get(
                    id=participant_id
                )

                if participant:
                    response = bot.reply_to(
                        message,
                        f"Введите размер бонуса (если хотите автоматом задать рандомное число введите 'random'):"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_3_random,
                        uid=uid,
                        tournament_number=tournament_number,
                        participant=participant
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_3_random(message, **kwargs):
    """
    Запрашивает диапазон для рандомного бонуса, если пользователь ввел 'random' (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    participant = kwargs.get('participant')
    bonuses = message.text

    if bonuses == "Главное меню":
        main_menu(message)

    elif bonuses == "Выход":
        logout(message)

    else:
        if bonuses.isdigit():
            if int(bonuses) > 0:
                bonuses = int(bonuses)

                process_points_type_3_result(
                    message,
                    uid=uid,
                    tournament_number=tournament_number,
                    participant=participant,
                    bonuses=bonuses
                )

            else:
                bot.reply_to(
                    message,
                    "Размер бонуса должен быть больше нуля"
                )

        else:
            if bonuses == 'random':
                response = bot.reply_to(
                    message,
                    'Введите минимальный и максимальный возможный размер бонуса через запятую (пример - 1, 100):'
                )

                bot.register_next_step_handler(
                    response,
                    process_points_type_3_result,
                    uid=uid,
                    tournament_number=tournament_number,
                    participant=participant,
                    bonuses=None
                )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод размера бонуса"
                )


def process_points_type_3_result(message, **kwargs):
    """
    Заносит бонусы в таблицу PointsTournament (3-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    participant = kwargs.get('participant')
    bonuses = kwargs.get('bonuses')

    if bonuses is None:
        random_bonuses = message.text

        if random_bonuses == "Главное меню":
            main_menu(message)

        elif random_bonuses == "Выход":
            logout(message)

        else:
            random_bonuses = random_bonuses.replace(' ', '').split(',')
            a = random_bonuses[0]
            b = random_bonuses[1]

            if a.isdigit() and b.isdigit():
                a = int(a)
                b = int(b)

                if a > 0 and b > 0:
                    if b > a:
                        bonuses = random.randint(a=a, b=b)

                    else:
                        bot.reply_to(
                            message,
                            "Диапазон бонуса должен быть указан от меньшего к большему в формате 'a, b'"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Принимаются только положительные числа"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ввод диапазона бонуса"
                )

    if bonuses and tournament_number:
        transferor = Authorization.objects.get(
            telegram_id=uid
        )

        tournament = Tournament.objects.get(
            id=int(tournament_number[0])
        )

        if tournament and transferor:
            participant_row = PointsTournament.objects.filter(
                sender_telegram_id=participant.telegram_id,
                transferor_telegram_id=transferor.telegram_id,
                tournament_id=tournament.id
            )

            if not participant_row:
                PointsTournament.objects.create(
                    sender_telegram_id=participant.telegram_id,
                    transferor_telegram_id=transferor.telegram_id,
                    tournament_id=tournament.id,
                    bonuses=bonuses
                )

                update_tournament_points(
                    telegram_id=participant.telegram_id,
                )

            else:
                participant_row.update(
                    bonuses=bonuses,
                    points_datetime=timezone.now(),
                )

                update_tournament_points(
                    telegram_id=participant.telegram_id,
                )

            bot.reply_to(
                message,
                f"Баллы начислены участнику {participant.full_name} в размере {bonuses} баллов/балла"
            )


def process_points_type_4_receiver(message, **kwargs):
    """
    Запрашивает ID участника, которому начисляем баллы (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    sender_id = message.text

    if sender_id == "Главное меню":
        main_menu(message)

    elif sender_id == "Выход":
        logout(message)

    else:
        if sender_id.isdigit():
            if int(sender_id) > 0:
                sender = Authorization.objects.get(
                    id=sender_id
                )

                if sender:
                    response_receiver = bot.reply_to(
                        message,
                        f"Выберите участника, которому начисляем баллы по его ID в БД:"
                    )

                    bot.register_next_step_handler(
                        response_receiver,
                        process_points_type_4_amount,
                        tournament_number=tournament_number,
                        uid=uid,
                        sender=sender,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Участника не существует в БД"
                    )

            else:
                bot.reply_to(
                    message,
                    "ID должен быть больше нуля"
                )

        else:
            bot.reply_to(
                message,
                "ID должно быть числом"
            )


def process_points_type_4_amount(message, **kwargs):
    """
    Запрашивает количество начисляемых баллов (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    sender = kwargs.get('sender')
    receiver_id = message.text

    if receiver_id == "Главное меню":
        main_menu(message)

    elif receiver_id == "Выход":
        logout(message)

    else:
        receiver = Authorization.objects.get(
            id=receiver_id
        )

        if int(receiver.telegram_id) != int(sender.telegram_id):
            if receiver:
                if receiver.role_id == 3:
                    response = bot.reply_to(
                        message,
                        f"Введите количество начисляемых баллов:"
                    )

                    bot.register_next_step_handler(
                        response,
                        process_points_type_4_result,
                        tournament_number=tournament_number,
                        uid=uid,
                        sender=sender,
                        receiver=receiver,
                    )

                else:
                    bot.reply_to(
                        message,
                        "Я принимаю только участников"
                    )

            else:
                bot.reply_to(
                    message,
                    "Некорректный ID участника"
                )

        else:
            bot.reply_to(
                message,
                "Нельзя переводить баллы самому себе"
            )


def process_points_type_4_result(message, **kwargs):
    """
    Фиксирует факт перевода баллов в таблицу PointsTournament (4-й тип начисления баллов)
    """
    uid = kwargs.get('uid')
    tournament_number = kwargs.get('tournament_number')
    sender = kwargs.get('sender')
    receiver = kwargs.get('receiver')
    amount = message.text

    if amount == "Главное меню":
        main_menu(message)

    elif amount == "Выход":
        logout(message)

    else:
        if amount.isdigit():
            amount = int(amount)
            if amount > 0:
                transferor = Authorization.objects.get(
                    telegram_id=uid
                )

                tournament = Tournament.objects.get(
                    id=int(tournament_number)
                )

                if tournament:
                    transaction_row11 = PointsTournament.objects.filter(
                        sender_telegram_id=sender.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        tournament_id=tournament.id,
                    )

                    transaction_row12 = PointsTournament.objects.filter(
                        sender_telegram_id=sender.telegram_id,
                        receiver_telegram_id=receiver.telegram_id,
                        transferor_telegram_id=transferor.telegram_id,
                        tournament_id=tournament.id,
                    )

                    if not transaction_row11.exists():
                        PointsTournament.objects.create(
                            transfer_datetime=timezone.now(),
                            sender_telegram=sender.telegram_id,
                            receiver_telegram=receiver.telegram_id,
                            points_transferred=amount,
                            transferor_telegram=transferor.telegram_id,
                            tournament_id=tournament.id,
                        )

                        update_tournament_points(
                            telegram_id=sender.telegram_id,
                        )

                        update_tournament_points(
                            telegram_id=receiver.telegram_id,
                        )

                    else:
                        if not transaction_row12.exists():
                            transaction_row11.update(
                                receiver_telegram_id=receiver.telegram_id,
                            )

                        transaction_row12.update(
                            points_transferred=amount,
                            transfer_datetime=timezone.now(),
                            points_datetime=timezone.now(),
                        )

                        update_tournament_points(
                            telegram_id=sender.telegram_id,
                        )

                        update_tournament_points(
                            telegram_id=receiver.telegram_id,
                        )

                    bot.reply_to(
                        message,
                        f"Баллы начислены участнику {receiver.full_name} в размере {amount} баллов/балла"
                    )

            else:
                bot.reply_to(
                    message,
                    "Количество начисляемых баллов должно быть больше 0"
                )

        else:
            bot.reply_to(
                message,
                "Количество начисляемых баллов должно быть числом"
            )


def tournament_rating(message, tour_number=None, my_telegram_id=None, sort_param="total_points"):
    """
    В целом отвечает за рейтинг участников в рамках викторины
    tour_number - номер тура
    my_telegram_id - Telegram ID участника
    sort_param - параметр сортировки рейтинга (по умолчанию total_points, отражающее суммарное количество баллов)
       * sort_param='total_points' - сортировка по суммарному количеству баллов
       * sort_param='total_right_answers' - сортировка по количеству правильных ответов

    Итоговое количество баллов рассчитывается относительно sender_telegram_id из таблицы PointsTransaction
    ИТОГ = total_tournament_points + total_rot_pot + total_bonuses + total_transfer_profit
        * total_tournament_points - общее количество баллов, начисленных участнику по занятому месту (тип 1)
        * total_rot_pot - общее количество баллов, начисленных участнику по принципу "РОТ/ПОТ" (тип 2)
        * total_bonuses - общее количество баллов, начисленных участнику в виде бонусов (тип 3)
        * total_transfer_profit - общий выигрыш участника, полученный в результате перевода баллов (тип 4)
            * total_transfer_profit = total_transfer_income - total_transfer_loss
            * total_transfer_income - общее количество баллов, начисленных участнику в результате перевода баллов
            * total_transfer_loss - общее количество баллов, списанных у участника в результате перевода баллов
    """
    telegram_ids = []
    participants = Authorization.objects.filter(role_id=3)

    if participants.exists():
        if participants.count() >= 1:
            for participant in participants:
                telegram_ids.append(
                    participant.telegram_id
                )

    if telegram_ids:
        participants_dict = {}
        senders = None
        question_ids = []
        tour_error = True

        if tour_number:
            if str(tour_number).isdigit():
                if int(tour_number) > 0:
                    questions = Question.objects.filter(
                        tour_id=int(tour_number)
                    )

                    if questions.exists():
                        tour_error = False

                        question_ids = [
                            question.id for question in questions
                        ]

                        senders = PointsTransaction.objects.filter(
                            sender_telegram_id__in=telegram_ids,
                            question_id__in=question_ids
                        )

                    else:
                        bot.reply_to(
                            message,
                            "Номера тура не существует"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Нужно именно положительное число"
                    )

            else:
                bot.reply_to(
                    message,
                    "Нужен именно номер турнира"
                )

        else:
            senders = PointsTransaction.objects.filter(
                sender_telegram_id__in=telegram_ids
            )

        if senders:
            if senders.count() >= 1:
                for telegram_id in telegram_ids:
                    if question_ids:
                        sender_data = PointsTransaction.objects.filter(
                            sender_telegram_id=telegram_id,
                            question_id__in=question_ids
                        )

                    else:
                        sender_data = PointsTransaction.objects.filter(
                            sender_telegram_id=telegram_id
                        )

                    total_tournament_points = 0
                    total_bonuses = 0
                    total_rot_pot = 0
                    total_transfer_loss = 0
                    total_right_answers = 0
                    question_count = 0
                    tours_list = []

                    if sender_data.exists():
                        for item in sender_data:
                            total_tournament_points += item.tournament_points if item.tournament_points else 0
                            total_bonuses += item.bonuses if item.bonuses else 0
                            total_rot_pot += item.points_received_or_transferred if item.points_received_or_transferred else 0
                            total_transfer_loss += item.points_transferred if item.points_transferred else 0
                            total_right_answers += item.is_answered if item.is_answered else 0
                            question_count += item.is_done if item.is_done else 0

                            question_data = Question.objects.filter(
                                id=item.question_id
                            )

                            if question_data.exists():
                                question_data = question_data.first()

                                tours_list.append(
                                    question_data.tour_id
                                )

                        participants_dict[telegram_id] = {
                            'total_tournament_points': total_tournament_points,
                            'total_bonuses': total_bonuses,
                            'total_rot_pot': total_rot_pot,
                            'total_transfer_loss': total_transfer_loss,
                            'total_right_answers': total_right_answers,
                            'question_count': question_count,
                            'tour_count': len(set(tours_list)) if tours_list else 0,
                        }

        if question_ids:
            receivers = PointsTransaction.objects.filter(
                receiver_telegram_id__in=telegram_ids,
                question_id__in=question_ids
            )

        else:
            receivers = PointsTransaction.objects.filter(
                receiver_telegram_id__in=telegram_ids
            )

        if receivers:
            if receivers.count() >= 1:
                for telegram_id in telegram_ids:
                    if question_ids:
                        receiver_data = PointsTransaction.objects.filter(
                            receiver_telegram_id=telegram_id,
                            question_id__in=question_ids
                        )

                    else:
                        receiver_data = PointsTransaction.objects.filter(
                            receiver_telegram_id=telegram_id
                        )

                    total_transfer_income = 0

                    for item in receiver_data:
                        total_transfer_income += item.points_transferred if item.points_transferred else 0

                    if telegram_id in participants_dict:
                        participants_dict[telegram_id]['total_transfer_income'] = total_transfer_income

                    else:
                        participants_dict[telegram_id] = {
                            'total_transfer_income': total_transfer_income,
                        }

        if participants_dict:
            for _, telegram_id_dict in participants_dict.items():
                telegram_id_dict['total_transfer_profit'] = telegram_id_dict.get('total_transfer_income', 0) - \
                                                            telegram_id_dict.get('total_transfer_loss', 0)

                telegram_id_dict['total_points'] = telegram_id_dict.get('total_tournament_points', 0) + \
                                                   telegram_id_dict.get('total_bonuses', 0) + \
                                                   telegram_id_dict.get('total_rot_pot', 0) + \
                                                   telegram_id_dict.get('total_transfer_profit', 0)

            sorted_data = dict(
                sorted(
                    participants_dict.items(), key=lambda x: x[1][sort_param],
                    reverse=True
                )
            )

            ranked_data = {
                key: {**value, 'rank': i + 1} for i, (key, value) in enumerate(sorted_data.items())
            }

            data_list = []
            if ranked_data:
                for telegram_id, rank_data in ranked_data.items():
                    participant = participants.get(
                        telegram_id=telegram_id
                    )

                    data_list.append([
                        rank_data.get('rank', 0),
                        participant.full_name,
                        participant.telegram_nickname,
                        participant.telegram_id,
                        rank_data.get('total_points', 0),
                        rank_data.get('total_tournament_points', 0),
                        rank_data.get('total_rot_pot', 0),
                        rank_data.get('total_bonuses', 0),
                        rank_data.get('total_transfer_profit', 0),
                        rank_data.get('total_transfer_income', 0),
                        rank_data.get('total_transfer_loss', 0),
                        rank_data.get('total_right_answers', 0),
                        rank_data.get('question_count', 0),
                        rank_data.get('tour_count', 0),
                    ])

            if data_list:
                result_list = [[
                    'Место',
                    'ФИО',
                    'Никнейм в Telegram',
                    'Telegram ID',
                    'Общее количество баллов',
                    'Баллы, начисленные по типу 1 (рейтинг)',
                    'Баллы, начисленные по типу 2 (РОТ/ПОТ)',
                    'Баллы, начисленные по типу 3 (бонусы)',
                    'Баллы, начисленные по типу 4 (прибыль от трансфера)',
                    'Суммарный доход от трансфера',
                    'Суммарный убыток от трансфера',
                    'Количество правильных ответов',
                    'Количество вопросов',
                    'Количество туров',
                ]] + data_list

                wb = Workbook()
                ws = wb.active

                for idx, row in enumerate(result_list):
                    if not my_telegram_id:
                        ws.append(
                            row
                        )

                    else:
                        if my_telegram_id == row[3] or idx == 0:
                            ws.append(
                                row
                            )

                if my_telegram_id or question_ids:
                    if not len(data_list) >= 1:
                        bot.reply_to(
                            message,
                            "Нет результатов"
                        )

                wb.save("results.xlsx")

                if not tour_number:
                    if not my_telegram_id:
                        bot.send_document(
                            message.chat.id,
                            document=open('results.xlsx', 'rb'),
                            caption='Рейтинг участников турнира'
                        )

                        message_text = 'Список участников в рейтинге:\n\n'
                        for participant in data_list:

                            text_info = '\n'.join([
                                f'Место: {participant[0]}',
                                f'ФИО: {participant[1]}',
                                f'Никнейм в Telegram: {participant[2]}',
                                f'Telegram ID: {participant[3]}',
                                f'Общее количество баллов: {participant[4]}',
                                f'Баллы, начисленные по рейтингу: {participant[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant[6]}',
                                f'Баллы, начисленные по бонусам: {participant[7]}',
                                f'Прибыль от трансфера баллов: {participant[8]}',
                                f'Суммарный доход от трансфера: {participant[9]}',
                                f'Суммарный убыток от трансфера: {participant[10]}',
                                f'Количество правильных ответов: {participant[11]}',
                                f'Количество вопросов: {participant[12]}',
                                f'Количество туров: {participant[13]}\n\n',
                            ])

                            message_text += text_info

                        bot.reply_to(
                            message,
                            message_text
                        )

                    else:
                        try:
                            idx = list(ranked_data.keys()).index(my_telegram_id)
                            participant_data = result_list[idx + 1]
                            full_name = participant_data[1]
                            telegram_id = participant_data[3]

                            bot.send_document(
                                message.chat.id,
                                document=open('results.xlsx', 'rb'),
                                caption=f'Рейтинг участника ({full_name}, {telegram_id})'
                            )

                            message_text = 'Положение участника в рейтинге:\n\n'

                            text_info = '\n'.join([
                                f'Место: {participant_data[0]}',
                                f'ФИО: {participant_data[1]}',
                                f'Никнейм в Telegram: {participant_data[2]}',
                                f'Telegram ID: {participant_data[3]}',
                                f'Общее количество баллов: {participant_data[4]}',
                                f'Баллы, начисленные по рейтингу: {participant_data[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant_data[6]}',
                                f'Баллы, начисленные по бонусам: {participant_data[7]}',
                                f'Прибыль от трансфера баллов: {participant_data[8]}',
                                f'Суммарный доход от трансфера: {participant_data[9]}',
                                f'Суммарный убыток от трансфера: {participant_data[10]}',
                                f'Количество правильных ответов: {participant_data[11]}',
                                f'Количество вопросов: {participant_data[12]}',
                                f'Количество туров: {participant_data[13]}\n\n',
                            ])

                            bot.reply_to(
                                message,
                                message_text + text_info
                            )

                        except ValueError:
                            bot.reply_to(
                                message,
                                'Не удалось найти ваш результат в рейтинге'
                            )

                else:
                    if not tour_error:
                        bot.send_document(
                            message.chat.id,
                            document=open('results.xlsx', 'rb'),
                            caption='Рейтинг участников тура №' + str(tour_number)
                        )

                        message_text = f'Список участников в рейтинге по туру № {tour_number}:\n\n'
                        for participant in data_list:

                            text_info = '\n'.join([
                                f'Место: {participant[0]}',
                                f'ФИО: {participant[1]}',
                                f'Никнейм в Telegram: {participant[2]}',
                                f'Telegram ID: {participant[3]}',
                                f'Общее количество баллов: {participant[4]}',
                                f'Баллы, начисленные по рейтингу: {participant[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant[6]}',
                                f'Баллы, начисленные по бонусам: {participant[7]}',
                                f'Прибыль от трансфера баллов: {participant[8]}',
                                f'Суммарный доход от трансфера: {participant[9]}',
                                f'Суммарный убыток от трансфера: {participant[10]}',
                                f'Количество правильных ответов: {participant[11]}',
                                f'Количество вопросов: {participant[12]}',
                                f'Количество туров: {participant[13]}\n\n',
                            ])

                            message_text += text_info

                        bot.reply_to(
                            message,
                            message_text
                        )

    else:
        bot.reply_to(
            message,
            "Нет участников в турнире"
        )


def points_tournament_rating(message, tour_number=None, my_telegram_id=None):
    """
    В целом отвечает за рейтинг участников в разрезе турнира
    tour_number - номер турнира
    my_telegram_id - Telegram ID участника

    Итоговое количество баллов рассчитывается относительно sender_telegram_id из таблицы PointsTransaction
    ИТОГ = total_tournament_points + total_rot_pot + total_bonuses + total_transfer_profit
        * total_tournament_points - общее количество баллов, начисленных участнику по занятому месту (тип 1)
        * total_rot_pot - общее количество баллов, начисленных участнику по принципу "РОТ/ПОТ" (тип 2)
        * total_bonuses - общее количество баллов, начисленных участнику в виде бонусов (тип 3)
        * total_transfer_profit - общий выигрыш участника, полученный в результате перевода баллов (тип 4)
            * total_transfer_profit = total_transfer_income - total_transfer_loss
            * total_transfer_income - общее количество баллов, начисленных участнику в результате перевода баллов
            * total_transfer_loss - общее количество баллов, списанных у участника в результате перевода баллов
    """
    participants = Authorization.objects.filter(
        role_id=3
    )

    telegram_ids = []
    if participants.exists():
        if participants.count() >= 1:
            for participant in participants:
                telegram_ids.append(
                    participant.telegram_id
                )

    if telegram_ids:
        participants_dict = {}
        senders = None
        tournament_ids = []
        tour_error = True

        if tour_number:
            if str(tour_number).isdigit():
                if int(tour_number) > 0:

                    tournament = Tournament.objects.filter(
                        id=int(tour_number)
                    )

                    if tournament.exists():
                        tour_error = False

                        tournament_ids = [
                            tournament_obj.id for tournament_obj in tournament
                        ]

                        senders = PointsTournament.objects.filter(
                            sender_telegram_id__in=telegram_ids,
                            tournament_id__in=tournament_ids
                        )

                    else:
                        bot.reply_to(
                            message,
                            "Номера турнира не существует"
                        )

                else:
                    bot.reply_to(
                        message,
                        "Нужно именно положительное число"
                    )

            else:
                bot.reply_to(
                    message,
                    "Нужен именно номер турнира"
                )

        else:
            senders = PointsTournament.objects.filter(
                sender_telegram_id__in=telegram_ids
            )

        if senders:
            if senders.count() >= 1:
                for telegram_id in telegram_ids:
                    if tournament_ids:
                        sender_data = PointsTournament.objects.filter(
                            sender_telegram_id=telegram_id,
                            tournament_id__in=tournament_ids
                        )

                    else:
                        sender_data = PointsTournament.objects.filter(
                            sender_telegram_id=telegram_id
                        )

                    total_tournament_points = 0
                    total_bonuses = 0
                    total_rot_pot = 0
                    total_transfer_loss = 0
                    tours_list = []

                    if sender_data.exists():
                        for item in sender_data:
                            total_tournament_points += item.tournament_points if item.tournament_points else 0
                            total_bonuses += item.bonuses if item.bonuses else 0
                            total_rot_pot += item.points_received_or_transferred if item.points_received_or_transferred else 0
                            total_transfer_loss += item.points_transferred if item.points_transferred else 0

                            tournament_data = Tournament.objects.filter(
                                id=item.tournament_id
                            )

                            if tournament_data.exists():
                                tournament_data = tournament_data.first()

                                tours_list.append(
                                    tournament_data.id
                                )

                        participants_dict[telegram_id] = {
                            'total_tournament_points': total_tournament_points,
                            'total_bonuses': total_bonuses,
                            'total_rot_pot': total_rot_pot,
                            'total_transfer_loss': total_transfer_loss,
                            'tour_count': len(set(tours_list)) if tours_list else 0,
                        }

        if tournament_ids:
            receivers = PointsTournament.objects.filter(
                receiver_telegram_id__in=telegram_ids,
                tournament_id__in=tournament_ids
            )

        else:
            receivers = PointsTournament.objects.filter(
                receiver_telegram_id__in=telegram_ids
            )

        if receivers:
            if receivers.count() >= 1:
                for telegram_id in telegram_ids:

                    if tournament_ids:
                        receiver_data = PointsTournament.objects.filter(
                            receiver_telegram_id=telegram_id,
                            tournament_id__in=tournament_ids
                        )

                    else:
                        receiver_data = PointsTournament.objects.filter(
                            receiver_telegram_id=telegram_id
                        )

                    total_transfer_income = 0

                    for item in receiver_data:
                        total_transfer_income += item.points_transferred if item.points_transferred else 0

                    if telegram_id in participants_dict:
                        participants_dict[telegram_id]['total_transfer_income'] = total_transfer_income

                    else:
                        participants_dict[telegram_id] = {
                            'total_transfer_income': total_transfer_income,
                        }

        if participants_dict:
            for _, telegram_id_dict in participants_dict.items():
                telegram_id_dict['total_transfer_profit'] = telegram_id_dict.get('total_transfer_income', 0) - \
                                                            telegram_id_dict.get('total_transfer_loss', 0)

                telegram_id_dict['total_points'] = telegram_id_dict.get('total_tournament_points', 0) + \
                                                   telegram_id_dict.get('total_bonuses', 0) + \
                                                   telegram_id_dict.get('total_rot_pot', 0) + \
                                                   telegram_id_dict.get('total_transfer_profit', 0)

            sorted_data = dict(
                sorted(
                    participants_dict.items(), key=lambda x: x[1]['total_points'],
                    reverse=True
                )
            )

            ranked_data = {
                key: {**value, 'rank': i + 1} for i, (key, value) in enumerate(sorted_data.items())
            }

            data_list = []
            if ranked_data:
                for telegram_id, rank_data in ranked_data.items():
                    participant = participants.get(
                        telegram_id=telegram_id
                    )

                    data_list.append([
                        rank_data.get('rank', 0),
                        participant.full_name,
                        participant.telegram_nickname,
                        participant.telegram_id,
                        rank_data.get('total_points', 0),
                        rank_data.get('total_tournament_points', 0),
                        rank_data.get('total_rot_pot', 0),
                        rank_data.get('total_bonuses', 0),
                        rank_data.get('total_transfer_profit', 0),
                        rank_data.get('total_transfer_income', 0),
                        rank_data.get('total_transfer_loss', 0),
                        rank_data.get('tour_count', 0),
                    ])

            if data_list:
                result_list = [[
                    'Место',
                    'ФИО',
                    'Никнейм в Telegram',
                    'Telegram ID',
                    'Общее количество баллов',
                    'Баллы, начисленные по типу 1 (рейтинг)',
                    'Баллы, начисленные по типу 2 (РОТ/ПОТ)',
                    'Баллы, начисленные по типу 3 (бонусы)',
                    'Баллы, начисленные по типу 4 (прибыль от трансфера)',
                    'Суммарный доход от трансфера',
                    'Суммарный убыток от трансфера',
                    'Количество турниров',
                ]] + data_list

                wb = Workbook()
                ws = wb.active

                for idx, row in enumerate(result_list):
                    if not my_telegram_id:
                        ws.append(
                            row
                        )

                    else:
                        if my_telegram_id == row[3] or idx == 0:
                            ws.append(
                                row
                            )

                if my_telegram_id or tournament_ids:
                    if not len(data_list) >= 1:
                        bot.reply_to(
                            message,
                            "Нет результатов"
                        )

                wb.save("results.xlsx")

                if not tour_number:
                    if not my_telegram_id:
                        bot.send_document(
                            message.chat.id,
                            document=open('results.xlsx', 'rb'),
                            caption='Рейтинг участников турнира'
                        )

                        message_text = 'Список участников в рейтинге:\n\n'
                        for participant in data_list:

                            text_info = '\n'.join([
                                f'Место: {participant[0]}',
                                f'ФИО: {participant[1]}',
                                f'Никнейм в Telegram: {participant[2]}',
                                f'Telegram ID: {participant[3]}',
                                f'Общее количество баллов: {participant[4]}',
                                f'Баллы, начисленные по рейтингу: {participant[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant[6]}',
                                f'Баллы, начисленные по бонусам: {participant[7]}',
                                f'Прибыль от трансфера баллов: {participant[8]}',
                                f'Суммарный доход от трансфера: {participant[9]}',
                                f'Суммарный убыток от трансфера: {participant[10]}',
                                f'Количество турниров: {participant[11]}\n\n',
                            ])

                            message_text += text_info

                        bot.reply_to(
                            message,
                            message_text
                        )

                    else:
                        try:
                            idx = list(ranked_data.keys()).index(my_telegram_id)
                            participant_data = result_list[idx + 1]
                            full_name = participant_data[1]
                            telegram_id = participant_data[3]

                            bot.send_document(
                                message.chat.id,
                                document=open('results.xlsx', 'rb'),
                                caption=f'Рейтинг участника ({full_name}, {telegram_id})'
                            )

                            message_text = 'Положение участника в рейтинге:\n\n'

                            text_info = '\n'.join([
                                f'Место: {participant_data[0]}',
                                f'ФИО: {participant_data[1]}',
                                f'Никнейм в Telegram: {participant_data[2]}',
                                f'Telegram ID: {participant_data[3]}',
                                f'Общее количество баллов: {participant_data[4]}',
                                f'Баллы, начисленные по рейтингу: {participant_data[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant_data[6]}',
                                f'Баллы, начисленные по бонусам: {participant_data[7]}',
                                f'Прибыль от трансфера баллов: {participant_data[8]}',
                                f'Суммарный доход от трансфера: {participant_data[9]}',
                                f'Суммарный убыток от трансфера: {participant_data[10]}',
                                f'Количество турниров: {participant_data[11]}\n\n',
                            ])

                            bot.reply_to(
                                message,
                                message_text + text_info
                            )

                        except ValueError:
                            bot.reply_to(
                                message,
                                'Не удалось найти ваш результат в рейтинге'
                            )

                else:
                    if not tour_error:
                        bot.send_document(
                            message.chat.id,
                            document=open('results.xlsx', 'rb'),
                            caption='Рейтинг участников турнира №' + str(tour_number)
                        )

                        message_text = f'Список участников в рейтинге по турниру № {tour_number}:\n\n'

                        for participant in data_list:
                            text_info = '\n'.join([
                                f'Место: {participant[0]}',
                                f'ФИО: {participant[1]}',
                                f'Никнейм в Telegram: {participant[2]}',
                                f'Telegram ID: {participant[3]}',
                                f'Общее количество баллов: {participant[4]}',
                                f'Баллы, начисленные по рейтингу: {participant[5]}',
                                f'Баллы, начисленные по РОТ/ПОТ: {participant[6]}',
                                f'Баллы, начисленные по бонусам: {participant[7]}',
                                f'Прибыль от трансфера баллов: {participant[8]}',
                                f'Суммарный доход от трансфера: {participant[9]}',
                                f'Суммарный убыток от трансфера: {participant[10]}',
                                f'Количество турниров: {participant[11]}\n\n',
                            ])

                            message_text += text_info

                        bot.reply_to(
                            message,
                            message_text
                        )

    else:
        bot.reply_to(
            message,
            "Нет участников в турнире"
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг по баллам (викторина)' in message.text or message.text == '/quiz_rating')
def tournament_rating_realization(message):
    """"
    Выводит общий рейтинг турнира в виде Excel-файла
    """
    is_AttributeError = False
    uid = message.from_user.id

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            bot.send_message(
                message.chat.id,
                "Общий рейтинг по баллам",
                reply_markup=markup
            )

            tournament_rating(
                message=message
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


@bot.message_handler(func=lambda message: 'Мое место в рейтинге по баллам (викторина)' in message.text or message.text=='/my_quiz_rating')
def participant_question(message):
    """"
    Фиксирует Telegram ID участника для вывода индивидуального рейтинга
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    participants = Authorization.objects.all().filter(
        role=3
    )

    participants_list = []
    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            if participants.exists():
                for participant in participants:
                    part_id = participant.id
                    part_name = participant.full_name
                    part_nick = participant.telegram_nickname
                    part_tel_id = participant.telegram_id

                    participants_list.append(
                        f"{part_id}: {part_name}" + f" (Telegram: {part_nick}, {part_tel_id})"
                    )

                markup = types.ReplyKeyboardMarkup(
                    resize_keyboard=True
                )

                btn_main_menu = types.KeyboardButton(
                    text='Главное меню'
                )

                btn_logout = types.KeyboardButton(
                    text='Выход'
                )

                markup.add(
                    btn_main_menu,
                    btn_logout
                )

                participants_list = "\n".join(
                    participants_list
                )

                bot.reply_to(
                    message,
                    f"Список участников: \n{participants_list}",
                    reply_markup=markup,
                )

                response = bot.reply_to(
                    message,
                    "Укажите свой Telegram ID (его вы можете найти в представленном выше списке):"
                )

                bot.register_next_step_handler(
                    response,
                    process_participant_rating_question,
                )

            else:
                bot.reply_to(
                    message,
                    "Участников в турнире пока нет"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


def process_participant_rating_question(message):
    """"
    Выводит индивидуальный рейтинг турнира в виде Excel-файла
    """
    telegram_id = message.text

    if telegram_id == "Главное меню":
        main_menu(message)

    elif telegram_id == "Выход":
        logout(message)

    else:
        tournament_rating(
            message=message,
            my_telegram_id=telegram_id
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг тура по баллам (викторина)' in message.text or message.text == '/quiz_tour_stat')
def tour_question(message):
    """"
    Фиксирует номер тура для вывода рейтинга участников в разрезе тура
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            response = bot.reply_to(
                message,
                "Введите номер тура по которому хотите получить статистику",
                reply_markup=markup,
            )

            bot.register_next_step_handler(
                response,
                process_tour_question,
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


def process_tour_question(message):
    """"
    Выводит рейтинг тура в виде Excel-файла
    """
    tour_number = message.text

    if tour_number == "Главное меню":
        main_menu(message)

    elif tour_number == "Выход":
        logout(message)

    else:
        tournament_rating(
            message,
            tour_number
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг по всем турам (викторина)' in message.text or message.text == '/quiz_tours_stat')
def tours_output(message):
    """"
    Выводит рейтинг всех туров сразу в виде Excel-файла
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            tours = Question.objects.all().values_list(
                'tour_id',
                flat=True
            ).distinct()

            if tours.exists():
                bot.reply_to(
                     message,
                    'Вывожу результаты туров',
                    reply_markup=markup
                )

                for tour in tours:
                    tournament_rating(
                        message,
                        tour_number=tour,
                    )

            else:
                bot.reply_to(
                    message,
                    "Нет туров для получения статистики"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг по верным ответам (викторина)' in message.text or message.text=='/quiz_answers_rating')
def answers_rating(message):
    """"
    Выводит рейтинг участников с сортированием по количеству правильных ответов
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            bot.reply_to(
                message,
                'Вывожу рейтинг участников с сортировкой по количеству правильных ответов',
                reply_markup=markup
            )

            tournament_rating(
                message,
                sort_param='total_right_answers'
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг по баллам (турнир)' in message.text or message.text == '/tournament_rating')
def tournament_rating_realization2(message):
    """"
    Выводит общий рейтинг турнира в виде Excel-файла
    """
    is_AttributeError = False
    uid = message.from_user.id

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            bot.send_message(
                message.chat.id,
                "Общий рейтинг по баллам",
                reply_markup=markup
            )

            points_tournament_rating(
                message=message
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


@bot.message_handler(func=lambda message: 'Мое место в рейтинге по баллам (турнир)' in message.text or message.text == '/my_tournam_rating')
def participant_question2(message):
    """"
    Фиксирует Telegram ID участника для вывода индивидуального рейтинга
    """
    is_AttributeError = False
    uid = message.from_user.id

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    participants = Authorization.objects.all().filter(
        role=3
    )

    participants_list = []
    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            if participants.exists():
                for participant in participants:
                    part_id = participant.id
                    part_name = participant.full_name
                    part_nick = participant.telegram_nickname
                    part_tel_id = participant.telegram_id

                    participants_list.append(
                        f"{part_id}: {part_name}" + f" (Telegram: {part_nick}, {part_tel_id})"
                    )

                markup = types.ReplyKeyboardMarkup(
                    resize_keyboard=True
                )

                btn_main_menu = types.KeyboardButton(
                    text='Главное меню'
                )

                btn_logout = types.KeyboardButton(
                    text='Выход'
                )

                markup.add(
                    btn_main_menu,
                    btn_logout
                )

                participants_list = "\n".join(
                    participants_list
                )

                bot.reply_to(
                    message,
                    f"Список участников: \n{participants_list}",
                    reply_markup=markup,
                )

                response = bot.reply_to(
                    message,
                    "Укажите свой Telegram ID (его вы можете найти в представленном выше списке):"
                )

                bot.register_next_step_handler(
                    response,
                    process_participant_rating_question2,
                )

            else:
                bot.reply_to(
                    message,
                    "Участников в турнире пока нет"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


def process_participant_rating_question2(message):
    """"
    Выводит индивидуальный рейтинг турнира в виде Excel-файла
    """
    telegram_id = message.text

    if telegram_id == "Главное меню":
        main_menu(message)

    elif telegram_id == "Выход":
        logout(message)

    else:
        points_tournament_rating(
            message,
            my_telegram_id=telegram_id
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг турнира по баллам (турнир)' in message.text or message.text == '/tournam_stat')
def tour_question2(message):
    """"
    Фиксирует номер тура для вывода рейтинга участников в разрезе турнира
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            response = bot.reply_to(
                message,
                "Введите номер турнира по которому хотите получить статистику",
                reply_markup=markup,
            )

            bot.register_next_step_handler(
                response,
                process_tour_question2,
            )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup
        )


def process_tour_question2(message):
    """"
    Выводит рейтинг тура в виде Excel-файла
    """
    tour_number = message.text

    if tour_number == "Главное меню":
        main_menu(message)

    elif tour_number == "Выход":
        logout(message)

    else:
        points_tournament_rating(
            message,
            tour_number
        )


@bot.message_handler(func=lambda message: 'Общий рейтинг по всем турнирам (турнир)' in message.text or message.text == '/tournams_stat')
def tours_output2(message):
    """"
    Выводит рейтинг всех туров сразу в виде Excel-файла
    """
    is_AttributeError = False
    uid = message.from_user.id
    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if user_auth_data.exists() and not is_AttributeError:
        if custom_user.is_authorized:

            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_main_menu = types.KeyboardButton(
                text='Главное меню'
            )

            btn_logout = types.KeyboardButton(
                text='Выход'
            )

            markup.add(
                btn_main_menu,
                btn_logout
            )

            tours = Tournament.objects.all().values_list(
                'id',
                flat=True
            ).distinct()

            if tours.exists():
                bot.reply_to(
                     message,
                    'Вывожу результаты туров',
                    reply_markup=markup
                )

                for tour in tours:
                    points_tournament_rating(
                        message,
                        tour_number=tour
                    )

            else:
                bot.reply_to(
                    message,
                    "Нет туров для получения статистики"
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не авторизованы. Для авторизации введите /login",
                reply_markup=markup,
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_register = types.KeyboardButton(
            text='Регистрация'
        )

        btn_login = types.KeyboardButton(
            text='Авторизация'
        )

        btn_password = types.KeyboardButton(
            text='Забыл пароль'
        )

        markup.add(
            btn_register,
            btn_login,
            btn_password
        )

        bot.reply_to(
            message,
            "Вы не зарегистрированы. Для регистрации введите /register",
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: 'Начать викторину' in message.text or message.text == '/start_quiz')
def tour_question(message):
    """
    Запускает викторину
    """
    questions = Question.objects.all()

    if questions.exists():
        tours = questions.values_list(
            'tour_id',
            flat=True
        ).distinct()

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        for tour in tours:
            markup.add(types.KeyboardButton(
                text=str(tour)
                )
            )

        reply = bot.reply_to(
            message,
            'Выберите тур для начала викторины:',
            reply_markup=markup,
        )

        bot.register_next_step_handler(
            reply,
            start_quiz,
            tours=[str(tour) for tour in tours],
        )

    else:
        bot.reply_to(
            message,
            "Нет доступных туров для викторины"
        )


def start_quiz(message, tours, question_number=None, tour_id=None, question_id=None):
    """"
    Начинает викторину или продолжает ее в зависимости от question_number
    question_number - номер вопроса в турнире (ID из таблицы Question)
    """

    is_AttributeError = False
    is_tour_number = False
    is_over = False
    is_repeat = False

    uid = message.from_user.id

    if not tour_id:
        tour_input = message.text

        if tour_input in tours:
            is_tour_number = True

    else:
        if tour_id in tours:
            is_tour_number = True

    user_auth_data = Authorization.objects.filter(
        telegram_id=uid
    )

    try:
        custom_user = CustomUser.objects.get(
            username_id=user_auth_data.first().id
        )
    except AttributeError as e:
        is_AttributeError = True

    if is_tour_number:
        if user_auth_data.exists() and not is_AttributeError:
            if custom_user.is_authorized:
                if custom_user.role_id == 3:
                    markup = types.ReplyKeyboardMarkup(
                        resize_keyboard=True
                    )

                    btn_main_menu = types.KeyboardButton(
                        text='Главное меню'
                    )

                    btn_logout = types.KeyboardButton(
                        text='Выход'
                    )

                    markup.add(
                        btn_main_menu,
                        btn_logout
                    )

                    questions = Question.objects.filter(
                        tour_id=tour_input if not tour_id else tour_id
                    )

                    if questions.exists():

                        if not question_id:
                            question_ids = [
                                question.id for question in questions
                            ]
                            question_id = min(question_ids)

                        if not question_number:
                            question_number = 1

                            participant = PointsTransaction.objects.filter(
                                sender_telegram_id=message.from_user.id,
                                question_id__in=question_ids
                            )

                            if participant.exists():
                                is_done_list = participant.values_list(
                                    'is_done',
                                    flat=True
                                )

                                sum_is_done = len(
                                    is_done_list
                                )

                                if sum_is_done == questions.count():
                                    is_over = True
                                    is_repeat = True
                                    question = None

                                    markup = types.ReplyKeyboardMarkup(
                                        resize_keyboard=True
                                    )

                                    btn_main_menu = types.KeyboardButton(
                                        text='Главное меню'
                                    )

                                    btn_logout = types.KeyboardButton(
                                        text='Выход'
                                    )

                                    markup.add(
                                        btn_main_menu,
                                        btn_logout
                                    )

                                    bot.reply_to(
                                        message,
                                        'Викторина уже завершена',
                                        reply_markup=markup,
                                    )

                            else:
                                bot.reply_to(
                                    message,
                                    'Начинаем викторину'
                                )

                            if not is_over:
                                question = Question.objects.filter(
                                    tour_question_number_id=question_number,
                                    tour_id=tour_input if not tour_id else tour_id
                                )

                        else:
                            question = Question.objects.filter(
                                tour_question_number_id=question_number,
                                tour_id=tour_input if not tour_id else tour_id
                            )

                    else:
                        question = None

                        bot.reply_to(
                            message,
                            'Нет вопросов для викторины'
                        )

                    if question:
                        tour = question.first().tour_id
                        tour_question_number_id = question.first().tour_question_number_id
                        question_text = question.first().question_text
                        answer_explanation = question.first().explanation[1:][:-1]

                        answer_dict = {
                            'A': question.first().answer_a,
                            'B': question.first().answer_b,
                            'C': question.first().answer_c,
                            'D': question.first().answer_d,
                        }

                        correct_answer = answer_dict.get(question.first().correct_answer)

                        participant = PointsTransaction.objects.filter(
                            sender_telegram_id=message.from_user.id,
                            question_id=question_number,
                        )

                        if not participant.exists() or participant.first().is_done == 0:
                            bot.reply_to(
                                message,
                                text=f"### Тур № {tour} ### Вопрос № {tour_question_number_id} ###",
                            )

                        markup = types.ReplyKeyboardMarkup(row_width=2)
                        for option in list(answer_dict.values()):
                            button = types.KeyboardButton(option)
                            markup.add(button)

                        bot.send_message(
                            message.chat.id,
                            text=question_text,
                            reply_markup=markup,
                        )

                        image_path = question.first().image

                        if image_path:
                            try:
                                with open(image_path.path, 'rb') as photo:
                                    bot.send_photo(chat_id=message.chat.id, photo=photo)
                            except Exception as e:
                                print(f"Ошибка при отправке фото: {e}")

                        try:
                            bot.register_next_step_handler(
                                message,
                                handle_answer,
                                correct_answer=correct_answer,
                                question_number=question_number,
                                answer_explanation=answer_explanation,
                                tours=tours,
                                tour_id=tour_input if not tour_id else tour_id,
                                question_id=question_id
                            )
                        except TypeError:
                            pass

                    else:
                        if not is_repeat:
                            markup = types.ReplyKeyboardMarkup(
                                resize_keyboard=True
                            )

                            btn_main_menu = types.KeyboardButton(
                                text='Главное меню'
                            )

                            btn_logout = types.KeyboardButton(
                                text='Выход'
                            )

                            markup.add(
                                btn_main_menu,
                                btn_logout
                            )

                            bot.reply_to(
                                message,
                                "На этом викторина тура окончена",
                                reply_markup=markup,
                            )

                else:
                    bot.reply_to(
                        message,
                        "Вы не являетесь участником турнира"
                    )

            else:
                markup = types.ReplyKeyboardMarkup(
                    resize_keyboard=True
                )

                btn_register = types.KeyboardButton(
                    text='Регистрация'
                )

                btn_login = types.KeyboardButton(
                    text='Авторизация'
                )

                btn_password = types.KeyboardButton(
                    text='Забыл пароль'
                )

                markup.add(
                    btn_register,
                    btn_login,
                    btn_password
                )

                bot.reply_to(
                    message,
                    "Вы не авторизованы. Для авторизации введите /login",
                    reply_markup=markup,
                )

        else:
            markup = types.ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            btn_register = types.KeyboardButton(
                text='Регистрация'
            )

            btn_login = types.KeyboardButton(
                text='Авторизация'
            )

            btn_password = types.KeyboardButton(
                text='Забыл пароль'
            )

            markup.add(
                btn_register,
                btn_login,
                btn_password
            )

            bot.reply_to(
                message,
                "Вы не зарегистрированы. Для регистрации введите /register",
                reply_markup=markup
            )

    else:
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True
        )

        btn_main_menu = types.KeyboardButton(
            text='Главное меню'
        )

        btn_logout = types.KeyboardButton(
            text='Выход'
        )

        markup.add(
            btn_main_menu,
            btn_logout
        )

        bot.reply_to(
            message,
            "Тур завершен",
            reply_markup=markup,
        )


@bot.message_handler(func=lambda message: True)
def handle_answer(message, correct_answer=None, answer_explanation=None, question_number=None, tours=None, tour_id=None, question_id=None):
    """"
    Фиксирует ответ участника и переходит к следующему вопросу, если он есть
    """
    uid = message.from_user.id

    participant = PointsTransaction.objects.filter(
        sender_telegram_id=uid,
        question_id=question_id,
    )

    if message.text == 'Главное меню':
        main_menu(message)

    elif message.text == 'Выход':
        logout(message)

    elif message.text == correct_answer:
        bot.send_message(
            message.chat.id,
            f"Верно! \n{answer_explanation}", reply_markup=types.ReplyKeyboardRemove()
        )

        if not participant.exists():
            PointsTransaction.objects.create(
                sender_telegram_id=uid,
                question_id=question_id,
                is_answered=1,
                is_done=1,
            )

        else:
            if participant.first().is_done == 0:
                PointsTransaction.objects.filter(
                    sender_telegram_id=uid,
                    question_id=question_id,
                ).update(
                    is_answered=1,
                    is_done=1,
                )

        start_quiz(
            message,
            tours=tours,
            tour_id=tour_id,
            question_number=question_number+1,
            question_id=question_id+1
        )

    else:
        bot.send_message(
            message.chat.id,
            f"Неверно! \n{answer_explanation}", reply_markup=types.ReplyKeyboardRemove()
        )

        if not participant.exists():
            PointsTransaction.objects.create(
                sender_telegram_id=uid,
                question_id=question_id,
                is_answered=0,
                is_done=1,
            )

        else:
            PointsTransaction.objects.filter(
                sender_telegram_id=uid,
                question_id=question_id,
            ).update(
                is_answered=0,
                is_done=1,
            )

        start_quiz(
            message,
            tours=tours,
            tour_id=tour_id,
            question_number=question_number+1,
            question_id=question_id + 1
        )


if __name__ == "__main__":
    bot.polling()

    # while True:
    #     try:
    #         bot.polling()
    #     except Exception as e:
    #         print(f'Произошла ошибка: {e}')
    #         time.sleep(10)
