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
    return "🪙 Орёл!" if random.choice([True, False]) else "🪙 Решка!"


# ----------------------------------------------
# 2. Случайное число в диапазоне
# ----------------------------------------------
def random_number(args):
    """
    args: список строк, например ['1', '100'] или []
    Возвращает строку с результатом или ошибкой.
    """
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
            return "❌ Ошибка: введите два целых числа. Пример: /rand 1 100"
    else:
        return "❌ Укажите два числа через пробел. Пример: /rand 1 100"


# ----------------------------------------------
# 3. Эмодзи для кубиков
# ----------------------------------------------
def get_dice_emoji(dice_type):
    emojis = {
        4:  "⚀",   # d4
        6:  "⚁",   # d6
        8:  "⚂",   # d8
        10: "⚃",   # d10
        12: "⚄",   # d12
        20: "🎲",   # d20
        100:"💯"    # d100
    }
    return emojis.get(dice_type, "🎲")


# ----------------------------------------------
# 4. Поддержка нескольких кубиков разных типов
# ----------------------------------------------
def parse_and_roll_multiple(expression):
    """
    Принимает выражение вида "2d6+1d20+5" или "d20-3"
    Возвращает (результат_в_виде_строки, сообщение_об_ошибке)
    """
    # Заменяем русскую 'д' на латинскую 'd', убираем пробелы
    expr = expression.lower().replace(' ', '').replace('д', 'd')
    if not expr:
        return None, "❌ Пустое выражение"

    # Разбиваем на части по + и -, сохраняя знак
    parts = re.findall(r'([+-]?\d*d\d+|[+-]?\d+)', expr)
    if not parts:
        return None, "❌ Неверный формат. Пример: 2d6+1d20+5"

    total = 0
    details = []
    dice_emojis = []

    for part in parts:
        sign = 1
        if part.startswith('-'):
            sign = -1
            part = part[1:]
        elif part.startswith('+'):
            part = part[1:]
        # Теперь part может быть числом или выражением d
        if 'd' in part:
            # Формат: [кол-во]d[тип]
            if part.startswith('d'):
                num_dice = 1
                dice_type = int(part[1:])
            else:
                num_dice_str, dice_type_str = part.split('d')
                num_dice = int(num_dice_str) if num_dice_str else 1
                dice_type = int(dice_type_str)
            # Проверки
            if num_dice > 100:
                return None, "❌ Слишком много кубиков (макс. 100)"
            if dice_type > 1000:
                return None, "❌ Слишком большой кубик (макс. d1000)"
            if num_dice <= 0 or dice_type <= 0:
                return None, "❌ Количество и тип кубика должны быть положительными"
            # Бросаем
            rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
            subtotal = sum(rolls) * sign
            total += subtotal
            # Формируем описание
            if num_dice == 1:
                detail = f"{part}={rolls[0]}"
            else:
                detail = f"{part}=({', '.join(map(str, rolls))})"
            if sign == -1:
                detail = '-' + detail
            details.append(detail)
            # Для эмодзи берем только если положительный вклад, иначе не добавляем
            if sign == 1:
                dice_emojis.append(get_dice_emoji(dice_type))
        else:
            # Это просто число (модификатор)
            value = int(part) * sign
            total += value
            if value > 0:
                details.append(f"+{value}")
            elif value < 0:
                details.append(f"{value}")  # уже с минусом
            # если 0, пропускаем

    # Формируем красивый вывод
    if not details:
        return None, "❌ Не удалось разобрать выражение"

    # Собираем детали в строку
    details_str = " ".join(details)
    # Эмодзи: если есть кубики, показываем их
    emoji_str = ""
    if dice_emojis:
        # Если несколько разных кубиков, перечисляем через пробел
        emoji_str = " ".join(dice_emojis) + " "
    result_str = f"{emoji_str}{expression} → **{total}**  ({details_str})"
    return result_str, None


# ----------------------------------------------
# 5. Основной цикл
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

            # --- ПРОВЕРКА НА КОМАНДУ (через / или !) ---
            if text.startswith(('/', '!')):
                # Убираем первый символ
                cmd = text[1:].strip()
                if not cmd:
                    send_message(user_id, "❌ Введите команду. Например: /d20", peer_id)
                    continue

                # Разбиваем на слова для команд с аргументами
                parts = cmd.split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # --- Обработка специальных команд ---
                if command in ('help', 'помощь'):
                    help_text = (
                        "🎲 **Команды бота:**\n\n"
                        "**Бросок кубиков** (можно через / или !):\n"
                        "`/d20` или `!d20` — бросить 20-гранный кубик\n"
                        "`/2d6+1d20+5` — несколько кубиков разных типов\n"
                        "`/d100-3` — d100 с модификатором\n\n"
                        "**Специальные команды:**\n"
                        "`/coin` или `/монетка` — подбросить монетку\n"
                        "`/rand 1 100` — случайное число в диапазоне\n"
                        "`/ping` — проверка работы\n"
                        "`/help` или `!help` — эта справка"
                    )
                    send_message(user_id, help_text, peer_id)

                elif command in ('coin', 'монетка'):
                    send_message(user_id, flip_coin(), peer_id)

                elif command in ('rand', 'random'):
                    result = random_number(args)
                    send_message(user_id, result, peer_id)

                elif command == 'ping':
                    send_message(user_id, "🏓 Pong! Бот работает.", peer_id)

                else:
                    # Любая другая команда считается выражением для броска
                    # Восстанавливаем полную строку после префикса (может содержать пробелы)
                    full_expr = cmd  # уже без первого символа
                    result, error = parse_and_roll_multiple(full_expr)
                    if error:
                        send_message(user_id, error, peer_id)
                    else:
                        send_message(user_id, result, peer_id)

            # --- ВСЁ ОСТАЛЬНОЕ ИГНОРИРУЕМ ---

        except Exception as e:
            print(f"Ошибка в цикле: {e}")
            try:
                send_message(user_id, "⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
