// Site storage can throw (blocked cookies, some private modes). Preferences kept
// here are conveniences, so a failure falls back to the default instead of
// breaking the app at startup.

export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // The preference applies for this page load only.
  }
}
