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
OWNER_ID = os.environ.get("OWNER_ID")

if not VK_TOKEN or not GROUP_ID:
    raise Exception("VK_TOKEN и GROUP_ID должны быть заданы в переменных окружения!")

try:
    GROUP_ID = int(GROUP_ID)
    OWNER_ID = int(OWNER_ID) if OWNER_ID else None
except ValueError:
    raise Exception("GROUP_ID и OWNER_ID должны быть целыми числами!")

if OWNER_ID is None:
    logger.warning("OWNER_ID не задан – команда /reload будет недоступна")

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

# ---- Утилиты ----
NICKNAMES_FILE = "nicknames.json"

def load_nicknames():
    try:
        with open(NICKNAMES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
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
            user = vk.users.get(user_ids=user_id, fields=[])[0]
            user_cache[user_id] = user['first_name']
        except:
            user_cache[user_id] = f"Пользователь {user_id}"
    return user_cache[user_id]

def mention_user(user_id, peer_id):
    if peer_id != user_id:
        return f"[id{user_id}|{get_user_name(user_id)}], "
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
        logger.error(f"Ошибка отправки: {e}")

def format_response(mention, result, comment=None):
    if comment:
        return f"{mention}{result} (комментарий: {comment})"
    return f"{mention}{result}"

def extract_comment(cmd):
    if '#' in cmd:
        clean, comment = cmd.rsplit('#', 1)
        return clean.strip(), comment.strip()
    return cmd, None

# ---- Загрузчик таблиц ----
TABLE_FILES = {
    "tables": "tables.json",
    "injury": "injury.json",
    "spark": "spark.json",
    "exploration": "exploration.json"
}

def load_json_file(filename, default=None):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Загружен файл {filename}")
            return data
    except FileNotFoundError:
        logger.warning(f"Файл {filename} не найден")
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Ошибка чтения {filename}: {e}")
    return default if default is not None else {}

# Глобальные таблицы
TABLES = load_json_file(TABLE_FILES["tables"])
INJURY_TABLE = load_json_file(TABLE_FILES["injury"])
SPARK_TABLE = load_json_file(TABLE_FILES["spark"])
EXPLORATION_DATA = load_json_file(TABLE_FILES["exploration"])
EXPLORATION_TABLES = {
    "common": EXPLORATION_DATA.get("common", {}),
    "rare": EXPLORATION_DATA.get("rare", {}),
    "legendary": EXPLORATION_DATA.get("legendary", {})
}
SPARK_MAX_KEY = max(map(int, SPARK_TABLE.keys())) if SPARK_TABLE else 0

def reload_tables():
    global TABLES, INJURY_TABLE, SPARK_TABLE, SPARK_MAX_KEY, EXPLORATION_TABLES
    tables = load_json_file(TABLE_FILES["tables"])
    injury = load_json_file(TABLE_FILES["injury"])
    spark = load_json_file(TABLE_FILES["spark"])
    exploration = load_json_file(TABLE_FILES["exploration"])
    if tables:
        TABLES = tables
    if injury:
        INJURY_TABLE = injury
    if spark:
        SPARK_TABLE = spark
        SPARK_MAX_KEY = max(map(int, SPARK_TABLE.keys())) if SPARK_TABLE else 0
    if exploration:
        EXPLORATION_TABLES = {
            "common": exploration.get("common", {}),
            "rare": exploration.get("rare", {}),
            "legendary": exploration.get("legendary", {})
        }
    return any((tables, injury, spark, exploration))

# ---- Основные функции команд ----
def roll_dice(expression):
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
                num, dice = 1, int(part[1:])
            else:
                num_str, dice_str = part.split('d')
                num = int(num_str) if num_str else 1
                dice = int(dice_str)

            if num > 100 or dice > 1000 or num <= 0 or dice <= 0:
                return None, "Некорректные параметры кубиков (макс: 100 шт, d1000)"

            rolls = [random.randint(1, dice) for _ in range(num)]
            subtotal = sum(rolls) * sign
            total += subtotal
            detail = f"{part}=({','.join(map(str, rolls))})" if num > 1 else f"{part}={rolls[0]}"
            if sign == -1:
                detail = '-' + detail
            details.append(detail)
        else:
            val = int(part) * sign
            total += val
            if val > 0:
                details.append(f"+{val}")
            elif val < 0:
                details.append(str(val))

    return f"{expression} → результат * {total} * ({' '.join(details)})", None

def roll_table(table_name):
    if not TABLES:
        return None, "Таблицы навыков не загружены."
    if table_name not in TABLES:
        return None, f"Таблица '{table_name}' не найдена. Доступны: {', '.join(TABLES.keys())}"

    roll1, roll2 = random.randint(1, 6), random.randint(1, 6)
    total = roll1 + roll2
    entry = TABLES[table_name].get(str(total))
    if not entry:
        return None, f"Для суммы {total} нет записи в таблице."

    name, desc = entry if isinstance(entry, list) and len(entry) >= 2 else (entry, "")
    return f"2d6 → {roll1}+{roll2} = {total} — {name} — {desc}", None

def roll_spark(number=None):
    if not SPARK_TABLE:
        return None, "Таблица Spark не загружена."
    if number is not None:
        key = str(number)
        if key in SPARK_TABLE:
            return number, SPARK_TABLE[key]
        else:
            return None, f"Запись {number} не найдена"
    roll = random.randint(1, SPARK_MAX_KEY)
    return roll, SPARK_TABLE[str(roll)]

def roll_exploration(category, num_dice=None, modifier=0, direct_value=None):
    if category not in EXPLORATION_TABLES:
        return None, f"Неизвестная категория '{category}'. Доступны: common, rare, legendary"
    table = EXPLORATION_TABLES[category]
    if not table:
        return None, f"Таблица '{category}' не загружена."

    if direct_value is not None:
        total = direct_value
        desc = table.get(str(total))
        result = f"Значение {total} из таблицы {category.capitalize()}\nДукаты: **{total * 10}**"
        if desc:
            result += f"\nОписание: {desc}"
        return result, None

    if num_dice is None:
        num_dice = 3
    rolls = [random.randint(1, 6) for _ in range(max(1, num_dice))]
    total = sum(rolls) + modifier
    desc = table.get(str(total))
    result = f"Бросок {len(rolls)}d6: {', '.join(map(str, rolls))}"
    if modifier:
        result += f" {modifier:+d}"
    result += f" = **{total}**\nДукаты: **{total * 10}**"
    if desc:
        result += f"\nОписание: {desc}"
    return result, None

def roll_injury():
    units, tens = random.randint(1, 6), random.randint(1, 6)
    result = tens * 10 + units
    entry = INJURY_TABLE.get(str(result), ["Unknown", "No description"])
    return result, units, tens, entry[0], entry[1]

def flip_coin():
    return "Орёл!" if random.choice([True, False]) else "Решка!"

def random_number(args):
    if not args:
        return f"🔢 Случайное число от 0 до 100: **{random.randint(0, 100)}**", None
    if len(args) == 2:
        try:
            a, b = sorted(map(int, args[:2]))
            return f"🔢 Случайное число от {a} до {b}: **{random.randint(a, b)}**", None
        except ValueError:
            return None, "Введите два целых числа. Пример: /rand 1 100"
    return None, "Укажите два числа через пробел. Пример: /rand 1 100"

# ---- Обработчики команд (функции) ----
def cmd_help(user_id, peer_id, mention, args, comment):
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
        "/spark [номер] — показать описание прокачки Spark (если номер не указан — случайный бросок)\n"
        "/skill [таблица] — бросок 2d6 по таблице прокачки Trench Crusade (по умолчанию melee)\n"
        "/table <таблица> — бросок по указанной таблице\n"
        "/tables — список доступных таблиц\n"
        "/exp <common|rare|legendary> [Xd6 или число+d6 или просто число] — бросок по таблице Exploration (по умолчанию 3d6). Если указать просто число, выводится описание для этого числа.\n"
        "/ping — проверка работы\n"
        "/reload — перезагрузить таблицы (только для владельца)\n"
        "/help — эта справка\n\n"
        "**Комментарии:**\nДобавьте `# текст` в конце команды для пояснения."
    )
    send_message(user_id, help_text, peer_id)

def cmd_coin(user_id, peer_id, mention, args, comment):
    result = flip_coin()
    send_message(user_id, format_response(mention, f"Бросок монетки: {result}", comment), peer_id)

def cmd_rand(user_id, peer_id, mention, args, comment):
    result, error = random_number(args)
    if error:
        send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, f"Результат: {result}", comment), peer_id)

def cmd_inj(user_id, peer_id, mention, args, comment):
    result, units, tens, name, desc = roll_injury()
    send_message(user_id, format_response(mention, f"Бросок на ранение: {tens}+{units} = **{result}** — *{name}* — {desc}", comment), peer_id)

def cmd_spark(user_id, peer_id, mention, args, comment):
    if args:
        try:
            num = int(args[0])
        except ValueError:
            send_message(user_id, format_response(mention, "Ошибка: укажите число. Пример: /spark 42", comment), peer_id)
            return
        roll, result = roll_spark(num)
    else:
        roll, result = roll_spark()
    if roll is None:
        send_message(user_id, format_response(mention, f"Ошибка: {result}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, f"Бросок d{SPARK_MAX_KEY}: **{roll}** — {result}", comment), peer_id)

def cmd_skill(user_id, peer_id, mention, args, comment):
    table_name = args[0] if args else 'melee'
    result, error = roll_table(table_name)
    if error:
        send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, f"Бросок навыка ({table_name}): {result}", comment), peer_id)

def cmd_table(user_id, peer_id, mention, args, comment):
    if not args:
        available = ", ".join(TABLES.keys()) if TABLES else "нет загруженных таблиц"
        send_message(user_id, format_response(mention, f"Укажите имя таблицы. Доступные: {available}", comment), peer_id)
        return
    table_name = args[0]
    result, error = roll_table(table_name)
    if error:
        send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, f"Бросок по таблице {table_name}: {result}", comment), peer_id)

def cmd_tables(user_id, peer_id, mention, args, comment):
    if TABLES:
        available = ", ".join(TABLES.keys())
        send_message(user_id, format_response(mention, f"Доступные таблицы: {available}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, "Таблицы навыков не загружены. Проверьте файл tables.json.", comment), peer_id)

def cmd_ping(user_id, peer_id, mention, args, comment):
    send_message(user_id, format_response(mention, "Pong! Бот работает.", comment), peer_id)

def cmd_reload(user_id, peer_id, mention, args, comment):
    if OWNER_ID is None:
        send_message(user_id, format_response(mention, "Команда /reload отключена (не задан OWNER_ID).", comment), peer_id)
    elif user_id != OWNER_ID:
        send_message(user_id, format_response(mention, "У вас нет прав на использование /reload.", comment), peer_id)
    else:
        success = reload_tables()
        if success:
            send_message(user_id, format_response(mention, "Таблицы успешно перезагружены из файлов.", comment), peer_id)
        else:
            send_message(user_id, format_response(mention, "Не удалось перезагрузить таблицы. Проверьте файлы.", comment), peer_id)

def cmd_exp(user_id, peer_id, mention, args, comment):
    if not args:
        send_message(user_id, format_response(mention, "Укажите категорию: common, rare или legendary. Пример: /exp common 3d6 или /exp common 10", comment), peer_id)
        return
    category = args[0].lower()
    if category not in ('common', 'rare', 'legendary'):
        send_message(user_id, format_response(mention, f"Неверная категория. Доступные: common, rare, legendary.", comment), peer_id)
        return

    # Если второй аргумент отсутствует, используем по умолчанию 3d6
    if len(args) == 1:
        result, error = roll_exploration(category, num_dice=3)
        if error:
            send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
        else:
            send_message(user_id, format_response(mention, result, comment), peer_id)
        return

    expr = args[1].lower().replace(' ', '')

    # Проверяем, является ли expr целым числом (прямой запрос)
    if expr.isdigit():
        try:
            direct_val = int(expr)
            if direct_val < 0:
                raise ValueError
            result, error = roll_exploration(category, direct_value=direct_val)
            if error:
                send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
            else:
                send_message(user_id, format_response(mention, result, comment), peer_id)
        except ValueError:
            send_message(user_id, format_response(mention, "Ошибка: укажите положительное целое число.", comment), peer_id)
        return

    # Проверяем на наличие d
    if 'd' not in expr:
        send_message(user_id, format_response(mention, "Ошибка: укажите выражение с d (например, 3d6) или простое число.", comment), peer_id)
        return

    # Парсим как бросок с модификатором
    num_dice = 3
    modifier = 0
    # Ищем модификатор
    mod_match = re.search(r'([+-]\d+)$', expr)
    if mod_match:
        modifier = int(mod_match.group(1))
        expr = expr[:mod_match.start()]  # удаляем модификатор
    if 'd' in expr:
        parts = expr.split('d')
        if parts[0] == '':
            num_dice = 1
        else:
            try:
                num_dice = int(parts[0])
                if num_dice < 1:
                    raise ValueError
            except ValueError:
                send_message(user_id, format_response(mention, "Ошибка: некорректное число кубиков. Пример: 3d6 или 11+d6.", comment), peer_id)
                return
    else:
        send_message(user_id, format_response(mention, "Ошибка: выражение должно содержать d. Пример: 3d6 или 11+d6.", comment), peer_id)
        return

    result, error = roll_exploration(category, num_dice, modifier)
    if error:
        send_message(user_id, format_response(mention, f"Ошибка: {error}", comment), peer_id)
    else:
        send_message(user_id, format_response(mention, result, comment), peer_id)

# ---- Словарь команд ----
COMMAND_HANDLERS = {
    "help": cmd_help,
    "помощь": cmd_help,
    "coin": cmd_coin,
    "монетка": cmd_coin,
    "rand": cmd_rand,
    "random": cmd_rand,
    "inj": cmd_inj,
    "ранение": cmd_inj,
    "injury": cmd_inj,
    "spark": cmd_spark,
    "skill": cmd_skill,
    "навык": cmd_skill,
    "table": cmd_table,
    "tables": cmd_tables,
    "ping": cmd_ping,
    "exp": cmd_exp,
    "reload": cmd_reload
}

# ---- Главный цикл ----
logger.info("Бот успешно запущен и слушает сообщения...")
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        try:
            peer_id = event.object.message['peer_id']
            user_id = event.object.message['from_id']
            text = event.object.message['text'].strip()

            if not text or not text.startswith(('/', '!')):
                continue

            cmd_raw = text[1:].strip()
            if not cmd_raw:
                send_message(user_id, format_response(mention_user(user_id, peer_id), "Введите команду. Например: /d20"), peer_id)
                continue

            cmd_clean, comment = extract_comment(cmd_raw)
            parts = cmd_clean.split()
            if not parts:
                send_message(user_id, format_response(mention_user(user_id, peer_id), "Введите команду. Например: /d20"), peer_id)
                continue

            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            mention = mention_user(user_id, peer_id)

            if command in COMMAND_HANDLERS:
                COMMAND_HANDLERS[command](user_id, peer_id, mention, args, comment)
            else:
                # Попытка интерпретировать как бросок кубика
                result, error = roll_dice(cmd_clean)
                if error:
                    send_message(user_id, format_response(mention, f"Ошибка: {error}"), peer_id)
                else:
                    send_message(user_id, format_response(mention, f"Бросок {result}", comment), peer_id)

        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
            try:
                mention = mention_user(user_id, peer_id)
                send_message(user_id, f"{mention}⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
