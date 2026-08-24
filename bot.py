import os
import json
import random
import re
import time
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

# ----------------------------------------------
# 1. Переменные окружения и инициализация
# ----------------------------------------------
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

vk_session = vk_api.VkApi(token=VK_TOKEN)

def init_longpoll_with_retry(session, group_id, retries=5, delay=3):
    for attempt in range(1, retries + 1):
        try:
            longpoll = VkBotLongPoll(session, group_id)
            print(f"✅ LongPoll успешно инициализирован (попытка {attempt})")
            return longpoll
        except Exception as e:
            print(f"⚠️ Ошибка инициализации LongPoll (попытка {attempt}/{retries}): {e}")
            if attempt == retries:
                raise
            time.sleep(delay)

longpoll = init_longpoll_with_retry(vk_session, GROUP_ID)
vk = vk_session.get_api()

# ----------------------------------------------
# 2. Кастомные имена (nicknames.json)
# ----------------------------------------------
NICKNAMES_FILE = "nicknames.json"

def load_nicknames():
    if os.path.exists(NICKNAMES_FILE):
        try:
            with open(NICKNAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Ошибка чтения nicknames.json: {e}. Используется пустой словарь.")
            return {}
    return {}

def save_nicknames(data):
    try:
        with open(NICKNAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"⚠️ Ошибка сохранения nicknames.json: {e}")

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
# 3. Утилита для извлечения комментария
# ----------------------------------------------
def extract_comment(cmd):
    if '#' in cmd:
        clean, comment = cmd.rsplit('#', 1)
        return clean.strip(), comment.strip()
    return cmd, None

# ----------------------------------------------
# 4. Таблицы навыков (четыре таблицы) - без звёздочек
# ----------------------------------------------
TABLES = {
    "melee": {
        2: ("Patron Skill", "Pick one of the Skills offered by your patron."),
        3: ("Stand Firm", "The first time a model with this Skill suffers a Down result on the Injury table, it is treated as a Minor Hit result instead."),
        4: ("Parry", "Add -1 Dice to Success Rolls for Melee Attacks that target a model with this Skill."),
        5: ("Close Quarter Combat", "Add +1 Dice and +1 Injury Dice to rolls for Melee Attacks made by a model with this Skill if it is in contact with a terrain piece."),
        6: ("Relentless Charge", "Add +1 Dice to rolls for Melee Attacks made by a model with this Skill if it successfully charged earlier in the same Activation."),
        7: ("Melee Proficiency", "Add +1 Dice to the Melee Characteristic of a model with this Skill."),
        8: ("Strength of Samson", "Add +1 Injury Dice to rolls for Melee Attacks using a Melee Weapon made by a model with this Skill. In addition, a model with this Skill has the Strong keyword."),
        9: ("Hard as Nails", "The first time a model with this Skill suffers a Down result on the Injury table, it is treated as a No Effect result instead."),
        10: ("Surgical Strike", "Once per Activation, before you make an Injury Roll for a Melee Attack made by a model with this Skill, you can say that the roll has the Ignore Armour Keyword."),
        11: ("Champion", "Melee Weapons that do not have the Cleave Keyword which are used by a model with this Skill gain the Cleave 2 Keyword. In addition, add -1 Dice to the Success Roll for the second Melee Attack made with each Melee Weapon that gains the Cleave Keyword."),
        12: ("Patron Skill", "Pick one of the Skills offered by your patron."),
    },
    "ranged": {
        2: ("Patron Skill", "Pick one of the Skills offered by your patron."),
        3: ("Hunter", "Ranged Attacks made by a model with this Skill have the Ignore COVER Keyword."),
        4: ("Gunslinger", "The following rules apply to a model with this Skill if it is armed with Ranged Weapons with the Pistol Keyword.\n\nIf it is equipped with 2 Weapons with the Pistol Keyword, it can take a Shoot ACTION with one and then immediately take a Shoot ACTION with the other.\nAdd the Assault and Ignore OFF-HAND WEAPON Keywords to any weapons that have the Pistol Keyword (unless they have them already)."),
        5: ("Far Shot", "Add 6\" to the Range of the following Weapons when they are used by a model that has this Skill:\n\n- Any Weapon with the Pistol Keyword.\n- Any Weapon which has the word “Rifle” as part of its name (i.e. a Bolt Action Rifle, Assault Rifle etc).\n- Any Weapon which has either the word “Jezzail” or “Arquebus” as part of its name."),
        6: ("Sharp Eyes", "Ranged Attacks made by a model with this Skill have the Ignore LONG RANGE Keyword."),
        7: ("Ranged Proficiency", "Add +1 Dice to the Ranged Characteristic of a model with this Skill."),
        8: ("Sniper's Nest", "Add +2 Dice to rolls for Ranged Attacks made with the Elevated Position modifier by a model with this Skill instead of +1 Dice."),
        9: ("Point Blank", "When a model with this Skill makes a Melee Attack, it can use a Ranged Weapon and its Ranged Attack Characteristic instead of a Melee Weapon and its Melee Attack Characteristic. It must still be within 1\" of the target model to make the attack. It can also use the Ranged Weapon to make a Ranged Attack during the same Activation if it has the Assault Keyword."),
        10: ("Hip Shot", "Ranged Weapons used by a model with this Skill count as having the Assault Keyword unless they already have it."),
        11: ("Head Shot", "Ranged Attacks made by a model with this Skill have the Ignore Armour Keyword if the attack was a Critical Success."),
        12: ("Patron Skill", "Pick one of the Skills offered by your patron."),
    },
    "stealth": {
        2: ("Patron Skill", "Pick one of the Skills offered by your patron."),
        3: ("Sixth Sense", "If a model with this Skill suffers a Down result on the Injury table, it is treated as a Minor Hit result instead if the model does not have any Blood Markers. If the model also has the Tough Keyword, once per game it can use the Keyword to change an Out of Action result to a Down result, and then use this Skill to change the Down result to No Effect."),
        4: ("Assassinate", "Add +1 Dice to rolls for attacks made by a model with this Skill if the target has not yet been Activated this Turn."),
        5: ("Shadow Walker", "Add -2 Dice to rolls for Ranged Attacks that target a model with this Skill at Long Range instead of -1 Dice."),
        6: ("Athletic", "Add +1 Dice to Risky Success rolls for a model with this Skill when it Climbs, Jumps or makes a Diving Charge, and add -1 Injury Dice to Injury Rolls if it Falls."),
        7: ("Sprinter", "Add +1 Dice to the Risky Success Roll for a model with this Skill that is taking a Dash ACTION."),
        8: ("Disengage", "Enemy models cannot make a Melee Attack on a model with this Skill when it Retreats."),
        9: ("Incoming", "When you roll the Charge Bonus for a model with this Skill, roll 1 extra D6 and use the single highest dice to determine the bonus."),
        10: ("Nimble", "Do not halve the Movement Characteristic of a model with this Skill when it stands up."),
        11: ("Dodge", "Add -1 Dice to rolls for Ranged Attacks that target a model with this Skill."),
        12: ("Patron Skill", "Pick one of the Skills offered by your patron."),
    },
    "wildcard": {
        2: ("Patron Skill", "Pick one of the Skills offered by your patron."),
        3: ("War Luck", "A model with this Skill can suffer 1 extra Battle Scar before they are Unfit for Duty."),
        4: ("'Tis but a Scratch", "You can re-roll the result on the Trauma Chart for a model with this Skill."),
        5: ("Bad Company", "A model with this Skill does not count towards the number of Elite models that are in your Warband at the start of the Promotion step."),
        6: ("Scavenger", "A model with this Skill has the Extra Dice Exploration Skill."),
        7: ("Skill & Expertise", "When you give a model this Skill, choose 1 Action on that model's Warband Entry, or 1 Common Action apart from Fight or Shoot ActionS, and write it on your Warband Roster. Add +1 Dice to rolls made as part of the chosen Action when they are taken by this model."),
        8: ("Show Off", "Add 1 dice to the Promotion Pool in the Promotion step for each model in your Warband with this Skill."),
        9: ("Friends In High Places", "A model with this Skill has the Re-roll Dice Exploration Skill."),
        10: ("Glory Hound", "At the end of each game, your Warband receives 1 extra  for each model with this Skill that is on the battlefield."),
        11: ("War Stories", "When you are recording the Experience Points earned by the models in your Warband in the Campaign Phase, you can give each model with the Elite Keyword that does not also have this Skill +1 extra Experience Point. You can’t pick the model with the Skill itself. A Warband can only have one model with this Skill."),
        12: ("Patron Skill", "Pick one of the Skills offered by your patron."),
    }
}

# Убираем звёздочки в выводе таблицы
def roll_table(table_name):
    if table_name not in TABLES:
        available = ", ".join(TABLES.keys())
        return None, f"Таблица '{table_name}' не найдена. Доступные: {available}"
    table = TABLES[table_name]
    roll1 = random.randint(1, 6)
    roll2 = random.randint(1, 6)
    total = roll1 + roll2
    name, description = table[total]
    result = f"2d6 → {roll1}+{roll2} = {total} — {name} — {description}"
    return result, None

# ----------------------------------------------
# 5. Основные функции команд
# ----------------------------------------------
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

# ----------------------------------------------
# 6. Главный цикл (с упоминанием, без звёздочек в таблице)
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
                cmd_raw = text[1:].strip()
                if not cmd_raw:
                    msg = mention_user(user_id, peer_id) + "Введите команду. Например: /d20"
                    send_message(user_id, msg, peer_id)
                    continue

                cmd_clean, comment = extract_comment(cmd_raw)
                parts = cmd_clean.split()
                if not parts:
                    msg = mention_user(user_id, peer_id) + "Введите команду. Например: /d20"
                    send_message(user_id, msg, peer_id)
                    continue

                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # Упоминание добавляем везде, где нужен автор
                mention = mention_user(user_id, peer_id)

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
                    msg = f"{mention}Бросок монетки: {result}"
                    if comment:
                        msg += f" (комментарий: {comment})"
                    send_message(user_id, msg, peer_id)

                elif command in ('rand', 'random'):
                    result, error = random_number(args)
                    if error:
                        msg = f"{mention}Ошибка: {error}"
                    else:
                        msg = f"{mention}Результат: {result}"
                        if comment:
                            msg += f" (комментарий: {comment})"
                    send_message(user_id, msg, peer_id)

                elif command in ('skill', 'навык'):
                    table_name = args[0].lower() if args else 'melee'
                    result, error = roll_table(table_name)
                    if error:
                        msg = f"{mention}Ошибка: {error}"
                    else:
                        msg = f"{mention}Бросок навыка ({table_name}): {result}"
                        if comment:
                            msg += f" (комментарий: {comment})"
                    send_message(user_id, msg, peer_id)

                elif command == 'table':
                    if not args:
                        available = ", ".join(TABLES.keys())
                        msg = f"Укажите имя таблицы. Доступные: {available}"
                    else:
                        table_name = args[0].lower()
                        result, error = roll_table(table_name)
                        if error:
                            msg = f"Ошибка: {error}"
                        else:
                            msg = f"{mention}Бросок по таблице {table_name}: {result}"
                            if comment:
                                msg += f" (комментарий: {comment})"
                    send_message(user_id, mention + msg, peer_id)

                elif command == 'tables':
                    available = ", ".join(TABLES.keys())
                    msg = f"Доступные таблицы: {available}"
                    send_message(user_id, mention + msg, peer_id)

                elif command == 'ping':
                    send_message(user_id, f"{mention}Pong! Бот работает.", peer_id)

                else:
                    result, error = parse_and_roll_multiple(cmd_clean)
                    if error:
                        msg = f"{mention}Ошибка: {error}"
                    else:
                        msg = f"{mention}Бросок {result}"
                        if comment:
                            msg += f" (комментарий: {comment})"
                    send_message(user_id, msg, peer_id)

        except Exception as e:
            print(f"Ошибка в цикле: {e}")
            try:
                mention = mention_user(user_id, peer_id)
                send_message(user_id, f"{mention}⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
