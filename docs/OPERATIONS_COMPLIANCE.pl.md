# Mapa danych, podprocesorzy i retencja

- **Status:** projekt operacyjny, niezatwierdzony prawnie
- **Właściciel dokumentu:** `[DECYZJA WŁAŚCICIELA PRODUKTU]`
- **DPO / kancelaria:** `[DO UZUPEŁNIENIA]`
- **Ostatni przegląd:** 2026-07-19
- **Następny przegląd:** `[DATA, maksymalnie za 3 miesiące]`

Ten dokument opisuje aktualnie rozpoznane przepływy danych w Driftwatch i
proponuje zasady operacyjne. Nie jest poradą prawną, rejestrem czynności
przetwarzania ani potwierdzeniem zgodności. Podstawy prawne, role stron,
obowiązki informacyjne, okresy retencji i transfery międzynarodowe wymagają
zatwierdzenia przez właściciela produktu i kancelarię/DPO przed uruchomieniem
publicznej usługi.

## 1. Granice i role

Driftwatch może działać jako instalacja własna klienta albo usługa wielodostępna.
Te modele mają inne role i umowy:

| Obszar | Hipoteza robocza | Wymagana decyzja |
|---|---|---|
| Dane konta, bezpieczeństwa, sprzedaży i rozliczeń usługi SaaS | operator może być administratorem | kancelaria określa cele, podstawy i obowiązki informacyjne |
| Dane stron, odbiorców i reguł wprowadzone przez klienta B2B | operator zwykle działa jako procesor klienta | DPA ma opisać instrukcje, poufność, usuwanie, audyt i dalszych procesorów |
| Dane osób na monitorowanych stronach | mogą być treścią kontrolowaną przez klienta albo podmiot trzeci | klient potwierdza uprawnienie do monitorowania i przekazywania treści |
| Instalacja self-hosted | użytkownik instalacji zwykle sam określa role i dostawców | dokumentacja oraz umowa licencyjna nie zastępują jego analizy prawnej |

**Gate publicznego SaaS:** nie publikować zapewnień typu „GDPR compliant” ani
„zgodne z RODO”, dopóki role, podstawy, DPA, transfery i faktyczne procedury nie
zostaną zatwierdzone i przećwiczone.

## 2. Mapa danych

„Stan usuwania” opisuje zachowanie rozpoznane w kodzie, a nie przyjętą politykę.

| Kategoria | Przykłady i osoby | Cel techniczny | Lokalizacja / odbiorca | Stan usuwania i ryzyko |
|---|---|---|---|---|
| Konto i uwierzytelnianie | e-mail, imię, hash hasła, rola, status, ostatnie logowanie, TOTP i hashe kodów odzyskiwania | dostęp, MFA, bezpieczeństwo | główna baza; TOTP szyfrowany | użytkownika można usunąć; brak kompletnego workflow DSAR/offboarding |
| Organizacja i uprawnienia | nazwa tenanta, członkostwo, granty, status, limity i plan | izolacja tenantów i provisioning | główna baza | hard delete organizacji jest wyłączony; zawieszenie zachowuje dane; brak kompletnego staged offboardingu |
| Konfiguracja monitoringu | URL, selektor CSS, interwał, reguły AI, kroki interakcji, nazwy projektów | wykonywanie monitoringu | główna baza; URL trafia do Chromium i może trafić do AI/powiadomienia | pojedynczą witrynę można usunąć; organizacja wymaga osobnego offboardingu; URL może zawierać dane w ścieżce lub query |
| Sekrety interakcji | login, token lub inna wartość wpisywana w formularz strony | odtworzenie kroków przed capture | ciphertext w osobnej tabeli; plaintext chwilowo w pamięci workera i wprowadzany na stronie docelowej | kaskada witryny; offboarding organizacji nie jest zautomatyzowany; kopie bazy nadal zawierają ciphertext |
| Treść monitorowanych stron | oczyszczony HTML i tekst, nagłówki dokumentów, fingerprinty zasobów | porównanie wersji | główna baza; pobierana z systemu zewnętrznego | retencja ilościowa, nie czasowa; treść może przypadkowo zawierać dane osobowe lub poufne |
| Historia zmian | diff tekstowy/HTML, podsumowanie, headline, wynik AI i feedback użytkownika | detekcja, prezentacja i jakość | główna baza; diff i reguły są wysyłane do dostawcy AI, jeśli AI jest włączone | związana z retencją snapshotów i usunięciem witryny; brak samodzielnej retencji czasowej |
| Odbiorcy i zastępstwa | adresy e-mail, imiona, adres zastępcy, zakres i daty zastępstwa | dostarczanie alertów | główna baza, SMTP/Brevo, ewentualnie log kanału lokalnego | ręczne usunięcie; historia dostaw i dostawca mogą nadal zawierać etykietę/adres |
| Dostawa powiadomień | e-mail/etykieta celu, payload, status, błędy, provider message ID, idempotency key | outbox, retry, audyt dostawy | główna baza; dostawca poczty albo endpoint webhooka | brak niezależnej retencji czasowej; zwykle kaskada od zdarzenia zmiany |
| Zużycie AI | model, tokeny, koszt, tenant, powiązanie z witryną/zmianą | limit i kontrola kosztu | główna baza | automatyczne usuwanie po 180 dniach domyślnie; własność tenantowa przeżywa usunięcie witryny; offboarding organizacji nie jest zautomatyzowany |
| Billing i zgody zakupowe | identyfikatory customer/subscription/price/invoice, kwoty i waluta, status, okres, wersje Terms/Privacy, użytkownik i czas zgody, hash/event ID | checkout, portal, entitlement, reconciliacja i dowód zgody | główna baza oraz Stripe po włączeniu | klucze obce celowo blokują hard delete; retencja księgowa, refund/dispute i offboarding dostawcy wymagają decyzji Finance/Legal |
| Audyt administracyjny | aktor i e-mail, IP, akcja, cel, szczegóły before/after/reason | rozliczalność i dochodzenie | główna baza | rekordy są append-only i przeżywają usunięcie celu; brak przyjętego terminu retencji/anonymizacji |
| Logi operacyjne | czas, moduł, błędy, identyfikatory, czasem e-mail/URL | diagnostyka i bezpieczeństwo | stdout platformy oraz pliki `data_dir` | rotacja rozmiarem: plik 10 MiB i 5 kopii; brak gwarantowanego okresu czasowego |
| Ustawienia i sekrety integracji | klucz AI, SMTP/Brevo, webhook, klucze TOTP/interakcji | integracje platformy i tenantów | baza; pola sekretne szyfrowane, klucze główne w zmiennych środowiska | ustawienia organizacji kaskadowo; ustawienia instancji i sekrety platformy pozostają do ręcznego usunięcia |
| Branding | logo/hero jako PNG/JPEG, nazwa, teksty i kolory | white-label i landing page | ustawienia w bazie; same-origin pliki w `data_dir/branding` | usunięcie assetu usuwa plik; hard delete organizacji jest wyłączony, a cleanup katalogu wymaga kroku offboardingu |
| Backupy i kopie bezpieczeństwa | pełna baza, w tym hashe, ciphertexty, adresy i treści | DR i rollback | SQLite w `data_dir/backups`; Postgres u dostawcy lub w repozytorium operatora | SQLite domyślnie 7 kopii co 24 h; restore tworzy dodatkową safety copy; polityka dostawcy Postgres musi być jawna |
| Dane w przeglądarce użytkownika | cookie sesji/MFA/step-up, język, motyw, żądany acting-org | sesja i preferencje UI | urządzenie użytkownika | sesja domyślnie 14 dni; MFA pending i step-up 5 minut; Local Storage pozostaje do wyczyszczenia przez użytkownika/aplikację |

### Minimalizacja po stronie klienta

Warunki umowy i onboarding powinny wymagać, aby klient:

1. nie umieszczał danych osobowych, tokenów ani identyfikatorów w URL, nazwie
   witryny, regule AI lub selektorze, jeśli nie jest to konieczne;
2. monitorował tylko zasoby, do których ma uprawnienie, z uwzględnieniem
   regulaminu strony i rozsądnej częstotliwości żądań;
3. nie używał kroków interakcji do przetwarzania danych szczególnych kategorii
   bez odrębnej oceny i zgody operatora;
4. informował osoby, których adresy dodaje jako odbiorców lub zastępców;
5. wybierał retencję adekwatną do celu i usuwał niepotrzebne witryny/odbiorców.

## 3. Przepływy zewnętrzne

1. Użytkownik przesyła konfigurację i dane konta do API Driftwatch.
2. API zapisuje dane w SQLite albo Postgresie; sekrety aplikacyjne są
   szyfrowane, ale pełny backup nadal jest materiałem wrażliwym.
3. Chromium łączy się z monitorowaną stroną. Strona widzi adres IP infrastruktury,
   User-Agent, czas żądania i odtwarzane interakcje. Wartość sekretu interakcji
   jest ujawniana stronie docelowej zgodnie z instrukcją klienta.
4. Przy włączonym AI diff, URL i reguły analizy są przekazywane dostawcy modelu.
5. Powiadomienie przekazuje adres e-mail oraz treść alertu do SMTP/Brevo albo
   payload do wybranego webhooka (np. Slack/Discord/system klienta).
6. Hosting, baza, logi i backupy mogą być obsługiwane przez różnych dostawców.

Nie należy klasyfikować monitorowanej strony automatycznie jako podprocesora.
Jest to zewnętrzny system wskazany przez klienta; jego rola i legalność przepływu
muszą wynikać z instrukcji klienta. Podobnie własny webhook klienta może być jego
odbiorcą, a nie podprocesorem operatora.

## 4. Rejestr podprocesorów

Każdy wiersz musi wskazywać faktycznie wybraną osobę prawną i ofertę, nie tylko
markę. Wiersz bez właściciela, DPA i lokalizacji jest blokadą produkcji.

| Funkcja | Kandydat wynikający z repo | Dane | Pola do zatwierdzenia | Status |
|---|---|---|---|---|
| Hosting aplikacji i logów | Railway albo inny operator | cały ruch, metadane, zmienne środowiska, logi; przy wolumenie także branding | podmiot umowy, region, DPA, TOMs, usuwanie po zakończeniu, transfer | `[NIEZATWIERDZONE]` |
| Zarządzany Postgres i backup | Supabase albo inny dostawca | wszystkie dane bazy i kopie | region projektu, harmonogram i retencja backupu, PITR, DPA, transfer, szyfrowanie | `[NIEZATWIERDZONE]` |
| Analiza AI | OpenAI albo zamiennik adaptera | URL, diff, reguły/prompt, metadane użycia | właściwa oferta i ustawienia użycia danych, region, retencja, DPA, transfer, lista dalszych procesorów | `[NIEZATWIERDZONE]` |
| Dostarczanie e-mail | Brevo albo skonfigurowany SMTP | odbiorca, treść, metadane dostawy | podmiot, region, DPA, retencja treści/logów, transfer, suppression list | `[NIEZATWIERDZONE]` |
| Observability | obecnie stdout/pliki; docelowy dostawca nie wybrany | logi, IP, identyfikatory, możliwe e-maile/URL | redakcja, region, RBAC, retencja, DPA, alerty dostępu | `[BRAK DOSTAWCY / DECYZJI]` |
| Płatności i podatki | Stripe hosted Checkout i Customer Portal są zaimplementowane, lecz domyślnie wyłączone i niezatwierdzone dla live | identyfikatory customer/subscription/price/invoice, kwoty, waluta, statusy, okresy i dowód zgody; dane karty omijają Driftwatch | Stripe, hosted checkout/portal, podpisane webhooki i lokalny ledger; DPA, PCI scope, tax/VAT i retencja finansowa wymagają osobnej decyzji | `[KOD DO SANDBOXU; LIVE NO-GO]` |
| Analityka produktu / support | niezaimplementowane | zależne od przyszłej decyzji | cel, minimalizacja, consent, DPA, region, retencja | `[WYŁĄCZONE]` |

Dla każdego aktywnego dostawcy rejestr organizacyjny powinien dodatkowo zawierać:

- datę akceptacji i właściciela biznesowego;
- link i wersję DPA, polityki prywatności, TOMs i listy subprocessors;
- państwa przechowywania i dostępu wsparcia;
- podstawę transferu poza EOG, ocenę transferu i środki dodatkowe;
- procedurę zgłaszania incydentu oraz kontakt bezpieczeństwa;
- tryb eksportu i potwierdzonego usunięcia po rozwiązaniu umowy;
- datę ostatniego przeglądu i zmianę wymagającą powiadomienia klientów.

## 5. Retencja: stan i polityka docelowa

Poniższe terminy docelowe są propozycją operacyjną. Kancelaria/DPO zatwierdza je
w kontekście podstaw prawnych, roszczeń, podatków, umów i legal hold. Zespół
techniczny musi wdrożyć egzekwowanie zanim termin zostanie obiecany klientom.

| Zbiór | Stan techniczny | Propozycja docelowa | Właściciel / gate |
|---|---|---|---|
| Konto i dane organizacji | konto można usunąć; hard delete organizacji jest celowo wyłączony, a zawieszenie zachowuje dane | aktywna umowa + maks. 30 dni na kontrolowany offboarding; potem tylko kopie do ich wygaśnięcia | Product + Legal; potrzebny staged offboarding i kontrolowany mechanizm erasure |
| Snapshoty i zmiany | domyślnie 50 snapshotów na witrynę; pruning następuje przy pracy schedulera | konfigurowalny okres i limit ilościowy, np. 90 dni jako ustawienie bazowe po akceptacji | Product + DPO; wymagane time-based enforcement |
| Użycie AI | 180 dni domyślnie | 180 dni lub krócej, chyba że agregacja/anonymizacja wystarcza do rozliczeń | Finance + DPO; obecny mechanizm istnieje |
| Historia powiadomień/outbox | bez samodzielnego terminu; zależy od cyklu zmiany/witryny | np. 90 dni danych operacyjnych, dłużej wyłącznie agregaty i wymagane dowody | Ops + DPO; potrzebny cleanup job |
| Audyt uprzywilejowany | append-only, bez terminu; e-mail i IP pozostają po usunięciu użytkownika | proponowane 24 miesiące, później usunięcie lub pseudonimizacja, chyba że legal hold | Security + Legal; potrzebny job i polityka legal hold |
| Logi operacyjne | limit rozmiaru, nie czasu | 30 dni online; dłużej tylko dla otwartego incydentu, z kontrolą dostępu i redakcją | Security + Ops; potrzebne centralne logi |
| Reset hasła / tokeny | reset 30 min, MFA pending 5 min, step-up 5 min, sesja domyślnie 14 dni; tokeny stateless | utrzymać krótkie terminy, udokumentować sesję i mechanizm unieważnienia | Security; okres sesji wymaga akceptacji produktu |
| Branding w `data_dir` | asset można usunąć w panelu; offboarding całej organizacji nie czyści jeszcze katalogu automatycznie | usunąć przy offboardingu i potwierdzić brak plików osieroconych | Ops; wymagany krok i docelowo automatyzacja |
| SQLite backup | domyślnie 7 rotowanych kopii co 24 h; kopie na tym samym wolumenie | szyfrowana kopia off-site, retencja zgodna z RPO oraz maks. okresem usunięcia | Ops + Security; obecny backup nie jest pełnym DR |
| Postgres backup | zależny od wybranej usługi/planu | jawny PITR/snapshot z zapisanym okresem i testem restore | Ops; wymaga dowodu dostawcy i drill |
| Safety copy po restore | tworzona obok live DB; pruning zależny od późniejszego backup ticka | automatyczne, terminowe usunięcie po zaakceptowanym oknie rollback | Ops + Security; brak gwarancji czasowej |

### Legal hold

Legal hold może wstrzymać zwykłe usuwanie tylko na udokumentowane polecenie osoby
uprawnionej. Rejestr powinien zawierać zakres, podstawę, właściciela, początek,
datę przeglądu i zwolnienie blokady. Nie wolno używać ogólnego „może się przydać”
jako powodu bezterminowej retencji.

## 6. Procedura usunięcia / zakończenia usługi

Hard delete organizacji jest wyłączony w API i panelu, ponieważ przypadkowa
kaskada zniszczyłaby billing oraz dowody audytowe. Nie istnieje jeszcze kompletny
mechanizm DSAR/offboardingu ani zatwierdzona ścieżka erasure.
Do czasu automatyzacji operacja wymaga kontrolowanej checklisty:

1. **Przyjęcie żądania.** Nadaj identyfikator, zapisz zakres, termin, kanał i
   podstawę. Nie umieszczaj danych wrażliwych w tytule zgłoszenia.
2. **Weryfikacja.** Potwierdź tożsamość i uprawnienie osoby/administratora
   organizacji. Dla danych przetwarzanych na rzecz klienta wykonuj jego
   udokumentowane instrukcje, a nie samodzielną ocenę osoby zgłaszającej.
3. **Kolizje.** Sprawdź aktywną umowę, należności, legal hold, incydent oraz
   obowiązki podatkowe. Decyzję o odmowie lub ograniczeniu podejmuje Legal/DPO.
4. **Eksport.** Jeśli umowa lub prawo tego wymaga, utwórz eksport przed
   usunięciem, zaszyfruj go, ogranicz dostęp i ustal osobny krótki termin wygaśnięcia.
5. **Zatrzymanie przetwarzania.** Zawieś tenant i scheduler, unieważnij sesje,
   wyłącz powiadomienia i integracje. Zapisz moment rozpoczęcia.
6. **Dane live.** Użyj zatwierdzonego, osobnego mechanizmu erasure (nie endpointu
   hard delete, którego aplikacja nie udostępnia) do usunięcia danych tenanta i
   plików brandingu. Zweryfikuj billing, tabele zależne, outbox, ustawienia,
   sekrety i usage; audyt oraz księgowość obsłuż zgodnie z zatwierdzoną retencją,
   a nie przez przypadkową kaskadę.
7. **Dostawcy.** Usuń dane z systemu poczty, observability, supportu, AI lub
   hostingu, jeżeli są tam przechowywane i umowa tego wymaga. Zachowaj potwierdzenie.
8. **Backupy.** Zapisz tombstone z identyfikatorem tenanta. Nie modyfikuj
   historycznych kopii ad hoc; dopilnuj ich wygaśnięcia i zastosuj tombstone po
   każdym awaryjnym restore, aby usunięte dane nie wróciły do produkcji.
9. **Kontrola.** Wykonaj zapytania weryfikacyjne i przegląd plików. Druga osoba
   zatwierdza wynik dla usunięcia całej organizacji.
10. **Zamknięcie.** Zapisz zakres, czas, wykonawcę, wyjątki, terminy wygaśnięcia
    backupów i odpowiedź dla klienta. Nie dołączaj pełnego eksportu do zgłoszenia.

## 7. Cookies i Local Storage

Aktualny frontend nie zawiera analityki ani reklam. Rozpoznane mechanizmy to:

| Mechanizm | Rodzaj | Cel | Termin techniczny |
|---|---|---|---|
| `driftwatch_session` | httpOnly cookie | sesja uwierzytelniona | domyślnie 14 dni |
| `driftwatch_2fa` | httpOnly cookie | dokończenie logowania TOTP | 5 minut |
| `driftwatch_stepup` | httpOnly cookie | potwierdzenie operacji wysokiego ryzyka | 5 minut |
| `driftwatch_lang` | Local Storage | język interfejsu | do ręcznego wyczyszczenia |
| `driftwatch_theme` | Local Storage | motyw | do ręcznego wyczyszczenia |
| żądany acting-org | Local Storage | kontekst operatora; serwer potwierdza zakres | usuwany przy wyjściu/utracie kontekstu |

Kancelaria powinna ocenić, czy w danych jurysdykcjach dla mechanizmów ściśle
niezbędnych wystarcza informacja bez bannera zgody. Dodanie analityki, marketingu,
chat widgetu, A/B testów albo fingerprintingu wymaga ponownej inwentaryzacji i
nie może zostać „przykryte” istniejącą tabelą.

## 8. Decyzje wymagane przed produkcją

- [ ] właściciel produktu zatwierdził model usługi, grupy klientów i jurysdykcje;
- [ ] kancelaria/DPO zatwierdzili role administrator/procesor i podstawy prawne;
- [ ] powstały Privacy Notice, Terms, DPA i instrukcje klienta zgodne z produktem;
- [ ] rejestr podprocesorów wskazuje faktycznych kontrahentów, regiony i umowy;
- [ ] zatwierdzono transfery poza EOG i procedurę zmian podprocesorów;
- [ ] retencja docelowa ma właściciela, podstawę i techniczne egzekwowanie;
- [ ] istnieje działający DSAR/offboarding z testem usunięcia i restore tombstone;
- [ ] wyznaczono kontakt prywatności, bezpieczeństwa i procedurę skarg;
- [ ] zweryfikowano zgodność sposobu użycia z PolyForm Noncommercial 1.0.0
      i zachowano wymagane informacje licencyjne komponentów zewnętrznych;
- [ ] każda nowa integracja płatności/analityki przechodzi update tej mapy przed wdrożeniem.

## 9. Rejestr przeglądów

| Data | Zakres | Osoba | Wynik / decyzje | Następny przegląd |
|---|---|---|---|---|
| 2026-07-17 | mapa wynikająca z repo, wersja robocza | Codex / do akceptacji | brak akceptacji prawnej i właścicielskiej | `[DO UZUPEŁNIENIA]` |
