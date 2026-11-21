@echo off
chcp 65001 > nul
rem Первый запуск проекта на Windows.
rem Перед запуском: создайте базу в PostgreSQL, запустите Redis и создайте файл .env (см. README.md).

if not exist .env (
    echo Нет файла .env. Скопируйте .env.sample в .env и впишите пароль от PostgreSQL.
    pause
    exit /b 1
)

echo === Установка зависимостей ===
poetry lock || goto :error
poetry install || goto :error

echo === Миграции ===
poetry run python manage.py makemigrations users mailing || goto :error
poetry run python manage.py migrate || goto :error

echo === Группа «Менеджеры» ===
poetry run python manage.py create_groups || goto :error

echo === Создание администратора (введите email и пароль) ===
poetry run python manage.py createsuperuser || goto :error

echo === Запуск сервера: http://127.0.0.1:8000/ ===
poetry run python manage.py runserver
exit /b 0

:error
echo.
echo Что-то пошло не так. Скопируйте текст ошибки выше.
pause
exit /b 1
