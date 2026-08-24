import os
import json
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import re

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
VK_TOKEN = os.environ.get("VK_TOKEN")
GROUP_ID = os.environ.get("GROUP_ID")

if not VK_TOKEN:
    raise Exception("Переменная окружения VK_TOKEN не задана!")
if not GROUP_ID:
    raise Exception("Переменная окружения GROUP_ID не задана!")

try:
    GROUP_ID = int(GROUP_ID)
except ValueError:
    raise Exception("GROUP_ID должен быть целым числом!")

# --- ИНИЦИАЛИЗАЦИЯ ---
vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()

# ---------- Кастомные имена ----------
NICKNAMES_FILE = "nicknames.json"

def load_nicknames():
    """Загружает словарь кастомных имён из JSON-файла. При ошибке возвращает {}."""
    if os.path.exists(NICKNAMES_FILE):
        try:
            with open(NICKNAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Ошибка чтения nicknames.json: {e}. Используется пустой словарь.")
            # Можно заархивировать повреждённый файл
            # os.rename(NICKNAMES_FILE, NICKNAMES_FILE + ".broken")
            return {}
    return {}

def save_nicknames(nicknames):
    """Сохраняет словарь кастомных имён в JSON-файл."""
    try:
        with open(NICKNAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(nicknames, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"⚠️ Ошибка сохранения nicknames.json: {e}")

# Загружаем кастомные имена при старте
nicknames = load_nicknames()

user_cache = {}  # кеш для стандартных имён

def get_user_name(user_id):
    user_id_str = str(user_id)
    # Если есть кастомное имя — используем его
    if user_id_str in nicknames:
        return nicknames[user_id_str]
    # Иначе — стандартное имя (только имя, без фамилии)
    if user_id not in user_cache:
        try:
            user = vk.users.get(user_ids=user_id, fields=[])
            if user:
                user_cache[user_id] = user[0]['first_name']
            else:
                user_cache[user_id] = f"Пользователь {user_id}"
        except:
            user_cache[user_id] = f"Пользователь {user_id}"
    return user_cache[user_id]

def mention_user(user_id, peer_id):
    if peer_id != user_id:
        name = get_user_name(user_id)
        return f"[id{user_id}|{name}], "
    return ""

def send_message(user_id, message, peer_id=None):
    try:
        vk.messages.send(
            user_id=user_id if peer_id is None else None,
            peer_id=peer_id,
            message=message,
            random_id=0
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ----------------------------------------------
# 1. Монетка
# ----------------------------------------------
def flip_coin():
    return "Орёл!" if random.choice([True, False]) else "Решка!"

# ----------------------------------------------
# 2. Случайное число
# ----------------------------------------------
def random_number(args):
    if not args:
        num = random.randint(0, 100)
        return f"🔢 Случайное число от 0 до 100: **{num}**", None
    if len(args) == 2:
        try:
            a = int(args[0])
            b = int(args[1])
            if a > b:
                a, b = b, a
            num = random.randint(a, b)
            return f"🔢 Случайное число от {a} до {b}: **{num}**", None
        except ValueError:
            return None, "Ошибка: введите два целых числа. Пример: /rand 1 100"
    else:
        return None, "Укажите два числа через пробел. Пример: /rand 1 100"

# ----------------------------------------------
# 3. Бросок нескольких кубиков
# ----------------------------------------------
def parse_and_roll_multiple(expression):
    expr = expression.lower().replace(' ', '').replace('д', 'd')
    if not expr:
        return None, "Пустое выражение"

    parts = re.findall(r'([+-]?\d*d\d+|[+-]?\d+)', expr)
    if not parts:
        return None, "Неверный формат. Пример: 2d6+1d20+5"

    total = 0
    details = []

    for part in parts:
        sign = 1
        if part.startswith('-'):
            sign = -1
            part = part[1:]
        elif part.startswith('+'):
            part = part[1:]

        if 'd' in part:
            if part.startswith('d'):
                num_dice = 1
                dice_type = int(part[1:])
            else:
                num_dice_str, dice_type_str = part.split('d')
                num_dice = int(num_dice_str) if num_dice_str else 1
                dice_type = int(dice_type_str)

            if num_dice > 100:
                return None, "Слишком много кубиков (макс. 100)"
            if dice_type > 1000:
                return None, "Слишком большой кубик (макс. d1000)"
            if num_dice <= 0 or dice_type <= 0:
                return None, "Количество и тип кубика должны быть положительными"

            rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
            subtotal = sum(rolls) * sign
            total += subtotal

            if num_dice == 1:
                detail = f"{part}={rolls[0]}"
            else:
                detail = f"{part}=({', '.join(map(str, rolls))})"
            if sign == -1:
                detail = '-' + detail
            details.append(detail)
        else:
            value = int(part) * sign
            total += value
            if value > 0:
                details.append(f"+{value}")
            elif value < 0:
                details.append(f"{value}")

    if not details:
        return None, "Не удалось разобрать выражение"

    details_str = " ".join(details)
    result_str = f"{expression} → результат * {total} * ({details_str})"
    return result_str, None

# ----------------------------------------------
# 4. Основной цикл
# ----------------------------------------------
print("Бот успешно запущен и слушает сообщения...")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        try:
            peer_id = event.object.message['peer_id']
            user_id = event.object.message['from_id']
            text = event.object.message['text'].strip()

            if not text:
                continue

            if text.startswith(('/', '!')):
                cmd = text[1:].strip()
                if not cmd:
                    msg = mention_user(user_id, peer_id) + "Введите команду. Например: /d20"
                    send_message(user_id, msg, peer_id)
                    continue

                parts = cmd.split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                if command in ('help', 'помощь'):
                    help_text = (
                        "🎲 **Команды бота:**\n\n"
                        "**Бросок кубиков** (можно через / или !):\n"
                        "/d20 или !d20 — бросить 20-гранный кубик\n"
                        "/2d6+1d20+5 — несколько кубиков разных типов\n"
                        "/d100-3 — d100 с модификатором\n\n"
                        "**Специальные команды:**\n"
                        "/coin или /монетка — подбросить монетку\n"
                        "/rand 1 100 — случайное число в диапазоне\n"
                        "/ping — проверка работы\n"
                        "/help или !help — эта справка"
                    )
                    send_message(user_id, help_text, peer_id)

                elif command in ('coin', 'монетка'):
                    result = flip_coin()
                    mention = mention_user(user_id, peer_id)
                    msg = f"{mention}Бросок монетки: {result}"
                    send_message(user_id, msg, peer_id)

                elif command in ('rand', 'random'):
                    result, error = random_number(args)
                    if error:
                        msg = mention_user(user_id, peer_id) + "Ошибка: " + error
                        send_message(user_id, msg, peer_id)
                    else:
                        mention = mention_user(user_id, peer_id)
                        msg = f"{mention}Результат: {result}"
                        send_message(user_id, msg, peer_id)

                elif command == 'ping':
                    mention = mention_user(user_id, peer_id)
                    send_message(user_id, f"{mention}Pong! Бот работает.", peer_id)

                else:
                    result, error = parse_and_roll_multiple(cmd)
                    if error:
                        msg = mention_user(user_id, peer_id) + "Ошибка: " + error
                        send_message(user_id, msg, peer_id)
                    else:
                        mention = mention_user(user_id, peer_id)
                        msg = f"{mention}Бросок {result}"
                        send_message(user_id, msg, peer_id)

        except Exception as e:
            print(f"Ошибка в цикле: {e}")
            try:
                mention = mention_user(user_id, peer_id)
                send_message(user_id, f"{mention}⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
