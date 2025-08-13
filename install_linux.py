#!/usr/bin/env python3
"""
Bitcoin Mixer - Linux Otomatik Kurulum Betiği

Bu betik: Docker/Docker Compose kurar (gerekiyorsa), .env dosyasını oluşturur,
opsiyonel olarak self-signed SSL sertifikası üretir ve docker compose servislerini başlatır.
"""

import os
import sys
import subprocess
import shutil
import time
import getpass
from datetime import datetime

BANNER = """
=== Bitcoin Mixer - Otomatik Kurulum (Linux) ===
Bu betik: Docker/Docker Compose kurar, .env dosyası oluşturur, servisleri başlatır.
"""


def run(cmd, sudo=False, check=True):
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + (cmd if isinstance(cmd, list) else ["bash", "-lc", cmd])
    elif isinstance(cmd, str):
        cmd = ["bash", "-lc", cmd]
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def which(bin_name):
    return shutil.which(bin_name) is not None


def prompt(question, default=None, secret=False):
    q = f"{question}"
    if default is not None:
        q += f" [{default}]"
    q += ": "
    if secret:
        val = getpass.getpass(q)
    else:
        val = input(q).strip()
    return (default if (val == "" and default is not None) else val)


def _has_compose_plugin():
    try:
        out = subprocess.check_output(["docker", "compose", "version"], stderr=subprocess.STDOUT)
        return b"Docker Compose" in out
    except Exception:
        return False


def ensure_docker():
    if which("docker") and (which("docker-compose") or _has_compose_plugin()):
        print("Docker ve Compose algılandı.")
        return
    print("Docker/Compose bulunamadı. Kurulum başlıyor (Ubuntu/Debian varsayılanı).")

    # Paket yöneticisi tespiti
    apt = which("apt-get")
    dnf = which("dnf")
    yum = which("yum")

    if apt:
        # Docker resmi talimatlar (güncel)
        run("sudo apt-get update", check=True)
        run("sudo apt-get install -y ca-certificates curl gnupg lsb-release", check=True)
        run('sudo install -m 0755 -d /etc/apt/keyrings', check=True)
        run('curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg | '
            'sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg', check=True)
        run('echo "deb [arch=$(dpkg --print-architecture) '
            'signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/'
            '$(. /etc/os-release; echo "$ID") $(. /etc/os-release; echo "$VERSION_CODENAME") stable" | '
            'sudo tee /etc/apt/sources.list.d/docker.list > /dev/null', check=True)
        run("sudo apt-get update", check=True)
        run("sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin", check=True)
        run("sudo systemctl enable --now docker", check=True)
    elif dnf or yum:
        pm = "dnf" if dnf else "yum"
        run(f"sudo {pm} -y install dnf-plugins-core || true", check=False)
        run("sudo mkdir -p /etc/yum.repos.d", check=False)
        run(f"sudo {pm} config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo", check=False)
        run(f"sudo {pm} -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin", check=False)
        run("sudo systemctl enable --now docker", check=False)
    else:
        print("Uyarı: Paket yöneticisi tespit edilemedi. Lütfen Docker’ı manuel kurun:")
        print("https://docs.docker.com/engine/install/")
        sys.exit(1)

    print("Docker kuruldu. Compose eklentisi:", "var" if _has_compose_plugin() else "yok")


def compose_cmd():
    return ["docker", "compose"] if _has_compose_plugin() else (["docker-compose"] if which("docker-compose") else None)


def write_env(env_path, data: dict):
    if os.path.exists(env_path):
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(env_path, env_path + f".bak-{ts}")
        print(f"Var olan .env yedeklendi: {env_path}.bak-{ts}")
    lines = []
    for k, v in data.items():
        lines.append(f"{k}={v}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f".env yazıldı: {env_path}")


def ensure_ssl():
    os.makedirs("ssl", exist_ok=True)
    cert = "ssl/cert.pem"
    key = "ssl/key.pem"
    if os.path.exists(cert) and os.path.exists(key):
        print("SSL sertifikaları mevcut, atlanıyor.")
        return
    print("Self-signed SSL sertifikası oluşturuluyor...")
    run('openssl req -x509 -newkey rsa:4096 -nodes -out ssl/cert.pem -keyout ssl/key.pem -days 365 '
        '-subj "/C=TR/ST=State/L=City/O=Org/CN=localhost"', sudo=False, check=True)
    print("SSL sertifikaları oluşturuldu: ssl/cert.pem, ssl/key.pem")


def bring_up(services):
    cmd = compose_cmd()
    if not cmd:
        print("Docker Compose bulunamadı. Lütfen docker-compose kurun.")
        sys.exit(1)
    run(cmd + ["up", "-d", "--build"] + services, check=True)


def main():
    if not os.path.exists("docker-compose.yml"):
        print("Hata: Bu betiği proje klasöründe çalıştırın (docker-compose.yml bulunamadı).")
        sys.exit(1)

    print(BANNER)

    # Girdi al
    print("Aşağıdaki bilgiler sadece ilk kurulum için gerekli.")
    secret_key = prompt("SECRET_KEY (boş bırakılırsa otomatik oluşturulur)", default="")
    if not secret_key:
        import secrets
        secret_key = secrets.token_hex(32)

    # Bitcoin RPC bilgileri
    rpc_user = prompt("Bitcoin RPC kullanıcı adı (rpcuser)", default="bitcoinrpc")
    rpc_pass = prompt("Bitcoin RPC parolası (rpcpassword)", default="", secret=True)
    rpc_host = prompt("Bitcoin RPC host", default="host.docker.internal")
    rpc_port = prompt("Bitcoin RPC port", default="8332")

    # Nginx/SSL seçimi
    use_nginx = prompt("Nginx + SSL (HTTPS) ile çalıştırılsın mı? (y/N)", default="N").lower().startswith("y")

    # Docker/Compose kur
    ensure_docker()

    # .env yaz
    env = {
        "SECRET_KEY": secret_key,
        "FLASK_ENV": "production",
        "DATABASE_URL": "postgresql://mixer:mixer_password@postgres:5432/mixer_db",
        "REDIS_URL": "redis://:redis_password@redis:6379/0",
        "CELERY_BROKER_URL": "redis://:redis_password@redis:6379/1",
        "CELERY_RESULT_BACKEND": "redis://:redis_password@redis:6379/2",
        "RPC_USER": rpc_user,
        "RPC_PASS": rpc_pass,
        "RPC_HOST": rpc_host,
        "RPC_PORT": rpc_port,
        "MIN_AMOUNT": "0.001",
        "MAX_AMOUNT": "100",
        "FEE_PERCENT": "0.03",
        "MIXING_ROUNDS": "3",
        "DELAY_MINUTES_MIN": "10",
        "DELAY_MINUTES_MAX": "60",
        "RATE_LIMIT_SECONDS": "6",
        "LOG_LEVEL": "INFO",
        "CORS_ORIGINS": "https://yourdomain.com",
    }
    write_env(".env", env)

    # SSL istenirse üret
    if use_nginx:
        ensure_ssl()

    # Servisleri ayağa kaldır
    core_services = ["postgres", "redis", "web", "celery_worker", "celery_beat"]
    if use_nginx:
        core_services.append("nginx")

    print("Servisler başlatılıyor...")
    bring_up(core_services)

    # Sağlık kontrolü ve çıktı
    time.sleep(5)
    print("\nKurulum tamamlandı.")
    print("- Uygulama (HTTP):  http://localhost:5000")
    if use_nginx:
        print("- Uygulama (HTTPS): https://localhost")
    print("- Loglar için:      docker compose logs -f")
    print("- Servisler:        docker compose ps")

    # Bitcoin RPC hatırlatması
    print("\nBitcoin Core RPC ayarlarını unutmayın (bitcoin.conf):")
    print("server=1")
    print(f"rpcuser={rpc_user}")
    print(f"rpcpassword={'*' * max(8, len(rpc_pass) or 8)}")
    print("rpcallowip=127.0.0.1")
    print("rpcbind=0.0.0.0 (gerekirse)")


if __name__ == "__main__":
    if sys.platform.startswith("linux"):
        main()
    else:
        print("Bu betik Linux içindir.")



