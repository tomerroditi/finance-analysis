import { useQuery } from "@tanstack/react-query";
import { onboardingApi, type OnboardingStatus } from "../services/api";

export const ONBOARDING_STATUS_KEY = ["onboardingStatus"] as const;

/**
 * Fetches the backend onboarding status flags. Used by the OnboardingGate
 * to decide whether to redirect a fresh user to /onboarding, and by the
 * wizard itself to skip steps the user has already completed.
 */
export function useOnboardingStatus(options?: { enabled?: boolean }) {
  return useQuery<OnboardingStatus>({
    queryKey: ONBOARDING_STATUS_KEY,
    queryFn: () => onboardingApi.getStatus().then((res) => res.data),
    enabled: options?.enabled,
    staleTime: 60_000,
  });
}
