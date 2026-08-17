import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

/**
 * Fetch something, and expose the three states every screen actually has.
 *
 * This is the small, honest version of what TanStack Query does. That library is what
 * most teams reach for and is the right answer once caching, deduplication and
 * background revalidation start to matter; here there are five screens, each fetching
 * on mount, so the whole of its value would be unused while its concepts still had to
 * be understood by anyone reading this.
 *
 * Two things it does get right, because they are bugs rather than features:
 *
 *   - **Stale responses are dropped.** Switch screens while a slow request is in
 *     flight and the old response can land after the new one. Each run takes a token
 *     and only the newest is allowed to set state.
 *   - **No setState after unmount.** The same token check covers it, so React never
 *     warns about updating an unmounted component.
 */
/**
 * The parts of a resource that do not mention its type.
 *
 * `ViewFrame` takes a list of mixed resources — a Snapshot[] next to a Goal — and only
 * ever reads their status. Splitting that out is what lets it accept them: adding
 * `patch(update: (current: T) => T)` made `Resource<T>` invariant in T, because T
 * appears in both an input and an output position, so `Resource<Goal>` stopped being
 * assignable to `Resource<unknown>`. The compiler was right, and the fix is to hand
 * that component the half of the interface it actually uses rather than to widen it.
 */
export interface ResourceStatus {
  loading: boolean;
  refreshing: boolean;
  error: ApiError | undefined;
  reload: () => void;
}

export interface Resource<T> extends ResourceStatus {
  data: T | undefined;
  error: ApiError | undefined;
  /**
   * True only until the first response arrives.
   *
   * Separating this from `refreshing` is the difference between a screen that works
   * and one that flickers. Every write is followed by a refetch, and while a single
   * `loading` flag was true the view replaced its entire contents with a loading
   * message — so ticking a checkbox blanked the page, for as long as the round trip
   * took. On a host that idles, that is most of a second, every time.
   */
  loading: boolean;
  /** A refetch is in flight but there is already data to keep showing. */
  refreshing: boolean;
  /** Refetch. Views call this after a write instead of patching local state, so what
   *  is on screen is always what the server stored. */
  reload: () => void;
  /**
   * Apply a change locally, without waiting for the server.
   *
   * For actions whose outcome is not in doubt — ticking a checkbox — waiting for a
   * round trip before moving the tick is the whole of the lag the user feels. The
   * caller still reloads afterwards, so the server remains the source of truth; this
   * only decides what is on screen in between. A failed write puts the old value
   * back when the reload lands.
   */
  patch: (update: (current: T) => T) => void;
}

export function useResource<T>(fetcher: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [settled, setSettled] = useState(false);
  const [inFlight, setInFlight] = useState(true);
  const [nonce, setNonce] = useState(0);

  // Bumped on every run; a response whose token is no longer current is discarded.
  const runId = useRef(0);

  // The fetcher is usually an inline closure, so it is a new function on every render.
  // Keeping it in a ref means it can change freely without re-triggering the effect —
  // the effect re-runs on `deps` and `nonce`, which is what the caller controls.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    // Two guards, for two different failures.
    //
    // `cancelled` is per-run and set by this effect's own cleanup: it covers unmount
    // and re-run, so nothing calls setState on a component that is gone.
    //
    // `runId` is shared: it covers ordering. Two requests in flight can return out of
    // order, and without this the slower, older one would overwrite the newer result.
    // A cleanup that read `runId.current` would be reading whatever the newest run had
    // set, which is not the value this run needs to compare against.
    let cancelled = false;
    const id = ++runId.current;

    setInFlight(true);
    setError(undefined);

    fetcherRef
      .current()
      .then((value) => {
        if (cancelled || runId.current !== id) return;
        setData(value);
        setSettled(true);
        setInFlight(false);
      })
      .catch((err: unknown) => {
        if (cancelled || runId.current !== id) return;
        // A 401 has already cleared the session and swapped in the sign-in screen;
        // surfacing it here too would flash an error behind that screen.
        if (err instanceof ApiError && err.status !== 401) setError(err);
        setSettled(true);
        setInFlight(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const patch = useCallback((update: (current: T) => T) => {
    setData((current) => (current === undefined ? current : update(current)));
  }, []);

  return {
    data,
    error,
    loading: !settled,
    refreshing: settled && inFlight,
    reload,
    patch,
  };
}
