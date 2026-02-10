# 🚀 Hetzner Deployment Guide - InfoHub AI

## Рекомендуемая конфигурация

### ✅ Оптимально (рекомендуется):
**CX41** - €15.97/месяц
- 4 vCPU
- 16 GB RAM
- 160 GB SSD
- Ubuntu 22.04 LTS

### 💰 Минимально (для тестов):
**CX31** - €7.59/месяц
- 2 vCPU
- 8 GB RAM
- 80 GB SSD
- Ubuntu 22.04 LTS

⚠️ **Внимание:** ML модель займет ~2GB RAM в runtime

---

## Быстрый деплой (5 минут)

### 1. Создать сервер на Hetzner

1. Зайти на https://console.hetzner.cloud
2. Создать проект
3. Add Server → выбрать **CX41** или **CX31**
4. Location: Нюрнберг (самый быстрый для Грузии)
5. Image: **Ubuntu 22.04**
6. SSH key: добавить свой публичный ключ
7. Create server

### 2. Подключиться к серверу

```bash
ssh root@YOUR_SERVER_IP
```

### 3. Запустить deployment скрипт

```bash
# Скачать и запустить скрипт
curl -O https://raw.githubusercontent.com/G357M/Warp-AI-Tax-Advisor-System/main/deploy_hetzner.sh
chmod +x deploy_hetzner.sh
./deploy_hetzner.sh
```

Скрипт автоматически:
- ✅ Установит Docker и Docker Compose
- ✅ Клонирует репозиторий
- ✅ Создаст .env файл
- ✅ Настроит nginx
- ✅ Запустит все сервисы

### 4. Настроить .env

Скрипт попросит отредактировать .env файл:

```bash
nano .env
```

**Обязательно изменить:**
1. `OPENAI_API_KEY=sk-your-key-here` - твой OpenAI ключ
2. `POSTGRES_PASSWORD=` - надежный пароль
3. `JWT_SECRET_KEY=` - случайная строка (можно сгенерировать: `openssl rand -hex 32`)

Сохранить: `Ctrl+X`, `Y`, `Enter`

### 5. Готово! 🎉

Система доступна по адресу:
- **Main App:** http://YOUR_SERVER_IP
- **Admin Panel:** http://YOUR_SERVER_IP/admin
- **API Docs:** http://YOUR_SERVER_IP:8000/docs

---

## Ручной деплой (если нужен контроль)

### Шаг 1: Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установить Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Шаг 2: Клонировать репозиторий

```bash
git clone https://github.com/G357M/Warp-AI-Tax-Advisor-System.git infohub
cd infohub
```

### Шаг 3: Настроить environment

```bash
# Скопировать пример
cp .env.example .env

# Отредактировать
nano .env
```

### Шаг 4: Запустить

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Шаг 5: Проверить

```bash
# Статус сервисов
docker-compose -f docker-compose.prod.yml ps

# Логи
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Полезные команды

### Управление сервисами

```bash
# Посмотреть логи
docker-compose -f docker-compose.prod.yml logs -f

# Остановить
docker-compose -f docker-compose.prod.yml down

# Перезапустить
docker-compose -f docker-compose.prod.yml restart

# Обновить (после git pull)
docker-compose -f docker-compose.prod.yml up -d --build

# Статус
docker-compose -f docker-compose.prod.yml ps
```

### Мониторинг

```bash
# Использование ресурсов
docker stats

# Логи конкретного сервиса
docker-compose -f docker-compose.prod.yml logs -f backend

# Войти в контейнер
docker exec -it infohub-backend bash
```

### Обслуживание

```bash
# Backup базы данных
docker exec infohub-postgres pg_dump -U infohub_user infohub_ai > backup.sql

# Restore базы данных
cat backup.sql | docker exec -i infohub-postgres psql -U infohub_user infohub_ai

# Очистка старых образов
docker system prune -a
```

---

## Настройка SSL (HTTPS)

### Вариант 1: Certbot (Let's Encrypt)

```bash
# Установить Certbot
sudo apt install certbot python3-certbot-nginx

# Получить сертификат
sudo certbot --nginx -d your-domain.com

# Auto-renewal (уже настроен)
sudo certbot renew --dry-run
```

### Вариант 2: Cloudflare (бесплатно)

1. Добавить домен в Cloudflare
2. Включить SSL/TLS → Full
3. Указать A-record на IP сервера
4. Готово!

---

## Firewall настройка

```bash
# Установить UFW
sudo apt install ufw

# Разрешить SSH
sudo ufw allow 22

# Разрешить HTTP/HTTPS
sudo ufw allow 80
sudo ufw allow 443

# Включить firewall
sudo ufw enable
```

---

## Автоматические бэкапы

Создать cron job:

```bash
# Открыть crontab
crontab -e

# Добавить (ежедневно в 3:00)
0 3 * * * docker exec infohub-postgres pg_dump -U infohub_user infohub_ai | gzip > /backup/infohub_$(date +\%Y\%m\%d).sql.gz
```

---

## Monitoring (опционально)

### Setup Grafana + Prometheus

```bash
# Добавить в docker-compose.prod.yml:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  
  grafana:
    image: grafana/grafana
    ports:
      - "3001:3000"
    depends_on:
      - prometheus
```

---

## Troubleshooting

### Backend не запускается

```bash
# Проверить логи
docker-compose -f docker-compose.prod.yml logs backend

# Проверить переменные
docker exec infohub-backend env | grep OPENAI
```

### Не хватает памяти

```bash
# Добавить swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### База данных не подключается

```bash
# Проверить PostgreSQL
docker exec infohub-postgres pg_isready -U infohub_user

# Сбросить пароль
docker exec -it infohub-postgres psql -U infohub_user -c "ALTER USER infohub_user WITH PASSWORD 'new_password';"
```

---

## Стоимость

### Минимальная конфигурация (CX31):
- Сервер: €7.59/месяц
- Backup (опционально): €1.52/месяц (20%)
- Volume для данных (опционально): €4.00/месяц (40GB)
- **Итого:** ~€13/месяц

### Оптимальная конфигурация (CX41):
- Сервер: €15.97/месяц
- Backup: €3.19/месяц
- Volume: €8.00/месяц (80GB)
- **Итого:** ~€27/месяц

### Дополнительные расходы:
- OpenAI API: зависит от использования (~$10-50/месяц для тестов)
- Домен: ~€10/год

---

## Production Checklist

Перед запуском в production:

- [ ] Изменены все дефолтные пароли
- [ ] Настроен SSL/HTTPS
- [ ] Настроен firewall
- [ ] Настроены автоматические backup
- [ ] Мониторинг настроен
- [ ] Домен настроен
- [ ] Проверена работа всех endpoints
- [ ] Загружены реальные документы
- [ ] Настроены alerts
- [ ] Документация обновлена

---

## Полезные ссылки

- **Hetzner Console:** https://console.hetzner.cloud
- **Hetzner Docs:** https://docs.hetzner.com
- **Docker Docs:** https://docs.docker.com
- **PostgreSQL Docs:** https://www.postgresql.org/docs

---

**Готово к деплою!** 🚀

Любые вопросы - пиши в issues: https://github.com/G357M/Warp-AI-Tax-Advisor-System/issues
