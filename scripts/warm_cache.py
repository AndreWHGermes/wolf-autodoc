"""Прогрев кэшей Wolf: адреса клиентов и тексты документов.

Первый разбор документов клиента занимает ~10 секунд, из-за чего страница
заявки на первом заходе не успевала ответить. Прогрев выполняется в фоне
при старте сервиса — пользователь всегда попадает на прогретый кэш.
"""
import sys, sqlite3, time

sys.path.insert(0, "/opt/wolf_v2")


def warm():
    try:
        from CLIENT.CLIENT import _address_from_client_docs, _ADDR_DOC_CACHE
        c = sqlite3.connect("/opt/wolf_v2/data/wolf.db")
        ids = [r[0] for r in c.execute("SELECT id FROM CLIENT ORDER BY id")]
        t0 = time.time()
        for cid in ids:
            try:
                _address_from_client_docs(cid)
            except Exception:
                pass
        print("прогрев адресов: %d клиентов за %.1f сек, в кэше %d"
              % (len(ids), time.time() - t0, len(_ADDR_DOC_CACHE)), flush=True)
    except Exception as e:
        print("прогрев не удался:", e, flush=True)


if __name__ == "__main__":
    warm()
