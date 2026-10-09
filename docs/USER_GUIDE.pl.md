# Driftwatch — przewodnik użytkownika

Ten przewodnik prowadzi krok po kroku po aplikacji. Opisuje działania i nazwy
kontrolek bez wymagania wiedzy programistycznej. Aktualne widoki z syntetycznymi
danymi znajdziesz w [galerii interfejsu](screenshots/README.md).

W nowej instalacji zarejestruj pierwsze konto, aby zostać jej
administratorem/operatorem. Dalsza rejestracja jest domyślnie zamknięta;
administrator zaprasza kolejnych użytkowników (rozdział 10). Instancję można też
zainicjalizować kontem właściciela z konfiguracji. Zobacz [instalację](INSTALL.md).

> Język i wylogowanie znajdziesz na dole menu, w lewym dolnym
> rogu (patrz rozdział 2). Wersja angielska tego przewodnika:
> [USER_GUIDE.en.md](USER_GUIDE.en.md).

Do czego to służy: Driftwatch sam pilnuje wybranych stron internetowych i daje znać
mailem, gdy zmieni się coś ważnego (np. cena, regulamin, oferta) — nie musisz
sprawdzać ich ręcznie.

---

## Słowniczek — kilka pojęć na start

- **Strona** (ang. *site*) — pojedynczy adres internetowy, który Driftwatch pilnuje.
- **Projekt** (ang. *project*) — grupa stron o wspólnych regułach i odbiorcach
  (można myśleć o nim jak o folderze).
- **Odbiorca** (ang. *recipient*) — adres e-mail, na który przychodzą powiadomienia.
- **Zmiana** (ang. *change*) — różnica wykryta na stronie między dwoma sprawdzeniami.
- **Zmiana istotna** (ang. *significant*) — zmiana, którą AI uznała za ważną według
  Twoich reguł (np. zmiana ceny, a nie literówka w banerze).
- **Punkt wyjścia** (ang. *baseline*) — zapamiętany stan strony, do
  którego porównywane są kolejne sprawdzenia.
- **Organizacja** — odizolowana przestrzeń własna lub zespołu: projekty, strony
  i odbiorcy, niewidoczne dla innych organizacji.

## Role — dlaczego widzisz inne menu niż ktoś inny

Część pozycji w menu pojawia się zależnie od Twoich uprawnień:

- **Operator** (superadmin) — właściciel całej instancji;
  widzi dodatkowo **Organizacje** (rozdział 9).
- **Administrator** — zarządza swoją organizacją; widzi **Dostęp** (użytkownicy,
  rozdział 10) oraz pełne **Ustawienia** (rozdział 8).
- **Użytkownik** — widzi dane organizacji, ale edytować może tylko to, do czego
  dostał uprawnienia. Może też zmienić własne hasło i język.

---

## 1. Logowanie

1. **E-mail** — wpisz swój adres e-mail.
2. **Hasło** — wpisz hasło ustawione z zaproszenia albo początkowe hasło
   administratora nowej instalacji. Administrator nie wybiera i nie poznaje
   hasła zaproszonego użytkownika.
3. **Zaloguj się** — kliknij, aby wejść.
4. **Nie pamiętasz hasła?** — wyślemy Ci na e-mail link do
  ustawienia nowego (link działa przez 30 minut — patrz rozdział 1a).

Jeśli masz włączone logowanie dwuskładnikowe (kod z aplikacji w telefonie), po
haśle aplikacja poprosi jeszcze o sześciocyfrowy kod (albo jeden z kodów
zapasowych). Jak to włączyć — patrz rozdział 8.

Administrator wystawionej instalacji musi włączyć TOTP przed wejściem do produktu.
Pierwszy właściciel zarządza swoją organizacją przez członkostwo administratora,
bez grantu supportowego. Dostęp operatora do innej organizacji wymaga czasowego,
audytowanego grantu supportowego. Szczegóły: [instrukcja administratora](ADMIN_GUIDE.pl.md).

### 1a. Odzyskiwanie hasła

Po kliknięciu **„Nie pamiętasz hasła?"** podajesz e-mail i klikasz **„Wyślij link
resetujący"**. Jeśli konto istnieje, dostaniesz wiadomość z linkiem. Link otwiera ekran
**„Wybierz nowe hasło"**, gdzie dwa razy wpisujesz nowe hasło (min. 8 znaków) i
zatwierdzasz **„Ustaw nowe hasło"**. Potem logujesz się już nowym hasłem.

---

## 2. Jak poruszać się po stronie (menu)

Po zalogowaniu po lewej stronie jest **menu** — to z niego korzystasz przez cały czas.

1. **Pulpit** — strona główna z podsumowaniem.
2. **Dodaj stronę** — dodajesz nowy adres do śledzenia.
3. **Projekty** — grupy stron o wspólnych regułach.
4. **Odbiorcy** — adresy e-mail, które dostają powiadomienia.
5. **Powiadomienia** — historia wysłanych wiadomości.
6. **Ustawienia** — konfiguracja i Twoje konto.

Zależnie od roli w menu mogą pojawić się też: **Dostęp** — dla
administratora (rozdział 10) — oraz **Organizacje** — dla
operatora (rozdział 9).

**Na samym dole menu (lewy dolny róg)** masz: swój profil (imię i e-mail),
**przełącznik języka** (English / Polski) oraz **Wyloguj** („Sign out"). Tam
najszybciej zmienisz język i bezpiecznie wyjdziesz z konta.

Na **Pulpicie** widzisz najważniejsze liczby (ile stron, ile zmian, koszt analizy
AI), wykres aktywności, listę ostatnich zmian oraz kafelki Twoich stron z
przyciskiem **„Sprawdź teraz"**, który od razu sprawdza daną stronę.

---

## 3. Dodawanie strony do śledzenia

To najważniejsza czynność. Kliknij w menu **Dodaj stronę**.

1. **URL** — wklej pełny adres strony, którą chcesz śledzić (np. `https://example.com/cennik`).
2. **Nazwa** — własna, czytelna nazwa (np. „Cennik konkurenta"). Opcjonalna.
3. **Utwórz stronę** — zapisuje i zaczyna śledzić.

Dodatkowo na tym ekranie:
- **Wskaż obszar do śledzenia** — zamiast całej strony możesz wskazać myszką
  konkretny fragment (przycisk „Otwórz selektor wizualny"). Działa, gdy serwer ma ekran;
  jeśli nie — śledzona jest cała strona, a selektor możesz wpisać ręcznie w sekcji
  „Zaawansowane".
- **Nagraj kroki** — jeśli strona wymaga zalogowania lub zamknięcia
  baneru, nagraj te kliknięcia raz; będą powtarzane przed każdym sprawdzeniem.
- **Interwał sprawdzania** — co ile minut sprawdzać (np. 60).
- **Powiadomienia** — kiedy alarmować: *dziedzicz z projektu/globalnie*, *tylko
  istotne zmiany* albo *każda zmiana*.
- **Odbiorcy** — kto ma dostawać powiadomienia o tej stronie.
- **Analiza** — wybierz wyłączone AI, aby monitorować bez klucza OpenAI. Ten
  tryb wymaga powiadomień o każdej zmianie; zapisuje diff bez werdyktu modelu.

Selektor wizualny zależy od wdrożenia i jest wyłączony w referencyjnym Compose.
Nadal możesz ręcznie podać CSS i skonfigurować kroki interakcji.

Możesz też włączyć przełącznik **„Dodawanie zbiorcze”** (u góry), żeby wkleić wiele adresów
naraz — po jednym w każdej linii.

---

## 4. Projekty

Projekty grupują strony i nadają im wspólne reguły. Kliknij w menu **Projekty**.

1. **Nowy projekt** — tworzy nowy projekt.
2. **Karta projektu** — kliknij ją, aby wejść do środka, zobaczyć jego strony i
  dodać kolejne (przycisk „Dodaj stronę tutaj"). Obok każdej karty są też ikony
  **edycji** i **usunięcia** oraz **„Eksportuj do Excela"** (pobranie zmian projektu do
  arkusza).

W projekcie ustawiasz wspólne **reguły AI** (co jest ważne) i **tryb powiadomień**
(każda zmiana / tylko istotne), które dziedziczą wszystkie strony w środku.
Usunięcie projektu nie kasuje jego stron — przestają tylko dziedziczyć jego reguły.

---

## 5. Strona i podgląd zmiany

Kliknięcie w stronę (na pulpicie lub w projekcie) otwiera jej szczegóły. To tutaj
zobaczysz, co się dokładnie zmieniło.

1. **Sprawdź teraz** — natychmiast sprawdza stronę, bez czekania na
  harmonogram. W tym samym pasku narzędzi masz też:
  **Sprawdzenie próbne** (samo sprawdzenie strony, bez wysyłki alertów),
  **Ustaw punkt wyjścia** (zapisz stronę w obecnej postaci), **Wstrzymaj**,
  **Edytuj**, **Eksportuj do Excela** (pobierz zmiany do arkusza) oraz
  **Usuń**.
2. **Podgląd zmiany** — kolorami widać, co dokładnie się zmieniło:
  **czerwone** = usunięte/stare, **zielone** = nowe. Nad podglądem jest krótkie
  podsumowanie od AI (np. „Cena spadła z 199 zł na 149 zł”) i ocena, czy zmiana
  jest **istotna**.

Po lewej jest lista wszystkich wykrytych zmian dla tej strony — klikasz dowolną,
aby zobaczyć jej podgląd.

**Gdy coś się nie powiedzie:** jeśli sprawdzenie albo wysyłka maila zawiodą, zmiana
dostaje czerwoną etykietę **„Wymaga uwagi"**. Otwórz ją i użyj
**Ponów** (ponów wysyłkę) albo **Przeanalizuj ponownie** (ponów analizę AI bez wysyłania
maila).

Wyłączone AI, oczekiwanie, błąd i blokada limitu są różnymi stanami — nie oznaczają
werdyktu „nieistotna zmiana”. Historia zapisuje każdy rzeczywisty przebieg
analizy wraz z modelem i pochodzeniem reguł/wejścia; ponowna analiza zachowuje
poprzednie przebiegi. Podgląd zużywa tokeny, ale nie zastępuje zapisanego werdyktu.
Nieznany koszt pozostaje nieznany. Błąd przechwycenia zachowuje ostatni poprawny baseline.

---

## 6. Odbiorcy powiadomień

Odbiorcy to adresy e-mail, na które przychodzą powiadomienia. Kliknij **Odbiorcy**.

1. **Dodaj odbiorcę** — dopisujesz nowy adres e-mail.
2. **Ikona kalendarza (zastępstwo)** — gdy ktoś jest na urlopie, ustaw tu
  **zastępstwo urlopowe** na wybrane dni: w tym czasie jego powiadomienia
  pójdą do osoby zastępującej. Możesz je ograniczyć do jednego projektu lub jednej
  strony albo zostawić na wszystkich powiadomieniach.

Obok każdego odbiorcy są jeszcze ikony **edycji** (zmiana nazwy, włącz/wyłącz —
nieaktywny odbiorca jest pomijany przy wysyłce) i **usunięcia**.

---

## 7. Powiadomienia

Tu jest **historia** wszystkich powiadomień: do kogo i kiedy poszły oraz czy
dotarły. Możesz filtrować po statusie: **Wszystkie**, **Wysłane**,
**Nieudane** i **Pominięte**. To miejsce, w którym sprawdzisz, że
alerty faktycznie wychodzą.

---

## 8. Ustawienia (dla administratora)

Administrator organizacji ustawia reguły istotności, treść i język maila,
odbiorców, webhook oraz markę. Wspólny klucz i model AI, dostawca poczty,
nadawca i test e-mail należą do ustawień operatora instancji. Użytkownik
może zmienić własne hasło, język i motyw.

1. **Klucz API OpenAI (operator)** — klucz do modelu, który ocenia zmiany. Bez niego analiza
  się nie wykona. Jest przechowywany w postaci zaszyfrowanej (w polu widać tylko
  `********`).
2. **Model (operator)** — model wybrany do oceny różnic. Sprawdź aktualny cennik dostawcy
   i ekran zużycia. Nieznany koszt nie jest kosztem zero ani ceną innego modelu.
3. **Dostawca e-mail (operator)** — jak wysyłać maile (automatycznie / SMTP / Brevo / tylko
  zapis w dzienniku). Niżej podajesz dane nadawcy i serwera poczty.
4. **Adres webhooka** — opcjonalnie: oprócz maila każda istotna zmiana może trafić
  na Slacka, Discorda lub własny adres.
5. **Zapisz ustawienia** — zapamiętuje zmiany. **Pamiętaj, aby
  kliknąć go po każdej zmianie.**

Na tej stronie znajdziesz jeszcze kilka przydatnych rzeczy:

- **Wyślij test e-mail (operator)** — w ustawieniach instancji wysyła próbny mail na podany
  adres, żebyś sprawdził, czy poczta działa. Najpierw zapisz ustawienia. Webhook ma
  analogiczny przycisk **„Wyślij testowy webhook"**.
- **Operacje (tylko operator instancji)** — pobranie lub przywrócenie kopii SQLite
  w ustawieniach instancji po ponownym uwierzytelnieniu. Przywrócenie zastępuje
  całą bazę, zapisuje kopię bezpieczeństwa i unieważnia sesje. Administrator
  organizacji nie ma tych kontrolek. Surowe logi operator czyta na serwerze;
  aplikacja nie udostępnia ich do pobrania.
- **Preferencje** — zmiana **języka** i **koloru motywu** aplikacji.
- **Marka** — ustaw **nazwę marki**, **logo** i **kolor akcentu** swojej
  organizacji; widzi je cały Twój zespół w aplikacji, a puste pole dziedziczy
  wartość z ustawień instancji. Jeśli jesteś operatorem, ta sama karta ustawia też
  **publiczną stronę startową** — jej hasło, tekst hero i tło, które widzą goście
  przed zalogowaniem.
- **Zmiana hasła**, **uwierzytelnianie dwuskładnikowe (2FA)** (patrz rozdział 8a),
  **zużycie AI** (koszty — wg miesiąca, strony i projektu) oraz panel **„Co trafia
  do AI"** (co system usuwa ze strony przed analizą).

Puste pole zwykle oznacza „użyj wartości domyślnej".

### 8a. Włączanie logowania dwuskładnikowego (2FA)

W sekcji **„Uwierzytelnianie dwuskładnikowe"** kliknij **„Włącz uwierzytelnianie
dwuskładnikowe"**, zeskanuj kod QR aplikacją typu authenticator (lub wpisz klucz
ręcznie), przepisz wygenerowany kod i zatwierdź **„Potwierdź i włącz"**. Zapisz
pokazane **kody zapasowe** — każdy działa raz, gdyby telefon był niedostępny; nie
zobaczysz ich powtórnie.

---

## 9. Organizacje i plany (tylko operator)

Jeśli jesteś operatorem, widzisz w menu **Organizacje**. Domyślna organizacja
to Twoja pierwsza przestrzeń pracy. Kolejne organizacje pozwalają oddzielić
zespoły lub niezależne obszary monitorowania.

1. **Nowa organizacja** — zakłada kolejną przestrzeń pracy.
2. **Plan i zużycie** — na karcie widać etykietę planu (np. `business`) oraz
  liczniki: **Strony X/Y** i **AI/mc X/Y** (sprawdzenia AI w tym miesiącu
  względem limitu).
3. **Edytuj** (ołówek) — tu ustawisz **plan**, **limit stron**, **limit sprawdzeń
  AI/miesiąc** oraz **zawieszenie** (wyłącza dostęp i nowe kontrole, zachowując
  dane). Przycisk **„Zarządzaj"** (obok, na karcie) wchodzi w
  organizację, żeby zarządzać jej projektami i stronami; wracasz przez baner
  „Zarządzasz organizacją…” na górze.

Te limity i zawieszenie zmienia **tylko operator**. Rozliczenia pozostają
opcjonalne i domyślnie wyłączone.

---

## 10. Dostęp i użytkownicy (administrator)

Tu administrator zaprasza użytkowników przez e-mail, nadaje im rolę
(administrator / zwykły użytkownik), włącza/wyłącza konta i nadaje uprawnienia
do projektów lub stron. Zaproszona osoba ustawia własne hasło przez jednorazowy
link. Administrator może unieważnić sesje lub zresetować 2FA po ponownym
uwierzytelnieniu. Odzyskiwanie hasła odbywa się przez **Nie pamiętasz hasła?**
i skonfigurowaną pocztę. Użytkownik widzi dane organizacji, a edytuje tylko
zasoby, do których dostał uprawnienia.

---

## Najczęstsze pytania

- **Nie dostaję maili.** Sprawdź w **Ustawieniach** sekcję e-mail i kliknij „Wyślij
  test". Upewnij się, że odbiorca jest przypisany do strony lub
  projektu i jest aktywny.
- **Dostaję za dużo powiadomień.** W projekcie lub stronie ustaw tryb „tylko
  istotne zmiany” i dopisz w regułach AI, co jest nieważne (np. banery, literówki).
- **Zmieniłem ustawienie i nic się nie dzieje.** Sprawdź, czy kliknąłeś **Zapisz
  ustawienia**.
- **Zmiana ma czerwoną etykietę „Wymaga uwagi".** Otwórz ją i kliknij **Ponów**
  (ponów wysyłkę) lub **Przeanalizuj ponownie** (ponów analizę AI).
- **Jak zmienić język albo się wylogować?** Na dole menu, w lewym dolnym rogu
  (język także w Ustawieniach → Preferencje).
- **Zapomniałem hasła.** Na ekranie logowania kliknij „Nie pamiętasz hasła?”.
