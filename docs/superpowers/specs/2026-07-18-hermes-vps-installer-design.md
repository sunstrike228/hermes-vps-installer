# Дизайн: одно-командный установщик Hermes для Ubuntu VPS

Дата: 2026-07-18
Статус: готов к ревью

## Цель

Публичный установщик для русскоязычного гайда, который разворачивает Hermes Agent на чистом Ubuntu VPS одной вставляемой в терминал командой. Пользователь не проходит общий мастер `hermes setup` и не выбирает provider, model, tools или gateway вручную.

При первом запуске от пользователя требуются только:

1. Telegram Bot Token от `@BotFather` — вставляется в скрытый terminal prompt;
2. авторизация OpenAI Codex через существующую ChatGPT-подписку по device-code flow.

После ввода Telegram token установщик не задаёт конфигурационных вопросов. Последний интерактивный этап — показ прямой ссылки `https://auth.openai.com/codex/device` и одноразового Codex-кода.

Для безопасной автоматической привязки владельца пользователь дополнительно отправляет показанную установщиком одноразовую фразу своему Telegram-боту. Telegram user ID вручную не вводится.

## Принятые решения

- Целевая система: Ubuntu VPS с systemd.
- Установщик запускается от `root` и gateway также работает от `root` — это явный выбор владельца проекта. Скрипт и README обязаны показать предупреждение, что бот с terminal-инструментами получает root-доступ к VPS.
- Репозиторий: публичный `sunstrike228/hermes-vps-installer`.
- Hermes устанавливается официальным `install.sh` с отключённым интерактивным мастером.
- Provider: `openai-codex` через ChatGPT/Codex OAuth, без API-ключа.
- Model: `gpt-5.6-terra`.
- Базовый reasoning effort: `medium`.
- Auto-effort: включён.
- Telegram gateway: systemd system service, включён при старте VPS и запускается сразу.

## Пользовательский интерфейс

Команда в гайде должна быть одной строкой и использовать зафиксированный release-тег:

```bash
curl -fsSL https://raw.githubusercontent.com/sunstrike228/hermes-vps-installer/v1.0.0/install.sh | bash
```

Для сессии не под root используется `sudo bash` на правой стороне pipe. Все интерактивные чтения выполняются из `/dev/tty`, поэтому pipe не ломает ввод.

## Последовательность установки

1. Проверить Ubuntu/Linux, наличие systemd, root-права, сеть, `/dev/tty`, свободное место и обязательные команды.
2. Установить минимальные системные зависимости через `apt-get` при необходимости.
3. Скачать официальный Hermes installer во временный файл и запустить его с `--skip-setup --non-interactive`. Версия Hermes фиксируется на проверенном upstream commit, указанном константой установщика.
4. Убедиться, что команда `hermes` доступна и `hermes doctor` не сообщает блокирующих проблем.
5. Запросить Telegram Bot Token скрытым вводом из `/dev/tty`.
6. Проверить формат токена и вызвать Telegram Bot API `getMe`. Не печатать токен ни в stdout, ни в логи.
7. Проверить `getWebhookInfo`. Если у бота уже настроен webhook, остановиться с объяснением вместо его удаления.
8. Сгенерировать криптографически случайную claim-фразу и показать безопасную deep-link ссылку на созданного бота. Пользователь нажимает Start; дополнительный terminal input не требуется.
9. До запуска gateway опрашивать Telegram `getUpdates`, принимать только точное совпадение с claim-фразой и извлекать `from.id`/`chat.id`. Устаревшие сообщения не считаются подтверждением.
10. Сохранить через безопасную атомарную запись с правами `0600`:

   ```text
   TELEGRAM_BOT_TOKEN=[REDACTED]
   TELEGRAM_ALLOWED_USERS=<captured user id>
   TELEGRAM_HOME_CHANNEL=<captured chat id>
   ```

11. Если валидная Codex OAuth-сессия ещё не существует, запустить напрямую:

   ```bash
   hermes auth add openai-codex
   ```

   Hermes показывает URL и одноразовый OpenAI-код и ждёт авторизацию. Никакой выбор provider/model не показывается.
12. Сохранить конфигурацию:

   ```yaml
   model:
     default: gpt-5.6-terra
     provider: openai-codex
   agent:
     reasoning_effort: medium
     reasoning_effort_auto:
       enabled: true
   ```

13. Выполнить минимальный реальный Codex smoke test на `gpt-5.6-terra`. Если модель недоступна конкретной подписке, завершить установку с точной ошибкой, не подменяя её другой моделью молча.
14. Установить и запустить systemd system service:

   ```bash
   hermes gateway install --system --run-as-user root --force --start-now --start-on-login
   ```

15. Проверить `systemctl is-enabled`, `systemctl is-active`, `hermes gateway status --system --deep` и отсутствие немедленного crash loop.
16. Отправить владельцу через Telegram подтверждение завершения и короткие команды `/status`, `/new`, `/goal`.
17. Показать итог: bot username, model, provider, reasoning, service status и команды диагностики. Секреты не показывать.

## Безопасность

- Токен Telegram вводится с отключённым echo.
- Секреты не передаются как CLI-аргументы, чтобы не попадать в process list и shell history.
- `.env`, OAuth store и временные файлы имеют права только для root.
- Временные файлы удаляются через `trap`.
- Скрипт не использует `eval` и не выполняет данные из Telegram.
- Claim-фраза генерируется через криптографический RNG и действует только в текущем запуске ограниченное время.
- Первый случайный пользователь не может захватить бота: принимается только точная новая claim-фраза.
- Webhook существующего бота не удаляется автоматически.
- Root-risk явно показан перед настройкой. Установщик не включает YOLO/approval bypass.
- Публичный README рекомендует сначала скачать и просмотреть скрипт, а затем запускать.

## Идемпотентность

Повторный запуск:

- не удаляет память, sessions, skills или проекты Hermes;
- обновляет/чинит официальный install и конфигурацию;
- переиспользует валидную Codex OAuth-сессию;
- переустанавливает systemd unit только через официальный `--force`;
- повторно запрашивает Telegram token только если токен отсутствует/невалиден либо оператор явно запускает режим повторной привязки;
- не создаёт второй competing gateway service.

## Обработка ошибок

- Каждая стадия имеет понятное имя и отдельный диагностический вывод.
- Ошибка OAuth, недоступная Terra, неверный Telegram token, timeout claim, активный webhook и неработающий systemd завершают скрипт с ненулевым кодом.
- После ошибки печатается точная команда продолжения или повторного запуска.
- Нельзя сообщать «готово», пока Codex smoke test, Telegram `getMe` и systemd active-check не прошли.
- Для сетевых запросов применяются ограниченные retry и timeout; бесконечных циклов нет.

## Репозиторий

Минимальная структура:

```text
hermes-vps-installer/
├── install.sh
├── README.md
├── LICENSE
├── tests/
│   ├── test_static.sh
│   └── test_installer.py
└── docs/superpowers/specs/
    └── 2026-07-18-hermes-vps-installer-design.md
```

## Проверка перед публикацией

1. `bash -n install.sh`.
2. `shellcheck install.sh` без error-level проблем.
3. Тесты функций token validation, `.env` atomic update, claim matching и OS/root preflight.
4. Dry-run в изолированном Ubuntu container без реальных секретов.
5. Полный end-to-end тест на отдельном Ubuntu/systemd окружении с тестовым Telegram bot и Codex OAuth либо документированный blocker, если отдельные тестовые credentials недоступны.
6. Проверка публичного raw URL и SHA-256 опубликованного `install.sh`.
7. Повторный запуск для проверки идемпотентности.

## Критерий готовности

Работа считается завершённой только если опубликованный raw-скрипт можно выполнить одной командой на поддерживаемом Ubuntu VPS, пользователь проходит только Codex device login, ввод Telegram token и отправку claim-фразы, после чего `gpt-5.6-terra` отвечает через автоматически запущенный Telegram gateway с `medium` + auto-effort.