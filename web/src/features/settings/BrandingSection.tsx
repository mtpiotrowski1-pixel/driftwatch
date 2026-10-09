import { Palette } from "lucide-react";
import { Field, Input, Textarea } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { BrandingAssetField } from "./BrandingAssetField";
import { ConfigurationInput } from "./controls";
import type { TextSettingsFields } from "./useSettingsDraft";

interface BrandingSectionProps {
  draft: TextSettingsFields;
  stored: Settings;
  settingsContext: ApiRequestContext;
  isPlatformScope: boolean;
}

export function BrandingSection({ draft, stored, settingsContext, isPlatformScope }: BrandingSectionProps) {
  const t = useT();
  const { textValue, setTextField } = draft;
  return (
    <SettingsSection
      title={t("settings.branding.title")}
      icon={<Palette className="h-4 w-4" />}
      defaultOpen
      bodyClassName="grid gap-5 lg:grid-cols-2"
    >
      <Field
        label={t("settings.branding.name")}
        hint={t("settings.branding.nameHint")}
        htmlFor="brand_name"
      >
        <Input
          id="brand_name"
          value={textValue("brand_name")}
          maxLength={40}
          onChange={(event) => setTextField("brand_name", event.target.value)}
          placeholder="Driftwatch"
        />
      </Field>
      <Field
        label={t("settings.branding.accent")}
        hint={t("settings.branding.accentHint")}
        htmlFor="brand_accent_color"
      >
        <div className="flex items-center gap-2">
          <input
            type="color"
            aria-label={t("settings.branding.accent")}
            value={
              /^#[0-9a-fA-F]{6}$/.test(textValue("brand_accent_color"))
                ? textValue("brand_accent_color")
                : "#b4e653"
            }
            onChange={(event) => setTextField("brand_accent_color", event.target.value)}
            className="h-9 w-12 shrink-0 cursor-pointer rounded-md border border-line bg-transparent"
          />
          <ConfigurationInput
            id="brand_accent_color"
            value={textValue("brand_accent_color")}
            onChange={(event) => setTextField("brand_accent_color", event.target.value)}
            placeholder="#b4e653"
          />
        </div>
      </Field>
      <div className="lg:col-span-2">
        <BrandingAssetField
          kind="logo"
          requestContext={settingsContext}
          label={t("settings.branding.logo")}
          hint={t("settings.branding.logoHint")}
          currentUrl={stored.brand_logo_url ?? ""}
        />
      </div>
      {isPlatformScope ? (
        <>
          <div className="lg:col-span-2 border-t border-line pt-4">
            <p className="text-xs font-medium uppercase text-mist-500">
              {t("settings.branding.landingHeading")}
            </p>
            <p className="mt-1 text-xs text-mist-500">
              {t("settings.branding.landingNote")}
            </p>
          </div>
          <Field label={t("settings.branding.tagline")} htmlFor="landing_tagline">
            <Input
              id="landing_tagline"
              value={textValue("landing_tagline")}
              maxLength={120}
              onChange={(event) => setTextField("landing_tagline", event.target.value)}
            />
          </Field>
          <Field label={t("settings.branding.heroTitle")} htmlFor="landing_hero_title">
            <Input
              id="landing_hero_title"
              value={textValue("landing_hero_title")}
              maxLength={90}
              onChange={(event) => setTextField("landing_hero_title", event.target.value)}
            />
          </Field>
          <div className="lg:col-span-2">
            <Field
              label={t("settings.branding.heroSubtitle")}
              htmlFor="landing_hero_subtitle"
            >
              <Textarea
                id="landing_hero_subtitle"
                value={textValue("landing_hero_subtitle")}
                maxLength={200}
                onChange={(event) =>
                  setTextField("landing_hero_subtitle", event.target.value)
                }
              />
            </Field>
          </div>
          <div className="lg:col-span-2">
            <BrandingAssetField
              kind="hero"
              requestContext={settingsContext}
              label={t("settings.branding.heroBackground")}
              hint={t("settings.branding.heroBackgroundHint")}
              currentUrl={stored.landing_hero_background_url ?? ""}
            />
          </div>
        </>
      ) : null}
    </SettingsSection>
  );
}
