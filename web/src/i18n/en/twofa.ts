const messages: Record<string, string> = {
  "twofa.login.prompt": "Enter the 6-digit code from your authenticator app.",
  "twofa.login.codeLabel": "Authentication code",
  "twofa.login.codeHint": "Or use one of your recovery codes.",
  "twofa.login.verify": "Verify",
  "twofa.login.useAnotherAccount": "Use a different account",

  "twofa.manage.title": "Two-factor authentication",
  "twofa.manage.statusOn": "Enabled",
  "twofa.manage.statusOff": "Not enabled",
  "twofa.manage.description":
    "Protect your account with a time-based code from an authenticator app, in addition to your password.",
  "twofa.manage.enable": "Enable two-factor authentication",
  "twofa.manage.scan": "Scan this QR code with your authenticator app.",
  "twofa.manage.qrAlt": "QR code for two-factor setup",
  "twofa.manage.manualEntry": "Can't scan? Enter this key manually:",
  "twofa.manage.codeLabel": "Enter the code from the app to confirm",
  "twofa.manage.confirm": "Confirm and enable",
  "twofa.manage.enabled": "Two-factor authentication enabled",
  "twofa.manage.disabled": "Two-factor authentication disabled",
  "twofa.manage.disable": "Disable two-factor authentication",
  "twofa.manage.disableLabel": "Confirm your password to disable",
  "twofa.manage.disableHint": "Disabling 2FA makes your account password-only.",
  "twofa.manage.recoveryTitle": "Save your recovery codes",
  "twofa.manage.recoveryHint":
    "Each code works once if you lose your device. Store them somewhere safe — they won't be shown again.",
  "twofa.manage.recoveryDone": "I've saved them",

  "twofa.nudge.required":
    "This administrator account must use two-factor authentication. Enable it to continue.",
  "twofa.nudge.action": "Enable it",

  "twofa.required.title": "Secure your administrator account",
  "twofa.required.description":
    "Two-factor authentication is required for administrators before they can access the application or organization data.",

  "twofa.stepup.prompt": "This is a sensitive action. Confirm your identity to continue.",
  "twofa.stepup.password": "Password",
  "twofa.stepup.code": "Authentication code",
  "twofa.stepup.codeHint": "From your authenticator app.",
};
export default messages;
