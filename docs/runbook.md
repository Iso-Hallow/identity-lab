# Runbook: воспроизведение лаборатории identity-lab

Пошаговое руководство. Предполагается, что Hyper-V уже включён на хосте, ISO Windows Server 2016 и Debian доступны, а также есть базовые навыки работы с PowerShell и bash.

---

## 1. Сеть Hyper-V

Открыть PowerShell на хосте от имени администратора.

Создать Internal-свитч:

```powershell
New-VMSwitch -Name "lab-net" -SwitchType Internal
```

Назначить хосту IP в этой сети (понадобится для SSH/scp до Debian):

```powershell
New-NetIPAddress -InterfaceAlias "vEthernet (lab-net)" `
  -IPAddress 192.168.100.1 -PrefixLength 24
```

---

## 2. Виртуальная машина DC01 (Windows Server 2016)

Создать VM:

```powershell
New-VM -Name "DC01" -MemoryStartupBytes 4GB -Generation 2 `
  -NewVHDSizeBytes 60GB -NewVHDPath "C:\Hyper-V\DC01\DC01.vhdx"
```

Отключить динамическую память (для контроллера домена предпочтительна статическая):

```powershell
Set-VMMemory -VMName "DC01" -DynamicMemoryEnabled $false
```

Подключить к `lab-net`:

```powershell
Connect-VMNetworkAdapter -VMName "DC01" -SwitchName "lab-net"
```

Подключить ISO Windows Server 2016, запустить VM, установить систему с параметром **Desktop Experience** (нужен GUI).

После установки задать статический IP внутри VM:

```powershell
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.100.10 -PrefixLength 24
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 192.168.100.10
```

Переименовать компьютер:

```powershell
Rename-Computer -NewName "DC01" -Restart -Force
```

---

## 3. Роли AD DS и DNS

Установить роли:

```powershell
Install-WindowsFeature -Name AD-Domain-Services, DNS -IncludeManagementTools
```

Поднять новый лес и домен:

```powershell
Install-ADDSForest -DomainName "lab.local" -DomainNetbiosName "LAB" -InstallDns -Force
```

> **Важно:** команда **запросит** пароль для режима восстановления (DSRM). Задайте **сложный** пароль и **сохраните** его -без него восстановление домена невозможно.

После автоматической перезагрузки войти как `LAB\Администратор`.

Проверить домен:

```powershell
Get-ADDomain | Select-Object Name, DNSRoot, NetBIOSName
```

---

## 4. Пользователь для тестов

Создать пользователя (можно через `dsa.msc` или PowerShell):

```powershell
New-ADUser -Name "Test User" -SamAccountName "testuser" `
  -UserPrincipalName "testuser@lab.local" `
  -AccountPassword (ConvertTo-SecureString "P@ssw0rd123!" -AsPlainText -Force) `
  -Enabled $true -ChangePasswordAtLogon $false
```

---

## 5. AD CS (Enterprise Root CA)

Установить роль:

```powershell
Install-WindowsFeature -Name ADCS-Cert-Authority -IncludeManagementTools
```

Настроить CA:

```powershell
Install-AdcsCertificationAuthority -CAType EnterpriseRootCA -Force
```

> Появление `ErrorId: 0` -это успех, не ошибка.

Проверить, что служба запущена:

```powershell
Get-Service -Name CertSvc
```

---

## 6. Шаблон сертификата и выдача для DC01

1. Открыть `certtmpl.msc`.
2. Найти шаблон «Проверка подлинности Kerberos», дублировать его.
3. На вкладке «Общие» задать имя `LDAPS-Template` (и отображаемое, и системное).
4. На вкладке «Имя субъекта» выбрать «Создавать из информации Active Directory», включить «DNS-имя».
5. Сохранить шаблон.
6. Опубликовать шаблон в CA:

```powershell
Import-Module ADCSAdministration
Add-CATemplate -Name "LDAPS-Template" -Force
```

> Если команда говорит, что шаблон уже существует -это нормально, значит он уже опубликован.

7. Выдать сертификат для DC01:

```powershell
Get-Certificate -Template "LDAPS-Template" -CertStoreLocation "Cert:\LocalMachine\My" `
  -DnsName "dc01.lab.local"
```

8. Перезапустить службу `NTDS`, чтобы она подхватила сертификат:

```powershell
Restart-Service -Name NTDS -Force
```

9. Проверить, что LDAPS слушает:

```powershell
netstat -an | findstr :636
```

Ожидается строка `LISTENING` на порту 636.

> **Про закрытый ключ:** «разрешить экспорт закрытого ключа» в шаблоне **не нужно** для одного DC. Ключ остаётся на DC. Включайте только если планируете переносить сертификат на другой сервер (например, для балансировки).

---

## 7. Экспорт корневого CA

В `certlm.msc` найти сертификат CA в «Доверенные корневые центры сертификации» → «Сертификаты».

Экспортировать **без закрытого ключа** в формате Base-64 (.CER) в файл `C:\lab-root-ca.cer` на DC01.

Конвертировать в PEM (на DC01):

```powershell
certutil -encode C:\lab-root-ca.cer C:\lab-root-ca.pem
```

Перенести `lab-root-ca.pem` на Debian. Удобный способ -через `Copy-VMFile` с хоста (Hyper-V PowerShell Direct, без сети):

```powershell
# На хосте: скопировать файл с DC01 на хост
$cred = Get-Credential LAB\Администратор
Copy-VMFile -VMName "DC01" -SourcePath "C:\lab-root-ca.pem" `
  -DestinationPath "C:\lab-root-ca.pem" -CreateFullPath `
  -FileSource Host -Credential $cred
```

Затем с хоста на Debian через `scp`:

```powershell
scp C:\lab-root-ca.pem leo@192.168.100.20:~/
```

> **Альтернатива через SMB** (если `Copy-VMFile` недоступен): на DC01 расшарить папку (`New-SmbShare -Name "lab" -Path "C:\" -FullAccess "LAB\Администратор"`), на хосте подключиться (`net use \\192.168.100.10\lab /user:LAB\Администратор "пароль"`), скопировать, отключиться (`net use \\192.168.100.10\lab /delete`).

---

## 8. Настройка Debian

Убедиться, что на `eth0` есть IP в lab-net:

```bash
sudo ip addr add 192.168.100.20/24 dev eth0
```

Установить DNS (чтобы `dhcpcd` не перезаписывал):

```bash
echo "nameserver 192.168.100.10" | sudo tee /etc/resolv.conf.head
sudo dhcpcd -n eth0
```

Проверить DNS:

```bash
nslookup lab.local
```

Установить корневой CA:

```bash
sudo cp ~/lab-root-ca.pem /usr/local/share/ca-certificates/lab-root-ca.crt
sudo update-ca-certificates
```

Установить Python-окружение и пакеты:

```bash
sudo apt update
sudo apt install -y python3-venv
python3 -m venv ~/labenv
source ~/labenv/bin/activate
pip install flask ldap3
```

---

## 9. Python-клиент

Создать файл `lab/client/app.py` (см. содержимое в репозитории).

Запустить:

```bash
source ~/labenv/bin/activate
cd lab/client
python app.py
```

Проверить с хоста (PowerShell):

```powershell
curl.exe -s -X POST -d "u=testuser&p=P@ssw0rd123!" http://192.168.100.20:5000/
curl.exe -s -X POST -d "u=testuser&p=wrong" http://192.168.100.20:5000/
```

Ожидается `Result: OK` и `Result: FAIL (LDAPBindError)`.

---

## 10. Включение безопасности LDAP

После того как LDAPS заработал, вернуть требование подписи:

```powershell
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Parameters' `
  -Name 'LDAPServerIntegrity' -Value 1
Restart-Service -Name NTDS -Force
```

Проверить, что LDAPS по-прежнему работает, а простой LDAP на 389 -нет. Это правильная итоговая конфигурация.

---

## Возможные проблемы

- **Ошибка `52e` при простом bind.** Проверить `LDAPServerIntegrity`. Если `1` -либо временно установить `0`, либо настроить LDAPS.
- **`nslookup` не работает на Debian.** Проверить, что `resolv.conf` содержит `nameserver 192.168.100.10` и что IP на `eth0` в подсети `192.168.100.0/24`.
- **`scp` с хоста не находит файл.** Убедиться, что файл лежит именно на хосте, а не на DC01 (для `Copy-VMFile` -сначала скопировать с DC01 на хост).
- **Порт 636 не слушается после выдачи сертификата.** Проверить, что сертификат в хранилище «Личное» компьютера и что `NTDS` перезапущен.
- **Flask не видит `192.168.100.20` в выводе.** Это косметика, Flask слушает `0.0.0.0`. Главное -что `curl` с хоста на `192.168.100.20:5000` отвечает.

---

## Откат (если что-то пошло не так)

### Полный снос лаборатории

На хосте (PowerShell):

```powershell
Stop-VM -Name "DC01" -Force -TurnOff
Remove-VM -Name "DC01" -Force
Remove-Item -Path "C:\Hyper-V\DC01" -Recurse -Force
Remove-VMSwitch -Name "lab-net" -Force
```

### Только сброс DC01 к checkpoint

```powershell
Checkpoint-VM -Name "DC01" -SnapshotName "clean-before-ad"

# ... если что-то сломалось:
Restore-VMSnapshot -VMName "DC01" -Name "clean-before-ad" -Confirm:$false
```

### Если AD сломан, а VM жалко

- Войти в **Directory Services Restore Mode** (F8 при загрузке).
- Или -**проще** -снести VM и пройти runbook заново. Для лаборатории это **быстрее**, чем чинить AD.

> **Совет:** делайте `Checkpoint-VM` **перед каждым этапом** (перед установкой AD DS, перед AD CS, перед выдачей сертификата). Если этап сломался -откат за 30 секунд, а не «переустановка с нуля».
