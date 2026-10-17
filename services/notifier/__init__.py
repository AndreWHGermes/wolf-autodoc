"""
Единая точка входа для уведомлений.

Тонкий фасад над bot.notify. Новый код может звать просто
«from services.notifier import notify» вместо «from bot.notify import ...».

Точка расширения: добавить email-канал, push-уведомления — добавляем
новые модули в services/notifier/ и регистрируем здесь.
"""
from bot.notify import (  # noqa: F401
    notify_manager_taken,
    notify_admins_new_app,
    notify_manager_done,
    notify_admins_done,
)


def notify(event: str, app_id: int, **kwargs) -> None:
    """Единый диспетчер уведомлений.

    event:
    - 'taken'    → notify_manager_taken(app_id)
    - 'new'      → notify_admins_new_app(app_id, **kwargs)
    - 'done'     → notify_manager_done(app_id, **kwargs) + notify_admins_done(app_id, **kwargs)
    - 'fail'     → notify_admins_done(app_id, ok=False, **kwargs) — будущее

    Не выбрасывает исключений: уведомления не должны ломать основной поток.
    """
    try:
        if event == "taken":
            notify_manager_taken(app_id)
        elif event == "new":
            notify_admins_new_app(app_id, **kwargs)
        elif event == "done":
            notify_manager_done(app_id, **kwargs)
            notify_admins_done(app_id, **kwargs)
        elif event == "fail":
            notify_admins_done(app_id, ok=False, **kwargs)
        else:
            # неизвестный event — тихо игнорируем
            pass
    except Exception:
        # уведомления не должны ломать обработку
        pass


__all__ = [
    "notify",
    "notify_manager_taken",
    "notify_admins_new_app",
    "notify_manager_done",
    "notify_admins_done",
]