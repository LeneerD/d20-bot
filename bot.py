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

if not VK_TOKEN:
    raise Exception("Переменная окружения VK_TOKEN не задана!")
if not GROUP_ID:
    raise Exception("Переменная окружения GROUP_ID не задана!")

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
    if comment:
        return f"{mention}{result} (комментарий: {comment})"
    return f"{mention}{result}"

# ---- Дефолтные таблицы (встроенные) ----
DEFAULT_TABLES = {
    "melee": {
        "2": ["Patron Skill", "Pick one of the Skills offered by your patron."],
        "3": ["Stand Firm", "The first time a model with this Skill suffers a Down result on the Injury table, it is treated as a Minor Hit result instead."],
        "4": ["Parry", "Add -1 Dice to Success Rolls for Melee Attacks that target a model with this Skill."],
        "5": ["Close Quarter Combat", "Add +1 Dice and +1 Injury Dice to rolls for Melee Attacks made by a model with this Skill if it is in contact with a terrain piece."],
        "6": ["Relentless Charge", "Add +1 Dice to rolls for Melee Attacks made by a model with this Skill if it successfully charged earlier in the same Activation."],
        "7": ["Melee Proficiency", "Add +1 Dice to the Melee Characteristic of a model with this Skill."],
        "8": ["Strength of Samson", "Add +1 Injury Dice to rolls for Melee Attacks using a Melee Weapon made by a model with this Skill. In addition, a model with this Skill has the Strong keyword."],
        "9": ["Hard as Nails", "The first time a model with this Skill suffers a Down result on the Injury table, it is treated as a No Effect result instead."],
        "10": ["Surgical Strike", "Once per Activation, before you make an Injury Roll for a Melee Attack made by a model with this Skill, you can say that the roll has the Ignore Armour Keyword."],
        "11": ["Champion", "Melee Weapons that do not have the Cleave Keyword which are used by a model with this Skill gain the Cleave 2 Keyword. In addition, add -1 Dice to the Success Roll for the second Melee Attack made with each Melee Weapon that gains the Cleave Keyword."],
        "12": ["Patron Skill", "Pick one of the Skills offered by your patron."]
    },
    "ranged": {
        "2": ["Patron Skill", "Pick one of the Skills offered by your patron."],
        "3": ["Hunter", "Ranged Attacks made by a model with this Skill have the Ignore COVER Keyword."],
        "4": ["Gunslinger", "The following rules apply to a model with this Skill if it is armed with Ranged Weapons with the Pistol Keyword.\n\nIf it is equipped with 2 Weapons with the Pistol Keyword, it can take a Shoot ACTION with one and then immediately take a Shoot ACTION with the other.\nAdd the Assault and Ignore OFF-HAND WEAPON Keywords to any weapons that have the Pistol Keyword (unless they have them already)."],
        "5": ["Far Shot", "Add 6\" to the Range of the following Weapons when they are used by a model that has this Skill:\n\n- Any Weapon with the Pistol Keyword.\n- Any Weapon which has the word “Rifle” as part of its name (i.e. a Bolt Action Rifle, Assault Rifle etc).\n- Any Weapon which has either the word “Jezzail” or “Arquebus” as part of its name."],
        "6": ["Sharp Eyes", "Ranged Attacks made by a model with this Skill have the Ignore LONG RANGE Keyword."],
        "7": ["Ranged Proficiency", "Add +1 Dice to the Ranged Characteristic of a model with this Skill."],
        "8": ["Sniper's Nest", "Add +2 Dice to rolls for Ranged Attacks made with the Elevated Position modifier by a model with this Skill instead of +1 Dice."],
        "9": ["Point Blank", "When a model with this Skill makes a Melee Attack, it can use a Ranged Weapon and its Ranged Attack Characteristic instead of a Melee Weapon and its Melee Attack Characteristic. It must still be within 1\" of the target model to make the attack. It can also use the Ranged Weapon to make a Ranged Attack during the same Activation if it has the Assault Keyword."],
        "10": ["Hip Shot", "Ranged Weapons used by a model with this Skill count as having the Assault Keyword unless they already have it."],
        "11": ["Head Shot", "Ranged Attacks made by a model with this Skill have the Ignore Armour Keyword if the attack was a Critical Success."],
        "12": ["Patron Skill", "Pick one of the Skills offered by your patron."]
    },
    "stealth": {
        "2": ["Patron Skill", "Pick one of the Skills offered by your patron."],
        "3": ["Sixth Sense", "If a model with this Skill suffers a Down result on the Injury table, it is treated as a Minor Hit result instead if the model does not have any Blood Markers. If the model also has the Tough Keyword, once per game it can use the Keyword to change an Out of Action result to a Down result, and then use this Skill to change the Down result to No Effect."],
        "4": ["Assassinate", "Add +1 Dice to rolls for attacks made by a model with this Skill if the target has not yet been Activated this Turn."],
        "5": ["Shadow Walker", "Add -2 Dice to rolls for Ranged Attacks that target a model with this Skill at Long Range instead of -1 Dice."],
        "6": ["Athletic", "Add +1 Dice to Risky Success rolls for a model with this Skill when it Climbs, Jumps or makes a Diving Charge, and add -1 Injury Dice to Injury Rolls if it Falls."],
        "7": ["Sprinter", "Add +1 Dice to the Risky Success Roll for a model with this Skill that is taking a Dash ACTION."],
        "8": ["Disengage", "Enemy models cannot make a Melee Attack on a model with this Skill when it Retreats."],
        "9": ["Incoming", "When you roll the Charge Bonus for a model with this Skill, roll 1 extra D6 and use the single highest dice to determine the bonus."],
        "10": ["Nimble", "Do not halve the Movement Characteristic of a model with this Skill when it stands up."],
        "11": ["Dodge", "Add -1 Dice to rolls for Ranged Attacks that target a model with this Skill."],
        "12": ["Patron Skill", "Pick one of the Skills offered by your patron."]
    },
    "wildcard": {
        "2": ["Patron Skill", "Pick one of the Skills offered by your patron."],
        "3": ["War Luck", "A model with this Skill can suffer 1 extra Battle Scar before they are Unfit for Duty."],
        "4": ["'Tis but a Scratch", "You can re-roll the result on the Trauma Chart for a model with this Skill."],
        "5": ["Bad Company", "A model with this Skill does not count towards the number of Elite models that are in your Warband at the start of the Promotion step."],
        "6": ["Scavenger", "A model with this Skill has the Extra Dice Exploration Skill."],
        "7": ["Skill & Expertise", "When you give a model this Skill, choose 1 Action on that model's Warband Entry, or 1 Common Action apart from Fight or Shoot ActionS, and write it on your Warband Roster. Add +1 Dice to rolls made as part of the chosen Action when they are taken by this model."],
        "8": ["Show Off", "Add 1 dice to the Promotion Pool in the Promotion step for each model in your Warband with this Skill."],
        "9": ["Friends In High Places", "A model with this Skill has the Re-roll Dice Exploration Skill."],
        "10": ["Glory Hound", "At the end of each game, your Warband receives 1 extra  for each model with this Skill that is on the battlefield."],
        "11": ["War Stories", "When you are recording the Experience Points earned by the models in your Warband in the Campaign Phase, you can give each model with the Elite Keyword that does not also have this Skill +1 extra Experience Point. You can’t pick the model with the Skill itself. A Warband can only have one model with this Skill."],
        "12": ["Patron Skill", "Pick one of the Skills offered by your patron."]
    }
}

DEFAULT_INJURY = {
    "11": ["Dead", "The wound proved to be fatal. Remove the model and its Battlekit from your Warband Roster."],
    "12": ["Captured", "The enemy captures the model. Before continuing the Trauma Step, you and your opponent from the game can negotiate a ransom price in  for the release of the model. If the ransom is not paid, the captured model is executed – remove them from your Warband Roster. If the ransom is paid, transfer the  from your Strongbox to your opponent’s, and treat this result as a Full Recovery. Continue with the Trauma Step after resolving the outcome of the ransom."],
    "13": ["Severe Nerve Damage", "All Success Rolls you take for this model are treated as being Risky Success Rolls, unless they are Risky Success Rolls already, in which case there is no additional penalty."],
    "14": ["Hand Wound", "Randomly determine which hand has been injured. Add -1 Dice to rolls for attacks made for this model with a Melee Weapon that is held (or jointly held) by the injured hand."],
    "15": ["Lost An Eye", "Add -1 Dice to rolls for Ranged Attacks made for this model. If this model receives this injury for a second time, they are blinded and you must remove them from your Warband Roster instead of re-rolling the result. Treat this injury as a Full Recovery if it is inflicted on a Sniper Priest."],
    "16": ["Chest Wound", "Add +1 Injury Dice to Injury Rolls for attacks that target this model."],
    "21": ["Insomniac", "This model must always be the first model you deploy in any game it takes part in, and loses the Infiltrator Keyword if it has it."],
    "22": ["Head Wound", "This model can no longer gain Experience Points. You can assign Promotion Dice to this model as if it were a Troop in the Promotions and Experience Step. If one of its assigned Promotion Dice rolls a “6”, it regains the ability to gain Experience Points, although the Battle Scar remains."],
    "23": ["Shell Shocked", "Roll a D6 the first time this model is deployed during a game. On a 1-2, add -1 Dice to rolls for this model for the rest of the game."],
    "24": ["Dark Memory", "Write down the name of the Warband from the game where this injury was received. Add -1 Dice to rolls for Melee Attacks made by this model if the target is a model from the Warband you have written down."],
    "25": ["Paranoid", "This model cannot be deployed within 8\" of a friendly model. Friendly models can be deployed within 8\" of this model after it has been deployed."],
    "26": ["Lost Arm", "This model cannot use Battlekit that requires 2 hands, and can only use one piece of Battlekit that requires 1 hand."],
    "31": ["Leg Wound", "Subtract 2\" from this model’s Movement Characteristic. In addition, add -1 Dice to the Risky Success Roll for this model when it takes a Dash Action."],
    "32": ["Expensive Treatment", "The model’s wounds require constant treatment. Before you can deploy this model, you must deduct 10  from your Warband’s Strongbox. This payment does not count towards your Warband’s Threshold Value."],
    "33": ["Possessed", "When this model is Activated, if it is more than 1” from any enemy models the first Action that it takes must take a Dash Action, even if another rule states that it cannot take a Dash Action. In addition, the first 3” of this move must be in a straight line directly away from its starting position, if it is possible for it to do so. If the model is Down at the start of the Activation, it will stand up if it can do so and must then attempt to move 3” in a straight line away from its starting position."],
    "34": ["Muscle Damage", "This model cannot have Battlekit that has the Heavy Keyword. Any that it has when the Injury is suffered is lost."],
    "35": ["Minor Wound", "This model cannot be used in the next game."],
    "36": ["Robbed", "All of the model’s Battlekit is lost, unless it is Battlekit that cannot be lost or removed during a campaign. It does not receive an Injury or a Battle Scar"],
    "41": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "42": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "43": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "44": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "45": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "46": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "47": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "48": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "49": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "50": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "51": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "52": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "53": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "54": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "55": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "56": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "57": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "58": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "59": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "60": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "61": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "62": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "63": ["Full Recovery", "The model has survived the battle with no ill effects. It does not receive an Injury or a Battle Scar."],
    "64": ["Hardened", "This model gains the Negate Fear Keyword. It does not receive an Injury or a Battle Scar."],
    "65": ["Bitter Lessons", "This model gains D3 extra Experience Points. It does not receive an Injury or a Battle Scar."],
    "66": ["Prominent Scar", "Write down the name of the Warband from the game where this injury was received. Add +1 Dice to rolls for Melee Attacks made by this model if the target is a model from the Warband you have written down. It does not receive an Injury or a Battle Scar."]
}

# ---- Загрузка таблиц из файлов в корне (если они есть) ----
TABLES_FILE = "tables.json"
INJURY_FILE = "injury.json"

def load_json_file(filename, default_dict):
    """Загружает JSON из файла, если он есть, иначе возвращает default_dict."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Загружен файл {filename}")
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения {filename}: {e}. Используются встроенные таблицы.")
            return default_dict
    else:
        logger.info(f"Файл {filename} не найден, используются встроенные таблицы.")
        return default_dict

# Глобальные таблицы (загружаем из файлов или используем дефолтные)
TABLES = load_json_file(TABLES_FILE, DEFAULT_TABLES)
INJURY_TABLE = load_json_file(INJURY_FILE, DEFAULT_INJURY)

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
    entry = table.get(str(total))
    if entry is None:
        return None, f"Ошибка: для суммы {total} нет записи в таблице."
    name, description = entry
    result = f"2d6 → {roll1}+{roll2} = {total} — {name} — {description}"
    return result, None

def get_injury_description(result):
    key = str(result)
    if key in INJURY_TABLE:
        entry = INJURY_TABLE[key]
        if isinstance(entry, list) and len(entry) >= 2:
            return entry[0], entry[1]
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

                else:
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
