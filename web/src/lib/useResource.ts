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
  /**
   * True while what is on screen came from the cache and no request has been made.
   *
   * For the follow-up work that only makes sense after the server was actually asked.
   * Without it, an effect written as "when the data arrives, also do X" fires on a
   * cache hit too, and X is usually another request — which is the cost the cache
   * exists to avoid.
   */
  servedFromCache: boolean;
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

/**
 * Responses kept across mounts, for the screens that opted in with a `cacheKey`.
 *
 * Switching screens unmounts the old one — `ViewBody` is a switch that returns a
 * different component — so without this, every visit to a screen refetches everything
 * it shows. On a host that idles and a database that bills by the second, walking
 * through the tabs and back is a surprising amount of work for data that did not
 * change.
 *
 * Deliberately module-level rather than React state: it has to outlive the components
 * that read it, which is the entire point. It is memory-only, so a page reload still
 * fetches fresh — the cache answers "I was just here", not "I saw this yesterday".
 */
const cache = new Map<string, unknown>();

/**
 * Drop everything. Called on sign-out and on session expiry.
 *
 * Not optional: the cache is keyed by resource, not by account, so leaving it in place
 * would show the previous account's rows to the next one to sign in on this browser —
 * before any request went out, so nothing server-side would catch it.
 */
export function clearResourceCache(): void {
  cache.clear();
}

/** Forget one entry, so the next screen that reads it fetches again. */
export function invalidateResource(key: string): void {
  cache.delete(key);
}

export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  cacheKey?: string,
): Resource<T> {
  // Read once, at mount. Reading on every render would swap live data back to the
  // cached copy whenever something else wrote to the same key mid-flight.
  const seed = useRef(cacheKey === undefined ? undefined : (cache.get(cacheKey) as T | undefined));
  const hydrated = seed.current !== undefined;

  const [data, setData] = useState<T | undefined>(seed.current);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [settled, setSettled] = useState(hydrated);
  const [inFlight, setInFlight] = useState(!hydrated);
  const [nonce, setNonce] = useState(0);

  // Set only while the cached value is what is on screen and no fetch has replaced it.
  // A caller that needs to know whether the server was actually asked reads this —
  // "the data is here" and "we just talked to the server" stop being the same thing
  // once a cache exists, and code written before that assumed they were.
  const [servedFromCache, setServedFromCache] = useState(hydrated);

  // Consumed by the effect below on its first run to skip the initial fetch. A ref
  // rather than state: flipping it must not cause a render, and the effect must see
  // the new value immediately rather than on the next pass.
  const skipInitialFetch = useRef(hydrated);

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
    // A cache hit already put the answer on screen. Asking anyway would make the cache
    // a way to render sooner rather than a way to fetch less, which is not what it is
    // for. `reload()` bumps `nonce`, so this only ever skips the mount fetch.
    if (skipInitialFetch.current) {
      skipInitialFetch.current = false;
      return;
    }

    let cancelled = false;
    const id = ++runId.current;

    setInFlight(true);
    setError(undefined);

    fetcherRef
      .current()
      .then((value) => {
        if (cancelled || runId.current !== id) return;
        if (cacheKey !== undefined) cache.set(cacheKey, value);
        setData(value);
        setServedFromCache(false);
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

  const patch = useCallback(
    (update: (current: T) => T) => {
      setData((current) => {
        if (current === undefined) return current;
        const next = update(current);
        // Written through, or an optimistic tick would be undone by leaving the screen
        // and coming back to the pre-tick copy still sitting in the cache.
        if (cacheKey !== undefined) cache.set(cacheKey, next);
        return next;
      });
    },
    [cacheKey],
  );

  return {
    data,
    error,
    loading: !settled,
    refreshing: settled && inFlight,
    servedFromCache,
    reload,
    patch,
  };
}
