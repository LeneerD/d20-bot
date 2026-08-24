import os
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

# Кеш для имён пользователей
user_cache = {}

def get_user_name(user_id):
    """Возвращает имя пользователя по его ID (с кешированием)"""
    if user_id not in user_cache:
        try:
            user = vk.users.get(user_ids=user_id, fields=[])
            if user:
                user_cache[user_id] = f"{user[0]['first_name']} {user[0]['last_name']}"
            else:
                user_cache[user_id] = f"Пользователь {user_id}"
        except:
            user_cache[user_id] = f"Пользователь {user_id}"
    return user_cache[user_id]

def mention_user(user_id, peer_id):
    """
    Возвращает строку с упоминанием пользователя, если это беседа.
    В личке возвращает пустую строку (обращение не нужно).
    """
    if peer_id != user_id:  # если peer_id отличается от user_id — это беседа
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
        return f"🔢 Случайное число от 0 до 100: **{num}**"
    if len(args) == 2:
        try:
            a = int(args[0])
            b = int(args[1])
            if a > b:
                a, b = b, a
            num = random.randint(a, b)
            return f"🔢 Случайное число от {a} до {b}: **{num}**"
        except ValueError:
            return None, "Ошибка: введите два целых числа. Пример: /rand 1 100"
    else:
        return None, "Укажите два числа через пробел. Пример: /rand 1 100"

# ----------------------------------------------
# 3. Бросок нескольких кубиков
# ----------------------------------------------
def parse_and_roll_multiple(expression):
    """
    Принимает выражение вида "2d6+1d20+5" или "d20-3"
    Возвращает (результат_в_виде_строки, сообщение_об_ошибке)
    """
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
    # Возвращаем результат без упоминания и со словом "бросок"
    result_str = f"Бросок {expression} → результат **{total}**  ({details_str})"
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

            # Проверяем, начинается ли сообщение с / или !
            if text.startswith(('/', '!')):
                cmd = text[1:].strip()
                if not cmd:
                    # Пустая команда — просто напоминаем
                    msg = mention_user(user_id, peer_id) + "Введите команду. Например: /d20"
                    send_message(user_id, msg, peer_id)
                    continue

                parts = cmd.split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # --- Обработка команд ---
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
                    # Справку отправляем без упоминания (или можно с упоминанием, но не обязательно)
                    send_message(user_id, help_text, peer_id)

                elif command in ('coin', 'монетка'):
                    result = flip_coin()
                    # Формируем сообщение с упоминанием и словом "бросок"
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
                    # Любая другая команда — бросок кубиков
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
                # Отправляем сообщение об ошибке с упоминанием
                mention = mention_user(user_id, peer_id)
                send_message(user_id, f"{mention}⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
