# Сервер 192.168.88.59 — Шпаргалка

## Підключення
```bash
ssh coyotl@192.168.88.59
```

---

## Ollama

| Дія | Команда |
|-----|---------|
| Статус | `sudo systemctl status ollama` |
| Перезапуск | `sudo systemctl restart ollama` |
| Зупинити | `sudo systemctl stop ollama` |
| Список моделей | `ollama list` |
| Завантажити модель | `ollama pull gemma4:e4b` |
| Видалити модель | `ollama rm <назва>` |
| Тест | `ollama run gemma4:e4b "привіт"` |

Конфіг файл: `/etc/systemd/system/ollama.service`
Порт: `11434`

---

## Open WebUI

| Дія | Команда |
|-----|---------|
| Статус | `docker ps` |
| Перезапуск | `docker restart open-webui` |
| Зупинити | `docker stop open-webui` |
| Запустити | `docker start open-webui` |
| Логи | `docker logs open-webui --tail 50` |
| Оновити | `docker pull ghcr.io/open-webui/open-webui:main && docker stop open-webui && docker rm open-webui` |

Веб-інтерфейс: `http://192.168.88.59:8080`

---

## Docker (повторний запуск Open WebUI після оновлення)
```bash
docker run -d \
  --network=host \
  -v open-webui:/app/backend/data \
  -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

---

## Timeshift (бекапи)

| Дія | Команда |
|-----|---------|
| Створити snapshot | `sudo timeshift --create --comments "опис" --snapshot-device /dev/sda1` |
| Список snapshots | `sudo timeshift --list` |
| Відновити | `sudo timeshift --restore` |

Бекапи зберігаються на `/dev/sda1` (SATA SSD)

---

## GPU моніторинг
```bash
watch -n 1 nvidia-smi
```

---

## Системне

| Дія | Команда |
|-----|---------|
| Оновити пакети | `sudo apt update && sudo apt upgrade -y` |
| Перезавантажити | `sudo reboot` |
| Місце на дисках | `df -h` |
| Диски | `lsblk` |
| Навантаження | `htop` |

---

## TODO
- [ ] Розширити LVM на nvme0n1 з 100GB до ~950GB
- [ ] Оновити IP сервера в desktop app
