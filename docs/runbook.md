# Runbook: воспроизведение лаборатории identity-lab

Пошаговое руководство. Предполагается, что Hyper-V уже включён на хосте, ISO Windows Server 2016 и Debian доступны, а также есть базовые навыки работы с PowerShell и bash.

## 1. Сеть Hyper-V

1. Открыть PowerShell на хосте от имени администратора.
2. Создать Internal-свитч:

## New-VMSwitch -Name "lab-net" -SwitchType Internal

```
3. Назначить хосту IP в этой сети (понадобится для SSH/scp до Debian):
```

## New-NetIPAddress -InterfaceAlias "vEthernet (lab-net)" -IPAddress 192.168.100.1 -PrefixLength 24

```
## 2. Виртуальная машина DC01 (Windows Server 2016)

1. Создать VM:
```

## New-VM -Name "DC01" -MemoryStartupBytes 4GB -Generation 2 -NewVHDSizeBytes 60GB -NewVHDPath "C:\Hyper-V\DC01\DC01.vhdx"

```
2. Отключить динамическую память (для контроллера домена предпочтительна статическая):
```

## Set-VMMemory -VMName "DC01" -DynamicMemoryEnabled $false

```
3. Подключить к `lab-net`:
```

## Connect-VMNetworkAdapter -VMName "DC01" -SwitchName "lab-net"

```
4. Подключить ISO Windows Server 2016, запустить VM, установить систему с параметром **Desktop Experience** (нужен GUI).
5. После установки задать статический IP внутри VM:
```

## New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.100.10 -PrefixLength 24
## Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 192.168.100.10

```
6. Переименовать компьютер:
```
## Rename-Computer -NewName "DC01" -Restart -Force

```
## 3. Роли AD DS и DNS

1. Установить роли:
```

## Install-WindowsFeature -Name AD-Domain-Services, DNS -IncludeManagementTools

```
2. Поднять новый лес и домен:
```

Install-ADDSForest -DomainName "lab.local" -DomainNetbiosName "LAB" -InstallDns -Force

```
3. После автоматической перезагрузки войти как `LAB\Администратор`.
4. Проверить домен:
```

## Get-ADDomain | Select-Object Name, DNSRoot, NetBIOSName

```
## 4. Пользователь для тестов

1. Создать пользователя (можно через `dsa.msc` или PowerShell):
```
```
New-ADUser -Name "Test User" -SamAccountName "testuser" `
  -UserPrincipalName "testuser@lab.local" `
  -AccountPassword (ConvertTo-SecureString "P@ssw0rd123!" -AsPlainText -Force) `
  -Enabled $true -ChangePasswordAtLogon $false
```

```
## 5. AD CS (Enterprise Root CA)

1. Установить роль:
```
## Install-WindowsFeature -Name ADCS-Cert-Authority -IncludeManagementTools

```
2. Настроить CA:
```

## Install-AdcsCertificationAuthority -CAType EnterpriseRootCA -Force

```
(Появление `ErrorId: 0` - это успех, не ошибка.)
3. Проверить, что служба запущена:
```

## Get-Service -Name CertSvc

```
## 6. Шаблон сертификата и выдача для DC01

1. Открыть `certtmpl.msc`.
2. Найти шаблон «Проверка подлинности Kerberos», дублировать его.
3. На вкладке «Общие» задать имя `LDAPS-Template` (и отображаемое, и системное).
4. На вкладке «Имя субъекта» выбрать «Создавать из информации Active Directory», включить «DNS-имя».
5. На вкладке «Обработка запроса» разрешить экспорт закрытого ключа.
6. Сохранить шаблон.
7. Опубликовать шаблон в CA:
```

## Import-Module ADCSAdministration
## Add-CATemplate -Name "LDAPS-Template" -Force
```
(Если команда говорит, что шаблон уже существует - это нормально, значит он уже опубликован.)
8. Выдать сертификат для DC01:
```

## Get-Certificate -Template "LDAPS-Template" -CertStoreLocation "Cert:\LocalMachine\My" -DnsName "dc01.lab.local"

```
9. Перезапустить службу `NTDS`, чтобы она подхватила сертификат:
```

## Restart-Service -Name NTDS -Force

```
10. Проверить, что LDAPS слушает:
```

## netstat -an | findstr :636

```
Ожидается строка `LISTENING` на порту 636.

## 7. Экспорт корневого CA

1. В `certlm.msc` найти сертификат CA в «Доверенные корневые центры сертификации» → «Сертификаты».
2. Экспортировать без закрытого ключа в формате Base-64 (.CER).
3. Конвертировать в PEM:
```

## certutil -encode C:\lab-root-ca.cer C:\lab-root-ca.pem

```
4. Перенести `lab-root-ca.pem` на Debian. Удобный способ - через SMB с хоста:
```

## net use \\192.168.100.10\C /user:LAB\Администратор "пароль" copy \\192.168.100.10\C\lab-root-ca.pem C:\lab-root-ca.pem
## net use \\192.168.100.10\C$ /delete
## scp C:\lab-root-ca.pem leo@192.168.100.20:~/

```
## 8. Настройка Debian

1. Убедиться, что на `eth0` есть IP в lab-net:
```

## sudo ip addr add 192.168.100.20/24 dev eth0

```
2. Установить DNS (чтобы `dhcpcd` не перезаписывал):
```

## echo "nameserver 192.168.100.10" | sudo tee /etc/resolv.conf.head
## sudo dhcpcd -n eth0

```
3. Проверить DNS:
```
## nslookup lab.local

```
4. Установить корневой CA:
```

## sudo cp ~/lab-root-ca.pem /usr/local/share/ca-certificates/lab-root-ca.crt
## sudo update-ca-certificates

```
5. Установить Python-окружение и пакеты:
```

## sudo apt update
## sudo apt install -y python3-venv
## python3 -m venv ~/labenv
## source ~/labenv/bin/activate
## pip install flask ldap3

```
## 9. Python-клиент

1. Создать файл `lab/client/app.py` (см. содержимое в репозитории).
2. Запустить:
```

## source ~/labenv/bin/activate
## cd lab/client
## python app.py

```
3. Проверить с хоста (PowerShell):
```

## curl.exe -s -X POST -d "u=testuser&p=P@ssw0rd123!" http://192.168.100.20:5000/
## curl.exe -s -X POST -d "u=testuser&p=wrong" http://192.168.100.20:5000/

```
Ожидается `Result: OK` и `Result: FAIL (LDAPBindError)`.

## 10. Включение безопасности LDAP

После того как LDAPS заработал, вернуть требование подписи:
```

## Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Parameters' -Name 'LDAPServerIntegrity' -Value 1
## Restart-Service -Name NTDS -Force

```
Проверить, что LDAPS по-прежнему работает, а простой LDAP на 389 - нет. Это правильная итоговая конфигурация.

## Возможные проблемы

- **Ошибка `52e` при простом bind.** Проверить `LDAPServerIntegrity`. Если `1` - либо временно установить `0`, либо настроить LDAPS.
- **`nslookup` не работает на Debian.** Проверить, что `resolv.conf` содержит `nameserver 192.168.100.10` и что IP на `eth0` в подсети `192.168.100.0/24`.
- **`scp` с хоста не находит файл.** Убедиться, что файл лежит именно на хосте, а не на DC01.
- **Порт 636 не слушается после выдачи сертификата.** Проверить, что сертификат в хранилище «Личное» компьютера и что `NTDS` перезапущен.
- **Flask не видит `192.168.100.20` в выводе.** Это косметика, Flask слушает `0.0.0.0`. Главное - что `curl` с хоста на `192.168.100.20:5000` отвечает.
```
