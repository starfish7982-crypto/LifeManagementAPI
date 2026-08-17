import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ConfirmDelete } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { ApiError, api } from "../lib/api";
import { useToast } from "../lib/context";
import { fmtDate, longDate } from "../lib/format";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import { useSortable } from "../lib/useSortable";
import type { Todo } from "../lib/types";

type TodoBucket = Todo["bucket"];

export function Today() {
  const toast = useToast();
  const today = useResource(() => api.today());
  const todos = useResource(() => api.todos());
  const [pendingDelete, setPendingDelete] = useState<Todo | null>(null);
  const [draft, setDraft] = useState("");
  const [refreshingCalendar, setRefreshingCalendar] = useState(false);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const title = draft.trim();
    if (!title) return;
    setDraft("");
    // Every freshly captured task begins in today's plan.
    await api.createTodo({ title, due_date: null });
    todos.reload();
  };

  const list = todos.data ?? [];
  const done = list.filter((todo) => todo.done).length;
  const futureCalendarEvents = (today.data?.calendar_events ?? []).filter(
    (event) => event.starts_at !== today.data?.date,
  );

  // The /today response may have just captured Google activities as local todos. The
  // independent /todos request can finish first, so reload it once the day is known.
  useEffect(() => {
    if (today.data) todos.reload();
  // A date change is the relevant event; depending on the whole response would reload
  // after every optimistic patch and create a request loop.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [today.data?.date]);

  const setDone = async (todo: Todo, done: boolean) => {
    todos.patch((rows) => rows.map((row) => (row.id === todo.id ? { ...row, done } : row)));
    try {
      await api.patchTodo(todo.id, { done });
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      todos.reload();
    }
  };

  const moveTo = async (todo: Todo, bucket: TodoBucket) => {
    if (todo.bucket === bucket) return;
    const destination = list.filter((row) => row.bucket === bucket && row.id !== todo.id);
    todos.patch((rows) => rows.map((row) => (row.id === todo.id ? { ...row, bucket } : row)));
    try {
      await api.patchTodo(todo.id, { bucket });
      // A moved task becomes the next thing to consider in its destination lane.
      await api.reorderTodos(bucket, [todo.id, ...destination.map((row) => row.id)]);
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      todos.reload();
    }
  };

  const reorder = async (bucket: TodoBucket, next: Todo[]) => {
    todos.patch((rows) => {
      const nextPosition = new Map(next.map((row, index) => [row.id, index]));
      return rows
        .map((row) =>
          row.bucket === bucket ? { ...row, position: nextPosition.get(row.id) ?? row.position } : row,
        )
        .sort((a, b) => a.bucket.localeCompare(b.bucket) || a.position - b.position || a.id - b.id);
    });
    try {
      await api.reorderTodos(bucket, next.map((row) => row.id));
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      todos.reload();
    }
  };

  const refreshCalendar = async () => {
    setRefreshingCalendar(true);
    try {
      const refreshed = await api.today(true);
      today.patch(() => refreshed);
      todos.reload();
      toast(t("calendar_updated"));
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      setRefreshingCalendar(false);
    }
  };

  return (
    <ViewFrame
      title={t("today_title")}
      subtitle={
        today.data
          ? t("today_sub", { date: longDate(today.data.date), count: list.length - done })
          : ""
      }
      resources={[today, todos]}
    >
      {today.data && (
        <div className="card">
          <button
            type="button"
            className="btn subtle calendar-refresh"
            disabled={refreshingCalendar}
            onClick={() => void refreshCalendar()}
          >
            {refreshingCalendar ? t("refreshing") : t("refresh_calendar")}
          </button>

          <div className="page-sub" style={{ margin: "14px 0 8px" }}>
            {t("my_todos", { done, total: list.length })}
          </div>

          <form className="shop-add" onSubmit={add}>
            <input
              type="text"
              maxLength={200}
              placeholder={t("add_todo_ph")}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button type="submit" className="btn">
              {t("add_btn")}
            </button>
          </form>
          <p className="todo-reorder-help">{t("todo_reorder_help")}</p>

          <div className="todo-columns">
            <TodoLane
              bucket="today"
              title={t("todo_today")}
              todos={list.filter((row) => row.bucket === "today")}
              onDone={setDone}
              onMove={moveTo}
              onDelete={setPendingDelete}
              onReorder={reorder}
            />
            <TodoLane
              bucket="later"
              title={t("todo_later")}
              todos={list.filter((row) => row.bucket === "later")}
              onDone={setDone}
              onMove={moveTo}
              onDelete={setPendingDelete}
              onReorder={reorder}
            />
          </div>

          {done > 0 && (
            <button
              type="button"
              className="btn small"
              onClick={async () => {
                for (const todo of list.filter((row) => row.done)) await api.deleteTodo(todo.id);
                toast(t("deleted"));
                todos.reload();
              }}
            >
              {t("clear_done")}
            </button>
          )}

          <div className="page-sub" style={{ margin: "22px 0 8px" }}>
            {t("week_ahead")}
          </div>

          {today.data.reminders_due.length === 0 && futureCalendarEvents.length === 0 && (
            <div className="empty-note">{t("nothing_this_week")}</div>
          )}

          {today.data.reminders_due.map((reminder) => (
            <div className="due-item" key={`r${reminder.id}`}>
              <span className="badge">
                {reminder.days_until_due === null
                  ? t("overdue")
                  : reminder.days_until_due === 0
                    ? t("due_today")
                    : t("due_in_days", { n: reminder.days_until_due })}
              </span>
              <div className="t">
                {reminder.title}
                {reminder.note && <div className="todo-note">{reminder.note}</div>}
              </div>
              <span className="d">{fmtDate(reminder.next_due)}</span>
            </div>
          ))}

          {futureCalendarEvents.map((event) => (
            <div className="due-item" key={`${event.title}${event.starts_at}`}>
              <span className="badge">📅</span>
              <div className="t">{event.title}</div>
              <span className="d">{fmtDate(event.starts_at)}</span>
            </div>
          ))}
        </div>
      )}

      {pendingDelete && (
        <ConfirmDelete
          what={pendingDelete.title}
          onCancel={() => setPendingDelete(null)}
          onConfirm={async () => {
            await api.deleteTodo(pendingDelete.id);
            setPendingDelete(null);
            toast(t("deleted"));
            todos.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

function TodoLane({
  bucket,
  title,
  todos,
  onDone,
  onMove,
  onDelete,
  onReorder,
}: {
  bucket: TodoBucket;
  title: string;
  todos: Todo[];
  onDone: (todo: Todo, done: boolean) => Promise<void>;
  onMove: (todo: Todo, bucket: TodoBucket) => Promise<void>;
  onDelete: (todo: Todo) => void;
  onReorder: (bucket: TodoBucket, todos: Todo[]) => Promise<void>;
}) {
  const sortable = useSortable(todos.length, (from, to) => {
    const next = [...todos];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(to, 0, moved);
    void onReorder(bucket, next);
  });
  const destination = bucket === "today" ? "later" : "today";

  return (
    <section className={`todo-lane todo-lane-${bucket}`}>
      <h2>
        {title} <span className="cnt">{todos.length}</span>
      </h2>
      <div className="todo-lane-list" {...sortable.containerProps}>
        {todos.length === 0 && <div className="empty-note">{t("no_todos")}</div>}
        {todos.map((todo, index) => {
          const rowProps = sortable.rowProps(index);
          return (
            <div
              className={`todo-item ${todo.done ? "done" : ""}`}
              key={todo.id}
              ref={rowProps.ref}
              style={rowProps.style}
            >
              <button
                type="button"
                className="drag-handle"
                aria-label={t("reorder")}
                title={t("reorder_hint")}
                {...sortable.handleProps(index)}
              >
                ⠿
              </button>
              <input
                type="checkbox"
                checked={todo.done}
                aria-label={todo.title}
                onChange={(e) => void onDone(todo, e.target.checked)}
              />
              <div className="todo-body">
                <div className="todo-title">{todo.title}</div>
                {todo.due_date && (
                  <div className="todo-meta">
                    <span className="todo-date">{fmtDate(todo.due_date)}</span>
                    {todo.source === "calendar" && <span className="todo-src">{t("calendar_source")}</span>}
                    {todo.calendar_time && <span className="todo-src">🕐 {todo.calendar_time.slice(0, 5)}</span>}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="btn subtle icon"
                aria-label={t(destination === "today" ? "move_to_today" : "move_to_later")}
                title={t(destination === "today" ? "move_to_today" : "move_to_later")}
                onClick={() => void onMove(todo, destination)}
              >
                {destination === "today" ? "←" : "→"}
              </button>
              <button
                type="button"
                className="btn danger icon"
                aria-label={t("delete")}
                onClick={() => onDelete(todo)}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
