# Grafiki Driftwatch

Logo, trzy dekoracyjne tła oraz ilustracje pustych widoków powstały przy użyciu
generatora obrazów AI w październiku 2026 r. Są dekoracją interfejsu; wyniki,
wykresy, tekst i kontrolki aplikacji pozostają rzeczywistymi danymi i HTML.
Grafiki projektu podlegają [licencji repozytorium](../LICENSE). Licencje
zewnętrznych fontów i bibliotek opisuje [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

[Manifest](manifest.json) zawiera sześć oryginałów, ich SHA256, aktualne pliki
aplikacji i miejsca użycia. Oryginały PNG zachowują rozdzielczość i kanał alfa.
Kompresowane pliki mają jedną kanoniczną lokalizację w `web/src/assets/brand`
lub `web/public`; kopie eksportów i wcześniejsze warianty nie są przechowywane.

| Grafika | Użycie |
| --- | --- |
| Logo | Komponent `Logo.tsx`, favicony i ikona w README |
| Portal hero | Strony publiczne i logowanie; osobny mniejszy eksport mobilny |
| Portal ambient | Tło przestrzeni roboczej |
| Recovery | Odzyskiwanie hasła |
| Workspace / delivery | Responsywne ilustracje pustych widoków |

Obrazy są dekoracyjne i nie przejmują kliknięć. Treść opisuje otaczający HTML.
Kontrast zapewniają warstwy CSS; animacje respektują `prefers-reduced-motion`.
Natywny SVG w `Logo.tsx` zapewnia fallback, gdy nie uda się pobrać logo.

## Opcjonalne odtworzenie eksportów

Instalacja i uruchomienie aplikacji używają gotowych plików. Odtworzenie
grafik wymaga Pillow dla logo i teł oraz Node.js z `sharp` dla ilustracji.
Uruchom kolejno z katalogu repozytorium:

```sh
python brand-kit/tools/export_logo.py
python brand-kit/tools/export_portal_assets.py
node brand-kit/tools/export_empty_states.mjs --sharp-module /path/to/node_modules/sharp
```

Gdy `sharp` jest dostępny przez standardowe wyszukiwanie modułów Node.js,
pomiń `--sharp-module`. Eksportery zachowują treść oryginałów, skalują lub
kompresują tylko warianty używane przez aplikację i aktualizują manifest.
Logo zachowuje przezroczystość i margines; jego WebP jest bezstratny.
Tła mają WebP i JPEG, z wyjątkiem recovery używającego wyłącznie WebP.
Ilustracje mają warianty PNG/WebP o szerokości 480 i 960 px, z kanałem alfa.
Wersje Pillow i `sharp` mogą wpływać na dokładne bajty skompresowanych plików.
