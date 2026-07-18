# Hermes Agent: one-command installer for Ubuntu VPS

Публичный установщик Hermes Agent без длинного setup-мастера. Он предназначен для чистого Ubuntu VPS с systemd и автоматически настраивает:

- OpenAI Codex через существующую ChatGPT-подписку;
- модель `gpt-5.6-terra`;
- reasoning `medium`;
- включённый auto-effort;
- Telegram с безопасной привязкой владельца;
- systemd gateway с немедленным запуском и автозапуском после reboot.

## ⚠️ Важное предупреждение о root-доступе

По требованиям этого гайда Hermes gateway запускается от **root**. Это означает, что AI-агент и его terminal-инструменты потенциально получают полный root-доступ ко всему VPS. Используйте отдельный VPS, не храните на нём посторонние секреты и никому не передавайте Telegram Bot Token.

Более безопасный вариант — отдельный непривилегированный Linux-пользователь — намеренно не используется в `v1.0.0`, поскольку этот установщик повторяет выбранную конфигурацию гайда.

## Что потребуется

1. Ubuntu VPS с systemd, минимум 2 GB свободного места и исходящим HTTPS.
2. Root shell или пользователь с `sudo`.
3. ChatGPT-подписка с доступом к OpenAI Codex.
4. Новый Telegram-бот, созданный через [@BotFather](https://t.me/BotFather): отправьте `/newbot` и скопируйте выданный token.

## Установка одной командой

Скопируйте всю строку в terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/sunstrike228/hermes-vps-installer/v1.0.0/install.sh -o /tmp/hermes-vps-install.sh && sudo bash /tmp/hermes-vps-install.sh
```

Если вы уже вошли на VPS как root, доступен короткий pipe-вариант:

```bash
curl -fsSL https://raw.githubusercontent.com/sunstrike228/hermes-vps-installer/v1.0.0/install.sh | bash
```

Первый вариант безопаснее: скрипт остаётся в `/tmp/hermes-vps-install.sh`, и перед запуском его можно посмотреть через `less`.

## Что увидит пользователь

Установщик не запускает `hermes setup` и не показывает меню provider/model/tools/gateway.

1. Установит зафиксированную проверенную версию Hermes.
2. Попросит вставить Telegram Bot Token. Ввод скрыт и не сохраняется в shell history.
3. Покажет приватную ссылку `t.me/...?...`, которую нужно открыть и нажать **Start**. Так установщик безопасно определяет Telegram user ID владельца — вводить его вручную не нужно.
4. Покажет только официальный Codex device-login:
   - ссылка `https://auth.openai.com/codex/device`;
   - одноразовый код.
5. После подтверждения ChatGPT-подписки проверит реальный ответ `gpt-5.6-terra`.
6. Установит и запустит gateway как systemd service.
7. Пришлёт в Telegram сообщение об успешном запуске.

Никаких API-ключей OpenAI не требуется: используется OAuth-доступ вашей ChatGPT-подписки.

## Итоговая конфигурация

```yaml
model:
  provider: openai-codex
  default: gpt-5.6-terra
agent:
  reasoning_effort: medium
  reasoning_effort_auto:
    enabled: true
```

Telegram ограничивается автоматически определённым владельцем. Установщик **не** включает allow-all, YOLO или отключение command approvals.

## Проверка и управление

```bash
hermes --version
hermes config
hermes gateway status --system --deep
systemctl status hermes-gateway.service --no-pager
journalctl -u hermes-gateway.service -n 100 --no-pager
```

Перезапуск gateway:

```bash
hermes gateway restart --system
```

Остановка и запуск:

```bash
hermes gateway stop --system
hermes gateway start --system
```

## Dry run без установки

Сначала скачайте release-скрипт, затем выведите план действий:

```bash
curl -fsSL https://raw.githubusercontent.com/sunstrike228/hermes-vps-installer/v1.0.0/install.sh -o /tmp/hermes-vps-install.sh && sudo HERMES_INSTALLER_DRY_RUN=1 bash /tmp/hermes-vps-install.sh
```

Dry run не просит токены, не запускает OAuth и не изменяет систему.

## Безопасность

- Telegram token читается через `/dev/tty` с отключённым echo.
- Token не передаётся аргументом процесса и не записывается в shell history.
- Telegram API вызывается из Python-процесса: token не появляется в URL командной строки `curl`.
- `~/.hermes/.env` и OAuth-хранилище доступны только root.
- Существующий Telegram webhook не удаляется автоматически.
- Привязка владельца принимает только новую криптографически случайную deep-link фразу в private chat.
- Terra не подменяется другой моделью при ошибке: установка останавливается с диагностикой.
- Официальный Hermes installer и checkout закреплены за upstream commit `e4ea0a0ed7fc24761b2b425146893561a73216e1`.

## Удаление

Сначала остановите и удалите service:

```bash
hermes gateway stop --system
hermes gateway uninstall --system
```

После проверки резервных копий можно запустить официальный деинсталлятор:

```bash
hermes uninstall
```

Не удаляйте `~/.hermes` вслепую: там находятся sessions, memory, skills, Telegram token и OAuth-состояние.

## Разработка и тесты

```bash
bash -n install.sh
shellcheck install.sh
python3 -m unittest discover -s tests -v
bash tests/test_static.sh
```

Подробные фактические результаты проверки публикуются в [`docs/verification.md`](docs/verification.md).

## Лицензия

MIT. Hermes Agent является отдельным проектом Nous Research и устанавливается из официального репозитория.
