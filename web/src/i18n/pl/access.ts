const messages: Record<string, string> = {
  "access.title": "Dostęp",
  "access.subtitle":
    "Zarządzaj tym, kto może się logować oraz które projekty i strony są dla niego widoczne.",
  "access.loading": "Wczytywanie dostępu",
  "access.addUser": "Dodaj użytkownika",

  "access.adminRequired.title": "Wymagany dostęp administratora",
  "access.adminRequired.description":
    "Tylko administratorzy mogą zarządzać dostępem do tej przestrzeni roboczej.",

  "access.instance.subtitle": "Granica tożsamości na poziomie instancji",
  "access.instance.title": "Tożsamości operatorów są zarządzane podczas wdrożenia",
  "access.instance.description":
    "Konta operatorów są nadawane w kontrolowanej procedurze wdrożeniowej, a nie na stronie dostępu tenanta. Wejdź do organizacji, aby zarządzać jej użytkownikami.",
  "access.instance.action": "Otwórz organizacje",

  "access.operators.title": "Tożsamości operatorów",
  "access.operators.subtitle":
    "Zarządzaj małą grupą kont, które mogą obsługiwać całą instancję. Użytkownicy tenantów pozostają odseparowani w swoich organizacjach.",
  "access.operators.loading": "Wczytywanie tożsamości operatorów",
  "access.operators.add": "Dodaj operatora",
  "access.operators.empty.title": "Brak tożsamości operatorów",
  "access.operators.empty.description":
    "Przed uruchomieniem produkcyjnym utwórz operatora odzyskiwania dostępu.",
  "access.operators.self": "Ty",
  "access.operators.state.active": "Aktywny",
  "access.operators.state.inactive": "Nieaktywny",
  "access.operators.mfa.active": "2FA aktywne",
  "access.operators.mfa.pending": "2FA nieskonfigurowane",
  "access.operators.firstLoginPending": "Oczekuje na pierwsze logowanie",
  "access.operators.lastLogin": "Ostatnie logowanie: {date}",
  "access.operators.invite": "Wyślij link konfiguracji",
  "access.operators.deactivate": "Dezaktywuj",
  "access.operators.reactivate": "Aktywuj ponownie",
  "access.operators.create.title": "Dodaj operatora",
  "access.operators.create.description":
    "To konto będzie mogło obsługiwać każdą organizację. Jednorazowy link ustawienia hasła trafi do kolejki.",
  "access.operators.create.submit": "Utwórz operatora",
  "access.operators.edit.title": "Edytuj operatora",
  "access.operators.edit.submit": "Zapisz operatora",
  "access.operators.confirm.createTitle": "Potwierdź utworzenie operatora",
  "access.operators.confirm.createDescription":
    "Utworzenie operatora instancji przyznaje najwyższy poziom uprawnień aplikacji.",
  "access.operators.confirm.editTitle": "Potwierdź zmiany operatora",
  "access.operators.confirm.editDescription":
    "Zmiana konta {email} dotyczy tożsamości na poziomie całej instancji.",
  "access.operators.confirm.inviteTitle": "Dodać nowy link konfiguracji do kolejki?",
  "access.operators.confirm.inviteDescription":
    "Nowy jednorazowy link ustawienia hasła dla {email} trafi do kolejki.",
  "access.operators.confirm.deactivateTitle": "Dezaktywować tego operatora?",
  "access.operators.confirm.deactivateDescription":
    "{email} natychmiast utraci dostęp, a wszystkie istniejące sesje zostaną cofnięte.",
  "access.operators.confirm.reactivateTitle": "Aktywować tego operatora ponownie?",
  "access.operators.confirm.reactivateDescription":
    "{email} odzyska dostęp do instancji i będzie podlegać aktualnej polityce 2FA.",
  "access.operators.toast.created": "Operator utworzony; link konfiguracji trafił do kolejki",
  "access.operators.toast.updated": "Operator zaktualizowany",
  "access.operators.toast.inviteQueued": "Link konfiguracji trafił do kolejki",
  "access.operators.toast.deactivated": "Operator dezaktywowany",
  "access.operators.toast.reactivated": "Operator aktywowany ponownie",
  "access.operators.error": "Nie udało się zaktualizować operatora",

  "access.empty.title": "Brak użytkowników",
  "access.empty.description":
    "Dodaj członka zespołu, aby mógł zalogować się do Driftwatch.",

  "access.role.superadmin": "Operator",
  "access.role.admin": "Administrator",
  "access.role.member": "Użytkownik",
  "access.state.active": "Aktywny",
  "access.state.inactive": "Nieaktywny",

  "access.editAria": "Edytuj użytkownika {email}",
  "access.userUpdated": "Użytkownik zaktualizowany",
  "access.editError": "Nie udało się zapisać zmian",
  "access.edit.title": "Edytuj użytkownika",
  "access.edit.submit": "Zapisz zmiany",
  "access.field.activeUser": "Aktywny",
  "access.field.activeUserHint": "Nieaktywni użytkownicy nie mogą się logować.",
  "access.deleteAria": "Usuń użytkownika {email}",

  "access.userAdded": "Zaplanowano wysyłkę zaproszenia",
  "access.userRemoved": "Użytkownik usunięty",

  "access.create.title": "Dodaj użytkownika",
  "access.create.description":
    "Wyślemy bezpieczny link, pod którym użytkownik ustawi własne hasło. Link jest ważny przez 24 godziny.",
  "access.field.email": "Adres e-mail",
  "access.field.emailPlaceholder": "wspolpracownik@firma.com",
  "access.field.name": "Imię i nazwisko",
  "access.field.nameHint": "Opcjonalne",
  "access.field.namePlaceholder": "Jan Kowalski",
  "access.field.administrator": "Administrator",
  "access.field.administratorHint":
    "Administratorzy mają pełny dostęp i mogą zarządzać innymi użytkownikami.",
  "access.create.submit": "Wyślij zaproszenie",

  "access.field.projects": "Projekty",
  "access.field.sites": "Strony",
  "access.noProjects": "Brak projektów.",
  "access.noSites": "Brak stron.",

  "access.delete.title": "Usunąć tego użytkownika?",
  "access.delete.description": "Użytkownik {email} natychmiast utraci dostęp.",
  "access.delete.submit": "Usuń użytkownika",
  "access.stepup.createTitle": "Potwierdź zaproszenie do konta",
  "access.stepup.createDescription":
    "Utworzenie konta przyznaje dostęp do danych przestrzeni roboczej. Potwierdź operację obecnym hasłem.",
  "access.stepup.editTitle": "Potwierdź wrażliwe zmiany konta",
    "access.stepup.editDescription":
      "Zmiana tożsamości, roli, statusu lub uprawnień wymaga ponownego uwierzytelnienia.",
    "access.security.title": "Bezpieczeństwo konta",
    "access.security.description":
      "Działania na wypadek utraty urządzenia lub podejrzenia ujawnienia sesji.",
    "access.security.sendInvitation": "Wyślij link do hasła",
    "access.security.sendInvitationTitle": "Wysłać nowy link do hasła?",
    "access.security.sendInvitationDescription":
      "Wyślemy na adres {email} jednorazowy link ważny przez 24 godziny.",
    "access.security.invitationSent": "Zaplanowano wysyłkę linku do hasła",
    "access.security.revokeSessions": "Cofnij sesje",
    "access.security.revokeSessionsTitle": "Cofnąć wszystkie sesje?",
    "access.security.revokeSessionsDescription":
      "{email} zostanie wylogowany na wszystkich urządzeniach i będzie musiał zalogować się ponownie.",
    "access.security.sessionsRevokedDone": "Wszystkie sesje zostały cofnięte",
    "access.security.resetTotp": "Zresetuj 2FA",
    "access.security.resetTotpTitle": "Zresetować uwierzytelnianie dwuskładnikowe?",
    "access.security.resetTotpDescription":
      "{email} utraci obecny token i kody odzyskiwania oraz zostanie wylogowany na wszystkich urządzeniach.",
    "access.security.totpResetDone": "Uwierzytelnianie dwuskładnikowe zostało zresetowane",
  };
export default messages;
