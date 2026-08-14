# FPHelper
[![python](https://img.shields.io/badge/python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://www.python.org/downloads/)
[![plugins](https://img.shields.io/badge/%F0%9F%A7%A9%20%D0%BF%D0%BB%D0%B0%D0%B3%D0%B8%D0%BD%D1%8B-%D1%81%D0%B2%D0%BE%D0%B8-green?style=for-the-badge)](#-плагины-своя-логика-поверх-ядра)
[![funpayapi](https://img.shields.io/badge/FunPayAPI-GPLv3-blue?style=for-the-badge)](https://pypi.org/project/FunPayAPI/)
[![telegram](https://img.shields.io/badge/telegram-мультиадмины-2CA5E0?style=for-the-badge&logo=telegram)](#-несколько-админов)

Бот-помощник для продавцов FunPay с готовым набором функций и открытой системой плагинов для своих доработок 🤖🟩

FPHelper подключается к вашему аккаунту FunPay и в реальном времени слушает
происходящее в магазине — новые сообщения, новые заказы, смену их статуса.
Управляется он из Telegram (кнопочное меню + команды), где может быть сразу
несколько админов. Всё, что нужно продавцу day-to-day — чаты, заказы, лоты,
авто-выдача, авто-поднятие, статистика и т.д. — уже встроено в бота и всегда
включено. Отдельно есть система **плагинов** — для своей, кастомной логики
поверх этого, без правки ядра.

---

## 🗺️ Навигация
- **[Что делает бот](#-что-делает-бот)**
- **[Установка](#️-установка)**
- **[Несколько админов](#-несколько-админов)**
- **[Плагины: своя логика поверх ядра](#-плагины-своя-логика-поверх-ядра)**
- **[Структура проекта](#-структура-проекта)**
- **[О лицензии](#️-о-лицензии)**

## ⚙️ Что делает бот

### 🎛️ Управление ботом
- **🎪 Кнопочное меню в Telegram** — `/start` открывает разделы по кнопкам, без запоминания команд;
  для действий с параметрами (ID заказа, текст и т.п.) бот сам спрашивает текстом по шагам
- **🤖 Несколько админов** — `/whoami` + `/addadmin`, без правки файлов и перезапуска
- **🔔 Уведомления админам** о новых заказах, отзывах, ошибках выдачи и т.п.
- **⚙️ Мастер первого запуска** — golden key, токен бота и первый админ вводятся один раз в консоли
- **🗒️ Логи** прямо в Telegram

### 🧰 Встроенные модули (`builtin/`, всегда активны)
- **👤 Profile** — баланс, валюта, активные продажи/покупки
- **💬 Chats** — просмотр чатов и истории, ответ покупателю, отправка картинок
- **📋 Orders** — список заказов, детали, возврат
- **🛍️ Lots** — просмотр лота по ID, вкл/выкл, изменение цены
- **⬆️ Auto Raise Lots** — авто-поднятие категорий с учётом кулдауна FunPay
- **🚀 Auto Delivery** — авто-выдача текстом или со «склада» одноразовых позиций по ключевому слову в лоте
- **⚡ Fast Replies** — заготовленные шаблоны текста для быстрой отправки в чат
- **❗ Custom Commands** — покупатель пишет `!команда` в чате — бот отвечает заданным текстом
- **💸 Auto Withdrawal** — периодический вывод баланса по расписанию (выключен по умолчанию)
- **🌟 Reviews** — уведомления о новых отзывах, ответ/удаление ответа
- **📊 Stats** — заказы/выручка/сообщения за 24ч/неделю/месяц/всё время
- **🗒️ Logs** — последние строки лога в Telegram
- **📦 Plugin Installer** — кнопка «➕ Установить плагин»: пришлите `.zip` прямо в Telegram,
  бот сам распакует в `plugins/` (с защитой от zip-slip и лимитами на размер)

Реализация каждого — в [`builtin/`](builtin/), полноценные читаемые модули, а не
чёрный ящик; можно смело смотреть и менять под себя.

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
| `/plugins` | админам | список встроенных модулей и плагинов |

Флоу добавления второго админа: новый человек пишет боту `/whoami`, присылает свой ID
действующему админу, тот вводит `/addadmin <id>` — готово, без перезапуска бота.

## 🧩 Плагины: своя логика поверх ядра

Всё из раздела выше — часть самого бота, всегда включена и лежит в `builtin/`.
Плагины — отдельный, опциональный слой поверх этого: сюда вы пишете свою
кастомную логику (или то, что позже захотите продавать отдельно от движка),
не трогая ядро. Плагин — папка в `plugins/` с файлом `__init__.py`, где заданы
`INFO` (метаданные) и функция `setup(ctx)`, вызываемая один раз при старте бота.
API для плагинов и встроенных модулей — один и тот же (можно подсмотреть
любой файл в `builtin/` как более развёрнутый пример).

Готовые плагины на продажу:
- **`plugins/telegram_stars`** — выдаёт Telegram Stars по заказам FunPay через
  Fragment.com (официального способа пополнить чужой баланс Stars нет, поэтому
  используется сторонняя библиотека `pyfragment` и TON-кошелёк — заведите под
  это отдельный кошелёк, не основной). Продавец задаёт ключевое слово лота,
  бот сам просит у покупателя Telegram username в чате и выдаёт звёзды.

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

  Готовый рабочий пример-заготовка: [`plugins/example_autoreply/`](plugins/example_autoreply/__init__.py).
  Плагин подхватывается автоматически при следующем запуске — просто положите папку в `plugins/`.

</details>

## 📁 Структура проекта

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

## ⚠️ О лицензии

Движок построен на официальной библиотеке [`FunPayAPI`](https://pypi.org/project/FunPayAPI/)
(автор Woopertail, лицензия **GPLv3**) и [`pyTelegramBotAPI`](https://pypi.org/project/pyTelegramBotAPI/)
(MIT). Весь остальной код в репозитории — оригинальный.

Если планируете распространять/продавать **сам движок** в закрытом,
обфусцированном виде — сверьтесь с юристом на совместимость с GPLv3. Продажа
**отдельных плагинов**, устанавливаемых поверх уже работающего движка, —
более безопасная с этой точки зрения модель, и именно для неё спроектирован
плагин-API выше.
