import { useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useOnboardingStatus } from "../hooks/useOnboardingStatus";

const ONBOARDING_PATH = "/onboarding";
const ONBOARDING_DISMISSED_KEY = "onboardingDismissedAt";

/**
 * Layout-level gate that redirects fresh users to the onboarding wizard.
 *
 * Behaviour:
 * - On the dashboard route ("/") only — never redirect from any other
 *   page. Deep links and intentional navigation are respected.
 * - Only when the backend reports `is_first_run` true.
 * - Honoured at most once per session: the flag is stored in
 *   sessionStorage so the user can navigate back to "/" without being
 *   bounced again after manually dismissing.
 *
 * The hook is keyed by the React Query cache, so it shares the
 * fetch with anyone else who reads onboarding status.
 */
export function OnboardingGate() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data, isLoading } = useOnboardingStatus();

  useEffect(() => {
    if (isLoading || !data) return;
    if (location.pathname !== "/") return;
    if (!data.is_first_run) return;
    if (sessionStorage.getItem(ONBOARDING_DISMISSED_KEY)) return;

    sessionStorage.setItem(ONBOARDING_DISMISSED_KEY, String(Date.now()));
    navigate(ONBOARDING_PATH, { replace: true });
  }, [data, isLoading, location.pathname, navigate]);

  return <Outlet />;
}
