# Beta deployment

The beta instance runs independently from production:

- application directory: `/opt/interpres-atom-beta`
- application port: `7861`
- Ollama endpoint: `http://127.0.0.1:11434/v1`
- systemd unit: `interpres-atom-beta.service`

## First setup

Run on the server:

```bash
cd /opt/interpres-atom-beta
python3 -m venv .venv-beta
.venv-beta/bin/pip install --upgrade pip
.venv-beta/bin/pip install -r requirements.txt
```

In `/opt/interpres-atom-beta/translator_config.json`, set:

```json
"base_url": "http://127.0.0.1:11434/v1"
```

Install and start the beta service:

```bash
sudo cp /opt/interpres-atom-beta/interpres-atom-beta.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now interpres-atom-beta.service
sudo systemctl status interpres-atom-beta.service
```

The beta interface is available at `http://SERVER_IP:7861`.

## Checks

```bash
curl -I http://127.0.0.1:7860/
curl -I http://127.0.0.1:7861/
journalctl -u interpres-atom-beta.service -n 100 --no-pager
```

Both `7860` and `7861` must respond. The production service does not need to
be restarted when the beta service is installed or updated.

## Beta update

```bash
cd /opt/interpres-atom-beta
git pull --ff-only
.venv-beta/bin/pip install -r requirements.txt
sudo systemctl restart interpres-atom-beta.service
sudo systemctl status interpres-atom-beta.service
```
