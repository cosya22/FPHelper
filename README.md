# FPHelper
[![python](https://img.shields.io/badge/python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://www.python.org/downloads/)
[![plugins](https://img.shields.io/badge/%F0%9F%A7%A9%20%D0%BF%D0%BB%D0%B0%D0%B3%D0%B8%D0%BD%D1%8B-%D1%81%D0%B2%D0%BE%D0%B8-green?style=for-the-badge)](#-для-разработчиков-плагинов)
[![funpayapi](https://img.shields.io/badge/FunPayAPI-GPLv3-blue?style=for-the-badge)](https://pypi.org/project/FunPayAPI/)
[![telegram](https://img.shields.io/badge/telegram-мультиадмины-2CA5E0?style=for-the-badge&logo=telegram)](#-несколько-админов)

Бот-помощник для продавцов FunPay с открытой системой плагинов и поддержкой нескольких админов 🤖🟩

FPHelper подключается к вашему аккаунту FunPay и в реальном времени слушает
происходящее в магазине — новые сообщения, новые заказы, смену их статуса.
Управляется он из Telegram, где может быть сразу несколько админов. Сам по
себе движок лёгкий и не делает ничего лишнего — всю прикладную логику
(авто-выдачу, авто-ответы, аналитику, интеграции с чем угодно) добавляют
**плагины**, которые подключаются простым копированием папки.

---

## 🗺️ Навигация
- **[Что делает бот](#-что-делает-бот)**
- **[Готовые плагины](#-готовые-плагины)**
- **[Установка](#️-установка)**
- **[Несколько админов](#-несколько-админов)**
- **[Для разработчиков плагинов](#-для-разработчиков-плагинов)**
- **[Структура проекта](#-структура-проекта)**
- **[О лицензии](#️-о-лицензии)**

## ⚙️ Что делает бот

### 📡 Из коробки (ядро)
- **🔌 Постоянное подключение к FunPay** — держит сессию, слушает события через `Runner`
- **💬 Реакция на новые сообщения** в чатах в реальном времени
- **🛒 Реакция на новые заказы** и на смену их статуса
- **🎪 Кнопочное меню в Telegram** — `/start` открывает разделы по кнопкам, без запоминания команд;
  для действий с параметрами (ID заказа, текст и т.п.) бот сам спрашивает текстом по шагам
- **🤖 Telegram-панель управления** с несколькими админами (не нужно шарить один аккаунт)
- **🆔 Самостоятельная выдача доступа** — `/whoami` + `/addadmin`, без правки файлов и перезапуска
- **🔔 Рассылка уведомлений** всем админам разом (`notify_admins`) — например, о новом заказе
- **⚙️ Мастер первого запуска** — golden key, токен бота и первый админ вводятся один раз в консоли
- **🗒️ Логирование** в файл и консоль

### 🧩 Через плагины (расширяется без правки ядра)
Ядро специально не хардкодит бизнес-логику — она подключается плагинами из
папки `plugins/`. Уже готов демо-плагин ([`example_autoreply`](plugins/example_autoreply/__init__.py)),
показывающий базовый набор: автоответ по ключевому слову, уведомление о заказе,
своя команда в боте. По этому же API можно писать что угодно: авто-выдачу
товара, динамические цены, статистику, интеграции с внешними сервисами —
и продавать такие плагины отдельно, без переустановки движка.

- **💾 У каждого плагина своё изолированное JSON-хранилище**
- **⌨️ Свои команды и кнопки в общем Telegram-боте**
- **📥 Подписка на любые события FunPay** без изменений в ядре

## 🧩 Готовые плагины

В `plugins/` уже лежит 13 рабочих плагинов — можно использовать как есть, включать
только нужные (удалив папку — остальные), или взять за основу своих.

<details>
  <summary><strong>👤 Profile</strong> — профиль аккаунта</summary>

  `/profile` — баланс, валюта, активные продажи/покупки.
</details>

<details>
  <summary><strong>💬 Chats</strong> — просмотр чатов и переписки</summary>

  `/chats` — последние чаты · `/history <chat_id>` — история сообщений ·
  `/reply <chat_id> <текст>` — ответить покупателю.
</details>

<details>
  <summary><strong>📋 Orders</strong> — заказы</summary>

  `/orders` — список заказов · `/order <id>` — детали (включая отзыв, если есть) ·
  `/refund <id>` — оформить возврат.
</details>

<details>
  <summary><strong>🛍️ Lots</strong> — управление лотом</summary>

  `/lot <id>` — просмотр · `/lot_toggle <id>` — вкл/выкл ·
  `/lot_price <id> <цена>` — изменить цену.
</details>

<details>
  <summary><strong>⬆️ Auto Raise Lots</strong> — авто-поднятие лотов</summary>

  Сам поднимает выбранные категории с учётом кулдауна FunPay (правильно ждёт
  `wait_time` из ответа сайта, а не долбит запросами).
  `/autoraise` — статус · `/autoraise_categories` — ваши категории с ID ·
  `/autoraise_add <id>` / `/autoraise_remove <id>` · `/autoraise_on` / `/autoraise_off`.
</details>

<details>
  <summary><strong>🚀 Auto Delivery</strong> — авто-выдача товара</summary>

  По ключевому слову в названии лота — либо шлёт фиксированный текст, либо
  выдаёт одну позицию со «склада» (коды/ключи, каждая ровно одному покупателю).
  `/delivery_add_text <слово> <текст>` · `/delivery_stock_add <слово> <позиция>` ·
  `/delivery_list` · `/delivery_remove <слово>`.
</details>

<details>
  <summary><strong>⚡ Fast Replies</strong> — быстрые ответы</summary>

  Заготовленные шаблоны текста, отправляемые в любой чат одной командой.
  `/freply_add <имя> <текст>` · `/freply_list` · `/freply <имя> <chat_id>` ·
  `/freply_remove <имя>`.
</details>

<details>
  <summary><strong>❗ Custom Commands</strong> — команды для покупателей</summary>

  Покупатель пишет в чате `!команда` — бот отвечает заданным текстом
  (поддерживает `{username}`). `/cmd_add <имя> <текст>` · `/cmd_list` · `/cmd_remove <имя>`.
</details>

<details>
  <summary><strong>💸 Auto Withdrawal</strong> — авто-вывод средств</summary>

  Периодический вывод баланса на карту/кошелёк по расписанию. Выключен по
  умолчанию — двигает реальные деньги, включайте осознанно.
  `/withdrawal_status` · `/withdrawal_setup <валюта> <кошелёк> <адрес> <сумма|all> <часы>` ·
  `/withdrawal_on` / `/withdrawal_off`.
</details>

<details>
  <summary><strong>🌟 Reviews</strong> — отзывы</summary>

  Уведомляет о новых отзывах на последние закрытые заказы (см. ограничение в
  докстринге плагина — FunPayAPI не даёт события «новый отзыв», поэтому это
  периодический опрос, а не мгновенно). `/review_reply <id> <текст>` ·
  `/review_delete <id>`.
</details>

<details>
  <summary><strong>🗒️ Logs</strong> — логи</summary>

  `/logs [N]` — последние N строк лога (по умолчанию 30) прямо в Telegram.
</details>

<details>
  <summary><strong>📊 Stats</strong> — статистика</summary>

  Считает свои новые заказы (+ выручку) и сообщения от покупателей с момента
  установки плагина, `/stats` показывает разбивку за 24 часа / неделю / месяц /
  всё время. Истории до установки плагина нет — FunPay её не отдаёт.
</details>

<details>
  <summary><strong>🔧 Example Autoreply</strong> — учебный пример</summary>

  Простейший плагин-заготовка для тех, кто пишет свой первый плагин — смотрите
  его код, там же и `/ping`.
</details>

## ⬇️ Установка

### 🔷 Windows
1. Установите **Python 3.10+** с [официального сайта](https://www.python.org/downloads/) (отметьте `Add to PATH`).
2. Скачайте проект (`git clone` или архивом) и откройте папку.
3. Запустите `install.bat` — создастся виртуальное окружение и установятся зависимости.
4. Запустите `run.bat`.
5. При первом запуске введите в консоли: golden key от FunPay, токен Telegram-бота (от [@BotFather](https://t.me/BotFather)), свой Telegram ID и, при необходимости, прокси (можно пропустить Enter'ом).

```bash
install.bat
run.bat
```

Дальше бот сам подключится к FunPay и поднимет Telegram-бота — управление полностью там.

## 👥 Несколько админов

| Команда | Доступ | Что делает |
|---|---|---|
| `/whoami` | всем | показать свой Telegram ID |
| `/admins` | админам | список текущих админов |
| `/addadmin <id>` | админам | добавить нового админа |
| `/deladmin <id>` | админам | удалить админа (кроме себя) |
| `/plugins` | админам | список загруженных плагинов |

Флоу добавления второго админа: новый человек пишет боту `/whoami`, присылает свой ID
действующему админу, тот вводит `/addadmin <id>` — готово, без перезапуска бота.

## 📚 Для разработчиков плагинов

Плагин — папка в `plugins/` с файлом `__init__.py`, где заданы `INFO` (метаданные) и
функция `setup(ctx)`, вызываемая один раз при старте бота.

<details>
  <summary><strong>📌 Доступные события (<code>ctx.events</code>)</strong></summary>

  | Декоратор | Когда срабатывает | Что приходит в обработчик |
  |---|---|---|
  | `@ctx.events.new_message` | новое сообщение в чате | `NewMessageEvent` (`.message`) |
  | `@ctx.events.new_order` | новый заказ | `NewOrderEvent` (`.order`) |
  | `@ctx.events.order_status_changed` | статус заказа изменился | `OrderStatusChangedEvent` (`.order`) |
  | `@ctx.events.chats_list_changed` | список чатов изменился | `ChatsListChangedEvent` |
  | `@ctx.events.orders_list_changed` | список заказов изменился | `OrdersListChangedEvent` |

</details>

<details>
  <summary><strong>🧰 Что доступно в <code>ctx</code> (<code>PluginContext</code>)</strong></summary>

  | Поле | Описание |
  |---|---|
  | `ctx.account` | объект `FunPayAPI.Account` — `send_message`, `get_order`, `save_lot`, `get_sells`... |
  | `ctx.events` | декораторы подписки на события FunPay (см. выше) |
  | `ctx.telegram` | `@ctx.telegram.command("имя")`, `@ctx.telegram.callback("префикс")`, `@ctx.telegram.menu_item(...)`, `.ask(...)`, `.reply()`, `.send()`, `.bot` (сырой `telebot.TeleBot`) |
  | `ctx.storage` | JSON-хранилище плагина: `.get(key, default)`, `.set(key, value)`, `.update({...})`, `.all()` |
  | `ctx.logger` | `logging.Logger`, уже настроенный под имя плагина |
  | `ctx.notify_admins(text)` | отправить сообщение всем админам разом |

  По умолчанию Telegram-команды плагина доступны только админам. Чтобы сделать команду
  публичной: `@ctx.telegram.command("start", admin_only=False)`.

</details>

<details>
  <summary><strong>🎪 Кнопки в главном меню и запрос текста (<code>ask</code>)</strong></summary>

  `@ctx.telegram.menu_item(раздел, подпись, callback_data)` одновременно регистрирует
  колбэк-обработчик и кнопку с ним — раздел меню создаётся сам при первой такой кнопке
  и появляется в `/start` автоматически.

  ```python
  @ctx.telegram.menu_item("📦 Мой раздел", "📋 Показать список", "myplugin:list")
  def cbq_list(call):
      ctx.telegram.bot.send_message(call.message.chat.id, "тут список")
  ```

  Если действию нужен параметр (ID заказа, текст и т.п.) — используйте `ctx.telegram.ask()`,
  он спросит текстом и один раз вызовет колбэк с ответом; несколько `ask()` подряд
  (внутри друг друга) дают цепочку из нескольких вопросов:

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

</details>

<details>
  <summary><strong>🔧 Пример плагина</strong></summary>

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

  Готовый рабочий пример смотрите в [`plugins/example_autoreply/`](plugins/example_autoreply/__init__.py).
  Плагин подхватывается автоматически при следующем запуске — просто положите папку в `plugins/`.

</details>

## 📁 Структура проекта

```
FPHelper/
  fphelper/            # ядро движка
    config.py          # конфиг + мастер первого запуска
    events.py           # шина событий FunPay
    context.py            # PluginContext и всё, что видит плагин
    telegram_admin.py       # Telegram-бот, мультиадмины, команды ядра
    funpay_client.py         # подключение к FunPay и цикл Runner'а
    plugin_manager.py         # загрузка плагинов из plugins/
  plugins/                    # сюда кладутся плагины
  storage/                     # JSON-хранилища плагинов (создаётся сама)
  logs/                         # логи (создаётся сама)
  main.py                        # точка входа
```

## ⚠️ О лицензии

Движок построен на официальной библиотеке [`FunPayAPI`](https://pypi.org/project/FunPayAPI/)
(автор Woopertail, лицензия **GPLv3**) и [`pyTelegramBotAPI`](https://pypi.org/project/pyTelegramBotAPI/)
(MIT). Весь остальной код в репозитории — оригинальный.

Если планируете распространять/продавать **сам движок** в закрытом,
обфусцированном виде — сверьтесь с юристом на совместимость с GPLv3. Продажа
**отдельных плагинов**, устанавливаемых поверх уже работающего движка, —
более безопасная с этой точки зрения модель, и именно для неё спроектирован
плагин-API выше.
