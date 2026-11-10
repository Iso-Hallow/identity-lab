# Сертификаты и PKI в identity-lab

## Что настроено

- AD CS в роли **Enterprise Root CA** на `dc01.lab.local`
- Имя CA: `lab-DC01-CA`
- Срок действия корневого CA: ~5 лет
- Шаблон сертификата `LDAPS-Template` (копия встроенного «Kerberos Authentication»)
- По этому шаблону выдан сертификат для самого контроллера домена `DC01.lab.local`
- Контроллер домена использует этот сертификат для LDAPS на порту 636

## Шаблон `LDAPS-Template`

Ключевые настройки, которые были изменены относительно встроенного шаблона:

- **Отображаемое имя:** `LDAPS-Template`
- **Имя шаблона:** `LDAPS-Template`
- **Имя субъекта:** «Создавать из информации Active Directory», включён пункт «DNS-имя»
- **Обработка запроса:** «Разрешить экспорт закрытого ключа»

Опубликован в CA командой:

## Add-CATemplate -Name "LDAPS-Template" -Force


```
(Командлет `Publish-CATemplate` не существует - часто встречается в интернете, но не работает. Используйте `Add-CATemplate` или `certutil -SetCaTemplates`.)

## Выдача сертификата DC01

Выполнено через PowerShell на DC01:
```

## Get-Certificate -Template "LDAPS-Template" -CertStoreLocation "Cert:\LocalMachine\My" -DnsName "dc01.lab.local"

```
После выдачи - перезапуск службы `NTDS`, чтобы она подхватила сертификат:
```

Restart-Service -Name NTDS -Force

```
Проверка, что LDAPS слушает:
```

## netstat -an | findstr :636

```
Ожидаемая строка: `TCP 0.0.0.0:636 ... LISTENING`.

## Что важно понимать про жизненный цикл

В текущей конфигурации сертификат DC01 выпущен один раз и используется до истечения срока. Автоматическое продление (auto-enrollment с renewal period) **не настроено** - это отдельный уровень, который требует:

- доменного членства Linux-клиента (или Windows-клиента) с групповой политикой
- Kerberos-аутентификации для автоматического запроса
- настройки renewal period в шаблоне (обычно 6 недель до истечения)
- GPO с auto-enrollment для целевых объектов

Для текущей демонстрации LDAPS этого не требуется: сертификат действителен, клиент валидирует его по корневому CA.

## Ротация сертификата (ручная)

Если сертификат нужно перевыпустить:

1. В `certlm.msc` → «Личное» → «Сертификаты» удалить старый сертификат DC01
2. Снова выполнить `Get-Certificate` с теми же параметрами
3. Перезапустить `NTDS`
4. Убедиться, что LDAPS отвечает: `ldapsearch -H ldaps://dc01.lab.local:636 ...`

Замечание: при каждом вызове `Get-Certificate` создаётся **новый** сертификат, старый остаётся в хранилище, пока его не удалить вручную.

## Экспорт корневого CA

Корневой сертификат CA экспортируется в формате Base-64 (.CER), затем конвертируется в PEM для Linux:
```

## certutil -encode C:\lab-root-ca.cer C:\lab-root-ca.pem

```
На Debian:
```

## sudo cp ~/lab-root-ca.pem /usr/local/share/ca-certificates/lab-root-ca.crt
## sudo update-ca-certificates

```
После этого `/etc/ssl/certs/lab-root-ca.pem` - симлинк на установленный сертификат, и Python-клиент может использовать его в `Tls(validate=CERT_REQUIRED, ca_certs_file="/etc/ssl/certs/lab-root-ca.pem")`.

## Безопасность: LDAP signing

На DC01 включён параметр:
```
HKLM\SYSTEM\CurrentControlSet\Services\NTDS\Parameters\LDAPServerIntegrity = 1

```
Это означает: простые bind без TLS на порту 389 отклоняются с ошибкой `52e`. Работает только LDAPS на 636, где TLS удовлетворяет требованию целостности. Это правильная итоговая конфигурация для демонстрации: «порт 389 закрыт для простых bind, аутентификация только через LDAPS с валидацией CA».

История о том, как мы к этому пришли - в `postmortems/2026-11-09-ldap-52e-signing.md`.
```
