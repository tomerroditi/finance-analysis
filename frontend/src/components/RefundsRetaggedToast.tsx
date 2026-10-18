import { useRefundsRetaggedToast } from "../hooks/useRefundsRetaggedToast";

/** Mounts the refunds-followed-the-purchase notice; renders nothing itself. */
export function RefundsRetaggedToast() {
  useRefundsRetaggedToast();
  return null;
}
