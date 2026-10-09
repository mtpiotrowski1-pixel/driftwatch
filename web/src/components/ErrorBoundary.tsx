import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { translateStatic as t } from "@/i18n";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Shared by render and router errors, including unavailable deployment chunks. */
export function ApplicationErrorScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center px-5" role="alert">
      <div className="glass w-full max-w-md rounded-lg p-7 text-center">
        <h1 className="text-lg font-semibold text-mist-100">{t("common.errorTitle")}</h1>
        <p className="mt-2 text-sm text-mist-400">{t("common.errorBody")}</p>
        <Button className="mt-6" onClick={() => location.reload()}>
          {t("common.reload")}
        </Button>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return <ApplicationErrorScreen />;
  }
}
