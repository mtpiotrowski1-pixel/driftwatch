# Backup, restore i disaster recovery

- **Status:** runbook roboczy, nie jest dowodem odtwarzalności
- **Właściciel usługi:** `[IMIĘ / ROLA]`
- **Właściciel backupu:** `[IMIĘ / ROLA]`
- **Osoba zatwierdzająca cutover:** `[IMIĘ / ROLA]`
- **Ostatni udany restore drill:** `[BRAK - GATE PRODUKCJI]`
- **Ostatni przegląd:** 2026-07-17

Backup istnieje dopiero wtedy, gdy jest zaszyfrowany, monitorowany, dostępny po
awarii głównego środowiska i został odtworzony w ćwiczeniu. Plik na tym samym
wolumenie nie jest strategią disaster recovery.

## 1. Zakres i założenia

Driftwatch składa się obecnie z procesu API/SPA/schedulera, izolowanego procesu
`capture-worker` oraz:

- SQLite na wolumenie albo zewnętrznego Postgresa;
- plików `data_dir`, w tym logów i uploadowanych assetów brandingu;
- sekretów i konfiguracji deploymentu poza bazą;
- zewnętrznych usług AI, poczty i webhooków.

Odtworzenie samej bazy nie odtwarza kompletnej usługi. Runbook obejmuje bazę,
branding, konfigurację, klucze, obraz aplikacji i stan integracji. Nie archiwizuj
sekretów w Git, zwykłym ticketcie ani razem z backupem zaszyfrowanym tym samym
kluczem, który znajduje się tylko w utraconym środowisku.

## 2. Cele usługi

Wartości poniżej są propozycją dla ograniczonego pilota, nie obowiązującym SLA.
Właściciel produktu i Operations muszą je zaakceptować po pomiarze restore drill.

| Tryb | Proponowany RPO | Proponowany RTO | Warunek techniczny | Status |
|---|---:|---:|---|---|
| lokalny/self-hosted SQLite | do 24 h | do 8 h | backup off-site co 24 h, instrukcja klienta, dostęp do kluczy | `[NIEZATWIERDZONE]` |
| kontrolowany pilot SaaS | do 4 h | do 4 h | zarządzany Postgres z PITR/snapshotami, monitoring, restore drill | `[NIEPOTWIERDZONE]` |
| płatny produkt z deklarowanym SLA | `[DECYZJA]` | `[DECYZJA]` | redundancja, kolejka/worker, obserwowalność, dyżur, testy i umowy dostawców | `[NIEGOTOWE]` |

**RPO** mierzymy od czasu ostatniego odzyskanego commitu/danych do początku
awarii. **RTO** mierzymy od ogłoszenia incydentu do przywrócenia uzgodnionej
funkcji i weryfikacji, nie tylko do uruchomienia procesu.

## 3. Inwentaryzacja do backupu

| Element | Krytyczność | Mechanizm | Weryfikacja |
|---|---|---|---|
| baza SQLite/Postgres | krytyczna | snapshot/online backup/PITR zgodny z backendem | integralność, Alembic head, liczności i smoke test |
| `data_dir/branding` | ważna dla UI i tenantów | wersjonowany obiektowy backup albo trwały wolumen | hash, typ MIME, odwołania ustawień do istniejących plików |
| zmienne konfiguracji | krytyczne | szyfrowany vault/IaC; bez wartości w repo | lista kluczy i wersji, test dostępu break-glass |
| klucze szyfrowania | krytyczne | osobny, ograniczony vault i procedura odzyskania | dwuosobowy test odczytu kontrolnego |
| obraz i migracje | krytyczne | niezmienny digest obrazu + odpowiadające źródła/migracje | digest, tag, SBOM/source offer, `alembic heads` |
| logi/audyt incydentu | ważne | zewnętrzny chroniony eksport | kompletność okna czasu, sumy kontrolne, RBAC |
| konfiguracja dostawców | ważna | runbook oraz rekord umów/regionów | test auth bez ujawniania sekretu |

Logi rotowane lokalnie i backupy SQLite w `data_dir/backups` mogą zniknąć wraz z
wolumenem. Dla Postgresa aplikacja nadal może zapisywać branding w `data_dir`,
więc kontenera nie należy uznawać za całkowicie bezstanowy bez zewnętrznego
storage dla tych plików.

## 4. Standard backupu

1. **3-2-1:** co najmniej trzy kopie, dwa rodzaje storage, jedna poza głównym
   środowiskiem lub kontem awarii.
2. Szyfrowanie w tranzycie i spoczynku; klucze oddzielone od danych.
3. Konto backupu ma tylko potrzebne uprawnienia; restore wymaga odrębnej roli i
   MFA. Usuwanie/zmiana retencji jest alertowane.
4. Kopia ma identyfikator, backend, czas start/koniec, rewizję Alembic, wersję
   obrazu, rozmiar, hash i status weryfikacji.
5. Backup nie może polegać na surowym kopiowaniu aktywnego pliku SQLite w WAL.
   Użyj online backup API lub zatrzymaj wszystkie procesy i skopiuj komplet
   plików zgodnie z dokumentacją SQLite.
6. Retencja odpowiada polityce usuwania. Po restore stosuje się tombstone'y
   tenantów/usunięć, aby nie reaktywować danych, które miały wygasnąć.
7. Alarm obejmuje brak kopii, opóźnienie względem RPO, błąd szyfrowania, brak
   replikacji off-site i brak udanego drill w terminie.

## 5. Przygotowanie do restore

1. Otwórz incydent i nadaj IC zgodnie z
   [procedurą incydentową](INCIDENT_RESPONSE.pl.md).
2. Zatrzymaj ruch zapisu, scheduler, manualne checki i delivery. Preferuj
   maintenance mode / odcięcie ingress oraz zatrzymanie procesu zamiast restore
   pod aktywną aplikacją.
3. Zapisz wersję obrazu, rewizję Alembic, backend, connection target, czas awarii
   i najnowszy prawdopodobnie poprawny punkt.
4. Zabezpiecz oryginalny uszkodzony stan jako dowód/safety copy. Nie nadpisuj go.
5. Wybierz backup na podstawie katalogu i hashy, nie tylko nazwy pliku.
6. Odtwarzaj zawsze do nowego pliku, wolumenu, bazy lub projektu. Cutover następuje
   dopiero po walidacji i akceptacji drugiej osoby.
7. Potwierdź dostęp do odpowiadających kluczy szyfrowania. Brak klucza oznacza,
   że ciphertext może być integralny, ale bezużyteczny.

## 6. Restore SQLite

### 6.1 Walidacja kopii

Na odseparowanym hoście, z kopią tylko do odczytu:

```bash
python -c "import sqlite3; c=sqlite3.connect('restore-candidate.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('SELECT version_num FROM alembic_version').fetchall())"
```

Wynik `integrity_check` musi być `ok`. Brak `alembic_version`, wiele rewizji albo
nieznana rewizja wymaga ręcznej decyzji i znanej ścieżki migracji; nie stempluj
bazy automatycznie na `head` tylko dlatego, że zawiera znaną tabelę.

Sprawdź również obecność co najmniej organizacji, użytkowników, witryn,
snapshotów, zmian, ustawień, audytu i tabel sekretów właściwych dla wersji.
Zapisz liczności kontrolne bez eksportowania treści do ticketu.

### 6.2 Migracja kandydata

Uruchom obraz odpowiadający planowanej wersji aplikacji, wskaż mu wyłącznie
kandydata i wykonaj:

```bash
DRIFTWATCH_DATABASE_URL=sqlite+aiosqlite:////recovery/restore-candidate.db \
  driftwatch migrate
```

Migracja ma zakończyć się kodem 0, a `alembic current` ma wskazać jedyny head.
Zachowaj log bez sekretów. Nie uruchamiaj jeszcze schedulera ani integracji.

### 6.3 Smoke test i cutover

- uruchom jedną instancję z `DRIFTWATCH_SCHEDULER_ENABLED=false` oraz
  bez aktywnych credentials poczty/AI;
- sprawdź `/livez` i `/readyz`, logowanie testowego operatora, odczyt tenantów,
  witryn, ostatnich zmian i audytu;
- odszyfruj kontrolny sekret przez normalny bezpieczny workflow, bez wypisywania
  wartości; sprawdź referencje do plików brandingu;
- wykonaj dry check bez analizy i wysyłki na zatwierdzonej witrynie testowej;
- zastosuj tombstone'y usuniętych tenantów i powtórz liczności;
- po akceptacji przełącz connection/volume atomowo, uruchom jedną instancję,
  następnie scheduler i integracje etapami;
- monitoruj co najmniej: błędy DB, readiness, tick, backlog, capture, outbox,
  koszty i cross-tenant denial. Zdefiniuj wcześniej próg rollbacku.

Rollback oznacza zatrzymanie nowej instancji i powrót do zachowanego poprzedniego
celu. Nie wykonuj kolejnego nadpisania live DB w panice.

## 7. Restore Postgres

Preferuj mechanizm zarządzanego dostawcy (snapshot/PITR) i jego udokumentowaną
ścieżkę odtworzenia do nowego projektu/bazy. Przed produkcją zapisz dokładną
nazwę planu, region, okno PITR, retencję oraz kontakt awaryjny.

1. Zatrzymaj write traffic i zapisz timestamp/LSN odpowiadający awarii, jeśli
   jest dostępny.
2. Odtwórz snapshot/PITR do **nowego** celu w tym samym wymaganym regionie.
3. Użyj oddzielnych, krótkotrwałych credentials i ogranicz ingress.
4. Uruchom `driftwatch migrate` przeciw nowemu celowi. Nie kieruj migracji do
   starego produkcyjnego endpointu.
5. Zweryfikuj pojedynczy Alembic head, kluczowe constrainty, liczności per tenant,
   najnowsze snapshoty/zmiany, audyt, outbox i użycie AI.
6. Uruchom jedną instancję bez schedulera/delivery, wykonaj smoke test jak dla
   SQLite, zastosuj tombstone'y i dopiero potem przełącz sekret connection.
7. Włącz funkcje etapami. Zachowaj stary cel tylko przez zatwierdzone okno
   rollback, z zablokowanym ruchem i kontrolą dostępu, po czym usuń go zgodnie z
   polityką retencji.

Jeśli używany jest logiczny dump, twórz go spójnie narzędziem zgodnym z wersją
serwera i przywracaj do pustego celu. Nie używaj `--clean` wobec aktywnej bazy.
Rozszerzenia, role i konfiguracja zarządzanego Postgresa mogą wymagać osobnego
odtworzenia; potwierdza to runbook konkretnego dostawcy.

## 8. Utrata klucza lub kompromitacja

| Sytuacja | Postępowanie |
|---|---|
| utracony klucz sesji | użytkownicy tracą sesje, ale baza jest czytelna; wygeneruj nowy primary i wymuś login |
| skompromitowany klucz sesji | nowy primary, bez skompromitowanego previous; przegląd audytu i sesji |
| utracony aktywny klucz szyfrowania bez kopii | ciphertextów nie da się odzyskać; ponowne wprowadzenie sekretów i ocena wpływu |
| skompromitowany klucz szyfrowania | containment, założenie możliwej ekspozycji dostępnych ciphertextów, rotacja i decyzja incydentowa |
| brak starego klucza po restore | użyj zatwierdzonego previous tylko w izolowanym oknie rewrap; nie pozostawiaj go bezterminowo |

Klucze previous są mechanizmem migracji, a nie archiwum wszystkich kluczy.
Repozytorium kluczy powinno mieć osobny backup, MFA, dwuosobowy dostęp i test.

## 9. Restore drill

Minimalna częstotliwość proponowana:

- przed pierwszą produkcją i po zmianie backendu/migracji krytycznej;
- kwartalnie dla pilota;
- miesięcznie albo według SLA po uruchomieniu płatnej usługi;
- dodatkowo po nieudanym backupie, zmianie kluczy, dostawcy lub regionu.

Ćwiczenie nie dotyka produkcyjnego celu. Używa najnowszej rzeczywistej kopii,
odizolowanych credentials i danych traktowanych z tym samym poziomem ochrony.

### Protokół dowodowy

```text
Drill ID:
Data, osoby i akceptujący:
Backend / region / dostawca:
Backup ID, czas, hash, rozmiar:
Wersja obrazu i Alembic przed/po:
Start awarii symulowanej:
Najpóźniejszy odzyskany rekord:
Zmierzony RPO:
Start i koniec recovery:
Zmierzony RTO:
Integralność / liczności / tenant isolation:
Test odszyfrowania:
Test brandingu:
Smoke API / scheduler / outbox:
Tombstone test:
Rollback test:
Wynik PASS/FAIL:
Luki, właściciele i terminy:
Potwierdzenie usunięcia środowiska drill:
```

PASS wymaga spełnienia przyjętego RPO/RTO, integralności, izolacji tenantów,
czytelności wymaganych sekretów i skutecznego cleanupu. Sam start aplikacji nie
jest udanym restore.

## 10. Gate przedprodukcyjny DR

- [ ] zaakceptowane RPO/RTO mają właściciela i są poparte pomiarem;
- [ ] baza, branding, konfiguracja i klucze są objęte inwentaryzacją;
- [ ] backup jest szyfrowany, off-site, monitorowany i odporny na usunięcie konta produkcyjnego;
- [ ] restore role oraz dostęp break-glass mają MFA i audyt;
- [ ] ostatni rzeczywisty backup przeszedł pełny drill do nowego celu;
- [ ] test objął migracje, tenant isolation, odszyfrowanie, tombstone i rollback;
- [ ] dostawca Postgres ma potwierdzony plan, region, PITR, retencję i support;
- [ ] alarmy wykrywają przekroczenie RPO i brak drill;
- [ ] procedura usunięcia uwzględnia wygaśnięcie kopii i restore tombstone;
- [ ] wynik i luki zostały zaakceptowane przez Operations, Security i właściciela produktu.
