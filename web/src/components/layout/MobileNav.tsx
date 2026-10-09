import * as DialogPrimitive from "@radix-ui/react-dialog";
import { LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { NavLink } from "@/lib/navigation";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

import { type NavItem } from "./nav";

interface MobileNavProps {
  items: NavItem[];
  userName: string;
  userEmail?: string;
  onLogout: () => void;
}

export function MobileNav({ items, userName, userEmail, onLogout }: MobileNavProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const mainItems = items.filter((item) => item.group !== "operator");
  const operatorItems = items.filter((item) => item.group === "operator");

  function close() {
    setOpen(false);
  }

  const renderLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.to === "/sites/new"}
      onClick={close}
      className={({ isActive }) =>
        cn(
          "dw-nav-link flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
          isActive
            ? "bg-brand-500 text-[#151915]"
            : "text-[#b5bfb6] hover:bg-[#252b25] hover:text-white",
        )
      }
    >
      {item.icon}
      {t(item.labelKey)}
    </NavLink>
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <header className="focus-on-dark sticky top-0 z-40 isolate overflow-hidden border-b border-[#2b322c] bg-[#141814] text-white shadow-lg lg:hidden">
        <BrandBackground variant="dark" className="dw-sidebar-art" />
        <div className="relative flex items-center justify-between p-4">
          <Wordmark className="!text-white" />
          <DialogPrimitive.Trigger asChild>
            <button
              type="button"
              aria-label={t("nav.menu")}
              aria-expanded={open}
              className="dw-button grid h-11 w-11 place-items-center rounded-lg text-[#d8e0d9] hover:bg-[#252b25] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              {open ? (
                <X className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Menu className="h-5 w-5" aria-hidden="true" />
              )}
            </button>
          </DialogPrimitive.Trigger>
        </div>
      </header>

      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dw-overlay fixed inset-x-0 bottom-0 top-[4.75rem] z-40 bg-[#111511]/60 backdrop-blur-sm lg:hidden" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          inert={!open}
          aria-hidden={open ? undefined : true}
          className="dw-mobile-menu focus-on-dark fixed inset-x-0 top-[4.75rem] z-50 max-h-[calc(100dvh-4.75rem)] overflow-y-auto border-t border-[#2b322c] bg-[#141814] p-4 text-white shadow-2xl outline-none lg:hidden"
        >
          <BrandBackground variant="dark" className="dw-sidebar-art" />
          <DialogPrimitive.Title className="sr-only">{t("nav.menu")}</DialogPrimitive.Title>
          <nav className="dw-sidebar-nav relative flex flex-col gap-1">
            {mainItems.map(renderLink)}
            {operatorItems.length > 0 ? (
              <>
                <p className="mt-4 px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-on-art-muted">
                  {t("nav.operatorSection")}
                </p>
                {operatorItems.map(renderLink)}
              </>
            ) : null}

            <div className="dw-sidebar-account mt-3 space-y-3 border border-white/10">
              <div className="flex items-center gap-3 px-1">
                <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500 text-sm font-bold text-[#151915]">
                  {userName.slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-white">{userName}</p>
                  {userEmail ? (
                    <p className="truncate text-xs text-on-art-muted">{userEmail}</p>
                  ) : null}
                </div>
              </div>
              <LanguageSwitcher compact />
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start !text-[#cbd4cc] hover:!bg-[#252b25] hover:!text-white"
                onClick={() => {
                  close();
                  onLogout();
                }}
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                {t("common.signOut")}
              </Button>
            </div>
          </nav>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
