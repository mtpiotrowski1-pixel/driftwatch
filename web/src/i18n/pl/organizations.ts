const messages: Record<string, string> = {
  "organizations.title": "Organizacje",
  "organizations.subtitle":
    "Każda organizacja to odrębna przestrzeń robocza z własnymi projektami, stronami i odbiorcami.",
  "organizations.loading": "Wczytywanie organizacji",
  "organizations.newOrganization": "Nowa organizacja",

  "organizations.superadminRequired.title": "Wymagany dostęp operatora",
  "organizations.superadminRequired.description":
    "Tylko operator instancji może tworzyć organizacje i nimi zarządzać.",

  "organizations.empty.title": "Brak organizacji",
  "organizations.empty.description":
    "Utwórz organizację, aby przechowywać projekty, strony i odbiorców klienta.",

  "organizations.memberCount.one": "{count} użytkownik",
  "organizations.memberCount.few": "{count} użytkowników",
  "organizations.memberCount.many": "{count} użytkowników",
  "organizations.siteCount.one": "{count} strona",
  "organizations.siteCount.few": "{count} strony",
  "organizations.siteCount.many": "{count} stron",

  "organizations.state.active": "Aktywna",
  "organizations.state.inactive": "Nieaktywna",
  "organizations.state.suspended": "Zawieszona",
  "organizations.usage.sites": "Strony {used}/{limit}",
  "organizations.usage.members": "Użytkownicy {used}/{limit}",
  "organizations.usage.ai": "AI/mc {used}/{limit}",
  "organizations.billing.managed": "Sterowana przez billing",
  "organizations.billing.suspended": "Zawieszona przez billing",
  "organizations.billing.managedHint":
    "Planem i limitami zarządza operator płatności. Zmień subskrypcję w narzędziach billingowych.",
  "organizations.billing.suspendedHint":
    "Dostęp może przywrócić wyłącznie aktualne zdarzenie subskrypcji od operatora płatności.",
  "organizations.yours": "Twoja organizacja",

  "organizations.enter": "Zarządzaj",
  "organizations.managing": "Zarządzasz organizacją {name} — dodawane projekty, strony i osoby należą do niej",
  "organizations.exit": "Wyjdź z organizacji",

  "organizations.created": "Organizacja utworzona",
  "organizations.updated": "Organizacja zaktualizowana",

  "organizations.field.name": "Nazwa",
  "organizations.field.active": "Aktywna",
  "organizations.field.activeHint":
    "Zawieszenie blokuje użytkowników, ale zachowuje dane klienta, audyt i historię rozliczeń.",
  "organizations.field.plan": "Plan",
  "organizations.field.planHint": "Etykieta planu rozliczeniowego, np. free, starter, business.",
  "organizations.field.maxSites": "Limit stron",
  "organizations.field.maxMembers": "Limit użytkowników",
  "organizations.field.aiLimit": "Sprawdzenia AI / miesiąc",
  "organizations.field.limitHint": "Puste = bez limitu.",
  "organizations.field.planSelect": "Plan (z katalogu)",
  "organizations.field.planSelectHint": "Przypisanie planu wypełni limity poniżej; nadal możesz je nadpisać.",
  "organizations.field.noPlan": "Bez planu (limity ręcznie)",

  "organizations.create.title": "Nowa organizacja",
  "organizations.create.description":
    "Dodawane projekty, strony i odbiorcy będą należeć do tej organizacji.",
  "organizations.create.namePlaceholder": "Acme Sp. z o.o.",
  "organizations.create.submit": "Utwórz organizację",
  "organizations.create.confirmTitle": "Potwierdź utworzenie organizacji",
  "organizations.create.confirmDescription":
    "Potwierdź ponownie tożsamość przed utworzeniem nowej, odizolowanej przestrzeni klienta.",

  "organizations.edit.title": "Edytuj organizację",
  "organizations.edit.submit": "Zapisz zmiany",
  "organizations.edit.confirmTitle": "Potwierdź zmianę uprawnień",
  "organizations.edit.confirmDescription":
    "Zawieszenie jest odwracalne i zachowuje historię klienta. Pozostałe zmiany uprawnień mogą natychmiast wpłynąć na usługę i koszty.",
  "organizations.openAria": "Otwórz {name}",
  "organizations.editAria": "Zmień nazwę {name}",
};
export default messages;
