import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state

import service
from service import APIService

API_TOKEN = "7002447822:AAG107hnxfe9ACZ4GPpZOKMjZvmYIoLBjls"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

login_url = 'http://api:8000/auth/login'
groups_url = 'http://api:8000/groups'
login_data = {
    "username": "telegram",
    "email": "telegram@telegram.com",
    "fullname": "none",
    "role": "system",
    "password": "awJwnbbT"
}

api_service = APIService(login_url, groups_url, login_data)

class SearchQuestions(StatesGroup):
    waiting_for_message = State()

class Form(StatesGroup):
    group = State()
    name = State()
    student_id = State()
    question = State()
    add_photo = State()
    question_photo = State()


main_b = [
    [InlineKeyboardButton(text="Подать заявку в группу", callback_data='select_course')],
    [InlineKeyboardButton(text="FAQ", callback_data='FAQ')]
]
main_auth_b = [
    [InlineKeyboardButton(text="Задать вопрос администратору", callback_data='ask_admin')],
    [InlineKeyboardButton(text="FAQ", callback_data='FAQ')]
]

main_kb = InlineKeyboardMarkup(inline_keyboard=main_b)
main_auth_kb = InlineKeyboardMarkup(inline_keyboard=main_auth_b)


@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    async with httpx.AsyncClient() as client:
        response = await client.get(f'http://api:8000/students/{message.from_user.id}',
                                    headers=api_service.headers)
        if response.status_code == 200:
            data = response.json()
            if data:
                await message.answer("Привет! Это информационная система для института. Пожалуйста, выберите опцию.",
                                     reply_markup=main_auth_kb)
            else:
                await message.answer("Привет! Это информационная система для института. Пожалуйста, выберите опцию.",
                                     reply_markup=main_kb)
        elif response.status_code == 403:
            await message.answer("Привет! Это информационная система для института. Пожалуйста, выберите опцию.",
                                 reply_markup=main_kb)
        else:
            await message.answer("Ошибка при запросе: " + str(response.status_code) + " - " + response.text)


@dp.callback_query(lambda c: c.data == "select_course")
async def select_course(callback_query: types.CallbackQuery):
    async with httpx.AsyncClient() as client:
        response = await client.get(f'http://api:8000/students/{callback_query.from_user.id}',
                                    headers=api_service.headers)
        result = response.json()
        if result:
            await callback_query.message.answer("У вас нет доступа к этой опции.")
            return

    courses_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{i} курс", callback_data=f"choose_course_{i}")] for i in range(1, 5)
        ]
    )
    await bot.send_message(callback_query.from_user.id, "Выберите курс:", reply_markup=courses_kb)


@dp.callback_query(lambda c: c.data.startswith("choose_course"))
async def process_course(callback_query: types.CallbackQuery):
    async with httpx.AsyncClient() as client:
        response = await client.get(f'http://api:8000/students/{callback_query.from_user.id}',
                                    headers=api_service.headers)
        result = response.json()
        if result:
            await callback_query.message.answer("У вас нет доступа к этой опции.")
            return
    course = int(callback_query.data.split("_")[-1])
    await api_service.update_token()
    groups = await api_service.get_groups()
    course_groups = [group for group in groups if group['short_name'].split('-')[-1].startswith(str(course))]
    groups_kb = await get_groups_kb([item['short_name'] for item in course_groups])
    await bot.send_message(callback_query.from_user.id, "Выберите группу:", reply_markup=groups_kb)


@dp.callback_query(lambda c: c.data.startswith("choose_group"))
async def process_group(callback_query: types.CallbackQuery, state: FSMContext):
    async with httpx.AsyncClient() as client:
        response = await client.get(f'http://api:8000/students/{callback_query.from_user.id}',
                                    headers=api_service.headers)
        result = response.json()
        if result:
            await callback_query.message.answer("У вас нет доступа к этой опции.")
            return
    group = callback_query.data.replace("choose_group", "")
    data = await api_service.get_group_details(group)
    department = data['department']
    specialty = data['specialty']
    members_count = data['user_count']
    await bot.send_message(callback_query.from_user.id,
                           f"Группа: {group}\nДепартамент: {department}\nСпециальность: {specialty}\nКоличество участников: {members_count}")
    join_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data=f"join_group{group}")],
        [InlineKeyboardButton(text="Нет", callback_data="select_course")]
    ])
    await bot.send_message(callback_query.from_user.id, "Хотите присоединиться к этой группе?", reply_markup=join_kb)


@dp.callback_query(lambda c: c.data.startswith("join_group"))
async def join_group(callback_query: types.CallbackQuery, state: FSMContext):
    async with httpx.AsyncClient() as client:
        response = await client.get(f'http://api:8000/students/{callback_query.from_user.id}',
                                    headers=api_service.headers)
        result = response.json()
        if result:
            await callback_query.message.answer("У вас нет доступа к этой опции.")
            return

    data = await api_service.check_active_ticket(callback_query.from_user.id)
    if data:
        await callback_query.message.answer("У вас уже имеется активная заявка, дождитесь ответа.")
        return

    await state.update_data(group=callback_query.data.replace("join_group", ""))
    await state.set_state(Form.name)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите ваше ФИО:")


@dp.message(Form.name)
async def process_name(message: types.Message, state: FSMContext):
    if 15 <= len(message.text) <= 50 and message.text.count(' ') >= 2:
        await state.update_data(name=message.text)
        await state.set_state(Form.student_id)
        await message.answer("Пожалуйста, отправьте фотографию вашего студенческого билета:")
    else:
        await message.reply(
            "Ваше ФИО должно быть минимум 15 символов и максимум 50 символов, а также содержать фамилию, имя и отчество. "
            "Пожалуйста, попробуйте еще раз ввести ваше полное имя."
        )


@dp.message(Form.student_id, F.photo)
async def process_student_id(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте корректную фотографию студенческого билета.")
        return

    user_data = await state.get_data()
    group = user_data['group']
    name = user_data['name']
    student_id_photo = message.photo[-1]
    tg_chat = message.chat.id

    photo_file = await bot.get_file(student_id_photo.file_id)
    photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{photo_file.file_path}"

    async with httpx.AsyncClient() as client:
        response = await client.get(photo_url)
        photo_bytes = response.content

    ticket_data = {
        'type_ticket': 'verification',
        'tgchat_id': tg_chat,
        'wish_group': group,
        'fullname': name,
    }

    response = await api_service.submit_ticket(ticket_data, photo_bytes, 'student_id.jpg')
    if response.status_code == 201:
        await message.answer(f"Ваша заявка была отправлена. Пожалуйста, дождитесь ответа")
    else:
        await message.answer("Ошибка отправки заявки. Пожалуйста, повторите попытку.")

    await state.clear()


@dp.callback_query(lambda c: c.data == "FAQ")
async def process_faq(callback_query: types.CallbackQuery):
    await bot.send_message(callback_query.from_user.id, "Выберите опцию:",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                               [InlineKeyboardButton(text="Ввести запрос", callback_data="request")]
                           ]))


@dp.callback_query(lambda c: c.data == "request")
async def request_faq(callback_query: types.CallbackQuery,  state: FSMContext):
    await callback_query.message.answer(
        "Привет! Я здесь, чтобы помочь с поиском нужно вопроса. Вот несколько примеров запросов, чтобы тебе было проще:\n\n"
        "- Какие документы нужны для поступления?\n"
        "- Есть ли правила для поступления в общагу?\n\n"
        "Введи свой вопрос, и я постараюсь помочь!")

    await state.set_state(SearchQuestions.waiting_for_message)
    await callback_query.answer(
        text="work",
        show_alert=False)


@dp.message(SearchQuestions.waiting_for_message)
async def process_name(message: types.Message, state: FSMContext):
    user_query = message.text
    data = await api_service.search_questions(user_query)
    if not data:
        await message.answer("Извините, ничего не найдено по вашему запросу.")
    else:
        response_text = "📚 <b>Вот что я нашел:</b>\n\n"
        for item in data:
            response_text += (
                f"❓ <b>Вопрос:</b> {item['question']}\n"
                f"💡 <b>Ответ:</b> {item['answer']}\n\n"
            )

        await message.answer(response_text, parse_mode="HTML")
    await state.clear()



@dp.callback_query(lambda c: c.data == "ask_admin")
async def ask_admin(callback_query: types.CallbackQuery, state: FSMContext):
    data = await api_service.check_active_ticket(callback_query.from_user.id)
    if data:
        await callback_query.message.answer("У вас уже имеется активная заявка, дождитесь ответа.")
        return

    await state.set_state(Form.question)
    await bot.send_message(callback_query.from_user.id, "Введите ваш вопрос:")


@dp.message(Form.question)
async def process_question(message: types.Message, state: FSMContext):
    question = message.text
    await state.update_data(question=question)
    add_photo_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="add_photo_yes")],
            [InlineKeyboardButton(text="Нет", callback_data="add_photo_no")]
        ]
    )
    await state.set_state(Form.add_photo)
    await message.answer("Хотите добавить фото к вашему вопросу?", reply_markup=add_photo_kb)


@dp.callback_query(lambda c: c.data == "add_photo_yes")
async def ask_for_photo(callback_query: types.CallbackQuery, state: FSMContext):
    data = await api_service.check_active_ticket(callback_query.from_user.id)
    if data:
        await callback_query.message.answer("У вас уже имеется активная заявка, дождитесь ответа.")
        return
    await state.set_state(Form.question_photo)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, отправьте фото:")


@dp.callback_query(lambda c: c.data == "add_photo_no")
async def submit_question(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    question = user_data['question']
    tg_chat = callback_query.from_user.id

    ticket_data = {
        'type_ticket': 'request',
        'tgchat_id': tg_chat,
        'message': question,
    }
    response = await api_service.submit_ticket(ticket_data)
    if response.status_code == 201:
        await bot.send_message(callback_query.from_user.id, "Ваш вопрос был отправлен.")
    else:
        await bot.send_message(callback_query.from_user.id,
                               f"Ошибка отправки вопроса. Пожалуйста, повторите попытку. {response.content}")

    await state.clear()


@dp.message(Form.question_photo, F.photo)
async def process_question_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте корректную фотографию")
        return

    user_data = await state.get_data()
    question = user_data['question']
    photo = message.photo[-1]
    tg_chat = message.chat.id

    photo_file = await bot.get_file(photo.file_id)
    photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{photo_file.file_path}"

    async with httpx.AsyncClient() as client:
        response = await client.get(photo_url)
        photo_bytes = response.content

    ticket_data = {
        'type_ticket': 'request',
        'tgchat_id': tg_chat,
        'message': question,
    }
    response = await api_service.submit_ticket(ticket_data, photo_bytes, 'question_photo.jpg')
    if response.status_code == 201:
        await message.answer("Ваш вопрос был отправлен.")
    else:
        await message.answer("Ошибка отправки вопроса. Пожалуйста, повторите попытку.")

    await state.clear()


async def get_groups_kb(groups):
    groups_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=group, callback_data="choose_group" + group)] for group in groups
        ]
    )
    return groups_kb



if __name__ == "__main__":
    dp.run_polling(bot)
