const messages: Record<string, string> = {
  "plans.title": "Szablony uprawnień",
  "plans.subtitle":
    "Definiuj wewnętrzne limity zasobów, które operator może przypisać organizacjom.",
  "plans.loading": "Wczytywanie szablonów uprawnień",
  "plans.newPlan": "Nowy szablon",

  "plans.hold.title": "Kontrola publikacji samoobsługowej",
  "plans.hold.description":
    "Publikuj dopiero po zweryfikowaniu aktywnej ceny dostawcy. Archiwizacja wycofuje plan z nowych zakupów; nie anuluje subskrypcji ani nie zmienia Stripe.",

  "plans.empty.title": "Brak szablonów uprawnień",
  "plans.empty.description": "Utwórz wewnętrzny szablon z jawnymi limitami zasobów.",

  "plans.card.sites": "Strony",
  "plans.card.members": "Użytkownicy",
  "plans.card.aiChecks": "Sprawdzeń AI / mies.",
  "plans.card.unlimited": "Bez limitu",
  "plans.card.auto": "Estymacja referencyjna z modelu kosztowego",
  "plans.card.algorithm": "Model kosztowy: {amount}",
  "plans.card.referenceEstimate": "Wewnętrzna estymacja miesięczna",
  "plans.card.operatorAssigned": "Przypisywany przez operatora",
  "plans.card.selfServePublished": "Publikacja włączona",
  "plans.card.selfServeArchived": "Publikacja wyłączona",
  "plans.card.inactive": "Nieaktywny",
  "plans.editAria": "Edytuj {name}",
  "plans.deleteAria": "Usuń {name}",
  "plans.publish.action": "Opublikuj",
  "plans.archive.action": "Archiwizuj",
  "plans.publish.unavailable": "Przed publikacją zarejestruj aktywną cenę dostawcy.",
  "plans.publish.inactive": "Przed publikacją aktywuj ten szablon uprawnień.",
  "plans.publish.priceUnknown": "Przed publikacją planu odśwież mapowania cen dostawcy.",
  "plans.publish.title": "Opublikować {name} dla nowych zakupów?",
  "plans.publish.description":
    "Plan pojawi się w katalogu samoobsługowym tylko wtedy, gdy globalne bramki rozliczeniowe i prawne będą gotowe. Ta operacja nie tworzy ani nie zmienia ceny w Stripe.",
  "plans.publish.confirmTitle": "Potwierdź publikację planu",
  "plans.publish.confirmDescription":
    "Potwierdź ponownie tożsamość przed udostępnieniem planu {name} dla nowych zakupów samoobsługowych.",
  "plans.publish.success": "Włączono publikację planu",
  "plans.publish.error.notReady":
    "Bramki wdrożeniowe dotyczące rozliczeń, webhooków lub dokumentów prawnych nie są gotowe. Plan nie został opublikowany.",
  "plans.publish.error.action": "Nie udało się zmienić stanu publikacji. Odśwież dane i spróbuj ponownie.",
  "plans.archive.title": "Wycofać {name} z nowych zakupów?",
  "plans.archive.description":
    "Plan zniknie z katalogu samoobsługowego. Istniejące subskrypcje i odpowiadająca im cena w Stripe pozostaną bez zmian.",
  "plans.archive.confirmTitle": "Potwierdź archiwizację planu",
  "plans.archive.confirmDescription":
    "Potwierdź ponownie tożsamość przed wycofaniem planu {name} z nowych zakupów samoobsługowych.",
  "plans.archive.success": "Wyłączono publikację planu",

  // Wersjonowane mapowania cen dostawcy
  "plans.billing.title": "Mapowania cen dostawcy",
  "plans.billing.subtitle":
    "Połącz ceny utworzone w Stripe z niezmiennymi warunkami uprawnień. Nowe mapowanie wycofuje poprzednią lokalną wersję dla tego planu.",
  "plans.billing.new": "Zarejestruj wersję ceny",
  "plans.billing.loading": "Wczytywanie mapowań cen dostawcy",
  "plans.billing.loadError": "Nie udało się wczytać mapowań cen dostawcy.",
  "plans.billing.empty.title": "Brak zarejestrowanych cen dostawcy",
  "plans.billing.empty.description":
    "Najpierw utwórz cenę cykliczną w Stripe, a następnie zarejestruj tutaj jej dokładne warunki.",
  "plans.billing.column.plan": "Plan",
  "plans.billing.column.providerId": "Identyfikator ceny Stripe",
  "plans.billing.column.amount": "Kwota",
  "plans.billing.column.interval": "Cykl rozliczeniowy",
  "plans.billing.column.state": "Stan lokalny",
  "plans.billing.column.created": "Zarejestrowano",
  "plans.billing.version": "Wersja {version}",
  "plans.billing.active": "Aktywne mapowanie",
  "plans.billing.retired": "Wycofane",
  "plans.billing.unknownPlan": "Usunięty plan #{id}",
  "plans.billing.dialog.title": "Zarejestruj cenę Stripe",
  "plans.billing.dialog.description":
    "Ta operacja weryfikuje i zapisuje istniejącą cenę Stripe. Nie tworzy, nie aktualizuje, nie aktywuje ani nie archiwizuje niczego w Stripe.",
  "plans.billing.field.plan": "Plan uprawnień",
  "plans.billing.field.provider": "Dostawca",
  "plans.billing.field.providerPriceId": "Identyfikator ceny Stripe",
  "plans.billing.field.providerPriceIdHint": "Podaj dokładny identyfikator ceny cyklicznej, np. price_123.",
  "plans.billing.field.amount": "Dokładna kwota cykliczna",
  "plans.billing.field.amountHint": "Musi odpowiadać kwocie skonfigurowanej w Stripe.",
  "plans.billing.field.currency": "Waluta",
  "plans.billing.field.interval": "Okres cykliczny",
  "plans.billing.field.intervalCount": "Liczba okresów",
  "plans.billing.interval.day": "Dzień",
  "plans.billing.interval.week": "Tydzień",
  "plans.billing.interval.month": "Miesiąc",
  "plans.billing.interval.year": "Rok",
  "plans.billing.register": "Zweryfikuj i zarejestruj",
  "plans.billing.confirmTitle": "Potwierdź mapowanie ceny dostawcy",
  "plans.billing.confirmDescription":
    "Potwierdź ponownie tożsamość przed weryfikacją ceny Stripe i aktywowaniem nowej lokalnej wersji mapowania. Każda obecna lokalna wersja zostanie wycofana.",
  "plans.billing.created": "Zarejestrowano wersję ceny dostawcy",
  "plans.billing.error.conflict":
    "Cena nie została zarejestrowana. Sprawdź, czy cena i produkt Stripe są aktywne, identyfikator jest unikalny, a kwota, waluta i cykl są dokładnie zgodne.",
  "plans.billing.error.provider":
    "Nie udało się teraz zweryfikować Stripe. Lokalna wersja ceny nie została utworzona.",
  "plans.billing.error.stalePlan":
    "Wybrany plan uprawnień już nie istnieje. Zamknij to okno, odśwież dane i wybierz inny plan.",
  "plans.billing.error.action": "Nie udało się zarejestrować wersji ceny dostawcy.",

  // Wewnętrzny model kosztowy
  "plans.pricing.title": "Wewnętrzny model kosztowy",
  "plans.pricing.subtitle":
    "Wyłącznie do planowania. Te wartości nie obciążają klienta i nie aktywują uprawnień.",
  "plans.pricing.baseFee": "Referencyjna kwota bazowa",
  "plans.pricing.perSiteFee": "Referencyjna kwota za stronę",
  "plans.pricing.aiMargin": "Mnożnik kosztu AI",
  "plans.pricing.aiMarginHint":
    "Mnożnik surowego kosztu OpenAI używany wyłącznie do wewnętrznego planowania.",
  "plans.pricing.currency": "Waluta",
  "plans.pricing.save": "Zapisz model kosztowy",
  "plans.pricing.saved": "Zapisano model kosztowy",
  "plans.pricing.confirmTitle": "Potwierdź zmianę modelu kosztowego",
  "plans.pricing.confirmDescription":
    "Potwierdź ponownie tożsamość przed zmianą ogólnych wartości referencyjnych używanych do wewnętrznych estymacji cen.",
  "plans.pricing.derived":
    "Dla {model} jedno sprawdzenie AI kosztuje ok. {cost} — z rzeczywistej średniej {prompt} + {completion} tokenów.",

  // Okno tworzenia / edycji
  "plans.create.title": "Nowy szablon uprawnień",
  "plans.edit.title": "Edytuj szablon uprawnień",
  "plans.field.name": "Nazwa",
  "plans.field.key": "Klucz",
  "plans.field.keyHint": "Krótki identyfikator małymi literami, np. starter.",
  "plans.field.maxSites": "Limit stron",
  "plans.field.maxMembers": "Limit użytkowników",
  "plans.field.aiLimit": "Sprawdzeń AI / miesiąc",
  "plans.field.limitHint": "Puste pole = bez limitu.",
  "plans.field.price": "Referencyjna estymacja miesięczna",
  "plans.field.priceHint":
    "Wyłącznie do planowania. Puste pole użyje estymacji modelu kosztowego {amount}.",
  "plans.field.priceHintPlain":
    "Wyłącznie do planowania. Puste pole użyje estymacji modelu kosztowego.",
  "plans.field.active": "Aktywny",
  "plans.field.activeHint": "Nieaktywnych szablonów nie przypiszesz nowym organizacjom.",
  "plans.field.useSuggestion": "Użyj estymacji {amount}",
  "plans.save": "Zapisz szablon",
  "plans.change.confirmTitle": "Potwierdź zmianę szablonu uprawnień",
  "plans.change.confirmDescription":
    "Potwierdź ponownie tożsamość przed zmianą szablonów sterujących limitami zasobów klientów.",
  "plans.created": "Utworzono szablon uprawnień",
  "plans.updated": "Zaktualizowano szablon uprawnień",
  "plans.deleted": "Usunięto szablon uprawnień",

  "plans.delete.title": "Usunąć ten szablon uprawnień?",
  "plans.delete.description":
    "{name} zostanie usunięty. Szablon z historią rozliczeń trzeba zarchiwizować; przypisane organizacje zachowają swoje limity.",
  "plans.delete.submit": "Usuń szablon",
  "plans.delete.confirmTitle": "Potwierdź usunięcie szablonu",
  "plans.delete.confirmDescription":
    "Potwierdź ponownie tożsamość przed usunięciem {name}. Opublikowanego szablonu nie można usunąć i trzeba go zarchiwizować.",

  // Publiczna strona dostępności
  "plans.public.eyebrow": "Dostępność",
  "plans.public.setupEyebrow": "Własna instalacja",
  "plans.public.setupTitle": "Ty zarządzasz swoją przestrzenią monitorowania",
  "plans.public.setupSubtitle": "Uruchom Driftwatch na swoim komputerze lub serwerze. Utwórz konto administratora, skonfiguruj monitoring i zaproś swój zespół.",
  "plans.public.setupStatusTitle": "Pierwsze konto zarządza tą instalacją",
  "plans.public.setupNote": "Zapewniasz hosting i wybierasz opcjonalne usługi powiadomień lub AI. Ich koszty zależą od Twoich dostawców i ustawień.",
  "plans.public.title": "Płatne plany nie są dostępne w trybie samoobsługowym",
  "plans.public.subtitle":
    "Driftwatch nie przyjmuje obecnie płatności ani nie aktywuje płatnego dostępu podczas publicznej rejestracji.",
  "plans.public.cta": "Utwórz ograniczoną przestrzeń",
  "plans.public.closedTitle": "Dostęp do przestrzeni jest obecnie tylko na zaproszenie",
  "plans.public.closedSubtitle":
    "Publiczne tworzenie kont jest wyłączone. Zaloguj się na istniejące konto lub skontaktuj się z operatorem swojej przestrzeni.",
  "plans.public.closedStatusTitle": "Wdrożenie zarządzane przez operatora",
  "plans.public.closedStatusBody":
    "Nowe przestrzenie i konta administratorów są tworzone świadomie, a nie przez anonimowy formularz.",
  "plans.public.closedManualNote":
    "Publiczna rejestracja pozostaje zamknięta do czasu uruchomienia weryfikacji, zgód prawnych i rozliczeń.",
  "plans.public.statusTitle": "Ograniczony bezpłatny dostęp, nie płatny plan",
  "plans.public.statusBody":
    "Każda publiczna rejestracja otrzymuje taką samą ograniczoną przestrzeń. Nazwa planu ani parametr URL nie zwiększą jej zasobów.",
  "plans.public.manualNote":
    "Dodatkowy dostęp nie jest dostępny samoobsługowo i wymaga decyzji operatora.",
  "plans.public.defaultSites": "Limit monitorowanych stron",
  "plans.public.defaultMembers": "Limit użytkowników zespołu",
  "plans.public.defaultAi": "Miesięczny limit sprawdzeń AI",
  "plans.public.backHome": "Powrót na stronę główną",
};
export default messages;
