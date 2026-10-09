# Driftwatch — przewodnik administratora

Prosty przewodnik po panelu dla osoby, która zarządza Driftwatch: co gdzie
ustawić, co znaczą poszczególne opcje, co warto dostosować, a czego lepiej nie
ruszać. Przykłady podane są w formie, którą można wpisać wprost.

> Ten dokument jest przeznaczony dla administratora/operatora wdrożenia.
> Dokumentacja techniczna (dla programistów) jest po angielsku w
> [`README.md`](../README.md) i [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
> English version: [ADMIN_GUIDE.en.md](ADMIN_GUIDE.en.md).

---

## 1. Role — kto co może

- **Operator (superadmin)** — właściciel instancji. Widzi wszystkie organizacje,
  tworzy je, zarządza ustawieniami instancji, audytem, operacjami, rozliczeniami
  i kopią zapasową. Pierwsze zarejestrowane lub jawnie zainicjalizowane konto
  jest także administratorem swojej organizacji.
- **Administrator** — zarządza jedną organizacją: jej projektami, stronami,
  odbiorcami, użytkownikami i ustawieniami. Nie widzi innych organizacji.
- **Użytkownik** — widzi dane swojej organizacji; edytować może tylko te projekty
  i strony, do których dostał uprawnienia do edycji. Grant projektu obejmuje
  jego strony; grant jednej strony nie daje edycji innych stron ani administracji
  całym projektem.

Zasada: **interfejs ukrywa to, czego dana rola nie może zrobić, a serwer i tak to
blokuje** — nie da się obejść tego, „dostając się" do ukrytego przycisku.

---

## 2. Pierwsze kroki

1. W nowej instalacji zarejestruj pierwsze konto, aby zostać operatorem
   i administratorem domyślnej organizacji. Dalsza rejestracja jest domyślnie
   zamknięta. Instancja spoza loopback wymaga jawnego włączenia jednorazowej
   rejestracji lub konta z konfiguracji; zobacz
   [pierwsze konto](INSTALL.md#first-account-and-registration).
2. **Włącz uwierzytelnianie dwuskładnikowe** (Ustawienia → Uwierzytelnianie
   dwuskładnikowe). To najważniejsze zabezpieczenie konta operatora — zob. sekcję 8.
3. Jeśli obsługujesz wielu klientów: w panelu **Organizacje** utwórz organizację
   i kliknij **Zarządzaj**, żeby „wejść" w nią. Wszystko, co wtedy tworzysz
   (projekty, strony, odbiorcy, użytkownicy), trafia do tej organizacji. Górny
   baner pokazuje, w której organizacji jesteś; „Wyjdź" wraca do widoku operatora.

Do własnego monitorowania otwórz **Organizacje → Zarządzaj** przy domyślnej
organizacji. Jako jej administrator tworzysz projekty i monitory bez grantu
supportowego. Dostęp do danych innej organizacji pozostaje odrębnym procesem
i na publicznym wdrożeniu wymaga grantu supportowego. Pierwszy właściciel jest
wybierany atomowo; restart lub usunięcie kont nie otwiera ponownie tego procesu.

**Plany, limity i zawieszanie (tylko operator).** Na karcie organizacji widzisz
plan i zużycie: liczbę stron oraz sprawdzeń AI w miesiącu. Organizacji zarządzanej
ręcznie można przypisać szablon planu i jawne limity. Gdy organizacja ma już
historię rozliczeń, zwykła edycja planu/capów jest blokowana — źródłem uprawnień
staje się zweryfikowana subskrypcja, a nie formularz operatora.

Limity są egzekwowane transakcyjnie na serwerze. Przełącznik **Aktywna** zawiesza
organizację: blokuje użytkowników i nowe kontrole, ale zachowuje dane, audyt i
historię rozliczeń. **Trwałe usunięcie organizacji nie jest dostępne w panelu ani
API.** Zakończenie umowy wymaga kontrolowanego offboardingu: eksportu, okresu
grace, usunięcia danych u dostawców, obsługi retencji i backup tombstone.

Ekran **Rozliczenia** pokazuje realny stan subskrypcji organizacji. Nowe zakupy
pozostają zamknięte do skonfigurowania dostawcy, self-service, zatwierdzonej bramki
prawnej i właściwego trybu test/live. Self-service dotyczy ręcznie utworzonych
organizacji; publiczna rejestracja musi pozostać wyłączona. Walidacja odrzuca
jednoczesne włączenie publicznej rejestracji i samodzielnych zakupów.

---

## 3. Monitorowanie — projekty, strony, odbiorcy

- **Projekt** — grupuje strony i nadaje im wspólne reguły AI oraz tryb
  powiadomień. Kliknij w projekt, aby zobaczyć jego strony i dodać kolejną
  („Dodaj stronę tutaj").
- **Strona** — pojedynczy adres monitorowany w wybranym interwale. Przy dodawaniu:
  - **URL** — pełny adres, np. `https://example.com/cennik`.
  - **Obszar do monitorowania** — kliknij „Otwórz selektor wizualny", aby wskazać
    fragment strony myszką (zamiast wpisywać selektor CSS ręcznie). Selektor
    wizualny otwiera prawdziwą przeglądarkę na serwerze — działa tylko, gdy serwer
    ma pulpit (na czystym Dockerze będzie niedostępny; wtedy użyj pola „Zaawansowane").
  - **Nagraj kroki** — jeśli strona wymaga logowania albo zamknięcia banera, nagraj
    te kliknięcia; zostaną odtworzone przed każdym sprawdzeniem. Wartości pól są
    szyfrowane na serwerze. Zmiana URL na inny origin wymaga usunięcia kroków albo
    jawnego wprowadzenia nowych wartości pól dla nowego originu.
  - **Interwał** — co ile minut sprawdzać (np. 60).
- **Odbiorcy** — adresy e-mail, do których trafiają powiadomienia. Przypisuje się
  ich do stron lub projektów. Odbiorca może mieć **zastępstwo** na zakres dat
  (urlop) — maile w tym czasie idą do zastępcy. W oknie zastępstwa pole
  **„Dotyczy"** pozwala ograniczyć je do jednego projektu albo jednej strony;
  domyślnie obejmuje wszystkie powiadomienia danego odbiorcy. Bardziej
  szczegółowe zastępstwo (strona) ma pierwszeństwo przed ogólniejszym (projekt,
  a potem wszystkie).

---

## 4. Ustawienia AI (sekcja „Analiza AI")

Monitorowanie działa bez AI: przeglądarka przechwytuje wskazany obszar,
usuwane są jawnie wykluczone elementy, a system porównuje całe rekordy i ich
powiązania. Pierwsze udane przechwycenie tworzy punkt odniesienia i nie wysyła
alertu o zmianie. Kolejna wykryta różnica staje się zapisanym zdarzeniem.
Jednocyfrowa cena jest istotną treścią; daty, identyfikatory i ceny nie są
uznawane automatycznie za szum. Dokładne granice opisuje
[semantyka monitorowania](MONITORING_SEMANTICS.md).

W formularzu **Dodaj stronę** lub **Edytuj stronę** wybierz **Wszystkie zmiany —
bez AI**, aby wyłączyć płatną analizę tej strony. Formularz jawnie ustawia wtedy
powiadomienia o **Każdej zmianie**, bez dziedziczenia filtra istotności. Ta ścieżka
nie wykonuje wywołań AI i nie zużywa limitu AI. Dostawa nadal wymaga odbiorcy albo
webhooka. Usunięcie klucza API przy włączonym AI powoduje błąd analizy; nie jest
wyłączeniem AI.

Przy włączonym AI model ocenia istotność już wykrytej zmiany. Nie decyduje,
czy zdarzenie istnieje. Reguły mają kolejność: strona → projekt → ustawienia
organizacji/instancji → reguły wbudowane. Panel efektywnych reguł wskazuje źródło.

| Opcja | Co to jest | Przykład / rada |
|---|---|---|
| **Klucz API OpenAI (operator instancji)** | Wspólny klucz do modelu oceniającego zmiany. | `sk-...` (z platform.openai.com). Bez niego analiza się nie wykona. Przechowywany zaszyfrowany; w panelu widać tylko `********`. |
| **Model (operator instancji)** | Który model OpenAI analizuje różnice. | Wybierz model obsługiwany przez skonfigurowanego dostawcę i sprawdź własne ocenione przykłady; koszt i zgodność zależą od modelu oraz reguł. |
| **Domyślne powiadomienia** | Czy mailować o każdej zmianie, czy tylko o istotnych. | „Tylko istotne zmiany" (zalecane) albo „Każda zmiana". Można nadpisać per projekt/strona. |
| **Reguły istotności AI** | Opis własnymi słowami, co jest ważne, a co nie. | zob. przykład niżej. Puste = używane są reguły domyślne (widoczne jako szary tekst). |
| **Format odpowiedzi** (prompt bazowy) | Instrukcja, jak model ma się zachować i w jakim języku pisać. | **Lepiej nie ruszać.** Puste = sensowny domyślny tekst (widoczny jako placeholder). „Przywróć domyślne" cofa zmiany. |

**Przykład reguł istotności** (możesz wpisać wprost):

```
Istotne: zmiany cen, dostępności produktów, oficjalne ogłoszenia, nowe lub
zmienione dokumenty (w tym PDF-y), zmienione daty, terminy i godziny otwarcia.

Nieistotne: poprawki literówek, zmiany wizualne, zmiana kolejności, banery
reklamowe, elementy nawigacji i stopki.
```

Pod ustawieniami AI jest panel **„Co trafia do AI"** (tylko do odczytu). Pokazuje,
co system usuwa ze strony przed analizą (nawigacja, skrypty, stopki…), jakie
jawne atrybuty techniczne i wykluczone obszary usuwa oraz jakie pola zwraca
model. Widoczne daty, liczby i identyfikatory zachowują znaczenie. Warto tam zajrzeć, zanim zmienisz reguły — widzisz, czego one dotyczą.

---

## 5. Wysyłanie e-maili (sekcja „Dostarczanie e-mail")

Operator instancji ustawia wspólnego dostawcę, poświadczenia i nadawcę oraz
wykonuje test e-mail. Administrator organizacji ustawia treść i język maili,
odbiorców oraz webhook we własnej przestrzeni.

| Opcja | Co to jest | Przykład |
|---|---|---|
| **Dostawca e-mail** | Jak wysyłać maile. | `auto` (sam wybierze wg podanych danych), `smtp`, `brevo` albo `log` (tylko zapis w logu — do testów, nic nie wychodzi). |
| **Język e-maili** | Język powiadomień i e-maili resetu hasła dla tej organizacji. | `Polski` lub `English`; domyślnie angielski. |
| **Adres nadawcy** | Z jakiego adresu idą maile. | `notifications@example.com` |
| **Nazwa nadawcy** | Wyświetlana nazwa. | `Driftwatch` (puste = nazwa marki) |
| **Temat (szablon)** | Szablon tematu maila. | zostaw domyślny, jeśli pasuje |
| **Wstęp do maila** | Opcjonalny tekst na początku. | np. „Wykryto zmianę na monitorowanej stronie." |

**Wariant SMTP** (np. własny serwer, Gmail, Office365):

| Opcja | Przykład |
|---|---|
| Host SMTP | `smtp.gmail.com` |
| Port SMTP | `587` |
| Szyfrowanie SMTP | `starttls` (port 587) lub `ssl` (port 465) |
| Użytkownik SMTP | `notifications@example.com` |
| Hasło SMTP | hasło aplikacji (Gmail wymaga „hasła aplikacji", nie zwykłego) — przechowywane zaszyfrowane |

**Wariant Brevo** (HTTP API, prościej niż SMTP):

- Ustaw **Dostawca e-mail** = `brevo` i wklej **Klucz API Brevo**.

**Wyślij testowy e-mail:** na dole sekcji wpisz adres i kliknij **„Wyślij test"** —
Driftwatch wyśle jedną wiadomość przez aktualnie zapisaną konfigurację i pokaże,
przez który kanał poszła (lub dlaczego się nie udała). **Najpierw zapisz
ustawienia** — test używa zapisanych wartości, nie tych wpisanych przed zapisem.

**Rada o dostarczalności:** żeby maile nie wpadały do spamu, adres nadawcy powinien
być w domenie, dla której masz poprawne **SPF/DKIM/DMARC**. To konfiguruje się u
dostawcy domeny/poczty, nie w Driftwatch.

**Odbiorcy alertów technicznych** — adresy, które dostają ostrzeżenia operacyjne
(np. strona zablokowana, zniknął monitorowany selektor). To Twój zespół, nie
klient.

**Webhook (Slack / Discord / własny)** — oprócz e-maila każda istotna zmiana może
trafić na webhook. W sekcji „Powiadomienia webhook" wklej adres (np. Slack/Discord
incoming webhook albo własny endpoint), wybierz format (`Generyczny JSON`, `Slack`
lub `Discord`) i kliknij **„Wyślij testowy webhook"** (najpierw zapisz ustawienia).
Adres jest traktowany jak sekret (zaszyfrowany, maskowany) i nigdy nie trafia do
logów. Adres musi być publiczny — wewnętrzne/lokalne adresy są odrzucane.

---

## 6. Marka i wygląd (branding)

Driftwatch możesz oznaczyć własną marką — nazwą, logo, kolorem akcentu i treścią
strony startowej. Branding ma **dwie warstwy**, dokładnie jak reszta ustawień:

- **Marka organizacji** (każdy administrator) — nazwa, logo i kolor akcentu Twojej
  organizacji; widzą je jej członkowie w panelu. Puste pole = dziedziczenie z
  ustawień instancji.
- **Marka instancji** (tylko operator) — te same pola jako domyślne dla całej
  instancji, plus treść **publicznej strony startowej**, którą widzi każdy przed
  zalogowaniem.

Ustawiasz to w **Ustawienia → Marka**.

| Pole | Warstwa | Co robi |
|---|---|---|
| **Nazwa marki** | org + instancja | Zastępuje „Driftwatch" w nagłówku, stopce i tytule karty przeglądarki. |
| **Kolor akcentu** | org + instancja | Kolor (hex, np. `#7c3aed`) przebarwiający przyciski, wyróżnienia i logo. Ciemny kolor jest automatycznie rozjaśniany, aby ciemny tekst na przyciskach pozostał czytelny. |
| **Obraz logo** | org + instancja | Prześlij PNG lub JPEG do 2 MB. Puste = wbudowany znak. Obraz jest przechowywany pod tym samym originem co aplikacja. |
| **Hasło (tagline)** | instancja | Krótkie hasło nad nagłówkiem hero i w stopce strony startowej. |
| **Nagłówek / podtytuł hero** | instancja | Główny tekst sekcji powitalnej strony startowej. |
| **Obraz tła hero** | instancja | Prześlij PNG lub JPEG do 8 MB; obraz jest przyciemniany, by tekst pozostał czytelny. |

Pola strony startowej (hasło, hero, tło) widzi **tylko operator** — strona startowa
jest jedna dla całej instancji. Wszystko jest opcjonalne: puste pola dają domyślny,
dopracowany wygląd. Kolor jest walidowany jako hex, a obrazy są sprawdzane po
rzeczywistej zawartości, rozmiarze i wymiarach. Zdalne adresy obrazów i SVG nie są
renderowane; bitmapy trafiają do kontrolowanego storage same-origin.

> **O kolorze:** akcent to jeden hex, z którego wyliczana jest cała paleta. Jeśli
> wolisz gotowy zestaw kolorów zamiast własnego hex, użyj przełącznika motywu w
> Ustawieniach — własny akcent z brandingu ma pierwszeństwo przed motywem.

---

## 7. Ustawienia instancji — czego lepiej nie ruszać

Te opcje (sekcja „Przechwytywanie i koszty") widzi tylko
operator i dotyczą całej instancji. **Domyślne wartości są dobre — zmieniaj tylko
świadomie.**

| Opcja | Rada |
|---|---|
| **Limit czasu / czas ustabilizowania** | Zostaw, chyba że konkretna strona ładuje się wolno. |
| **Min. odstęp / jitter** | Strażniki obciążenia wspólnego silnika. **Lepiej nie ruszać** — zbyt niskie wartości mogą przeciążyć przeglądarkę. |
| **Retencja snapshotów** | Ile migawek trzymać na stronę. Domyślne wystarcza; zwiększ tylko, jeśli potrzebujesz głębszej historii. |
| **Ceny OpenAI (za 1M tokenów)** | Służą tylko do **wyceny kosztów** w panelu. Zaktualizuj, jeśli OpenAI zmieni cennik; nie wpływają na działanie. |

W ustawieniach organizacji (gdy „wejdziesz" w organizację jako operator, albo jako
administrator) te instancyjne pola są ukryte — edytujesz tylko to, co należy do
organizacji. Każde nadpisywalne pole ma **„Przywróć domyślne"**, które czyści
wartość organizacji i przywraca dziedziczenie z ustawień instancji.

Adres aplikacji, `DRIFTWATCH_BASE_URL`, należy do konfiguracji wdrożenia,
nie formularza w panelu. Służy do linków w mailach i ochrony przed CSRF;
ustaw go zgodnie z [instrukcją wdrożenia](DEPLOY.md).

---

## 8. Bezpieczeństwo

- **Uwierzytelnianie dwuskładnikowe (2FA)** — Ustawienia → włącz, zeskanuj kod QR
  aplikacją (Google Authenticator itp.), wpisz kod, **zapisz kody zapasowe** (są
  pokazane raz; każdy działa jednorazowo, gdy nie masz telefonu). Na publicznym
  wdrożeniu operator i administrator organizacji muszą włączyć 2FA przed
  dostępem do chronionych paneli; wymóg egzekwuje także serwer.
- **Ponowne uwierzytelnienie (step-up)** — pobranie kopii zapasowej bazy i
  restore, zaproszenia i wrażliwe zmiany kont, otwarcie checkoutu/portalu oraz
  przyznanie dostępu supportowego wymagają ponownego podania hasła (i kodu 2FA,
  jeśli wymagany). To celowe zabezpieczenie operacji wysokiego ryzyka.
- **Hasła i sekrety** — hasła są hashowane (Argon2), a klucze (OpenAI, SMTP, 2FA,
  webhook) szyfrowane w bazie i maskowane w panelu (`********`). Zmiana hasła
  wylogowuje pozostałe sesje.
- **Zaproszenia użytkowników** — administrator tworzy konto bez pola hasła.
  Dostawa trafia do trwałej kolejki; użytkownik dostaje jednorazowy link ważny
  24 godziny od próby dostawy i sam ustala hasło. Provider `log` nie dostarcza
  linków konta, a Operations pokazuje wtedy `email_not_configured`.
  Administrator może ponowić zaproszenie, odwołać wszystkie sesje albo zresetować
  TOTP, ale nigdy nie poznaje poświadczenia klienta. Te akcje są audytowane.
- **Reset hasła** — na ekranie logowania jest „Nie pamiętasz hasła?”. Użytkownik
  podaje e-mail i dostaje jednorazowy link (ważny 30 minut). Skorzystanie z linku
  ustawia nowe hasło i wylogowuje wszystkie sesje. Żeby to działało, instancja
  musi mieć skonfigurowaną wysyłkę e-mail (sekcja 5). Formularz nie zdradza, czy
  dany adres ma konto. Tokeny są dodatkowo związane z losową generacją sesji;
  restore bazy zmienia ją dla każdego użytkownika i unieważnia wszystkie stare
  cookies oraz linki.
- **Dostęp supportu** — po wejściu operatora do innej organizacji dane klienta pozostają
  zablokowane. Odczyt i zapis wymagają step-up z 2FA, powodu i krótkiego grantu.
  Grant można natychmiast odwołać; serwer sprawdza jego stan i audytuje każde
  żądanie.

---

## 9. Operacje, audyt i rozliczenia (operator)

- **Operations** — pokazuje rzeczywisty stan bazy, schedulera, capture workera,
  kolejki, dostaw, storage i maintenance. Stan przechodzi na **degraded** m.in.
  przy martwych zadaniach, nieudanych dostawach albo braku miejsca na bezpieczną
  kopię. Nierozwiązane martwe zadanie można ponowić jako jeden audytowany,
  idempotentny następnik. To diagnostyka w aplikacji, nie zamiennik zewnętrznych
  alertów i SLO.
- **Audyt** — append-only historia operacji uprzywilejowanych: actor, cel, zakres
  organizacji i szczegóły zmiany. Poziom instancji pokazuje tylko control-plane;
  wpisy klienta są widoczne po wejściu do jego organizacji i, na publicznym
  wdrożeniu, po aktywnym grancie supportu. Surowy plik procesu nie jest
  udostępniany jako produktowy dziennik audytowy.
- **Rozliczenia** — w kontekście organizacji pokazują status subskrypcji,
  obowiązujące uprawnienie oraz hostowany checkout/portal. Checkout i portal
  wymagają step-up. Trybu live nie włączaj przed ukończeniem checklisty
  przedprodukcyjnej i przeglądem osoby zarządzającej wdrożeniem oraz dostawcą.
- **Pobierz kopię zapasową** — spójna migawka bazy SQLite (wymaga step-up; zawiera
  hashe haseł i zaszyfrowane sekrety, więc trzymaj go bezpiecznie). Najlepiej
  pobierać w spokojnym momencie i przechowywać kopie poza serwerem.
- **Przywróć kopię zapasową** — wgranie wcześniej pobranej kopii (wymaga step-up).
  **Zastępuje wszystkie obecne dane.** Przed nadpisaniem Driftwatch sam zapisuje
  obecną bazę jako kopię bezpieczeństwa z sygnaturą czasu (`…-pre-restore-….db`)
  obok pliku bazy. Po przywróceniu zaloguj się ponownie. Plik jest sprawdzany
  (musi być poprawną bazą SQLite z danymi Driftwatch), jest strumieniowany z
  limitem i migrowany przed instalacją. Restore rotuje generacje sesji, więc
  wszystkie stare sesje i linki są unieważnione.
- **Postgres** — kontrolki backup/restore SQLite są ukryte. Kopie, PITR i restore
  wykonuje się u dostawcy bazy zgodnie z runbookiem disaster recovery.
- **Zużycie AI** — liczba tokenów i szacowane koszty według modelu, miesiąca,
  strony i projektu. Brak ceny oznacza **Nieznany** koszt, nie zero. Gdy choć
  jedno wywołanie nie ma ceny, koszt całkowity jest nieznany, a suma wycenionych
  wywołań jest pokazana osobno. Zero oznacza znany koszt zerowy. To szacunek,
  a nie faktura dostawcy.
- **Pochodzenie analizy** — każda zakończona analiza w szczegółach strony zachowuje
  model, źródło i wersję reguł, dokładny prompt systemowy, SHA-256 wejścia,
  informację o skróceniu wejścia oraz identyfikator zużycia. Nowa zakończona
  analiza dopisuje przebieg. Sama edycja ustawień nie tworzy przebiegu ani nie
  zmienia danych starych analiz.
  Braki w starszych rekordach są oznaczone jako **Nieznane**, zamiast używać
  dzisiejszych ustawień.
- **Ocena człowieka** — oznacz gotowy wynik jako istotny/nieistotny. **Zgodność
  ocen w sprawdzonych zdarzeniach** obejmuje tylko wykryte zdarzenia z wynikiem AI
  i oceną człowieka. Nie mierzy zmian pominiętych przez detektor, pełnej
  skuteczności wykrywania ani poprawności nieocenionych zdarzeń.
- **Aktualizacje** — przy starcie aplikacja wykonuje migracje Alembic, jeśli nie
  zostały wyłączone. Przed aktualizacją wykonaj i sprawdź kopię zapasową;
  automatyczna migracja nie gwarantuje ochrony przed utratą danych. Na
  produkcyjnym Postgresie używaj osobnego zadania migracji przed wdrożeniem.
  Część downgrade celowo odmawia cofnięcia z utratą informacji. Przygotuj
  poprawkę albo odtworzenie zgodnej kopii z pasującym kodem i kluczami.

---

## 10. Szybka ściąga: co warto dostosować, czego nie

**Warto dostosować:**
- Klucz OpenAI i (ewentualnie) model.
- Reguły istotności — pod swój przypadek.
- Dane e-mail (dostawca, nadawca, SMTP/Brevo).
- Markę: nazwę, logo i kolor akcentu pod swoją firmę; jako operator także treść
  strony startowej (hasło, hero, tło).
- Ignorowane selektory dla konkretnych, „hałaśliwych" stron.
- Interwał sprawdzania per strona.

**Lepiej nie ruszać (bez wyraźnego powodu):**
- Format odpowiedzi (prompt bazowy) — jest dostrojony; w razie czego „Przywróć domyślne".
- Min. odstęp / jitter capture — strażniki obciążenia.
- `DRIFTWATCH_BASE_URL`; należy do konfiguracji wdrożenia i nie jest edytowalny
  w panelu.

**Jak zmieniać:** wpisz wartość w polu i kliknij **Zapisz ustawienia**. Puste pole
niebędące sekretem oznacza „użyj wartości domyślnej" (widocznej jako szary
placeholder). Pusty input sekretu zachowuje obecną wartość; użyj jawnej akcji
**Usuń zapisane dane logowania**, a następnie autoryzuj i zapisz usunięcie.


## 11. Historia, błędy i odzyskiwanie

Historia strony i Powiadomienia są stronicowane. Kliknij **Wczytaj starsze**, aby
zobaczyć wcześniejsze rekordy; podpisy wykresu i statystyk opisują wczytany zakres,
a nie bezwarunkowo całą historię. Stary link z alertu otwiera dokładne zdarzenie,
nawet jeśli nie znajduje się na pierwszej stronie listy. Eksport XLSX zachowuje
wybraną organizację oraz filtr strony/projektu i nie ogranicza się do stron listy
wczytanych w przeglądarce.

Widoczne panele monitorowania odświeżają się co 15 sekund, po powrocie do okna
oraz po kliknięciu **Odśwież**. Znacznik czasu opisuje ostatnie udane odświeżenie;
błąd odświeżenia oznacza nieaktualny widok. Nie jest to obietnica czasu wykonania
kontroli ani dostarczenia wiadomości.

| Stan | Znaczenie i działanie |
| --- | --- |
| Oczekuje / w trakcie | Analiza jeszcze się nie zakończyła. Odśwież albo poczekaj na kolejne odpytywanie. |
| Bez AI | Celowe monitorowanie wszystkich zmian. Sprawdź diff; brak oceny istotności. |
| Brak skonfigurowanej dostawy | Brak efektywnego odbiorcy i webhooka, więc automatyczne AI jest pomijane. Dodaj cel dostawy i w razie potrzeby ponów zdarzenie. |
| Błąd AI | Przechwycenie i diff zachowane; analiza nie powiodła się. Sprawdź błąd i konfigurację. Automatyczne próby następują po 5, 15, 60 i 240 minutach, potem wymagane jest działanie. |
| Limit AI | Model nie jest wywoływany. Próba jest planowana za 15 minut; może udać się po odnowieniu albo zmianie limitu. |
| Błąd / częściowa dostawa | Sprawdź wiersze dostawy dla odbiorców. Ponowienie obsługuje nieudane cele, zachowując ukończone dostawy. |

**Analizuj ponownie** wywołuje AI według bieżącej konfiguracji i dodaje zakończony
przebieg. **Ponów** wznawia przetwarzanie/dostawę i może zużyć limit, jeśli brakuje
analizy. **Test reguł** także zużywa limit AI i koszt szacunkowy, ale nie zapisuje
wyniku w zdarzeniu. Wynik należy do dokładnie testowanego szkicu; edycja reguł
ukrywa go.

Wyjście z formularza z niezapisanymi zmianami wymaga potwierdzenia. Zmiana
organizacji resetuje jej formularze i oczekujące dane sekretów; spóźnione
odpowiedzi poprzedniej sesji/kontekstu są odrzucane. Przy błędzie zmiany kontekstu
sprawdź bieżący baner i ponów działanie w tym kontekście. Dostępne akcje członka
wynikają z jego grantów; API niezależnie sprawdza każdą operację.

Dodawanie wielu stron zachowuje udane pozycje, a do ponowienia pozostawia tylko
nieudane. Sprawdź URL i przyczynę przed kolejnym wysłaniem. Selektor wizualny ma
akcje ponowienia i anulowania; wymaga pulpitu serwera. Gdy wdrożenie nie może
otworzyć interaktywnej przeglądarki, użyj pola CSS.

Typowe pytania opisuje [FAQ](FAQ.md). Instalację, konfigurację dostawców i kopie
zapasowe opisują [README](../README.md) oraz [instrukcja wdrożenia](DEPLOY.md).
