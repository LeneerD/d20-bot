import os
import json
import random
import re
import time
import logging
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

# ---- Настройка логирования ----
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- Переменные окружения ----
VK_TOKEN = os.environ.get("VK_TOKEN")
GROUP_ID = os.environ.get("GROUP_ID")
OWNER_ID = os.environ.get("OWNER_ID")  # ID владельца (для команды /reload)

if not VK_TOKEN:
    raise Exception("Переменная окружения VK_TOKEN не задана!")
if not GROUP_ID:
    raise Exception("Переменная окружения GROUP_ID не задана!")
if not OWNER_ID:
    logger.warning("OWNER_ID не задан – команда /reload будет недоступна")
else:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        logger.error("OWNER_ID должен быть целым числом!")
        OWNER_ID = None

try:
    GROUP_ID = int(GROUP_ID)
except ValueError:
    raise Exception("GROUP_ID должен быть целым числом!")

# ---- Инициализация VK ----
vk_session = vk_api.VkApi(token=VK_TOKEN)

def init_longpoll_with_retry(session, group_id, retries=5, delay=3):
    for attempt in range(1, retries + 1):
        try:
            longpoll = VkBotLongPoll(session, group_id)
            logger.info(f"LongPoll успешно инициализирован (попытка {attempt})")
            return longpoll
        except Exception as e:
            logger.warning(f"Ошибка инициализации LongPoll (попытка {attempt}/{retries}): {e}")
            if attempt == retries:
                raise
            time.sleep(delay)

longpoll = init_longpoll_with_retry(vk_session, GROUP_ID)
vk = vk_session.get_api()

# ---- Кастомные имена (nicknames.json) ----
NICKNAMES_FILE = "nicknames.json"

def load_nicknames():
    if os.path.exists(NICKNAMES_FILE):
        try:
            with open(NICKNAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения nicknames.json: {e}. Используется пустой словарь.")
            return {}
    return {}

def save_nicknames(data):
    try:
        with open(NICKNAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Ошибка сохранения nicknames.json: {e}")

nicknames = load_nicknames()
user_cache = {}

def get_user_name(user_id):
    user_id_str = str(user_id)
    if user_id_str in nicknames:
        return nicknames[user_id_str]
    if user_id not in user_cache:
        try:
            user = vk.users.get(user_ids=user_id, fields=[])
            if user:
                user_cache[user_id] = user[0]['first_name']
            else:
                user_cache[user_id] = f"Пользователь {user_id}"
        except Exception as e:
            logger.error(f"Ошибка получения имени пользователя {user_id}: {e}")
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
        logger.error(f"Ошибка отправки сообщения: {e}")

def format_response(mention, result, comment=None):
    """Универсальное форматирование ответа с упоминанием и комментарием."""
    if comment:
        return f"{mention}{result} (комментарий: {comment})"
    return f"{mention}{result}"

# ---- Загрузка таблиц из JSON ----
DATA_DIR = "data"
TABLES_FILE = os.path.join(DATA_DIR, "tables.json")
INJURY_FILE = os.path.join(DATA_DIR, "injury.json")

def load_tables():
    """Загружает таблицы навыков из tables.json."""
    default = {}  # пустой словарь, если файл не найден
    if os.path.exists(TABLES_FILE):
        try:
            with open(TABLES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения tables.json: {e}. Используется пустой словарь.")
            return default
    else:
        logger.warning(f"Файл {TABLES_FILE} не найден. Создайте его с таблицами.")
        return default

def load_injury():
    """Загружает таблицу ранений из injury.json."""
    default = {}
    if os.path.exists(INJURY_FILE):
        try:
            with open(INJURY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Для диапазона 41-63 автоматически заполним Full Recovery, если не заданы
                # Но мы можем положиться на данные из файла
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения injury.json: {e}. Используется пустой словарь.")
            return default
    else:
        logger.warning(f"Файл {INJURY_FILE} не найден. Создайте его с таблицей ранений.")
        return default

# Глобальные переменные для таблиц (будут загружены при старте)
TABLES = load_tables()
INJURY_TABLE = load_injury()

def reload_tables():
    """Перезагружает таблицы из файлов (используется в /reload)."""
    global TABLES, INJURY_TABLE
    new_tables = load_tables()
    new_injury = load_injury()
    if new_tables:
        TABLES = new_tables
    else:
        logger.warning("Не удалось загрузить tables.json – таблицы не обновлены")
    if new_injury:
        INJURY_TABLE = new_injury
    else:
        logger.warning("Не удалось загрузить injury.json – таблица ранений не обновлена")
    return bool(new_tables) or bool(new_injury)

# ---- Утилита для извлечения комментария ----
def extract_comment(cmd):
    if '#' in cmd:
        clean, comment = cmd.rsplit('#', 1)
        return clean.strip(), comment.strip()
    return cmd, None

# ---- Функции для работы с таблицами ----
def roll_table(table_name):
    if table_name not in TABLES:
        available = ", ".join(TABLES.keys())
        return None, f"Таблица '{table_name}' не найдена. Доступные: {available}"
    table = TABLES[table_name]
    roll1 = random.randint(1, 6)
    roll2 = random.randint(1, 6)
    total = roll1 + roll2
    # Ожидаем, что в JSON значение для ключа – список [название, описание]
    entry = table.get(str(total))  # ключи в JSON – строки
    if entry is None:
        return None, f"Ошибка: для суммы {total} нет записи в таблице."
    name, description = entry
    result = f"2d6 → {roll1}+{roll2} = {total} — {name} — {description}"
    return result, None

def get_injury_description(result):
    """Возвращает (название_травмы, описание) по числовому результату D66."""
    key = str(result)
    if key in INJURY_TABLE:
        entry = INJURY_TABLE[key]
        if isinstance(entry, list) and len(entry) >= 2:
            return entry[0], entry[1]
        elif isinstance(entry, str):
            # Если сохранено только описание, используем его
            return "Injury", entry
    return "Unknown Injury", "No description available."

def roll_injury():
    units = random.randint(1, 6)
    tens = random.randint(1, 6)
    result = tens * 10 + units
    name, desc = get_injury_description(result)
    return result, units, tens, name, desc

# ---- Основные функции команд ----
def flip_coin():
    return "Орёл!" if random.choice([True, False]) else "Решка!"

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

# ---- Главный цикл ----
logger.info("Бот успешно запущен и слушает сообщения...")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        try:
            peer_id = event.object.message['peer_id']
            user_id = event.object.message['from_id']
            text = event.object.message['text'].strip()

            if not text:
                continue

            if text.startswith(('/', '!')):
                cmd_raw = text[1:].strip()
                if not cmd_raw:
                    msg = format_response(mention_user(user_id, peer_id), "Введите команду. Например: /d20")
                    send_message(user_id, msg, peer_id)
                    continue

                cmd_clean, comment = extract_comment(cmd_raw)
                parts = cmd_clean.split()
                if not parts:
                    msg = format_response(mention_user(user_id, peer_id), "Введите команду. Например: /d20")
                    send_message(user_id, msg, peer_id)
                    continue

                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                mention = mention_user(user_id, peer_id)

                # ---------- Обработка команд ----------
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
                        "/inj или /ранение — бросок на ранение по таблице Elites Injury Chart\n"
                        "/skill [таблица] или /навык [таблица] — бросок 2d6 по таблице (по умолчанию melee)\n"
                        "/table <таблица> — бросок по указанной таблице\n"
                        "/tables — список доступных таблиц\n"
                        "/ping — проверка работы\n"
                        "/reload — перезагрузить таблицы из файлов (только для владельца)\n"
                        "/help или !help — эта справка\n\n"
                        "**Комментарии:**\n"
                        "Добавьте `# текст` в конце команды для пояснения."
                    )
                    send_message(user_id, help_text, peer_id)

                elif command in ('coin', 'монетка'):
                    result = flip_coin()
                    msg = format_response(mention, f"Бросок монетки: {result}", comment)
                    send_message(user_id, msg, peer_id)

                elif command in ('rand', 'random'):
                    result, error = random_number(args)
                    if error:
                        msg = format_response(mention, f"Ошибка: {error}")
                    else:
                        msg = format_response(mention, f"Результат: {result}", comment)
                    send_message(user_id, msg, peer_id)

                elif command in ('inj', 'ранение', 'injury'):
                    result, units, tens, name, desc = roll_injury()
                    result_str = f"Бросок на ранение: {tens}+{units} = **{result}** — *{name}* — {desc}"
                    msg = format_response(mention, result_str, comment)
                    send_message(user_id, msg, peer_id)

                elif command in ('skill', 'навык'):
                    table_name = args[0].lower() if args else 'melee'
                    result, error = roll_table(table_name)
                    if error:
                        msg = format_response(mention, f"Ошибка: {error}")
                    else:
                        msg = format_response(mention, f"Бросок навыка ({table_name}): {result}", comment)
                    send_message(user_id, msg, peer_id)

                elif command == 'table':
                    if not args:
                        available = ", ".join(TABLES.keys())
                        msg = format_response(mention, f"Укажите имя таблицы. Доступные: {available}")
                    else:
                        table_name = args[0].lower()
                        result, error = roll_table(table_name)
                        if error:
                            msg = format_response(mention, f"Ошибка: {error}")
                        else:
                            msg = format_response(mention, f"Бросок по таблице {table_name}: {result}", comment)
                    send_message(user_id, msg, peer_id)

                elif command == 'tables':
                    available = ", ".join(TABLES.keys())
                    msg = format_response(mention, f"Доступные таблицы: {available}")
                    send_message(user_id, msg, peer_id)

                elif command == 'ping':
                    send_message(user_id, format_response(mention, "Pong! Бот работает."), peer_id)

                elif command == 'reload':
                    if OWNER_ID is None:
                        send_message(user_id, "Команда /reload отключена (не задан OWNER_ID).", peer_id)
                    elif user_id != OWNER_ID:
                        send_message(user_id, "У вас нет прав на использование /reload.", peer_id)
                    else:
                        success = reload_tables()
                        if success:
                            send_message(user_id, "Таблицы успешно перезагружены из файлов.", peer_id)
                        else:
                            send_message(user_id, "Не удалось перезагрузить таблицы. Проверьте файлы в папке data/.", peer_id)

                else:
                    # Всё остальное — бросок кубиков
                    result, error = parse_and_roll_multiple(cmd_clean)
                    if error:
                        msg = format_response(mention, f"Ошибка: {error}")
                    else:
                        msg = format_response(mention, f"Бросок {result}", comment)
                    send_message(user_id, msg, peer_id)

        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
            try:
                mention = mention_user(user_id, peer_id)
                send_message(user_id, f"{mention}⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
