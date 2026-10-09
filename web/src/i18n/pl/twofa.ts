const messages: Record<string, string> = {
  "twofa.login.prompt": "Wpisz 6-cyfrowy kod z aplikacji uwierzytelniającej.",
  "twofa.login.codeLabel": "Kod uwierzytelniający",
  "twofa.login.codeHint": "Możesz też użyć jednego z kodów zapasowych.",
  "twofa.login.verify": "Zweryfikuj",
  "twofa.login.useAnotherAccount": "Użyj innego konta",

  "twofa.manage.title": "Uwierzytelnianie dwuskładnikowe",
  "twofa.manage.statusOn": "Włączone",
  "twofa.manage.statusOff": "Wyłączone",
  "twofa.manage.description":
    "Chroń konto kodem czasowym z aplikacji uwierzytelniającej, dodatkowo obok hasła.",
  "twofa.manage.enable": "Włącz uwierzytelnianie dwuskładnikowe",
  "twofa.manage.scan": "Zeskanuj ten kod QR aplikacją uwierzytelniającą.",
  "twofa.manage.qrAlt": "Kod QR do konfiguracji uwierzytelniania dwuskładnikowego",
  "twofa.manage.manualEntry": "Nie możesz zeskanować? Wpisz ten klucz ręcznie:",
  "twofa.manage.codeLabel": "Wpisz kod z aplikacji, aby potwierdzić",
  "twofa.manage.confirm": "Potwierdź i włącz",
  "twofa.manage.enabled": "Uwierzytelnianie dwuskładnikowe włączone",
  "twofa.manage.disabled": "Uwierzytelnianie dwuskładnikowe wyłączone",
  "twofa.manage.disable": "Wyłącz uwierzytelnianie dwuskładnikowe",
  "twofa.manage.disableLabel": "Potwierdź hasło, aby wyłączyć",
  "twofa.manage.disableHint": "Wyłączenie 2FA sprawia, że konto chroni tylko hasło.",
  "twofa.manage.recoveryTitle": "Zapisz kody zapasowe",
  "twofa.manage.recoveryHint":
    "Każdy kod działa raz, gdy stracisz urządzenie. Przechowaj je w bezpiecznym miejscu — nie pokażemy ich ponownie.",
  "twofa.manage.recoveryDone": "Zapisałem je",

  "twofa.nudge.required":
    "To konto administratora musi używać uwierzytelniania dwuskładnikowego. Włącz je, aby kontynuować.",
  "twofa.nudge.action": "Włącz",

  "twofa.required.title": "Zabezpiecz konto administratora",
  "twofa.required.description":
    "Uwierzytelnianie dwuskładnikowe jest wymagane dla administratorów przed uzyskaniem dostępu do aplikacji lub danych organizacji.",

  "twofa.stepup.prompt": "To wrażliwa operacja. Potwierdź swoją tożsamość, aby kontynuować.",
  "twofa.stepup.password": "Hasło",
  "twofa.stepup.code": "Kod uwierzytelniający",
  "twofa.stepup.codeHint": "Z aplikacji uwierzytelniającej.",
};
export default messages;
