# identity-lab

Изолированная лаборатория: **Active Directory + PKI + LDAPS** в Hyper-V, с Python-клиентом на Debian.

## Зачем

Показать живой стенд:
- создание пользователей в AD
- выпуск сертификата через AD CS (Enterprise Root CA)
- ручная ротация сертификата (auto-enrollment описан как следующий шаг в `docs/certificates.md`)
- LDAPS-аутентификация с валидацией CA на Linux-клиенте
- Python-клиент (Flask + ldap3): логин/пароль → OK / FAIL

## Требования

- Hyper-V включён на хосте (Windows 10/11 Pro или Windows Server)
- ISO Windows Server 2016 Evaluation (Desktop Experience)
- ISO Debian (12 или новее)
- Свободно ~100 ГБ на хосте (2 VM + checkpoint)
- Базовые навыки PowerShell и bash

## Схема

```
Windows host (Hyper-V), vEthernet lab-net: 192.168.100.1/24
    |
    +-- DC01 (Windows Server 2016): 192.168.100.10
    |     AD DS + DNS (lab.local), AD CS (Enterprise Root CA), LDAPS :636
    |
    +-- Debian: 192.168.100.20
          Python 3.13 + Flask + ldap3
```

## Что работает

- DNS: `nslookup lab.local` → `192.168.100.10`
- LDAPS bind: `ldapsearch -H ldaps://dc01.lab.local:636 -D "testuser@lab.local"` → `result: 0 Success`
- Python OK: `POST /` с верным паролем → `Result: OK`
- Python FAIL: `POST /` с неверным паролем → `Result: FAIL (LDAPBindError)`
- `LDAPServerIntegrity = 1`: простой LDAP на 389 отклоняется, работает только 636

## Как поднять (кратко)

1. Hyper-V: Internal-свитч `lab-net`, подсеть `192.168.100.0/24`
2. VM `DC01` (Windows Server 2016, Gen2, 4 ГБ RAM), IP `192.168.100.10`
3. Роли AD DS + DNS → домен `lab.local`
4. AD CS (Enterprise Root CA) → шаблон `LDAPS-Template` → сертификат для DC01
5. Экспорт корневого CA на Debian: `/usr/local/share/ca-certificates/` + `update-ca-certificates`
6. `lab/client/app.py` - Flask + ldap3, `Tls(validate=CERT_REQUIRED)`

Подробно: `docs/runbook.md`.

## Структура

- `README.md`
- `docs/architecture.md` - схема и адресация
- `docs/certificates.md` - жизненный цикл, ротация
- `docs/runbook.md` - пошагово
- `lab/client/app.py` - Python-клиент
- `windows/README.md` - заметки по Windows Server 2016
- `postmortems/2026-11-09-ldap-52e-signing.md` - история с 52e

## Обезличено

Все IP, имена и пароли - лабораторные (`lab.local`, `192.168.100.0/24`, `testuser`).

## Поток аутентификации

1. Браузер на хосте отправляет HTTP POST на `http://192.168.100.20:5000/`
2. Flask-приложение на Debian принимает логин и пароль
3. Приложение открывает LDAPS-соединение с `dc01.lab.local:636` через `ldap3`
4. TLS-соединение валидируется корневым CA из `/etc/ssl/certs/lab-root-ca.pem`
5. Контроллер домена проверяет `userPrincipalName` и пароль
6. Ответ возвращается в браузер: `Result: OK` или `Result: FAIL (LDAPBindError)`

## Изоляция

- `lab-net` - Internal-свитч Hyper-V, не связан с физической сетью
- Существующие VM (Flask, Apache, Nextcloud) находятся в других сетях и не затрагиваются
- Домашний роутер не используется как DNS для домена (это сломало бы AD)
- Единственная точка соприкосновения с внешним миром - временное подключение Debian к интернет-свитчу для `apt`/`git`

## Ограничения текущей конфигурации

- IP на Debian не сохраняется после перезагрузки (добавляется вручную через `ip addr add`)
- DNS на Debian прописан через `resolv.conf.head`, потому что `dhcpcd` перегенерирует `/etc/resolv.conf`
- `LDAPServerIntegrity = 1` - простой LDAP на 389 закрыт, работает только 636
- Windows Server 2016 Evaluation: 180 дней, потом потребуется переустановка или продление (для лаборатории - не критично)
- Flask development server, не production WSGI - для демо допустимо

## Проверка

```bash
# С Debian (192.168.100.20):
openssl s_client -connect dc01.lab.local:636 -showcerts
# ожидаемо: Verify return code: 0 (ok)

ldapsearch -H ldaps://dc01.lab.local:636 -D "testuser@lab.local" -W -b "dc=lab,dc=local" -s base
# ожидаемо: result: 0 Success

curl -s -X POST -d "u=testuser&p=P@ssw0rd123!" http://localhost:5000/
# ожидаемо: Result: OK
```
