"""
Демо-плагин: показывает три вещи, которые обычно нужны плагину —
реакцию на сообщение покупателя, уведомление о новом заказе и свою
Telegram-команду. Скопируйте эту папку как основу для нового плагина.
"""

from fphelper import PluginInfo

INFO = PluginInfo(
    name="Example Autoreply",
    version="1.0.0",
    description="Отвечает на 'привет', уведомляет о новых заказах, добавляет команду /ping.",
    author="you",
)


def setup(ctx):
    @ctx.events.new_message
    def on_message(event):
        message = event.message
        if message.author_id == ctx.account.id:
            return
        if message.text and message.text.strip().lower() == "привет":
            ctx.account.send_message(message.chat_id, "Привет! Чем можем помочь?")
            ctx.logger.info(f"Ответил на приветствие в чате {message.chat_id}")

    @ctx.events.new_order
    def on_order(event):
        order = event.order
        ctx.notify_admins(
            f"🛒 Новый заказ «{order.description}» на {order.price} — от {order.buyer_username}"
        )

    @ctx.telegram.command("ping")
    def cmd_ping(message):
        ctx.telegram.reply(message, "🏓 pong")
