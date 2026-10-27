import { useWriteFailedToast } from "../hooks/useWriteFailedToast";

/** Mounts the failed-write notice; renders nothing itself. */
export function WriteFailedToast() {
  useWriteFailedToast();
  return null;
}
