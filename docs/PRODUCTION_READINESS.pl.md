# Weryfikacja konkretnego wdrożenia

Ten dokument jest szablonem kontroli operatora. Nie nadaje aplikacji oceny,
certyfikatu ani statusu zgodności. Uzupełnij wersję źródeł, digest obrazu,
środowisko, datę i odnośnik do rzeczywistego wyniku każdej kontroli.

## Kontrole techniczne

| Kontrola | Dowód wymagany w danym środowisku |
|---|---|
| Powtarzalny build | instalacja z hash locków, build SPA i obrazy z tej samej wersji |
| Sekrety | zredagowany skan wszystkich refów i plików publikacji; osobne klucze |
| Zależności | aktualny pip-audit, npm audit oraz skan obrazów |
| Monitor | własna strona: baseline, zmiana, błąd HTTP, powrót do działania |
| Przeglądarka | osobny worker bez kluczy aplikacji, rootfs read-only, cap-drop ALL |
| Sieć | rzeczywisty socket test blokujący prywatne, CGNAT, loopback i metadata |
| Konta | atomowy pierwszy administrator, dalszy signup zamknięty, MFA, step-up, grant obcej organizacji |
| Izolacja | brak odczytu/zapisu danych drugiej organizacji przez użytkownika |
| Restart | odzyskanie dzierżawy bez starego zapisu i nieograniczonych prób |
| Powiadomienia | konfiguracja, retry i przegląd niejednoznacznej akceptacji |
| Backup | odtworzenie odrębnej instancji z kluczami i testem izolacji |
| Obserwowalność | JSON readiness, Operations, miejsce na dysku i wiek kolejki |

Przejście CI dotyczy sprawdzonego kodu i kontrolowanych fixture. Nie potwierdza
poprawności usług zewnętrznych, backupów ani topologii innego hostingu.
Obecna konfiguracja referencyjna ma jeden proces API/schedulera. Limity logowania
są lokalne dla procesu; wiele replik wymaga dodatkowego wspólnego budżetu.

## Moduły opcjonalne

AI i płatności nie są wymagane do monitoringu. AI disabled + Every change pozwala
sprawdzić główny przepływ bez klucza OpenAI. Włączanie AI wymaga świadomego
ustalenia reguł, limitu kosztów, danych wysyłanych do dostawcy i obsługi błędów.
Nieznany cennik modelu pozostaje nieznany, nie jest kosztem zero.

Publiczne płatności i dalsza rejestracja są wyłączone w ustawieniach startowych.
Jednorazowe utworzenie pierwszego administratora jest odrębnym procesem;
zakończ je przed publicznym wystawieniem instancji. Administrator własnej
organizacji pracuje przez swoje członkostwo, bez grantu supportowego.
Włączenie ich wymaga pełnej konfiguracji dostawcy i rzeczywistego procesu obsługi
klienta oraz dokumentów właściwych dla operatora. Sam przełącznik w aplikacji
nie potwierdza tych warunków.

Instrukcje: [instalacja](INSTALL.md), [wdrożenie](DEPLOY.md),
[recovery](RECOVERY.md), [security](../SECURITY.md), [FAQ](FAQ.md).
