# Driftwatch — brand kit „Emerald Portal”

Bieżąca tożsamość wizualna łączy szmaragdowe szkło, jasny metal i spokojne
powierzchnie ivory. Rzeźbiarski monogram „D” jest faktycznym logo aplikacji,
faviconą i ikoną urządzeń. Dwa wygenerowane tła trafiają do publicznych stron,
logowania i zalogowanego workspace. Tekst, kontrolki i wyniki analizy pozostają
interaktywnym HTML ponad dekoracyjną warstwą obrazu.

- [Podgląd logo na jasnym i ciemnym tle](previews/logo-variants.png)
- [Plansza marki](previews/brand-board.png)
- [Podgląd teł](previews/background-set.png)
- [Manifest plików i powiązań](manifest.json)

## Logo

Podstawowy znak to otwarty po prawej monogram „D”: szmaragdowa pętla z jasną
metalową krawędzią. Pojedyncze przesunięcie sugeruje wykrytą zmianę. Obraz ma
prawdziwy kanał alfa także wewnątrz otworu, więc może działać na jasnym i ciemnym
tle bez prostokątnej plakietki. Wordmark korzysta z kroju display aplikacji,
wagi 600 i odstępu liter −0,025 em.

| Plik | Rola |
|---|---|
| `logo/v3/driftwatch-emblem-source.png` | niezmienione źródło 1254×1254 z alfa |
| `logo/driftwatch-mark-{16,24,32,64,128,180,192,256,512}.png` | bezstratne rozmiary eksportowe |
| `web/public/brand/driftwatch-emblem-{64,128,256}.{png,webp}` w repo | rzeczywiste logo komponentu `Logo.tsx` |
| `logo/driftwatch-mark.svg` | samodzielny wrapper SVG z osadzonym rastrem alfa |
| `logo/driftwatch-native-mark.svg` | mały natywny fallback na wypadek błędu pobrania |
| `logo/driftwatch-mark-mono.svg` | wektorowy wariant fallbacku oparty na `currentColor` |
| `logo/v3/exports.json` | źródłowy SHA256, wymiary i dokładne eksporty |

Minimalny rozmiar eksportu to 16 px; w aplikacji logo ma standardowo 32 px.
Eksport pomija jedynie niezauważalne punkty alfa 1/255 przy skrajnych krawędziach
źródła, zachowuje zapas wokół widocznego znaku i dodaje 6,25% wolnej przestrzeni.
Kolory i kształt źródła pozostają zachowane. Nie rozciągać znaku, nie dodawać
kolejnego cienia ani poświaty. Logo wgrane przez operatora lub organizację ma
pierwszeństwo; po błędzie wgranego logo wraca znak domyślny, a po błędzie znaku
domyślnego — natywny SVG.

## Bieżące tła

| Obraz | Wymiary | WebP | Zastosowanie |
|---|---|---|---|
| `portal-hero-v3` | 1672×941 | ok. 127 KB | landing, logowanie, ciemne sekcje |
| `portal-hero-mobile-v3` | 960×540 | ok. 57 KB | lżejszy wariant tego samego kadru |
| `portal-ambient-v3` | 1672×941 | ok. 124 KB | workspace i jasne powierzchnie |

Oryginały są w `backgrounds/v3/sources/`; WebP i progressive JPEG znajdują się
w `backgrounds/v3/web/`. Kompresowane kopie są zintegrowane przez
`web/src/components/brand/assets.ts` i `BrandBackground.tsx`. Kontrast treści
zapewnia oddzielna warstwa CSS; grafika nie jest nośnikiem informacji o zmianach.
Kadrowanie w UI jest responsywne, bez deformacji obrazu.

Paleta to grafit `#111511`, szmaragd `#0B6753`, champagne `#E7D8B6`, ivory
`#F5F4ED` oraz limonkowy akcent `#B4E653`. Kolory statusów i akcent organizacji
pozostają tokenami CSS. Grafiki nie zastępują rzeczywistych wykresów ani danych.

## Pochodzenie i źródła

Logo i dwa nowe tła wygenerowano 8 października 2026 r. wbudowanym narzędziem
`image_gen`. Pełne prompty i żądane ustawienia przezroczystości znajdują się w
[PORTAL_V3_IMAGEGEN_PROMPTS.json](prompts/PORTAL_V3_IMAGEGEN_PROMPTS.json).
Oryginały zachowano bez zmian; metadane eksportów podają SHA256 pozwalający
porównać pliki ze źródłami. Narzędzia eksportowe wyłącznie kadrują puste marginesy
logo, skalują i kompresują obrazy — nie tworzą nowych detali ani treści UI.

Poprzednie tła „Quiet Signal” i ich prompty zostały zachowane w
`backgrounds/sources/`, `backgrounds/web/` oraz
[IMAGEGEN_PROMPTS.md](prompts/IMAGEGEN_PROMPTS.md). Manifest oznacza ich bieżący
zakres użycia. Nie należy mylić tych źródeł z aktualną grafiką portalu.

Ilustracje pustych widoków workspace/delivery nadal korzystają z transparentnych
bitmap wersji 2. Ich źródła, eksporty i prompty są opisane w
[illustrations/v2/README.md](illustrations/v2/README.md). Pierwotne ilustracje
wektorowe i opcjonalny `logo/signal-motif.svg` pozostają dostępne jako źródła.

## Dostępność i ruch

Obrazy w UI są dekoracyjne (`alt=""`) i nie przejmują kliknięć. Oznaczenia,
statusy i instrukcje pozostają w DOM. Logo towarzyszy tekstowej nazwie marki;
natywny fallback ma `aria-hidden="true"` i nie przejmuje focusu. Przejścia
powinny respektować `prefers-reduced-motion`. Nie animować tekstury wewnątrz
bitmapy ani wymuszać pobierania nieaktywnych wariantów źródeł.

## Reprodukcja eksportów

Wymagane są Pillow oraz Playwright z Chromium:

```sh
python brand-kit/tools/export_logo.py
python brand-kit/tools/export_portal_assets.py
python brand-kit/tools/render_svg_exports.py --logo-only
python brand-kit/tools/build_brand_board.py
```

Pierwsze dwa polecenia odświeżają również produkcyjne kopie obrazów i ikon.
Trzecie tworzy rzeczywisty render logo na jasnym i ciemnym tle oraz rozmiary
fallbacku monochromatycznego. Bez `--logo-only` odświeża też pierwotne ilustracje
wektorowe. `export_assets.py` służy osobno do poprzednich źródeł „Quiet Signal”.
