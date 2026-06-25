# Документация

## Скрипты администрирования

В каталоге `scripts/` находятся утилиты для ручного управления данными в БД. Они не запускаются автоматически при старте приложения — их вызывают администратор вручную.

### `promote_user.py` — назначение роли пользователю

Скрипт меняет роль (`role`) существующего пользователя в таблице `users`. Используется, когда нужно вручную выдать права администратора или реviewer без изменения кода.

#### Роли

| Роль | Значение | Права (кратко) |
|------|----------|----------------|
| `user` | Обычный пользователь | Загрузка документов, работа со своими записями |
| `reviewer` | Ревьюер | Проверка и смена статуса документов |
| `admin` | Администратор | Полный доступ, удаление документов, редактирование метаданных |

#### Синтаксис

```bash
python scripts/promote_user.py <login> <role>
```

- `<login>` — логин пользователя (как при регистрации в системе)
- `<role>` — одно из значений: `admin`, `reviewer`, `user`

#### Предварительные условия

1. Пользователь с указанным логином уже зарегистрирован в системе.
2. Файл `.env` настроен (можно скопировать из `.env.example`).
3. PostgreSQL доступна и миграции применены (`alembic upgrade head`).

---

## Запуск из Docker (рекомендуется)

Если приложение поднято через Docker Compose, скрипт нужно запускать **внутри контейнера `api`**. Там уже установлены зависимости и `DATABASE_URL` указывает на сервис `db` (`@db:5432`).

Убедитесь, что контейнеры запущены:

```bash
docker compose up -d
```

Назначить роль:

```bash
docker compose exec api python scripts/promote_user.py ivanov admin
```

Примеры:

```bash
# Повысить до администратора
docker compose exec api python scripts/promote_user.py ivanov admin

# Назначить реviewer
docker compose exec api python scripts/promote_user.py ivanov reviewer

# Вернуть обычную роль
docker compose exec api python scripts/promote_user.py ivanov user
```

Успешный вывод:

```text
User 'ivanov' role set to 'admin'.
```

Если пользователь не найден:

```text
User 'ivanov' not found.
```

(код выхода `1`)

---

## Запуск на хосте (без exec в контейнер)

Подходит для локальной разработки без Docker или когда контейнер `api` не запущен, но PostgreSQL доступна с хоста.

1. Создайте и активируйте виртуальное окружение, установите зависимости:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. В `.env` укажите `DATABASE_URL` с хостом `localhost` и портом из `POSTGRES_HOST_PORT` (по умолчанию `5433`):

   ```env
   DATABASE_URL=postgresql+asyncpg://archiveuser:change_me_in_production@localhost:5433/archivedb
   ```

   Если БД крутится в Docker, а скрипт — на хосте, используйте именно `localhost:5433`, а не `@db:5432`.

3. Запустите скрипт из корня репозитория:

   ```bash
   python scripts/promote_user.py ivanov admin
   ```

---

## Миграции (справочно)

Для применения миграций из Docker используйте тот же контейнер `api`:

```bash
docker compose exec api alembic upgrade head
```

С хоста — через `run_migrations.py` или `alembic`, с `ALEMBIC_DATABASE_URL` на `localhost` (см. комментарии в `.env.example`).
