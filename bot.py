import os
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import re

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (задаются на сервере) ---
VK_TOKEN = os.environ.get("VK_TOKEN")
GROUP_ID = os.environ.get("GROUP_ID")

# Проверка, что переменные установлены
if not VK_TOKEN:
    raise Exception("Переменная окружения VK_TOKEN не задана!")
if not GROUP_ID:
    raise Exception("Переменная окружения GROUP_ID не задана!")

try:
    GROUP_ID = int(GROUP_ID)
except ValueError:
    raise Exception("GROUP_ID должен быть целым числом!")

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
vk = vk_session.get_api()


def send_message(user_id, message, peer_id=None):
    """Универсальная функция отправки сообщения"""
    try:
        vk.messages.send(
            user_id=user_id if peer_id is None else None,
            peer_id=peer_id,
            message=message,
            random_id=0
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def roll_dice(expression):
    """
    Парсит выражение типа '2d6+3' или 'd20' и возвращает результат.
    Поддерживает: количество кубиков, тип кубика, модификатор.
    """
    expression = expression.lower().replace(' ', '')
    
    if expression.startswith('d'):
        expression = '1' + expression
    
    match = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', expression)
    
    if not match:
        return "❌ Неверный формат. Используйте: !roll 2d6+3 или !roll d20"
    
    num_dice = int(match.group(1))
    dice_type = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0
    
    if num_dice > 100:
        return "❌ Слишком много кубиков (максимум 100)"
    if dice_type > 1000:
        return "❌ Слишком большой кубик (максимум d1000)"
    if num_dice <= 0 or dice_type <= 0:
        return "❌ Количество и тип кубика должны быть положительными"
    
    rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    
    if num_dice == 1:
        result_str = f"🎲 **{total}** (бросок: {rolls[0]}" + (f" {modifier:+d}" if modifier else "") + ")"
    else:
        rolls_str = ", ".join(map(str, rolls))
        result_str = f"🎲 **{total}** (броски: {rolls_str}" + (f" {modifier:+d}" if modifier else "") + ")"
    
    return result_str


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
            
            if text.startswith('!roll'):
                parts = text.split(maxsplit=1)
                if len(parts) == 1:
                    result = roll_dice('d20')
                else:
                    result = roll_dice(parts[1])
                send_message(user_id, result, peer_id)
            
            elif text == '!help':
                help_text = (
                    "🎲 **Команды бота:**\n\n"
                    "`!roll d20` - бросок 20-гранного кубика\n"
                    "`!roll 2d6+3` - бросок двух шестигранных кубиков с модификатором +3\n"
                    "`!roll d100` - бросок 100-гранного кубика\n"
                    "`!help` - показать эту справку"
                )
                send_message(user_id, help_text, peer_id)
            
            elif text == '!ping':
                send_message(user_id, "🏓 Pong! Бот работает.", peer_id)
                
        except Exception as e:
            print(f"Ошибка в цикле: {e}")
            try:
                send_message(user_id, "⚠️ Произошла ошибка. Попробуйте позже.", peer_id)
            except:
                pass
