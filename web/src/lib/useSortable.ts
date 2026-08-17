import { useCallback, useRef, useState } from "react";
import type {
  CSSProperties,
  KeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";

/**
 * Drag-to-reorder for a vertical list, on mouse and touch alike.
 *
 * Built on Pointer Events rather than the HTML5 drag-and-drop API. That API sounds
 * like the right tool and is not: `dragstart` never fires from a touch, so a
 * drag-and-drop list built on it simply does not work on a phone — which is where
 * dragging is the most natural gesture in the first place. Pointer events unify mouse,
 * touch and pen into one code path.
 *
 * The geometry is measured once, at the moment the drag starts, and not again:
 *
 *   - Reading positions during the drag means reading a DOM that the drag is moving,
 *     so a row that shifts under the cursor changes the answer, which shifts it back.
 *     That oscillation is the classic bug in hand-written sortable lists.
 *   - With fixed measurements, the target index is a pure function of how far the
 *     pointer has travelled, and the visual shuffle is a transform applied on top —
 *     nothing that feeds back into the calculation.
 */
export interface SortableState {
  /** Index being dragged, or null. */
  from: number | null;
  /** Index it would land on. */
  to: number | null;
}

export interface Sortable {
  state: SortableState;
  /** Attach to the drag handle of row `index`. */
  handleProps: (index: number) => {
    onPointerDown: (e: ReactPointerEvent) => void;
    onKeyDown: (e: KeyboardEvent) => void;
    style: { touchAction: "none" };
  };
  /** Attach to each row element so it can be measured and shifted. */
  rowProps: (index: number) => {
    ref: (el: HTMLElement | null) => void;
    style: CSSProperties;
  };
  /**
   * Attach to the element wrapping the rows.
   *
   * Move and release are handled here rather than on each handle: pointer capture
   * already routes those events to the element that started the drag, so one set of
   * listeners on the container covers every row instead of N sets that mostly idle.
   */
  containerProps: {
    onPointerMove: (e: ReactPointerEvent) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
  };
}

export type Axis = "y" | "x";

export function useSortable(
  count: number,
  onCommit: (from: number, to: number) => void,
  axis: Axis = "y",
): Sortable {
  const [state, setState] = useState<SortableState>({ from: null, to: null });

  const rows = useRef<(HTMLElement | null)[]>([]);
  // Midpoints and height, frozen at drag start. See the note above.
  const geometry = useRef<{ midpoints: number[]; height: number } | null>(null);
  const startY = useRef(0);

  const setRow = useCallback((index: number) => {
    return (el: HTMLElement | null) => {
      rows.current[index] = el;
    };
  }, []);

  const onPointerDown = useCallback(
    (index: number) => (e: ReactPointerEvent) => {
      // Primary button only; a right-click drag is not a reorder.
      if (e.button !== 0) return;
      const elements = rows.current.slice(0, count).filter(Boolean) as HTMLElement[];
      if (elements.length !== count) return;

      const rects = elements.map((el) => el.getBoundingClientRect());
      // The same arithmetic on whichever axis the list runs along. The nav is a
      // column on a desktop and a scrolling row on a phone, and a reorder gesture
      // should follow the direction the items are actually laid out in.
      geometry.current =
        axis === "y"
          ? {
              midpoints: rects.map((r) => r.top + r.height / 2),
              height: rects[0]?.height ?? 0,
            }
          : {
              midpoints: rects.map((r) => r.left + r.width / 2),
              height: rects[0]?.width ?? 0,
            };
      startY.current = axis === "y" ? e.clientY : e.clientX;

      // Capture so the drag survives the pointer leaving the handle — without it, a
      // fast drag loses the pointer and the row sticks to the cursor.
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      setState({ from: index, to: index });
      e.preventDefault();
    },
    // `axis` belongs here: without it, rotating a phone leaves this closure measuring
    // the axis the page had when it loaded, and the drag then follows the wrong one.
    [count, axis],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent) => {
      setState((current) => {
        if (current.from === null || !geometry.current) return current;
        const { midpoints } = geometry.current;
        const position = axis === "y" ? e.clientY : e.clientX;
        // The last midpoint the pointer has passed decides the target.
        let target = 0;
        while (target < midpoints.length - 1 && position > (midpoints[target + 1] ?? Infinity)) {
          target++;
        }
        // Dragging backwards: land before the item whose midpoint we have crossed.
        if (position < (midpoints[target] ?? 0) && target > 0) target -= 1;
        return current.to === target ? current : { ...current, to: target };
      });
    },
    [axis],
  );

  const finish = useCallback(() => {
    setState((current) => {
      if (current.from !== null && current.to !== null && current.from !== current.to) {
        onCommit(current.from, current.to);
      }
      geometry.current = null;
      return { from: null, to: null };
    });
  }, [onCommit]);

  const onKeyDown = useCallback(
    (index: number) => (e: React.KeyboardEvent) => {
      // The handle is a button, so the keyboard reaches it by Tab. Moving with the
      // arrow keys is what makes reordering possible without a pointer at all —
      // drag-only reordering is unusable for anyone who cannot drag.
      const back = axis === "y" ? "ArrowUp" : "ArrowLeft";
      const forward = axis === "y" ? "ArrowDown" : "ArrowRight";
      if (e.key === back && index > 0) {
        e.preventDefault();
        onCommit(index, index - 1);
      } else if (e.key === forward && index < count - 1) {
        e.preventDefault();
        onCommit(index, index + 1);
      }
    },
    [count, onCommit, axis],
  );

  const handleProps = useCallback(
    (index: number) => ({
      onPointerDown: onPointerDown(index),
      onKeyDown: onKeyDown(index),
      // Without this the browser scrolls the page instead of sending pointermove,
      // which is the single line that makes touch dragging work at all.
      style: { touchAction: "none" } as const,
    }),
    [onPointerDown, onKeyDown],
  );

  const rowProps = useCallback(
    (index: number): { ref: (el: HTMLElement | null) => void; style: React.CSSProperties } => {
      const { from, to } = state;
      const height = geometry.current?.height ?? 0;

      let shift = 0;
      if (from !== null && to !== null && height) {
        if (index === from) {
          // The dragged row travels the whole distance to its destination.
          shift = (to - from) * height;
        } else if (from < to && index > from && index <= to) {
          shift = -height; // rows in between move up to make room below
        } else if (from > to && index >= to && index < from) {
          shift = height; // …or down, when dragging upward
        }
      }

      return {
        ref: setRow(index),
        style: {
          transform: shift
            ? axis === "y"
              ? `translateY(${shift}px)`
              : `translateX(${shift}px)`
            : undefined,
          transition: from === null ? "transform .18s" : index === from ? "none" : "transform .12s",
          position: index === from && from !== null ? "relative" : undefined,
          zIndex: index === from ? 2 : undefined,
          opacity: index === from ? 0.85 : undefined,
        },
      };
    },
    [state, setRow, axis],
  );

  return {
    state,
    handleProps,
    rowProps,
    containerProps: { onPointerMove, onPointerUp: finish, onPointerCancel: finish },
  };
}
