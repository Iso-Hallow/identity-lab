# Постмортем: LDAP bind падал с ошибкой 52e в домене lab.local

**Дата:** 2026-11-09
**Критичность:** лаборатория / учебная задача
**Статус:** решено

## Краткое описание

При первой попытке LDAP-аутентификации с Debian на контроллер домена `dc01.lab.local` простой bind с верными учётными данными падал с ошибкой `Invalid credentials (49)`, дополнительно `data 52e`. Учётная запись `testuser` была включена, не заблокирована, с корректным UPN и только что сброшенным паролем. Корневая причина - на контроллере домена было включено требование подписи LDAP (`LDAPServerIntegrity = 1`), из-за чего простые bind без TLS отклоняются. Долгосрочное решение - поднять AD CS, выдать сертификат контроллеру домена и перевести клиент на LDAPS (порт 636).

## Симптомы

- `ldapsearch -x -H ldap://dc01.lab.local` возвращает `result: 1 Operations error` для анонимного bind (это нормально, анонимный доступ в AD ограничен).
- Bind под `testuser@lab.local` возвращает `ldap_bind: Invalid credentials (49)`, `data 52e`.
- Та же ошибка 52e для `Administrator@lab.local` и `LAB\Administrator`.
- Флаги учётной записи в порядке: `Enabled = True`, `LockedOut = False`, `PasswordExpired = False`, `SmartcardLogonRequired = False`, `userAccountControl = 66048`.
- `LDP.exe` на самом контроллере домена тоже падает с 52e для тех же учётных данных.
- DNS и TCP 389 с Debian доступны: `ping 192.168.100.10` проходит, `nslookup lab.local` резолвится.

## Корневая причина

Параметр реестра `HKLM\SYSTEM\CurrentControlSet\Services\NTDS\Parameters\LDAPServerIntegrity` был установлен в `1` (требуется подпись LDAP). В этом режиме контроллер домена отклоняет простые bind без защиты целостности, возвращая 52e даже при верном пароле. Это политика безопасности по умолчанию, а не баг.

## Решение

1. Для первичной проверки базового LDAP временно установить `LDAPServerIntegrity = 0` и перезапустить службу `NTDS`. После этого bind под `testuser@lab.local` проходит с `result: 0 Success`.
2. Долгосрочное решение: установить AD CS как Enterprise Root CA, создать шаблон `LDAPS-Template`, выдать сертификат для `DC01`, экспортировать корневой CA, установить его на Debian через `update-ca-certificates`, перейти на LDAPS (порт 636).
3. Вернуть `LDAPServerIntegrity = 1`. Простой LDAP на порту 389 снова отклоняется, LDAPS на 636 продолжает работать, потому что TLS удовлетворяет требованию целостности.

## Проверка

- `ldapsearch -x -H ldaps://dc01.lab.local:636 -D "testuser@lab.local" -b "dc=lab,dc=local" -s base` возвращает `result: 0 Success`.
- Python-клиент (`lab/client/app.py`, Flask + ldap3, `Tls(validate=CERT_REQUIRED, ca_certs_file="/etc/ssl/certs/lab-root-ca.pem")`):
  - верный пароль: `Result: OK`
  - неверный пароль: `Result: FAIL (LDAPBindError)`

## Выводы

- В AD ошибка `52e` - это не всегда неверный пароль. Перед повторным сбросом учётных данных проверяйте `LDAPServerIntegrity`.
- Локализованная Windows меняет имена (`Администратор` вместо `Administrator`) и ломает часть фильтров вроде `MemberOf -like "*Domain Admins*"`. Надёжнее проверять по SID (`S-1-5-21-...-512`) или через `whoami /user`.
- Локальный тест bind через `LDP.exe` на контроллере домена отделяет проблемы AD от проблем Linux-клиента быстрее, чем отладка клиента.
- Правильный путь - LDAPS, а не постоянное отключение подписи.

## Контекст лаборатории

- DC: `dc01.lab.local`, `192.168.100.10`, Windows Server 2016, домен `lab.local`.
- Клиент: Debian, `192.168.100.20`, Python 3.13, Flask 3.1.3, ldap3 2.9.1.
- Сеть: Hyper-V Internal-свитч `lab-net`, `192.168.100.0/24`, изолирована от домашнего роутера.
