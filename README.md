# FPHelper
[![python](https://img.shields.io/badge/python-3.10%2B-yellow?style=for-the-badge&logo=python)](https://www.python.org/downloads/)
[![plugins](https://img.shields.io/badge/%F0%9F%A7%A9%20%D0%BF%D0%BB%D0%B0%D0%B3%D0%B8%D0%BD%D1%8B-%D1%81%D0%B2%D0%BE%D0%B8-green?style=for-the-badge)](#-для-разработчиков-плагинов)
[![funpayapi](https://img.shields.io/badge/FunPayAPI-GPLv3-blue?style=for-the-badge)](https://pypi.org/project/FunPayAPI/)
[![telegram](https://img.shields.io/badge/telegram-мультиадмины-2CA5E0?style=for-the-badge&logo=telegram)](#-несколько-админов)

Бот-помощник для продавцов FunPay с открытой системой плагинов и поддержкой нескольких админов 🤖🟩

---

## 🗺️ Навигация
- **[Возможности](#️-возможности)**
- **[Установка](#️-установка)**
- **[Несколько админов](#-несколько-админов)**
- **[Для разработчиков плагинов](#-для-разработчиков-плагинов)**
- **[Структура проекта](#-структура-проекта)**
- **[О лицензии](#️-о-лицензии)**

## ⚙️ Возможности

### 🤖 Управление в Telegram
- **🔐 Мультиадминство** — несколько человек управляют одним ботом
- **🆔 `/whoami`** — узнать свой Telegram ID и попроситься в админы
- **📋 `/plugins`** — список загруженных плагинов
- **🔔 Рассылка админам** — уведомления о заказах/событиях всем сразу

### ✨ Ядро
- **🧩 Система плагинов** — папка `plugins/`, любой плагин с `setup(ctx)` подхватывается сам
- **📡 Шина событий FunPay** — новые сообщения, заказы, смена статуса заказа и другие события Runner'а
- **💾 Изолированное хранилище** — у каждого плагина своё JSON-хранилище (`ctx.storage`)
- **⚙️ Мастер первого запуска** — golden key, токен бота и первый админ настраиваются один раз, без ручной правки файлов

## ⬇️ Установка

### 🔷 Windows
1. Установите **Python 3.10+** с [официального сайта](https://www.python.org/downloads/) (отметьте `Add to PATH`).
2. Скачайте проект (`git clone` или архивом) и откройте папку.
3. Запустите `install.bat` — создастся виртуальное окружение и установятся зависимости.
4. Запустите `run.bat`.
5. При первом запуске введите в консоли: golden key от FunPay, токен Telegram-бота (от [@BotFather](https://t.me/BotFather)) и свой Telegram ID.

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
  | `ctx.telegram` | `@ctx.telegram.command("имя")`, `@ctx.telegram.callback("префикс")`, `.reply()`, `.send()`, `.bot` (сырой `telebot.TeleBot`) |
  | `ctx.storage` | JSON-хранилище плагина: `.get(key, default)`, `.set(key, value)`, `.update({...})`, `.all()` |
  | `ctx.logger` | `logging.Logger`, уже настроенный под имя плагина |
  | `ctx.notify_admins(text)` | отправить сообщение всем админам разом |

  По умолчанию Telegram-команды плагина доступны только админам. Чтобы сделать команду
  публичной: `@ctx.telegram.command("start", admin_only=False)`.

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
