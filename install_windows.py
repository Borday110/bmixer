#!/usr/bin/env python3
"""
Bitcoin Mixer - Windows Otomatik Kurulum Betiği

Bu betik: .env dosyasını oluşturur, (varsa) self-signed SSL sertifikası üretir
ve Docker Desktop ile docker compose servislerini başlatır.

Notlar:
- Docker Desktop kurulu ve çalışır durumda olmalıdır (WSL 2 önerilir).
- Bitcoin Core RPC (bitcoind) host üzerinde çalışmalı ve .env ile eşleşmelidir.
"""

import os
import sys
import subprocess
import shutil
import time
import secrets
import getpass
from datetime import datetime


def is_windows() -> bool:
    return os.name == 'nt' or sys.platform.startswith('win')


def run(cmd, check=True):
    if isinstance(cmd, list):
        return subprocess.run(cmd, check=check)
    return subprocess.run(cmd, shell=True, check=check)


def which(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None


def prompt(question: str, default: str | None = None, secret: bool = False) -> str:
    q = question
    if default is not None:
        q += f" [{default}]"
    q += ": "
    if secret:
        val = getpass.getpass(q)
    else:
        val = input(q).strip()
    return default if (val == "" and default is not None) else val


def compose_cmd() -> list[str] | None:
    # Prefer 'docker compose' plugin, fallback to 'docker-compose'
    try:
        out = subprocess.check_output(["docker", "compose", "version"], stderr=subprocess.STDOUT)
        if b"Docker Compose" in out:
            return ["docker", "compose"]
    except Exception:
        pass
    if which("docker-compose"):
        return ["docker-compose"]
    return None


def ensure_docker_running():
    if not which("docker"):
        print("HATA: Docker CLI bulunamadı. Lütfen Docker Desktop kurun ve tekrar deneyin:")
        print("https://www.docker.com/products/docker-desktop/")
        sys.exit(1)
    # Check engine running
    try:
        run(["docker", "version"], check=True)
    except subprocess.CalledProcessError:
        print("HATA: Docker çalışmıyor gibi görünüyor. Docker Desktop'ı açıp bekleyin, sonra tekrar deneyin.")
        sys.exit(1)


def write_env(env_path: str, data: dict):
    if os.path.exists(env_path):
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{env_path}.bak-{ts}"
        shutil.copy(env_path, backup)
        print(f"Var olan .env yedeklendi: {backup}")
    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")
    print(f".env yazıldı: {env_path}")


def ensure_ssl_windows():
    # Opsiyonel: OpenSSL varsa self-signed üretelim; yoksa atlansın
    os.makedirs("ssl", exist_ok=True)
    cert = os.path.join("ssl", "cert.pem")
    key = os.path.join("ssl", "key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        print("SSL sertifikaları mevcut, atlanıyor.")
        return True
    if not which("openssl"):
        print("Uyarı: OpenSSL bulunamadı. SSL sertifikası oluşturulamadı. HTTPS/Nginx devre dışı bırakılacak.")
        return False
    print("Self-signed SSL sertifikası oluşturuluyor...")
    run('openssl req -x509 -newkey rsa:4096 -nodes -out ssl/cert.pem -keyout ssl/key.pem -days 365 '
        '-subj "/C=TR/ST=State/L=City/O=Org/CN=localhost"', check=True)
    print("SSL sertifikaları oluşturuldu: ssl/cert.pem, ssl/key.pem")
    return True


def bring_up(services: list[str]):
    cmd = compose_cmd()
    if not cmd:
        print("HATA: Docker Compose bulunamadı. Lütfen Docker Desktop kurun ve tekrar deneyin.")
        sys.exit(1)
    run(cmd + ["up", "-d", "--build"] + services, check=True)


def main():
    if not is_windows():
        print("Bu betik Windows içindir.")
        sys.exit(1)
    if not os.path.exists("docker-compose.yml"):
        print("Hata: Bu betiği proje klasöründe çalıştırın (docker-compose.yml bulunamadı).")
        sys.exit(1)

    print("=== Bitcoin Mixer - Windows Otomatik Kurulum ===")
    print("Docker Desktop'ın kurulu ve çalışır olduğundan emin olun.")

    # Bilgi topla
    secret_key = prompt("SECRET_KEY (boş bırakılırsa otomatik oluşturulur)", default="")
    if not secret_key:
        secret_key = secrets.token_hex(32)
    rpc_user = prompt("Bitcoin RPC kullanıcı adı (rpcuser)", default="bitcoinrpc")
    rpc_pass = prompt("Bitcoin RPC parolası (rpcpassword)", default="", secret=True)
    rpc_host = prompt("Bitcoin RPC host", default="host.docker.internal")
    rpc_port = prompt("Bitcoin RPC port", default="8332")
    use_nginx = prompt("Nginx + SSL (HTTPS) ile çalıştırılsın mı? (y/N)", default="N").lower().startswith("y")

    # Docker kontrolü
    ensure_docker_running()

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

    # SSL istenirse dene
    if use_nginx:
        has_ssl = ensure_ssl_windows()
        if not has_ssl:
            print("Nginx/SSL devre dışı bırakılıyor (sertifika oluşturulamadı).")
            use_nginx = False

    # Servisleri başlat
    services = ["postgres", "redis", "web", "celery_worker", "celery_beat"]
    if use_nginx:
        services.append("nginx")

    print("Servisler başlatılıyor...")
    bring_up(services)

    # Kullanıcıya bilgi
    time.sleep(3)
    print("\nKurulum tamamlandı.")
    print("- Uygulama (HTTP):  http://localhost:5000")
    if use_nginx:
        print("- Uygulama (HTTPS): https://localhost")
    print("- Loglar:           docker compose logs -f")
    print("- Servisler:        docker compose ps")

    print("\nBitcoin Core RPC ayarlarını (bitcoin.conf) kontrol edin:")
    print("server=1")
    print(f"rpcuser={rpc_user}")
    print(f"rpcpassword={'*' * max(8, len(rpc_pass) or 8)}")
    print("rpcallowip=127.0.0.1")
    print("rpcbind=127.0.0.1")


if __name__ == "__main__":
    main()



