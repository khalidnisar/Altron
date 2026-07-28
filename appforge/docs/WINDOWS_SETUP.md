# Windows setup and troubleshooting

## Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10 21H2+ or Windows 11 |
| Docker Desktop | 4.20 or newer, WSL2 backend |
| RAM | 8 GB minimum, 16 GB recommended |
| Disk | ~4 GB for images |
| Virtualization | Enabled in BIOS/UEFI |

## Install

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and accept the
   WSL2 prompts.
2. Launch it and wait for the whale icon to stop animating.
3. Confirm **Settings → General → Use the WSL 2 based engine** is ticked.
4. Double-click `start.bat`, or run `.\start.ps1 -Seed` from PowerShell.

First run pulls base images and builds; expect 3–6 minutes. Subsequent starts take
seconds.

## Script options

```powershell
.\start.ps1              # start only
.\start.ps1 -Seed        # start and seed a demo pipeline
.\start.ps1 -Rebuild     # force a no-cache rebuild
.\start.ps1 -NoBrowser   # do not open a browser
.\stop.ps1               # stop, preserve data
.\stop.ps1 -RemoveData   # stop and delete volumes
```

## Troubleshooting

### "Docker was not found on PATH"
Docker Desktop is not installed, or its CLI was not added to PATH. Reinstall and reboot.

### "Docker Desktop is installed but not running"
Start Docker Desktop and wait for the status indicator to settle before re-running.

### "Docker Desktop is currently in Windows-container mode"
The main stack needs Linux containers. Switch back:

```powershell
& "$Env:ProgramFiles\Docker\Docker\DockerCli.exe" -SwitchDaemon
```

### PowerShell blocks the script
`start.bat` already bypasses execution policy. To run the `.ps1` directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Seed
```

### Port 3000 or 8000 already in use

```powershell
netstat -ano | findstr ":3000"
taskkill /PID <pid> /F
```

Or change the host side of the mapping in `docker-compose.yml`
(`"3001:3000"`), leaving the container port untouched.

### Dashboard loads but shows no data
The API may still be warming up. Check:

```powershell
docker compose ps
docker compose logs -f api
curl http://localhost:8000/api/health
```

Then seed from **Settings → Seed platform**.

### Build fails with a network or TLS error
Usually a corporate proxy. Configure it under Docker Desktop
**Settings → Resources → Proxies**, then `.\start.ps1 -Rebuild`.

### Slow file access
Keep the repository on the Windows filesystem (`C:\...`), not inside a WSL mount
accessed through `\\wsl$`. Named volumes are used for the database and artifacts, which
avoids the worst of the cross-filesystem overhead.

### Reset everything

```powershell
.\stop.ps1 -RemoveData
docker system prune -af
.\start.ps1 -Seed
```

## Verifying the stack

```powershell
docker compose ps                       # all services should be running/healthy
curl http://localhost:8000/api/health   # {"status":"ok",...}
docker compose logs -f worker           # agent activity
```

## Windows containers

Needed only for Windows-native build tooling. Docker Desktop runs Linux **or** Windows
containers, never both simultaneously.

```powershell
& "$Env:ProgramFiles\Docker\Docker\DockerCli.exe" -SwitchDaemon
docker compose -f docker-compose.windows.yml up -d --build
```

The image tag must match your host kernel. Override if you are on Server 2019:

```powershell
docker compose -f docker-compose.windows.yml build --build-arg WINDOWS_TAG=ltsc2019
```

Windows base images are large (several GB) and the first pull is slow.
