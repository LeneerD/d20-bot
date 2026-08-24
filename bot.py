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


def parse_and_roll(original_expr):
    """
    Парсит выражение вида d20, 2d6+3 и возвращает результат.
    Поддерживает как латинскую 'd', так и русскую 'д'.
    Возвращает кортеж (результат_в_виде_строки, сообщение_об_ошибке).
    """
    display_expr = original_expr.strip()
    expr = original_expr.lower().replace(' ', '').replace('д', 'd')
    
    if expr.startswith('d'):
        expr = '1' + expr
    
    match = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', expr)
    if not match:
        return None, "❌ Неверный формат. Примеры: /d20, /2d6+3, /д100-5"
    
    num_dice = int(match.group(1))
    dice_type = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0
    
    if num_dice > 100:
        return None, "❌ Слишком много кубиков (максимум 100)"
    if dice_type > 1000:
        return None, "❌ Слишком большой кубик (максимум d1000)"
    if num_dice <= 0 or dice_type <= 0:
        return None, "❌ Количество и тип кубика должны быть положительными"
    
    rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    
    if num_dice == 1:
        details = f"бросок: {rolls[0]}"
        if modifier:
            details += f" {modifier:+d}"
    else:
        rolls_str = ", ".join(map(str, rolls))
        details = f"броски: {rolls_str}"
        if modifier:
            details += f" {modifier:+d}"
    
    result_str = f"🎲 {display_expr} → **{total}** ({details})"
    return result_str, None


# --- ОСНОВНОЙ ЦИКЛ ---
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
                # Убираем первый символ (слеш или восклицательный знак)
                cmd = text[1:].strip()
                
                # Проверяем служебные команды
                if cmd == 'help' or cmd == 'помощь':
                    help_text = (
                        "🎲 **Команды бота:**\n\n"
                        "**Бросок кубиков** (можно через / или !):\n"
                        "`/d20` или `!d20` — бросить 20-гранный кубик\n"
                        "`/2d6+3` или `!2d6+3` — два кубика d6 +3\n"
                        "`/d100-5` или `!d100-5` — d100 -5\n"
                        "`/3d8` или `!3d8` — три кубика d8\n\n"
                        "**Служебные:**\n"
                        "`/ping` или `!ping` — проверка работы\n"
                        "`/help` или `!help` — эта справка"
                    )
                    send_message(user_id, help_text, peer_id)
                
                elif cmd == 'ping':
                    send_message(user_id, "🏓 Pong! Бот работает.", peer_id)
                
                elif cmd:
                    # Любая другая команда считается выражением для броска
                    result, error = parse_and_roll(cmd)
                    if error:
                        send_message(user_id, error, peer_id)
                    else:
                        send_message(user_id, result, peer_id)
                else:
                    send_message(user_id, "❌ Введите команду. Например: /d20", peer_id)
            # --- ВСЁ ОСТАЛЬНОЕ ИГНОРИРУЕМ ---
                
        except Exception as e:
            print(f"Ошибка в цикле: {e}")
            try:
                send_message(user_id, "⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
