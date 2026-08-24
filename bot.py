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
    # Сохраняем оригинальное выражение для вывода (то, что ввел пользователь)
    display_expr = original_expr.strip()
    
    # Приводим к нижнему регистру и заменяем русскую 'д' на 'd' для парсинга
    expr = original_expr.lower().replace(' ', '').replace('д', 'd')
    
    # Если выражение начинается с d, добавляем 1
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
    
    # Генерируем броски
    rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    
    # Формируем детали в зависимости от количества кубиков
    if num_dice == 1:
        details = f"бросок: {rolls[0]}"
        if modifier:
            details += f" {modifier:+d}"
    else:
        rolls_str = ", ".join(map(str, rolls))
        details = f"броски: {rolls_str}"
        if modifier:
            details += f" {modifier:+d}"
    
    # Итоговая строка: 🎲 выражение → результат (детали)
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
            
            # --- ОБРАБОТКА КОМАНД (все начинаются с /) ---
            if text == '/help' or text == '/помощь':
                help_text = (
                    "🎲 **Команды бота:**\n\n"
                    "/d20 или /д20 — бросить 20-гранный кубик\n"
                    "/2d6+3 или /2д6+3 — бросить два шестигранных кубика с модификатором +3\n"
                    "/d100-5 или /д100-5 — бросить 100-гранный кубик и вычесть 5\n"
                    "/3d8 или /3д8 — бросить три восьмигранных кубика\n\n"
                    "/ping — проверить работу бота\n"
                    "/help или /помощь — показать эту справку"
                )
                send_message(user_id, help_text, peer_id)
            
            elif text == '/ping':
                send_message(user_id, "🏓 Pong! Бот работает.", peer_id)
            
            elif text.startswith('/'):
                # Убираем первый слеш, сохраняем оригинал для вывода
                cmd = text[1:]
                if cmd:
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
