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

    Каждое уведомление фиксируется в app_steps отдельной строкой,
    чтобы админ видел, кому и что ушло (менеджеру, администратору,
    владельцу заявки). Журнал не роняет уведомления: ошибки записи
    в app_steps глушатся.
    """
    def _log(channel: str, target: str, status: str, msg: str) -> None:
        try:
            from services import app_steps as _stp
            note = '%s → %s: %s' % (channel, target, msg)
            if len(note) > 200:
                note = note[:197] + '…'
            _stp.step(app_id, 'notify', status, note)
        except Exception:
            pass

    try:
        if event == "taken":
            _log('notify', 'менеджер', 'run', 'уведомление: заявка взята в работу')
            notify_manager_taken(app_id)
            _log('notify', 'менеджер', 'ok', 'менеджер уведомлён о взятии')
        elif event == "new":
            _log('notify', 'администратор', 'run', 'уведомление: новая заявка')
            notify_admins_new_app(app_id, **kwargs)
            _log('notify', 'администратор', 'ok', 'администратор уведомлён о новой заявке')
        elif event == "done":
            _log('notify', 'менеджер', 'run', 'уведомление: цикл завершён')
            notify_manager_done(app_id, **kwargs)
            _log('notify', 'менеджер', 'ok', 'менеджер уведомлён о завершении')
            _log('notify', 'администратор', 'run', 'уведомление админу о завершении')
            notify_admins_done(app_id, **kwargs)
            _log('notify', 'администратор', 'ok', 'администратор уведомлён о завершении')
        elif event == "fail":
            _log('notify', 'администратор', 'run', 'уведомление: цикл остановлен')
            notify_admins_done(app_id, ok=False, **kwargs)
            _log('notify', 'администратор', 'ok', 'администратор уведомлён об ошибке')
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