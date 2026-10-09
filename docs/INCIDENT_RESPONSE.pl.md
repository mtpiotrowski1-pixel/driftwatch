# Procedura reagowania na incydenty

- **Status:** runbook roboczy, do zatwierdzenia i przećwiczenia
- **Incident Commander:** `[IMIĘ / ROLA / TELEFON]`
- **Security Lead:** `[IMIĘ / ROLA / TELEFON]`
- **DPO / kancelaria:** `[KONTAKT 24/7 LUB ZASADA ESKALACJI]`
- **Kontakt dostawców:** `[LINK DO CHRONIONEJ LISTY, BEZ SEKRETÓW W TYM PLIKU]`
- **Ostatni przegląd:** 2026-07-17

Dokument jest procedurą techniczno-organizacyjną, nie poradą prawną. Decyzje o
kwalifikacji naruszenia, zawiadomieniu organu, osób, klientów, ubezpieczyciela
lub organów ścigania podejmują wyznaczone osoby z DPO/kancelarią. Zegar
regulacyjny może rozpocząć się przed pełnym poznaniem przyczyny, dlatego czas
pierwszego sygnału i czas uzyskania świadomości organizacji zapisuje się osobno.

## 1. Kiedy uruchomić procedurę

Uruchom runbook przy wiarygodnym podejrzeniu co najmniej jednego zdarzenia:

- dostęp do danych innego tenanta, błędny acting-org lub obejście uprawnień;
- przejęcie konta operatora, ominięcie MFA, masowe resetowanie haseł;
- ujawnienie klucza sesji, klucza szyfrowania, TOTP, sekretu interakcji, SMTP,
  AI, webhooka albo kopii bazy;
- wyjście Chromium do sieci prywatnej/metadanych lub wykonanie niezaufanej
  strony poza przyjętą izolacją;
- nietypowa wysyłka e-mail/webhook, spam, duplikaty albo utrata dostaw;
- nieautoryzowana zmiana planu, limitów, uprawnień lub przyszłego billingu;
- utrata, korupcja albo niedostępność bazy, backupu, schedulera lub capture;
- podatność lub kompromitacja zależności, obrazu, CI/CD albo konta dostawcy;
- zgłoszenie dostawcy o naruszeniu dotyczącym środowiska Driftwatch.

Nie czekaj na potwierdzenie wycieku. Otwarcie incydentu jest odwracalne; utrata
czasu i dowodów nie jest.

## 2. Klasyfikacja

| Poziom | Przykład | Reakcja początkowa |
|---|---|---|
| SEV-1 | potwierdzony cross-tenant, kompromitacja klucza głównego, destrukcja bazy, aktywny masowy abuse | natychmiast, IC i Security 24/7, zawieszenie ryzykownej funkcji/ruchu |
| SEV-2 | prawdopodobne naruszenie ograniczonego zbioru, niedostępność krytycznej funkcji, utrata RPO | do 30 min, właściciel systemu i Security |
| SEV-3 | pojedynczy błąd bez potwierdzonej ekspozycji, degradacja z obejściem | w godzinach pracy, analiza i poprawka z terminem |
| SEV-4 | zdarzenie obserwacyjne lub nieudana próba bez wpływu | rejestr, korelacja i przegląd trendu |

Poziom podnosi się przy danych wrażliwych, dzieciach, dużej liczbie osób,
aktywnym atakującym, braku logów, transferze poza oczekiwany region albo
niemożliwości pewnego określenia zakresu.

## 3. Role

| Rola | Odpowiedzialność |
|---|---|
| Incident Commander | priorytety, decyzje operacyjne, rytm odpraw, delegowanie i zamknięcie |
| Security Lead | analiza, containment, dowody, rotacja, ocena ekspozycji |
| Operations Lead | platforma, baza, backup/restore, monitoring, kontakt dostawców |
| Product/Customer Lead | lista klientów, wpływ funkcjonalny, status page i komunikacja |
| DPO / Legal | role stron, terminy, ryzyko praw i wolności, zgłoszenia i treść komunikatów |
| Scribe | niezmienny timeline, decyzje, hipotezy, źródła i action items |

Jedna osoba może pełnić kilka ról w małym zespole, ale IC nie powinien prowadzić
równocześnie głębokiej analizy. Wszystkie decyzje o usunięciu dowodu, trwałej
zmianie danych lub kontakcie zewnętrznym wymagają jawnego właściciela.

## 4. Pierwsze 15 minut

1. Nadaj identyfikator `INC-YYYY-NNN`, poziom i IC.
2. Zapisz: źródło sygnału, czas sygnału, czas świadomości, środowisko, tenanty,
   konta i funkcje potencjalnie objęte.
3. Utwórz chroniony kanał incydentu. Nie wklejaj sekretów, pełnych tokenów,
   backupów ani danych klientów do komunikatora lub zgłoszenia.
4. Zachowaj logi platformy, aplikacji, bazy, dostawców i CI w repozytorium dowodów
   z ograniczonym dostępem. Zapisz strefę czasową i sumy kontrolne eksportów.
5. Powstrzymaj automatyczne czyszczenie tylko w zakresie wymaganym dla dowodów;
   utwórz udokumentowany legal/security hold.
6. Wybierz najmniejszy skuteczny containment. Nie wyłączaj całej usługi, jeśli
   bezpiecznie wystarczy wyłączyć scheduler, AI, pocztę, webhook lub jeden tenant.

## 5. Containment

### Konto lub sesja

- dezaktywuj objęte konto i zwiększ jego `token_version` przez bezpieczny workflow;
- przy podejrzeniu globalnego klucza sesji wprowadź nowy primary i nie zachowuj
  skompromitowanego klucza jako `SESSION_SECRET_KEY_PREVIOUS`;
- wymuś ponowne logowanie, MFA operatorów i przegląd zmian w audycie;
- nie resetuj dowodowo wszystkich haseł przed ustaleniem listy kont, chyba że
  aktywny atak wymaga natychmiastowej ochrony.

### Sekret szyfrowania lub integracji

- zablokuj klucz u dostawcy i ogranicz egress/funkcję, która go używa;
- przy kompromitacji klucza szyfrowania załóż potencjalną ekspozycję wszystkich
  ciphertextów dostępnych atakującemu; samo ponowne zaszyfrowanie nie cofa wycieku;
- rotuj osobno sesje, encryption, AI, SMTP/Brevo i webhooki; prowadź listę
  obiektów przepisanych oraz tych, których nie udało się odszyfrować;
- usuń poprzedni klucz natychmiast przy kompromitacji, nawet jeśli powoduje to
  konieczność ponownego wprowadzenia części sekretów.

### Cross-tenant lub capture/SSRF

- zawieś dotknięty tenant/witrynę i manualne checki; w razie niepewnego zakresu
  wyłącz scheduler oraz worker capture na poziomie platformy;
- zastosuj blokadę egress w infrastrukturze, nie wyłącznie w kodzie przeglądarki;
- zachowaj URL, zweryfikowane DNS/IP, redirecty i requesty subresources bez
  wykonywania ponownego capture z konta produkcyjnego;
- sprawdź odczyty i mutacje, eksporty, powiadomienia oraz audyt dla obu tenantów.

### Poczta, webhook lub przyszłe płatności

- wyłącz delivery worker albo credential, zachowując outbox do późniejszej oceny;
- uzgodnij z dostawcą blokadę nadużycia i eksport message/event IDs;
- nie replayuj automatycznie całego backlogu; wybierz tylko niepotwierdzone cele
  i użyj stabilnych kluczy idempotencji;
- przy płatnościach wstrzymaj fulfillment i webhook replay do uzgodnienia z
  dostawcą; nie edytuj ręcznie salda/subskrypcji bez ledgeru i akceptacji Finance.

### Utrata danych lub dostępności

Postępuj według [runbooka disaster recovery](DISASTER_RECOVERY.pl.md). Restore
wykonuj do nowego celu i zweryfikuj przed cutoverem. Zastosuj tombstone'y
usuniętych tenantów, aby backup nie przywrócił danych wcześniej usuniętych.

## 6. Pierwsza godzina

- zbuduj listę faktów, hipotez i luk; oznacz każdą pozycję osobno;
- określ najwcześniejszy możliwy dostęp, wektor, dane, tenanty, regiony i odbiorców;
- sprawdź integralność audytu, konfiguracji, migracji, obrazu i historii deploy;
- skontaktuj dostawcę jego kanałem security i nadaj numer ticketu;
- ustal godzinę kolejnej odprawy oraz wewnętrzny deadline oceny prawnej;
- przygotuj bezpieczny status techniczny bez spekulacji i bez obietnic terminu;
- zacznij tabelę osób/klientów potencjalnie dotkniętych, ale nie wysyłaj jej
  niezaszyfrowanym kanałem.

## 7. Ocena naruszenia danych

DPO/kancelaria dokumentuje co najmniej:

- czy doszło do naruszenia poufności, integralności lub dostępności danych;
- rolę Driftwatch dla każdego zbioru (administrator czy procesor);
- kategorie i przybliżoną liczbę osób oraz rekordów;
- prawdopodobieństwo i wagę skutków, łatwość identyfikacji, szyfrowanie i klucze;
- państwa, podprocesorów, odbiorców i kategorie szczególne;
- środki już zastosowane oraz ryzyko po containment;
- obowiązki z DPA, umów, ubezpieczenia i regulacji sektorowych.

Jeśli organizacja działa jako administrator, GDPR przewiduje ocenę zawiadomienia
organu bez zbędnej zwłoki i, gdy jest to wykonalne, w ciągu 72 godzin od
stwierdzenia naruszenia, chyba że jest mało prawdopodobne ryzyko dla praw i
wolności. Procesor zawiadamia administratora bez zbędnej zwłoki zgodnie z umową.
Zawiadomienie osób może być wymagane przy wysokim ryzyku. Są to decyzje DPO/Legal,
nie automatyczna reguła techniczna. Źródła: [tekst GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
oraz [wytyczne EDPB 01/2021](https://www.edpb.europa.eu/documents/guideline/guidelines-012021-on-examples-regarding-personal-data-breach-notification_en).

## 8. Komunikacja

### Zasady

- komunikuj potwierdzone fakty, zakres niepewności, wpływ i konkretne działania;
- nie przypisuj winy i nie używaj „brak wpływu”, jeśli analiza nie jest zamknięta;
- każdy komunikat zewnętrzny zatwierdzają IC, Customer Lead i Legal/DPO;
- utrzymuj jedną wersję prawdy, historię korekt i listę odbiorców;
- nie ujawniaj wektora w sposób ułatwiający aktywny atak.

### Szablon pierwszej informacji dla klienta

> W dniu `[czas i strefa]` wykryliśmy zdarzenie dotyczące `[funkcja/zakres]`.
> Obecnie potwierdziliśmy `[fakty]`; nadal badamy `[otwarte pytania]`. Zastosowaliśmy
> `[containment]`. Potencjalny wpływ na Państwa organizację to `[wpływ]`.
> Zalecane działanie: `[konkret albo „brak działania na tym etapie”]`.
> Następna aktualizacja nastąpi do `[czas]`, nawet jeśli analiza nie będzie zakończona.

### Szablon aktualizacji wewnętrznej

```text
INC / SEV / IC:
Okno zdarzenia:
Potwierdzone fakty:
Hipotezy (z confidence):
Zakres danych i klientów:
Containment wykonany / planowany:
Decyzje prawne i deadline:
Blokery:
Następna odprawa:
```

## 9. Eradication, recovery i zamknięcie

1. Usuń przyczynę i wszystkie znane ścieżki dostępu, nie tylko pierwszy IOC.
2. Zbuduj i zweryfikuj artefakt z czystego źródła; sprawdź zależności i sekrety.
3. Odtwórz dane do odseparowanego celu, wykonaj migracje i smoke testy.
4. Przywracaj ruch etapami; monitoruj auth, błędy tenant scope, egress, delivery,
   koszty i kolejkę. Zdefiniuj trigger rollbacku przed cutoverem.
5. Potwierdź rotację, unieważnienie sesji, usunięcie tymczasowych eksportów i
   ograniczenie holdów do potrzebnego zakresu.
6. IC zamyka incydent dopiero po decyzji Security i Ops oraz po zapisaniu
   otwartych ryzyk z właścicielem i terminem.

Postmortem bez wskazywania winnego przeprowadź do 5 dni roboczych dla SEV-1/2.
Powinien zawierać timeline, wpływ, detekcję, przyczynę, czynniki systemowe,
skuteczność reakcji, action items i dowód ich zamknięcia.

## 10. Ćwiczenia i dowody

- ćwiczenie tabletop cross-tenant i wycieku klucza: co najmniej co 6 miesięcy;
- restore drill: zgodnie z [runbookiem DR](DISASTER_RECOVERY.pl.md);
- test kontaktów i dostępu awaryjnego: kwartalnie;
- test revoke/rotation kluczy: po każdej zmianie mechanizmu i co najmniej rocznie;
- przegląd procedury: po każdym SEV-1/2, zmianie dostawcy lub zmianie prawa/umowy.

Każde ćwiczenie zapisuje czas detekcji, eskalacji, containment, decyzji prawnej i
recovery, a także dowody, luki, właścicieli oraz terminy poprawek.
