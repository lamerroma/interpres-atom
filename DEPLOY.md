# Розгортання Interpres-API як системного сервісу

## Вимоги

- Ubuntu 22.04+
- Python 3.10+
- Ollama встановлена і запущена (`ollama serve`)

---

## Встановлення

### 1. Клонування репозиторію

```bash
sudo git clone https://github.com/lamerroma/localai-translator.git /opt/interpres-api
```

### 2. Системний користувач

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin interpres
```

### 3. Віртуальне середовище та залежності

```bash
cd /opt/interpres-api
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
```

### 4. Права доступу

```bash
sudo chown -R interpres:interpres /opt/interpres-api
```

### 5. Systemd сервіс

```bash
sudo nano /etc/systemd/system/interpres-api.service
```

Вміст файлу:

```ini
[Unit]
Description=Interpres-API Translation Server
After=network.target ollama.service

[Service]
Type=simple
User=interpres
WorkingDirectory=/opt/interpres-api
ExecStart=/opt/interpres-api/.venv/bin/python translate_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Запуск

```bash
sudo systemctl daemon-reload
sudo systemctl enable interpres-api
sudo systemctl start interpres-api
sudo systemctl status interpres-api
```

Сервіс доступний на `http://<IP-сервера>:7860`

---

## Керування сервісом

| Дія | Команда |
|-----|---------|
| Запустити | `sudo systemctl start interpres-api` |
| Зупинити | `sudo systemctl stop interpres-api` |
| Перезапустити | `sudo systemctl restart interpres-api` |
| Статус | `sudo systemctl status interpres-api` |
| Логи (live) | `journalctl -u interpres-api -f` |
| Логи (останні 100 рядків) | `journalctl -u interpres-api -n 100` |

---

## Оновлення

```bash
cd /opt/interpres-api
sudo git pull
sudo systemctl restart interpres-api
```

Якщо з'явились нові залежності:

```bash
sudo /opt/interpres-api/.venv/bin/pip install -r requirements.txt
sudo systemctl restart interpres-api
```

---

## Конфігурація

Налаштування зберігаються у `translator_config.json` (створюється автоматично при першому запуску).  
Змінити параметри можна через веб-інтерфейс: `http://<IP>:7860/admin`

Логін/пароль адмін-панелі за замовчуванням: `admin` / `translate`

---

## Порти

| Сервіс | Порт |
|--------|------|
| Interpres-API | 7860 |
| Ollama | 11434 |
