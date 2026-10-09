const messages: Record<string, string> = {
  "settings.security.confirmTitle": "Autoryzuj chronione zmiany",
  "settings.security.confirmDescription":
    "Potwierdź ponownie tożsamość przed zmianą tras wysyłki, danych logowania lub prywatnego adresu integracji.",
  "settings.security.confirmSubmit": "Zapisz chronione ustawienia",
  "settings.security.removeStored": "Usuń zapisane dane logowania",
  "settings.security.removePending": "Te dane zostaną usunięte po zapisaniu.",
  "settings.security.undoRemove": "Cofnij",
  // Page header
  "settings.title": "Ustawienia",
  "settings.subtitle": "Twoje preferencje i konto — oraz konfiguracja przestrzeni roboczej dla administratorów.",
  "settings.loading": "Ładowanie ustawień",
  "settings.saved": "Zapisano",

  // Etykiety grup sekcji
  "settings.group.account": "Twoje konto",
  "settings.group.data": "Zużycie i operacje",

  // Admin gate
  "settings.adminOnly":
    "Tylko administratorzy mogą zmieniać konfigurację przestrzeni roboczej. Poniżej nadal możesz zmienić swoje hasło.",

  // AI analysis card
  "settings.ai.title": "Analiza AI",
  "settings.ai.apiKey": "Klucz API OpenAI",
  "settings.ai.model": "Model",
  "settings.ai.defaultNotifications": "Domyślne powiadomienia",
  "settings.ai.modeOnlySignificant": "Tylko istotne zmiany",
  "settings.ai.modeAlways": "Każda zmiana",
  "settings.ai.importanceRules": "Globalne reguły istotności",
  "settings.ai.importanceRulesHint":
    "Wskazówki w języku naturalnym do oceny istotności zmian.",
  "settings.ai.importanceRulesPlaceholder":
    "Traktuj zmiany cen, dostępności i regulaminów jako istotne.",
  "settings.ai.responseFormat": "Format odpowiedzi AI (zaawansowane)",
  "settings.ai.responseFormatHint":
    "Pozostaw puste, aby użyć wbudowanego szablonu. Edytuj tylko po to, by przebudować strukturę kontraktu JSON dla AI.",

  // Email delivery card
  "settings.email.title": "Dostarczanie e-maili",
  "settings.email.provider": "Dostawca e-mail",
  "settings.email.providerAuto": "Wykryj automatycznie",
  "settings.email.providerBrevo": "Brevo",
  "settings.email.providerSmtp": "SMTP",
  "settings.email.providerLog": "Tylko dziennik",
  "settings.email.language": "Język e-maili",
  "settings.email.languageHint":
    "Język powiadomień i e-maili resetu hasła wysyłanych do odbiorców tej organizacji",
  "settings.email.languageDefault": "Domyślny (angielski)",
  "settings.email.fromEmail": "Adres nadawcy",
  "settings.email.fromName": "Nazwa nadawcy",
  "settings.email.subjectTemplate": "Szablon tematu e-maila",
  "settings.email.subjectTemplateHint": "Pola: {site}, {headline}, {severity}",
  "settings.email.subjectTemplatePlaceholder": "Zmiana na {site} — {headline}",
  "settings.email.intro": "Wstęp e-maila",
  "settings.email.introHint": "Opcjonalny wiersz wstępu dołączany do każdego powiadomienia",
  "settings.email.smtpHost": "Host SMTP",
  "settings.email.smtpPort": "Port SMTP",
  "settings.email.smtpSecurity": "Zabezpieczenie SMTP",
  "settings.email.securityStarttls": "STARTTLS",
  "settings.email.securitySsl": "SSL",
  "settings.email.securityNone": "Brak",
  "settings.email.smtpUsername": "Nazwa użytkownika SMTP",
  "settings.email.smtpPassword": "Hasło SMTP",
  "settings.email.brevoApiKey": "Klucz API Brevo",
  "settings.email.brevoApiKeyHint": "Używany, gdy SMTP nie jest skonfigurowany.",
  "settings.email.downThreshold": "Próg alertu niedostępności",
  "settings.email.downThresholdHint":
    "Liczba nieudanych sprawdzeń z rzędu, po której wysyłany jest mocniejszy alert o niedostępności strony (domyślnie 5).",
  "settings.email.technicalRecipients": "Odbiorcy alertów technicznych",
  "settings.email.technicalRecipientsHint":
    "Kto jest powiadamiany, gdy przechwytywanie lub dostarczanie ulegnie awarii.",
  "settings.email.noRecipients": "Brak odbiorców.",
  "settings.email.test": "Wyślij testowy e-mail",
  "settings.email.testHint":
    "Wysyła jedną wiadomość przy użyciu zapisanych ustawień powyżej. Najpierw zapisz.",
  "settings.email.testSend": "Wyślij test",
  "settings.email.testOk": "Wysłano przez {channel}.",
  "settings.email.testFail": "Nie udało się wysłać: {detail}",

  // Powiadomienia webhook
  "settings.webhook.title": "Powiadomienia webhook",
  "settings.webhook.url": "Adres webhooka",
  "settings.webhook.urlHint":
    "Wywoływany przy każdej istotnej zmianie. Adres webhooka Slacka/Discorda albo własny endpoint. Przechowywany zaszyfrowany.",
  "settings.webhook.format": "Format ładunku",
  "settings.webhook.formatGeneric": "Generyczny JSON",
  "settings.webhook.formatSlack": "Slack",
  "settings.webhook.formatDiscord": "Discord",
  "settings.webhook.test": "Wyślij testowy webhook",
  "settings.webhook.testOk": "Webhook dostarczony.",
  "settings.webhook.testFail": "Nie udało się dostarczyć: {detail}",

  // Capture & cost card
  "settings.capture.title": "Przechwytywanie i koszty",
  "settings.capture.timeout": "Limit czasu przechwytywania (sekundy)",
  "settings.capture.settle": "Opóźnienie stabilizacji (ms)",
  "settings.capture.minInterval": "Minimalny odstęp (sekundy)",
  "settings.capture.minIntervalHint": "Grzecznościowe opóźnienie między sprawdzeniami strony",
  "settings.capture.jitter": "Rozrzut (ms)",
  "settings.capture.jitterHint": "Losowe dodatkowe opóźnienie",
  "settings.capture.retention": "Przechowywanie migawek",
  "settings.capture.retentionHint": "Ile migawek przechowywać dla każdej strony.",
  "settings.capture.inputPrice": "Cena wejścia (za 1 mln tokenów)",
  "settings.capture.outputPrice": "Cena wyjścia (za 1 mln tokenów)",
  "settings.capture.priceScope": "Szacunek obejmuje zapisane odpowiedzi po standardowej cenie tokenów. Rabaty dostawcy i niezapisane błędne odpowiedzi są pomijane.",

  // Capture filters card
  "settings.filters.title": "Filtry przechwytywania",
  "settings.filters.watchDocuments": "Obserwuj podlinkowane dokumenty",
  "settings.filters.watchDocumentsHint":
    "Sprawdzaj też podlinkowane pliki (PDF, Word, Excel) pod kątem podmiany pod tym samym adresem — do 20 dokumentów na stronę, weryfikowane lekkimi żądaniami HEAD.",
  "settings.filters.ignoreSelectors": "Ignorowane selektory",
  "settings.filters.ignoreSelectorsHint":
    "Jeden w wierszu. Te obszary pomijamy przy szukaniu zmian.",

  "settings.restoreDefault": "Przywróć domyślne",

  "settings.filtering.title": "Co trafia do AI",
  "settings.filtering.intro":
    "Zanim cokolwiek zostanie porównane lub wysłane do modelu, każda strona jest sprowadzana do istotnej treści — analizowana jest tylko różnica, nigdy cała strona.",
  "settings.filtering.strippedTags": "Zawsze usuwane",
  "settings.filtering.strippedTagsHint":
    "Te elementy nigdy nie niosą monitorowanej treści i są usuwane z każdej strony.",
  "settings.filtering.volatile": "Zastępowane symbolem zastępczym",
  "settings.filtering.volatileHint":
    "Wartości pasujące do tych wzorców zmieniają się przy każdym wczytaniu, więc są neutralizowane przed porównaniem.",
  "settings.filtering.response": "Odpowiedź modelu",
  "settings.filtering.responseHint":
    "Model zawsze musi zwrócić dokładnie te pola; prompt powyżej kształtuje ich treść.",

  // Save button
  "settings.save": "Zapisz ustawienia",

  // Change password card
  "settings.password.title": "Zmień hasło",
  "settings.password.current": "Bieżące hasło",
  "settings.password.new": "Nowe hasło",
  "settings.password.newHint": "Co najmniej 8 znaków",
  "settings.password.confirm": "Potwierdź nowe hasło",
  "settings.password.mismatch": "Hasła nie są zgodne.",
  "settings.password.submit": "Zaktualizuj hasło",
  "settings.password.changed": "Hasło zmienione",

  // Operations card
  "settings.ops.title": "Operacje",
  "settings.ops.openAudit": "Otwórz dziennik audytu",
  "settings.ops.detectingCapabilities": "Sprawdzanie możliwości wdrożenia…",
  "settings.ops.capabilitiesUnavailable":
    "Nie udało się odczytać możliwości operacyjnych wdrożenia.",
  "settings.ops.providerManagedBackup":
    "To wdrożenie korzysta z zarządzanej bazy danych. Kopie i odtwarzanie wykonuje się w warstwie infrastruktury zgodnie z runbookiem DR.",
  "settings.scope.instance":
    "Edytujesz domyślne ustawienia instancji. Każda organizacja je dziedziczy, dopóki nie ustawi własnych.",
  "settings.scope.org":
    "Edytujesz ustawienia tej organizacji. Wyczyść pole, aby wrócić do domyślnej wartości instancji.",
  "settings.ops.downloadBackup": "Pobierz kopię zapasową",
  "settings.ops.backupConfirm":
    "Kopia zapasowa zawiera skróty haseł i sekrety. Potwierdź swoją tożsamość, aby ją pobrać.",
  "settings.ops.restore": "Przywróć kopię zapasową",
  "settings.ops.restoreConfirm":
    "Przywrócenie zastąpi wszystkie obecne dane wgraną kopią. Potwierdź tożsamość, aby kontynuować.",
  "settings.ops.restorePick":
    "Wybierz plik kopii zapasowej Driftwatch. Obecna baza zostanie najpierw zapisana jako kopia bezpieczeństwa z sygnaturą czasu.",
  "settings.ops.restoreSubmit": "Zastąp bazę danych",
  "settings.ops.restoreDone": "Baza przywrócona. Zaloguj się ponownie.",

  // AI usage card
  "settings.usage.title": "Zużycie AI",
  "settings.usage.totalCost": "Koszt całkowity",
  "settings.usage.tokens": "Tokeny",
  "settings.usage.calls": "Wywołania",
  "settings.usage.byMonth": "Wg miesiąca",
  "settings.usage.bySite": "Wg strony",
  "settings.usage.byProject": "Wg projektu",
  "settings.usage.callsSuffix": "wywołań",
  "settings.usage.tokensSuffix": "tokenów",
  "settings.usage.unavailable": "Dane o zużyciu są niedostępne.",

  // Branding card
  "settings.branding.title": "Marka",
  "settings.branding.name": "Nazwa marki",
  "settings.branding.nameHint": "Widoczna w nagłówku, stopce i tytule karty. Domyślnie Driftwatch.",
  "settings.branding.accent": "Kolor akcentu",
  "settings.branding.accentHint":
    "Przebarwia przyciski, wyróżnienia i logo. Zostaw puste, aby użyć domyślnego.",
  "settings.branding.logo": "Obraz logo",
  "settings.branding.logoHint":
    "Prześlij PNG lub JPEG do 2 MB. Bez obrazu używany jest wbudowany znak.",
  "settings.branding.landingHeading": "Publiczna strona startowa",
  "settings.branding.landingNote":
    "Tylko operator — kształtują publiczną stronę startową, którą widzi każdy przed zalogowaniem.",
  "settings.branding.tagline": "Hasło",
  "settings.branding.heroTitle": "Nagłówek główny",
  "settings.branding.heroSubtitle": "Podtytuł główny",
  "settings.branding.heroBackground": "Obraz tła sekcji głównej",
  "settings.branding.heroBackgroundHint":
    "Prześlij PNG lub JPEG do 8 MB. Obraz jest przyciemniany, aby tekst pozostał czytelny.",
  "settings.branding.upload": "Prześlij obraz",
  "settings.branding.replace": "Zastąp obraz",
  "settings.branding.remove": "Usuń obraz",
  "settings.branding.assetSaved": "Obraz marki zaktualizowany",
  "settings.branding.assetRemoved": "Obraz marki usunięty",

  // Toasts
  "settings.toast.saved": "Ustawienia zapisane",
};
export default messages;
