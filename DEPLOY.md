# Розгортання Interpres-Atom як системного сервісу

## Вимоги

- Ubuntu 22.04+
- Python 3.10+
- Ollama встановлена і запущена (`ollama serve`)

---

## Встановлення

### 1. Клонування репозиторію

```bash
sudo git clone https://github.com/lamerroma/localai-translator.git /opt/interpres-atom
```

### 2. Системний користувач

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin interpres
```

### 3. Віртуальне середовище та залежності

```bash
cd /opt/interpres-atom
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
```

### 4. Права доступу

```bash
sudo chown -R interpres:interpres /opt/interpres-atom
```

### 5. Systemd сервіс

```bash
sudo nano /etc/systemd/system/interpres-atom.service
```

Вміст файлу:

```ini
[Unit]
Description=Interpres-Atom Translation Server
After=network.target ollama.service

[Service]
Type=simple
User=interpres
WorkingDirectory=/opt/interpres-atom
ExecStart=/opt/interpres-atom/.venv/bin/python translate_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Запуск

```bash
sudo systemctl daemon-reload
sudo systemctl enable interpres-atom
sudo systemctl start interpres-atom
sudo systemctl status interpres-atom
```

Сервіс доступний на `http://<IP-сервера>:7860`

---

## Керування сервісом

| Дія | Команда |
|-----|---------|
| Запустити | `sudo systemctl start interpres-atom` |
| Зупинити | `sudo systemctl stop interpres-atom` |
| Перезапустити | `sudo systemctl restart interpres-atom` |
| Статус | `sudo systemctl status interpres-atom` |
| Логи (live) | `journalctl -u interpres-atom -f` |
| Логи (останні 100 рядків) | `journalctl -u interpres-atom -n 100` |

---

## Оновлення

```bash
cd /opt/interpres-atom
sudo git pull
sudo systemctl restart interpres-atom
```

Якщо з'явились нові залежності:

```bash
sudo /opt/interpres-atom/.venv/bin/pip install -r requirements.txt
sudo systemctl restart interpres-atom
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
| Interpres-Atom | 7860 |
| Ollama | 11434 |
