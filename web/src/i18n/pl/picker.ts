const messages: Record<string, string> = {
  "picker.actionClick": "Kliknij",
  "picker.actionFill": "Wypełnij",
  "picker.actionWaitFor": "Czekaj na",
  "picker.actionWait": "Czekaj",
  "picker.action": "Akcja",
  "picker.selector": "Element",
  "picker.value": "Wartość",
  "picker.milliseconds": "Milisekundy",
  "picker.removeStep": "Usuń krok",
  "picker.addStep": "Dodaj krok",
  "picker.pickVisually": "Wybierz wizualnie",
  "picker.recordSteps": "Nagraj kroki",
  "picker.couldNotStart": "Nie udało się uruchomić selektora",
  "picker.selectionCancelled": "Anulowano wybór",
  "picker.timedOut": "Upłynął limit czasu selektora",
  "picker.failed": "Selektor zakończył się błędem",
  "picker.selectorCaptured": "Zapisano zaznaczenie",
  "picker.stepsRecorded": "Nagrano kroki",
  "picker.openedIn": "Otwarto w {channel}",
  "picker.instructionsSelect":
    "Na serwerze otwarto okno przeglądarki. Przełącz się na nie, kliknij obszar(y) do monitorowania, a następnie naciśnij Zapisz w tym oknie.",
  "picker.instructionsRecord":
    "Na serwerze otwarto okno przeglądarki. Przełącz się na nie, nagraj swoje kliknięcia, a następnie naciśnij Zapisz w tym oknie.",
  "picker.starting": "Uruchamianie selektora…",
  "picker.waitingSelected": "Oczekiwanie na zapis — wybrano: {count}",
  "picker.waitingRecorded": "Oczekiwanie na zapis — nagrano: {count}",

  "picker.dialogLead": "Na serwerze monitorującym właśnie otwarto prawdziwe okno przeglądarki.",
  "picker.saveInWindow":
    "Gdy skończysz, kliknij Zapisz w tym oknie — ten panel zaktualizuje się automatycznie.",
  "picker.closePicker": "Zamknij selektor",
  "picker.selectNothingYet": "Nie wybrano jeszcze obszaru — kliknij element w oknie przeglądarki.",
  "picker.recordNothingYet": "Brak kroków — zacznij klikać w oknie przeglądarki.",
  "picker.useManualInstead": "Możesz też wprowadzić to ręcznie w sekcji zaawansowanej poniżej.",

  "picker.pick.title": "Wybierz obszar do monitorowania",
  "picker.pick.explainer":
    "Otwórz stronę i kliknij fragment, który chcesz śledzić. Reszta jest pomijana.",
  "picker.pick.action": "Otwórz selektor wizualny",
  "picker.pick.selected": "Monitorowane: {selector}",
  "picker.pick.selectedLabel": "Wybrany obszar",
  "picker.pick.watchingWhole": "Monitorowanie całej strony.",
  "picker.pick.clear": "Wyczyść",
  "picker.pick.advanced": "Zaawansowane — wpisz selektor CSS ręcznie",

  "picker.record.title": "Nagraj kroki interakcji",
  "picker.record.explainer":
    "Przejdź przez stronę — zaloguj się, zamknij baner, otwórz kartę — a odtworzymy to przed każdym sprawdzeniem.",
  "picker.record.action": "Nagraj kroki",
  "picker.record.clear": "Wyczyść kroki",
  "picker.record.advanced": "Zaawansowane — ręcznie edytuj kroki i reguły pomijania",
  "picker.record.count.one": "Nagrano {count} krok",
  "picker.record.count.few": "Nagrano {count} kroki",
  "picker.record.count.many": "Nagrano {count} kroków",
};
export default messages;
