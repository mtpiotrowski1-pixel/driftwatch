import { useCallback, useRef, useState } from "react";

interface VisibleDialog<T> {
  value: T;
  open: boolean;
  key: number;
}

/** Ordinary dialogs keep their subject only until Radix finishes the closing
 * animation. Clearing/resetting the value still unmounts immediately. Each new
 * opening gets a fresh form, and a late old exit cannot clear its replacement. */
export function useDialogState<T>(emptyValue: T) {
  const [dialog, setDialog] = useState<VisibleDialog<T> | null>(null);
  const nextKey = useRef(0);
  const setValue = useCallback((value: T) => {
    const key = nextKey.current++;
    setDialog(value === emptyValue ? null : { value, open: true, key });
  }, [emptyValue]);
  const close = useCallback(() => {
    setDialog((current) => current?.open ? { ...current, open: false } : current);
  }, []);
  const closingKey = dialog?.key;
  const onClosed = useCallback(() => {
    setDialog((current) => current && !current.open && current.key === closingKey ? null : current);
  }, [closingKey]);
  return {
    value: dialog?.value ?? emptyValue,
    open: dialog?.open ?? false,
    key: dialog?.key,
    setValue,
    close,
    onClosed,
  };
}
