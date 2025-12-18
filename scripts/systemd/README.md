# Systemd Service Configuration

This directory contains example systemd unit files for running vLLM and Ollama as system services.

## Installation

### 1. Copy service files

For system-wide installation:
```bash
sudo cp vllm.service.example /etc/systemd/system/vllm.service
sudo cp ollama.service.example /etc/systemd/system/ollama.service
```

For user-level installation:
```bash
mkdir -p ~/.config/systemd/user/
cp vllm.service.example ~/.config/systemd/user/vllm.service
cp ollama.service.example ~/.config/systemd/user/ollama.service
```

### 2. Edit service files

Edit the copied files and adjust paths, user/group, and environment variables to match your setup:
- `WorkingDirectory`: Path to Venom repository
- `User` and `Group`: System user running the service
- `Environment` variables: Model paths, ports, etc.

### 3. Reload systemd

For system services:
```bash
sudo systemctl daemon-reload
```

For user services:
```bash
systemctl --user daemon-reload
```

### 4. Enable and start services

For system services:
```bash
sudo systemctl enable vllm.service
sudo systemctl start vllm.service
sudo systemctl status vllm.service
```

For user services:
```bash
systemctl --user enable vllm.service
systemctl --user start vllm.service
systemctl --user status vllm.service
```

## Automatic Detection

The `vllm_service.sh` and `ollama_service.sh` scripts automatically detect if systemd services are available and use them if configured. The detection logic checks for:

1. Presence of `systemctl` command
2. Existence of the systemd unit file (e.g., `vllm.service`)

## Environment Variables

### vLLM Service

Control systemd behavior with environment variables:
- `VLLM_SYSTEMD_UNIT`: Name of the systemd unit (default: `vllm.service`)
- `VLLM_SYSTEMD_SCOPE`: Scope of the service - `system` or `user` (default: `system`)

### Ollama Service

Control systemd behavior with environment variables:
- `OLLAMA_SYSTEMD_UNIT`: Name of the systemd unit (default: `ollama.service`)
- `OLLAMA_SYSTEMD_SCOPE`: Scope of the service - `system` or `user` (default: `system`)

## Logs

Service logs are written to:
- vLLM: `/home/venom/Venom/logs/vllm.log`
- Ollama: `/home/venom/Venom/logs/ollama.log`

View real-time logs:
```bash
# System services
sudo journalctl -u vllm.service -f
sudo journalctl -u ollama.service -f

# User services
journalctl --user -u vllm.service -f
journalctl --user -u ollama.service -f
```

## Troubleshooting

### Service fails to start

1. Check service status:
   ```bash
   sudo systemctl status vllm.service
   ```

2. View detailed logs:
   ```bash
   sudo journalctl -u vllm.service -n 50
   ```

3. Verify paths in service file are correct
4. Ensure user/group have permissions to access directories and files

### Process won't stop

If the service becomes unresponsive:
```bash
# Find the PID
sudo systemctl show -p MainPID vllm.service

# Force kill if necessary
sudo kill -9 <PID>

# Restart the service
sudo systemctl restart vllm.service
```
