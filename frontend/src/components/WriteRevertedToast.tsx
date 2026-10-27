import { useWriteRevertedToast } from "../hooks/useWriteRevertedToast";

/** Mounts the refused-write notice; renders nothing itself. */
export function WriteRevertedToast() {
  useWriteRevertedToast();
  return null;
}
