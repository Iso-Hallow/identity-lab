# Архитектура лаборатории identity-lab

## Назначение

Изолированная среда для демонстрации on-prem identity: Active Directory, PKI (AD CS), LDAPS и Python-клиента аутентификации. Собрана в Hyper-V на домашнем хосте, полностью отделена от рабочей инфраструктуры (роутер, существующие VM Flask/Apache/Nextcloud не затрагиваются).

## Сеть

- Hyper-V Internal-свитч: `lab-net`
- Подсеть: `192.168.100.0/24`
- Шлюза в этой сети нет (изолирована)
- Выход в интернет: только у хоста, у VM - по необходимости через отдельный адаптер (временно)

## Узлы

### Хост (Windows, Hyper-V)

- Виртуальный адаптер `vEthernet (lab-net)`: `192.168.100.1/24`
- Используется для SSH/scp с хоста до Debian и для SMB-доступа к DC01

### DC01 - контроллер домена

- ОС: Windows Server 2016 (Desktop Experience)
- IP: `192.168.100.10/24`
- Имя: `dc01.lab.local`
- Домен: `lab.local`, NetBIOS: `LAB`
- Роли:
  - AD DS (Active Directory Domain Services)
  - DNS-сервер (единственный DNS для домена)
  - AD CS (Enterprise Root CA, `lab-DC01-CA`)
- Слушает:
  - DNS: 53 (UDP/TCP)
  - LDAP: 389 (простые bind отклоняются, `LDAPServerIntegrity = 1`)
  - LDAPS: 636 (TLS, используется клиентами)
- Сертификат DC01 выдан по шаблону `LDAPS-Template`, срок ~1 год

### Debian - Linux-клиент

- ОС: Debian, Python 3.13
- IP: `192.168.100.20/24` (на `eth0`, добавляется через `ip addr add`, не сохраняется после перезагрузки)
- DNS: `192.168.100.10` (через `/etc/resolv.conf.head`, чтобы `dhcpcd` не перезаписывал)
- Корневой CA: `/usr/local/share/ca-certificates/lab-root-ca.crt`, симлинк `/etc/ssl/certs/lab-root-ca.pem`
- Python-окружение: `~/labenv` (venv), пакеты `flask 3.1.3`, `ldap3 2.9.1`
- Приложение: `lab/client/app.py`, слушает `0.0.0.0:5000`

## Поток аутентификации
