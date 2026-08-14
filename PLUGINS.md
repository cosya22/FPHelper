# Разработка плагинов

Плагин — папка в `plugins/` с файлом `__init__.py`, где заданы `INFO`
(метаданные) и функция `setup(ctx)`, вызываемая один раз при старте бота.
Встроенные модули бота (`builtin/`) написаны по тому же API — можно смотреть
их код как более развёрнутые примеры.

## Пример плагина

```python
from fphelper import PluginInfo

INFO = PluginInfo(
    name="Мой плагин",
    version="0.1.0",
    description="Что делает плагин",
    author="я",
)

def setup(ctx):
    @ctx.events.new_order
    def on_order(event):
        ctx.notify_admins(f"🛒 Новый заказ: {event.order.description}")

    @ctx.telegram.command("stats")
    def cmd_stats(message):
        total = ctx.storage.get("orders_count", 0)
        ctx.telegram.reply(message, f"Заказов обработано: {total}")
```

Готовый рабочий пример-заготовка: [`plugins/example_autoreply/`](plugins/example_autoreply/__init__.py).
Плагин подхватывается автоматически при следующем запуске — просто положите папку в `plugins/`.

## События (`ctx.events`)

| Декоратор | Когда срабатывает | Что приходит в обработчик |
|---|---|---|
| `@ctx.events.new_message` | новое сообщение в чате | `NewMessageEvent` (`.message`) |
| `@ctx.events.new_order` | новый заказ | `NewOrderEvent` (`.order`) |
| `@ctx.events.order_status_changed` | статус заказа изменился | `OrderStatusChangedEvent` (`.order`) |
| `@ctx.events.chats_list_changed` | список чатов изменился | `ChatsListChangedEvent` |
| `@ctx.events.orders_list_changed` | список заказов изменился | `OrdersListChangedEvent` |

## Что доступно в `ctx` (`PluginContext`)

| Поле | Описание |
|---|---|
| `ctx.account` | объект `FunPayAPI.Account` — `send_message`, `get_order`, `save_lot`, `get_sells`... |
| `ctx.events` | декораторы подписки на события FunPay (см. выше) |
| `ctx.telegram` | `@ctx.telegram.command("имя")`, `@ctx.telegram.callback("префикс")`, `@ctx.telegram.menu_item(...)`, `.ask(...)`, `.reply()`, `.send()`, `.bot` (сырой `telebot.TeleBot`) |
| `ctx.storage` | JSON-хранилище плагина: `.get(key, default)`, `.set(key, value)`, `.update({...})`, `.all()` |
| `ctx.logger` | `logging.Logger`, уже настроенный под имя плагина |
| `ctx.notify_admins(text)` | отправить сообщение всем админам разом |

По умолчанию Telegram-команды плагина доступны только админам. Чтобы сделать
команду публичной: `@ctx.telegram.command("start", admin_only=False)`.

## Кнопки в главном меню и запрос текста (`ask`)

`@ctx.telegram.menu_item(раздел, подпись, callback_data)` одновременно
регистрирует колбэк-обработчик и кнопку с ним — раздел меню создаётся сам при
первой такой кнопке и появляется в `/start` автоматически.

```python
@ctx.telegram.menu_item("📦 Мой раздел", "📋 Показать список", "myplugin:list")
def cbq_list(call):
    ctx.telegram.bot.send_message(call.message.chat.id, "тут список")
```

Если действию нужен параметр (ID заказа, текст и т.п.) — используйте
`ctx.telegram.ask()`, он спросит текстом и один раз вызовет колбэк с ответом;
несколько `ask()` подряд (внутри друг друга) дают цепочку из нескольких
вопросов:

```python
@ctx.telegram.menu_item("📦 Мой раздел", "➕ Добавить", "myplugin:add_ask")
def cbq_add_ask(call):
    def on_name(msg):
        name = msg.text.strip()

        def on_value(msg2):
            ctx.storage.set(name, msg2.text)
            ctx.telegram.bot.send_message(msg2.chat.id, f"✅ «{name}» сохранено.")

        ctx.telegram.ask(msg.chat.id, msg.from_user.id, "Теперь пришлите значение.", on_value)

    ctx.telegram.ask(call.message.chat.id, call.from_user.id, "Пришлите имя.", on_name)
```

Пользователь может в любой момент отменить ожидание командой `/cancel` (уже
встроена в ядро — плагину ничего для этого делать не нужно).

## Структура проекта

```
FPHelper/
  fphelper/            # ядро движка
    config.py          # конфиг + мастер первого запуска
    events.py           # шина событий FunPay
    context.py            # PluginContext и всё, что видит плагин/модуль
    telegram_admin.py       # Telegram-бот, меню, мультиадмины, команды ядра
    funpay_client.py         # подключение к FunPay и цикл Runner'а
    plugin_manager.py         # загрузка builtin/ и plugins/
  builtin/                     # встроенные модули бота (всегда активны)
  plugins/                      # сюда кладутся свои плагины
  storage/                       # JSON-хранилища модулей и плагинов (создаётся сама)
  logs/                           # логи (создаётся сама)
  main.py                          # точка входа
```
