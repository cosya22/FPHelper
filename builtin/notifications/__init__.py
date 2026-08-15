"""Включение/выключение уведомлений владельцу по типам событий."""

from fphelper import PluginInfo
from fphelper.telegram_admin import NOTIFICATION_TYPES

INFO = PluginInfo(
    name="Notifications",
    version="1.0.0",
    description="Включение/выключение уведомлений владельцу по типам событий.",
    author="you",
)

SECTION = "🔔 Уведомления"


def setup(ctx):
    for event_type, label in NOTIFICATION_TYPES.items():
        def make_toggle(event_type=event_type, label=label):
            def toggle_label():
                on = ctx.telegram.is_notification_enabled(event_type)
                return f"🟢 {label}" if on else f"🔴 {label}"
            return toggle_label

        toggle_label = make_toggle()

        def make_handler(event_type=event_type):
            def cbq_toggle(call):
                ctx.telegram.toggle_notification(event_type)
                ctx.telegram.refresh_section(call, SECTION)
            return cbq_toggle

        ctx.telegram.menu_item(SECTION, toggle_label, f"notif:toggle:{event_type}")(make_handler())
