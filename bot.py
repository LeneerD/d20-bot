import os
import json
import random
import re
import time
import logging
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from requests.exceptions import ReadTimeout, ConnectionError

# ---- Настройка логирования ----
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- Константы ----
CONSTANTS = {
    "max_dice": 100,
    "max_dice_type": 1000,
    "default_exploration_dice": 3,
}

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

# ---- Проверка донатера (VK Donut) ----
donor_cache = {}

def is_donor(user_id):
    user_id_str = str(user_id)
    if user_id_str in donor_cache:
        return donor_cache[user_id_str]
    try:
        response = vk.method('donut.isDon', {'user_id': user_id})
        donor_cache[user_id_str] = response
        return response
    except Exception as e:
        logger.error(f"Ошибка проверки доната для {user_id}: {e}")
        return False

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

def format_response(mention, main, details=None, comment=None):
    if details:
        parts = f"{main} ({details})"
    else:
        parts = main
    if comment:
        parts += f" 💬 {comment}"
    return f"{mention}{parts}"

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

# ---- Универсальный парсер бросков ----
def explode_dice(initial_value, dice_type, explode_type):
    total = initial_value
    current = initial_value
    while True:
        if explode_type == '!':
            if current == dice_type:
                new_roll = random.randint(1, dice_type)
                total += new_roll
                current = new_roll
            else:
                break
        elif explode_type == '!!':
            if current == dice_type or current == 1:
                new_roll = random.randint(1, dice_type)
                if current == dice_type:
                    total += new_roll
                else:
                    total -= new_roll
                current = new_roll
            else:
                break
    return total

def parse_single_component(comp):
    comp = comp.strip()
    if not comp:
        return None, "Пустой компонент", None

    comp = comp.replace('к', 'd').replace('К', 'd').replace('д', 'd').replace('Д', 'd')

    adv_dis_map = {
        'adv': 1, 'advantage': 1, 'пр': 1, 'преимущество': 1,
        'dis': -1, 'disadvantage': -1, 'пом': -1, 'помеха': -1
    }
    for kw in adv_dis_map:
        if comp.lower().startswith(kw):
            rest = comp[len(kw):]
            roll1, roll2 = random.randint(1, 20), random.randint(1, 20)
            result = max(roll1, roll2) if adv_dis_map[kw] == 1 else min(roll1, roll2)
            mods = re.findall(r'([+-]\d+)', rest)
            for mod in mods:
                result += int(mod)
            return result, None, None

    if 'd' not in comp:
        try:
            return int(comp), None, None
        except ValueError:
            return None, f"Неверный компонент: {comp}", None

    explode_type = None
    explode_count = 0
    explode_match = re.search(r'(!{1,2})(\d*)', comp)
    if explode_match:
        explode_type = explode_match.group(1)
        explode_count_str = explode_match.group(2)
        explode_count = int(explode_count_str) if explode_count_str else 1
        comp = comp[:explode_match.start()] + comp[explode_match.end():]

    resist = False
    if comp.endswith('r') or comp.endswith('с'):
        resist = True
        comp = comp[:-1]

    multiplier = 1
    mult_match = re.search(r'[x*](\d+)', comp)
    if mult_match:
        multiplier = int(mult_match.group(1))
        comp = comp[:mult_match.start()] + comp[mult_match.end():]

    mods = re.findall(r'([+-]\d+)', comp)
    for mod in mods:
        comp = comp.replace(mod, '')

    if 'd' not in comp:
        return None, "Отсутствует 'd' в компоненте", None
    parts = comp.split('d')
    if parts[0] == '':
        num_dice = 1
    else:
        try:
            num_dice = int(parts[0])
        except ValueError:
            return None, f"Некорректное количество костей: {parts[0]}", None

    dice_type_str = parts[1]
    if dice_type_str == '%':
        dice_type = 100
    else:
        try:
            dice_type = int(dice_type_str)
        except ValueError:
            return None, f"Некорректный тип кости: {dice_type_str}", None

    if num_dice > CONSTANTS["max_dice"] or dice_type > CONSTANTS["max_dice_type"] or num_dice <= 0 or dice_type <= 0:
        return None, "Некорректные параметры кубиков (макс: 100 шт, d1000)", None

    rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
    if explode_type:
        if explode_count > num_dice:
            explode_count = num_dice
        indices = random.sample(range(num_dice), explode_count) if explode_count > 0 else []
        total = 0
        for i, val in enumerate(rolls):
            if i in indices:
                total += explode_dice(val, dice_type, explode_type)
            else:
                total += val
    else:
        total = sum(rolls)

    for mod in mods:
        total += int(mod)
    total *= multiplier
    if resist:
        total //= 2

    details_parts = []
    if len(rolls) > 1:
        details_parts.append(", ".join(map(str, rolls)))
    else:
        details_parts.append(str(rolls[0]))
    if mods:
        details_parts.append(" ".join(mods))
    if multiplier != 1:
        details_parts.append(f"x{multiplier}")
    if resist:
        details_parts.append("/2")
    details = " ".join(details_parts)

    return total, None, details

def parse_expression(expr):
    if not expr:
        return None, "Пустое выражение", None
    parts = re.split(r'\s+', expr)
    total = 0
    all_details = []
    for part in parts:
        if not part:
            continue
        sign = 1
        if part.startswith('+'):
            sign = 1
            part = part[1:]
        elif part.startswith('-'):
            sign = -1
            part = part[1:]
        if not part:
            continue
        value, error, detail = parse_single_component(part)
        if error:
            return None, error, None
        total += sign * value
        if detail:
            all_details.append(f"{sign if sign == -1 else ''}{detail}")
    return total, None, " ; ".join(all_details) if all_details else None

# ---- Основные функции команд ----
def roll_table(table_name):
    if not TABLES:
        return None, "Таблицы навыков не загружены.", None
    if table_name not in TABLES:
        return None, f"Таблица '{table_name}' не найдена. Доступны: {', '.join(TABLES.keys())}", None

    roll1, roll2 = random.randint(1, 6), random.randint(1, 6)
    total = roll1 + roll2
    entry = TABLES[table_name].get(str(total))
    if not entry:
        return None, f"Для суммы {total} нет записи в таблице.", None

    name, desc = entry if isinstance(entry, list) and len(entry) >= 2 else (entry, "")
    result = f"2d6 → {roll1}+{roll2} = {total} — {name} — {desc}"
    return result, None, None

def roll_spark(number=None):
    if not SPARK_TABLE:
        return None, "Таблица Spark не загружена.", None
    if number is not None:
        key = str(number)
        if key in SPARK_TABLE:
            return number, SPARK_TABLE[key], None
        else:
            return None, f"Запись {number} не найдена", None
    roll = random.randint(1, SPARK_MAX_KEY)
    return roll, SPARK_TABLE[str(roll)], None

def roll_exploration(category, num_dice=None, modifier=0, direct_value=None):
    if category not in EXPLORATION_TABLES:
        return None, f"Неизвестная категория '{category}'. Доступны: common, rare, legendary", None
    table = EXPLORATION_TABLES[category]
    if not table:
        return None, f"Таблица '{category}' не загружена.", None

    if direct_value is not None:
        total = direct_value
        desc = table.get(str(total))
        result = f"Значение {total} из таблицы {category.capitalize()}\nДукаты: {total * 10}"
        if desc:
            result += f"\nОписание: {desc}"
        return result, None, None

    if num_dice is None:
        num_dice = CONSTANTS["default_exploration_dice"]
    rolls = [random.randint(1, 6) for _ in range(max(1, num_dice))]
    total = sum(rolls) + modifier
    desc = table.get(str(total))
    result = f"Бросок {len(rolls)}d6: {', '.join(map(str, rolls))}"
    if modifier:
        result += f" {modifier:+d}"
    result += f" = {total}\nДукаты: {total * 10}"
    if desc:
        result += f"\nОписание: {desc}"
    return result, None, None

def roll_injury():
    units, tens = random.randint(1, 6), random.randint(1, 6)
    result = tens * 10 + units
    entry = INJURY_TABLE.get(str(result), ["Unknown", "No description"])
    return result, entry[0], entry[1]

def roll_d66():
    tens = random.randint(1, 6)
    units = random.randint(1, 6)
    result = tens * 10 + units
    return result, f"{tens}+{units}"

def flip_coin():
    return "Орёл!" if random.choice([True, False]) else "Решка!"

def random_number(args):
    if not args:
        return random.randint(0, 100), None
    if len(args) == 2:
        try:
            a, b = sorted(map(int, args[:2]))
            return random.randint(a, b), None
        except ValueError:
            return None, "Введите два целых числа. Пример: /rand 1 100"
    return None, "Укажите два числа через пробел. Пример: /rand 1 100"

def generate_stats():
    stats = []
    for _ in range(6):
        rolls = [random.randint(1, 6) for _ in range(4)]
        rolls.sort()
        stats.append(sum(rolls[1:]))
    return stats

# ---- Обработчики команд ----
def handle_help(mention, args, comment):
    help_text = (
        "🎲 *Команды бота:*\n\n"
        "*Бросок кубиков* (можно через /):\n"
        "/d20 или /к20 — бросить 20-гранный кубик\n"
        "/2d6+1d20+5 — несколько кубиков разных типов\n"
        "/d100-3 или /к100-3 — d100 с модификатором\n"
        "/d66 — бросок D66 (две шестёрки, первая – десятки, вторая – единицы)\n"
        "/d% или /к% — бросок процентной кости (1-100)\n\n"
        "*Расширенные броски:*\n"
        "/<выражение> — поддерживает:\n"
        "  - множители: x{N} или *{N} (например, /4d8-3x10)\n"
        "  - резист: r или с в конце (деление на 2, округление вниз)\n"
        "  - взрывные: ! или !! с количеством костей (например, /6d6!2)\n"
        "  - преимущество/помеха: /adv или /dis (или русские /пр, /пом)\n"
        "  - комбинирование через пробел или +/-\n"
        "  - пример: /4d8-3x10r -2d6+4 d% 6d6!!2\n\n"
        "*Специальные команды:*\n"
        "/s или /scores или /х, /характеристики — генерация шести характеристик (4d6, сумма трёх наибольших)\n"
        "/coin или /монетка — подбросить монетку\n"
        "/rand 1 100 — случайное число в диапазоне\n"
        "/inj или /ранение — бросок на ранение по таблице Elites Injury Chart (D66)\n"
        "/spark [номер] — показать описание прокачки Spark (если номер не указан — случайный бросок)\n"
        "/skill [таблица] — бросок 2d6 по таблице прокачки Trench Crusade (по умолчанию melee)\n"
        "/table <таблица> — бросок по указанной таблице\n"
        "/tables — список доступных таблиц\n"
        "/exp <common|rare|legendary> [Xd6 или число+d6 или просто число] — бросок по таблице Exploration (по умолчанию 3d6). Если указать просто число, выводится описание для этого числа.\n"
        "/ping — проверка работы\n"
        "/reload — перезагрузить таблицы (только для владельца)\n"
        "/help — эта справка\n\n"
        "*Эксклюзивные команды для донатеров VK Donut:*\n"
        "/donate_roll или /донат_бросок — эксклюзивный бросок 4d6\n"
        "/donate_stats или /донат_статы — генерация 7 характеристик (вместо 6)\n"
        "/donate_spark или /донат_искра — бросок по таблице Spark с бонусом +5 (или просмотр конкретной прокачки по номеру)\n\n"
        "*Комментарии:*\nДобавьте `# текст` в конце команды для пояснения."
    )
    return help_text, None, None

def handle_coin(mention, args, comment):
    return f"Бросок монетки: {flip_coin()}", None, None

def handle_rand(mention, args, comment):
    result, error = random_number(args)
    if error:
        return f"Ошибка: {error}", None, None
    return f"Случайное число: {result}", None, None

def handle_inj(mention, args, comment):
    result, name, desc = roll_injury()
    return f"Бросок на ранение: {result} — {name}", desc, None

def handle_d66(mention, args, comment):
    result, details = roll_d66()
    return f"Бросок D66: {result}", details, None

def handle_spark(mention, args, comment):
    if args:
        try:
            num = int(args[0])
        except ValueError:
            return "Ошибка: укажите число. Пример: /spark 42", None, None
        roll, result = roll_spark(num)
    else:
        roll, result = roll_spark()
    if roll is None:
        return f"Ошибка: {result}", None, None
    return f"Бросок d{SPARK_MAX_KEY}: {roll} — {result}", None, None

def handle_skill(mention, args, comment):
    table_name = args[0] if args else 'melee'
    result, error, _ = roll_table(table_name)
    if error:
        return f"Ошибка: {error}", None, None
    return f"Бросок навыка ({table_name}): {result}", None, None

def handle_table(mention, args, comment):
    if not args:
        available = ", ".join(TABLES.keys()) if TABLES else "нет загруженных таблиц"
        return f"Укажите имя таблицы. Доступные: {available}", None, None
    table_name = args[0]
    result, error, _ = roll_table(table_name)
    if error:
        return f"Ошибка: {error}", None, None
    return f"Бросок по таблице {table_name}: {result}", None, None

def handle_tables(mention, args, comment):
    if TABLES:
        return f"Доступные таблицы: {', '.join(TABLES.keys())}", None, None
    return "Таблицы навыков не загружены. Проверьте файл tables.json.", None, None

def handle_ping(mention, args, comment):
    return "Pong! Бот работает.", None, None

def handle_reload(mention, args, comment, user_id):
    if OWNER_ID is None:
        return "Команда /reload отключена (не задан OWNER_ID).", None, None
    if user_id != OWNER_ID:
        return "У вас нет прав на использование /reload.", None, None
    success = reload_tables()
    if success:
        return "Таблицы успешно перезагружены из файлов.", None, None
    return "Не удалось перезагрузить таблицы. Проверьте файлы.", None, None

def handle_stats(mention, args, comment):
    stats = generate_stats()
    return f"Характеристики: {', '.join(map(str, stats))}", None, None

def handle_dpercent(mention, args, comment):
    result, error, details = parse_expression("d%")
    if error:
        return f"Ошибка: {error}", None, None
    return f"Бросок процентной кости: {result}", details, None

def handle_adv(mention, args, comment):
    expr = ' '.join(args) if args else ''
    full_expr = f"adv {expr}" if expr else "adv"
    result, error, details = parse_expression(full_expr)
    if error:
        return f"Ошибка: {error}", None, None
    return f"Бросок с преимуществом: {result}", details, None

def handle_dis(mention, args, comment):
    expr = ' '.join(args) if args else ''
    full_expr = f"dis {expr}" if expr else "dis"
    result, error, details = parse_expression(full_expr)
    if error:
        return f"Ошибка: {error}", None, None
    return f"Бросок с помехой: {result}", details, None

def handle_exp(mention, args, comment):
    if not args:
        return "Укажите категорию: common, rare или legendary. Пример: /exp common 3d6 или /exp common 10", None, None
    category = args[0].lower()
    if category not in ('common', 'rare', 'legendary'):
        return f"Неверная категория. Доступные: common, rare, legendary.", None, None

    if len(args) == 1:
        result, error, _ = roll_exploration(category, num_dice=CONSTANTS["default_exploration_dice"])
        if error:
            return f"Ошибка: {error}", None, None
        return result, None, None

    expr = args[1].lower().replace(' ', '')
    if expr.isdigit():
        try:
            direct_val = int(expr)
            if direct_val < 0:
                raise ValueError
            result, error, _ = roll_exploration(category, direct_value=direct_val)
            if error:
                return f"Ошибка: {error}", None, None
            return result, None, None
        except ValueError:
            return "Ошибка: укажите положительное целое число.", None, None

    if 'd' not in expr:
        return "Ошибка: укажите выражение с d (например, 3d6) или простое число.", None, None

    num_dice = CONSTANTS["default_exploration_dice"]
    modifier = 0
    mod_match = re.search(r'([+-]\d+)$', expr)
    if mod_match:
        modifier = int(mod_match.group(1))
        expr = expr[:mod_match.start()]
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
                return "Ошибка: некорректное число кубиков. Пример: 3d6 или 11+d6.", None, None
    else:
        return "Ошибка: выражение должно содержать d. Пример: 3d6 или 11+d6.", None, None

    result, error, _ = roll_exploration(category, num_dice, modifier)
    if error:
        return f"Ошибка: {error}", None, None
    return result, None, None

# ---- Эксклюзивные команды для донатеров ----
def handle_donate_roll(mention, args, comment, user_id):
    if not is_donor(user_id):
        return "Этот функционал доступен только донатерам! Оформите подписку VK Donut.", None, None
    rolls = [random.randint(1, 6) for _ in range(4)]
    total = sum(rolls)
    return f"Эксклюзивный бросок 4d6: {total}", ", ".join(map(str, rolls)), None

def handle_donate_stats(mention, args, comment, user_id):
    if not is_donor(user_id):
        return "Этот функционал доступен только донатерам! Оформите подписку VK Donut.", None, None
    stats = []
    for _ in range(7):
        rolls = [random.randint(1, 6) for _ in range(4)]
        rolls.sort()
        stats.append(sum(rolls[1:]))
    return f"Эксклюзивные характеристики (7 шт): {', '.join(map(str, stats))}", None, None

def handle_donate_spark(mention, args, comment, user_id):
    if not is_donor(user_id):
        return "Этот функционал доступен только донатерам! Оформите подписку VK Donut.", None, None
    if not SPARK_TABLE:
        return "Таблица Spark не загружена.", None, None
    if args:
        try:
            num = int(args[0])
        except ValueError:
            return "Ошибка: укажите число. Пример: /donate_spark 42", None, None
        if str(num) in SPARK_TABLE:
            return f"Прокачка Spark #{num}: {SPARK_TABLE[str(num)]}", None, None
        else:
            return f"Запись {num} не найдена.", None, None
    else:
        roll = random.randint(1, SPARK_MAX_KEY)
        modified = min(roll + 5, SPARK_MAX_KEY)
        desc = SPARK_TABLE.get(str(modified), "Описание отсутствует")
        return f"Эксклюзивный бросок d{SPARK_MAX_KEY} с бонусом +5: {modified} (исходный бросок: {roll}) — {desc}", None, None

# ---- Словарь команд ----
COMMAND_HANDLERS = {
    "help": handle_help,
    "помощь": handle_help,
    "coin": handle_coin,
    "монетка": handle_coin,
    "rand": handle_rand,
    "random": handle_rand,
    "inj": handle_inj,
    "ранение": handle_inj,
    "injury": handle_inj,
    "d66": handle_d66,
    "spark": handle_spark,
    "skill": handle_skill,
    "навык": handle_skill,
    "table": handle_table,
    "tables": handle_tables,
    "ping": handle_ping,
    "exp": handle_exp,
    "reload": handle_reload,
    "s": handle_stats,
    "scores": handle_stats,
    "х": handle_stats,
    "характеристики": handle_stats,
    "d%": handle_dpercent,
    "к%": handle_dpercent,
    "adv": handle_adv,
    "advantage": handle_adv,
    "пр": handle_adv,
    "преимущество": handle_adv,
    "dis": handle_dis,
    "disadvantage": handle_dis,
    "пом": handle_dis,
    "помеха": handle_dis,
    "donate_roll": handle_donate_roll,
    "донат_бросок": handle_donate_roll,
    "donate_stats": handle_donate_stats,
    "донат_статы": handle_donate_stats,
    "donate_spark": handle_donate_spark,
    "донат_искра": handle_donate_spark,
}

# ---- Главный цикл с обработкой ошибок ----
logger.info("Бот успешно запущен и слушает сообщения...")
while True:
    try:
        for event in longpoll.listen():
            try:
                # Проверяем, что это событие нового сообщения
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue
                if not event.object or not event.object.message:
                    continue

                peer_id = event.object.message.get('peer_id')
                user_id = event.object.message.get('from_id')
                text = event.object.message.get('text')
                if not text:
                    continue

                text = text.strip()
                if not text.startswith('/'):
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
                    handler = COMMAND_HANDLERS[command]
                    # Команды, требующие user_id
                    if command in ("reload", "donate_roll", "донат_бросок", "donate_stats", "донат_статы", "donate_spark", "донат_искра"):
                        main, details, _ = handler(mention, args, comment, user_id)
                    else:
                        main, details, _ = handler(mention, args, comment)
                    send_message(user_id, format_response(mention, main, details, comment), peer_id)
                else:
                    result, error, details = parse_expression(cmd_clean)
                    if error:
                        send_message(user_id, format_response(mention, f"Ошибка: {error}", None, comment), peer_id)
                    else:
                        main = f"бросок {cmd_clean}: {result}"
                        send_message(user_id, format_response(mention, main, details, comment), peer_id)

            except Exception as e:
                logger.error(f"Ошибка обработки события: {e}")
                continue
    except (ReadTimeout, ConnectionError, Exception) as e:
        logger.error(f"Ошибка соединения с VK: {e}. Переподключение через 5 секунд...")
        time.sleep(5)
        longpoll = init_longpoll_with_retry(vk_session, GROUP_ID)
