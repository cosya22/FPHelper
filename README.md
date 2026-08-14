# FPHelper

Свой движок-помощник для продавцов на FunPay: подключается к аккаунту, слушает
события (новые сообщения, заказы, смена статуса), управляется через Telegram
несколькими админами, и расширяется плагинами.

Построен на официальной библиотеке [`FunPayAPI`](https://pypi.org/project/FunPayAPI/)
(автор Woopertail, лицензия **GPLv3**) и [`pyTelegramBotAPI`](https://pypi.org/project/pyTelegramBotAPI/)
(MIT). Весь остальной код в этом репозитории — оригинальный.

> **О лицензии.** `FunPayAPI` распространяется под GPLv3. Если вы захотите
> распространять/продавать сам движок (не только плагины) в закрытом,
> обфусцированном виде — сверьтесь с юристом на предмет совместимости с GPLv3.
> Продажа отдельных плагинов как самостоятельных файлов, устанавливаемых поверх
> уже работающего движка, — более безопасная с этой точки зрения модель, и именно
> для неё спроектирован плагин-API ниже.

## Установка

Требуется Python 3.10+.

```bash
install.bat
```

Это создаст виртуальное окружение `.venv` и поставит зависимости. Дальше:

```bash
run.bat
```

При первом запуске бот спросит:
1. **Golden key** — кука вашего аккаунта FunPay (браузер → F12 → Application →
   Cookies → `golden_key` на funpay.com).
2. **Токен Telegram-бота** — получить у [@BotFather](https://t.me/BotFather)
   командой `/newbot`.
3. **Ваш Telegram ID** — узнать у [@userinfobot](https://t.me/userinfobot) или
   просто написать `/whoami` любому боту.

Всё сохранится в `config.json` — этот файл никому не передавайте, в нём секреты
(добавлен в `.gitignore`, в git не попадёт).

## Несколько админов

- `/whoami` — работает для всех, показывает Telegram ID (чтобы узнать свой ID
  и передать действующему админу)
- `/admins` — список текущих админов
- `/addadmin <id>` — добавить админа
- `/deladmin <id>` — удалить админа (кроме себя)
- `/plugins` — список загруженных плагинов

Все команды, кроме `/whoami`, доступны только тем, чей Telegram ID уже в
списке админов.

## Как устроены плагины

Плагин — это папка внутри `plugins/` с файлом `__init__.py`, где есть:
- `INFO` — объект `PluginInfo` (имя, версия, описание, автор)
- `setup(ctx)` — функция, вызываемая при старте бота; в ней плагин
  подписывается на события и регистрирует свои Telegram-команды

Смотрите готовый пример: [`plugins/example_autoreply/__init__.py`](plugins/example_autoreply/__init__.py).

### Что доступно в `ctx` (`PluginContext`)

| Поле | Что это |
|---|---|
| `ctx.account` | объект `FunPayAPI.Account` — вся работа с FunPay (`send_message`, `get_order`, `save_lot`, `get_sells`, ...) |
| `ctx.events` | декораторы подписки на события: `@ctx.events.new_message`, `@ctx.events.new_order`, `@ctx.events.order_status_changed`, `@ctx.events.chats_list_changed`, `@ctx.events.orders_list_changed` |
| `ctx.telegram` | `@ctx.telegram.command("имя")` и `@ctx.telegram.callback("префикс")` для своих команд/кнопок; `ctx.telegram.reply(...)`, `ctx.telegram.send(...)`, `ctx.telegram.bot` — сырой объект `telebot.TeleBot` для сложных случаев |
| `ctx.storage` | приватный JSON-стор плагина: `ctx.storage.get(key, default)`, `.set(key, value)`, `.update({...})`, `.all()` |
| `ctx.logger` | `logging.Logger`, уже настроенный под имя плагина |
| `ctx.notify_admins(text)` | быстро отправить сообщение всем админам |

По умолчанию Telegram-команды плагина доступны только админам
(`admin_only=True`); чтобы сделать команду публичной:
`@ctx.telegram.command("start", admin_only=False)`.

### Пример: минимальный плагин

```python
from fphelper import PluginInfo

INFO = PluginInfo(name="Мой плагин", version="0.1.0", description="...", author="я")

def setup(ctx):
    @ctx.events.new_order
    def on_order(event):
        ctx.notify_admins(f"Новый заказ: {event.order.description}")
```

Плагин подхватывается автоматически при следующем запуске бота — просто
положите папку в `plugins/`.

## Структура проекта

```
FPHelper/
  fphelper/            # ядро движка
    config.py          # конфиг + мастер первого запуска
    events.py           # шина событий FunPay
    context.py           # PluginContext и всё, что видит плагин
    telegram_admin.py     # Telegram-бот, мультиадмины, команды ядра
    funpay_client.py       # подключение к FunPay и цикл Runner'а
    plugin_manager.py       # загрузка плагинов из plugins/
  plugins/               # сюда кладутся плагины
  storage/                # JSON-хранилища плагинов (создаётся сама)
  logs/                    # логи (создаётся сама)
  main.py                   # точка входа
```
