# Wejście HTTP w zaufanym LAN

Domyślny profil pozostaje `secure`. `trusted_lan` włączaj jawnie dla
sparowanej instalacji w zaufanej sieci Private. HTTP nie szyfruje tokenów ani
nie uwierzytelnia kryptograficznie tożsamości. Nadal obowiązują tokeny tras,
deadline, limity, polityka mutacji środowiska i deduplikacja poleceń.

## Kontrakt i konfiguracja

Pasywne, nieuwierzytelnione `GET /api/v1/transport/identity` zwraca:

```json
{"protocol_version":1,"peer_id":"trwale-id-instalacji","service_role":"venom","operator_access":"trusted_lan"}
```

ID powstaje raz w `data/transport/identity.json`, w istniejącej przestrzeni
`STORAGE_PREFIX`. `VENOM_TRANSPORT_IDENTITY_FILE` może wskazać trwałą lokalizację.
Zachowaj plik po restarcie i zmianie IP. Korupcja, nadmierny rozmiar i symlink
oznaczają odmowę zamiast cichego wygenerowania nowego ID. Przed wysłaniem tokenu
porównaj identity z jawnie sparowanym `expected_peer_id`. ID boot/sesji nie jest
trwałą tożsamością instalacji.

Ustaw te same wartości w API i launcherze frontendu:

```dotenv
VENOM_OPERATOR_ACCESS=trusted_lan
VENOM_LAN_ORIGINS=http://localhost:3300,http://127.0.0.1:3300,http://venom-host:3300
API_PROXY_TARGET=http://127.0.0.1:8800
```

Originy są dokładne, bez końcowego slash, ścieżki, poświadczeń i wildcardów.
Dodaj tylko nazwy/adresy faktycznie używane przez operatora. Nazwy w przykładzie
są symboliczne. Sprawdź DNS routera z Windows, WSL, Pi i telefonu; nie zakładaj
działania `.local` we wszystkich środowiskach. API pozostaje prywatne; publikuj
wyłącznie wejście panelu. Nie wystawiaj 8800 przez Windows portproxy ani inny relay.

Standardowe `npm run dev`, `dev:turbo` i `start` korzystają z
`scripts/serve-with-proxy.mjs`. Launcher zajmuje port panelu, uruchamia Next
na prywatnym, tymczasowym porcie loopback i strumieniuje `/api/*`, `/ws/*`
bezpośrednio do `API_PROXY_TARGET`. Rewrite Next nie jest już proxy.
Zachowaj to wejście również w produkcji; nie publikuj prywatnego portu Next.

Next wyprowadza `NEXT_PUBLIC_TRANSPORT_PROFILE` z `VENOM_OPERATOR_ACCESS`.
Przy buildzie produkcyjnym ustaw profil także podczas kompilacji. W LAN API
przeglądarki używa względnych URL, a event/audio WS originu panelu, również
przy starych publicznych URL API/WS w konfiguracji. Serwerowy fallback API to
8800. `VENOM_PROXY_MAX_BODY_BYTES` domyślnie wynosi 64 MiB i ogranicza zarówno
zadeklarowane, jak i chunked uploady bez buforowania ich w całości.

## Operator i administracja localhost

Wejście usuwa dostarczone nagłówki forwarded/tożsamości klienta i zapisuje własne
metadane transportu. API przyjmuje je wyłącznie od proxy loopback. W LAN odrzuca
nieznany Host/Origin oraz publiczny adres źródła. MJPEG, SSE i WS zachowują
strumieniowanie, backpressure i anulowanie upstreamu; JPEG nie jest transkodowany.
Proxy nie ponawia POST/zadań/ARM/ruchu.

Windows portproxy traci pierwotny adres TCP klienta. Dlatego **każde żądanie
wspólnego wejścia LAN, także localhost:3300, ma prawa operatora**. Konfiguracja,
backupy i inna administracja localhost pozostają niedostępne z tego wejścia.
Do administracji służy niewystawione lokalne API. Fałszywy Host/Origin i
`X-Forwarded-For: 127.0.0.1` nie nadają praw administratora.

Moduł może jawnie korzystać z
`venom_core.api.transport_access.require_operator_request(request)`, zachowując
własne tokeny i guard mutacji środowiska. Niemigrowane operacje localhost
pozostają zablokowane na wspólnym wejściu. Profil nie włącza globalnej
administracji zdalnej.

Publiczny kontrakt frontendu:

```ts
import { createBrowserUuid, getMicrophoneCapability } from "@/lib/optional-modules/transport";
```

Helper UUID zachowuje RFC 4122 v4 przez CSPRNG `getRandomValues`, gdy HTTP nie
udostępnia `randomUUID`; nie używa `Math.random`. Mikrofon przeglądarki wymaga
HTTPS lub localhost. Dla HTTP LAN ekran głosu pokazuje ograniczenie PL/EN/DE
i blokuje nagrywanie z przeglądarki. Panele, JPEG/MJPEG i osobny tor audio
urządzenia pozostają dostępne.

## Zarządzane wejście Windows / WSL NAT

Uruchamiaj `scripts/Manage-VenomLanEntry.ps1` w Windows PowerShell.
Helper nie zmienia globalnej sieci WSL, nie restartuje usług, nie skanuje
podsieci i niczego nie instaluje. Jawnie wybierz istniejącą dystrybucję
i aktywny interfejs **Private**. `Inspect` jest tylko odczytem:

```powershell
.\scripts\Manage-VenomLanEntry.ps1 -Mode Inspect -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId sparowane-id -Json
```

Preferowany `TargetMode localhost_relay` wskazuje zweryfikowany relay Windows
localhost, więc nie wymaga zmiany listenerów WSL ani celu po restarcie WSL.
Jeżeli relay jest niedostępny, `-TargetMode wsl_ip` odczytuje adres wyłącznie
wskazanej, już uruchomionej dystrybucji; wymaga osiągalnego listenera WSL.
Helper odmawia przy niejednoznacznych adresach i sprawdza identity, rolę,
wersję, profil oraz oczekiwany peer przed wystawieniem wejścia.

`Apply`, `Reconcile`, `Remove` i rejestracja zadania wymagają podwyższonego
PowerShell. Udany Inspect nie oznacza podwyższonych praw ani odbioru z LAN.
Istniejący niezarządzany wpis, nawet o takim samym celu, jest konfliktem;
jego osobny przegląd należy do operatora. Helper nie przejmuje ani nie zmienia
cudzych reguł/mapowań, nie uruchamia sam IP Helper i nie zmienia kategorii sieci.

```powershell
.\scripts\Manage-VenomLanEntry.ps1 -Mode Apply -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId sparowane-id
.\scripts\Manage-VenomLanEntry.ps1 -Mode Reconcile -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi -ExpectedPeerId sparowane-id
.\scripts\Manage-VenomLanEntry.ps1 -Mode Remove -Distribution Ubuntu-Venom -InterfaceAlias Wi-Fi
```

Domyślny stan to `%LOCALAPPDATA%\Venom\lan-entry\panel.json`. Własność dotyczy
`EntryName`, dokładnego zapisanego mapowania i nazwanej reguły firewalla.
Reguła dopuszcza tylko wybrany adres/interfejs, port TCP, profil Private oraz
klientów LocalSubnet. Reconcile aktualizuje własny adres LAN po DHCP i adres WSL
w trybie `wsl_ip`. Cudze lub zmienione mapowanie nie jest usuwane.

Automatyczne odtwarzanie wymaga sprawdzonej kopii skryptu w trwałej lokalizacji
Windows i `-RegisterTask` z Apply/Reconcile. Powstaje jedno zadanie bieżącego
zalogowanego użytkownika z najwyższymi prawami, co minutę, bez równoległych
instancji. Nie wykonuje pracy aplikacji i nie otwiera wejścia przed osiągalnością
sparowanego identity z profilem LAN. Remove usuwa wyłącznie własne zadanie.
Przy odtwarzaniu/rollback zachowaj StateFile i EntryName.

Sprawdź rzeczywisty listener Windows, następnie identity i UI z osobnego klienta
LAN przez trwałą nazwę. Odbierz localhost, PC LAN, telefon, compute Pi, świeże
MJPEG/SSE, faktyczny WS i spoofing nagłówków. Po kontrolowanej zmianie adresu
LAN/WSL wykonaj Reconcile i zmierz odzyskanie; mock nie zastępuje fizycznego
odbioru. Kartę pod starym liczbowym IP trzeba ponownie otworzyć przez nazwę.

## Rollback

Usuń tylko własne wejście LAN przez Remove, przywróć poprzednie URL/profile
transportu i połącz nowe sesje. Zachowaj identity, TTL tokenów, wybory operatora
i storage. Reconnect nie ponawia poleceń, nie uruchamia kamery/modelu i nie
uzbraja robota.
